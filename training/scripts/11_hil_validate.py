"""Stage 09: compare live STM32N6 Neural-ART results with host TFLite."""

from __future__ import annotations

import argparse
import os
import re
import time
import warnings
import zlib

import numpy as np
from serial import Serial

from common import (CONFIG_ROOT, MODELS_ROOT, PROJECT_ROOT, REPORTS_ROOT, atomic_json,
                    class_names, load_json, mark_stage,
                    npu_deployment_fingerprint, relative, stage_state,
                    utc_now)
from dataset import preprocess_depth
from protocol import FrameReader
from radio_hil import (load_feature_flags, load_radio_contract,
                       scan_ble_advertisement, validate_radio_cli)


# TensorFlow is used only as the host-side oracle.  Hide its CPU backend and
# API-lifecycle notices so the HIL output stays focused on the board.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

RPS_STATUS_RE = re.compile(
    r"RPS status: enabled=(?P<enabled>\d+) ready=(?P<ready>\d+) "
    r"frame=(?P<frame>\d+).*?runs=(?P<runs>\d+) errors=(?P<errors>\d+) "
    r"last_error=(?P<last_error>-?\d+) inference_ms=(?P<inference_ms>\d+)",
    re.DOTALL,
)


def find_port(requested: str | None) -> str:
    from serial.tools import list_ports
    if requested:
        return requested.upper()
    candidates = [port.device for port in list_ports.comports()
                  if port.vid == 0x0483 and port.pid == 0x5740]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one N6 CN8 CDC port; found {candidates}")
    return candidates[0]


def make_interpreter():
    model = MODELS_ROOT / "rps_int8.tflite"
    if not model.exists():
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=r".*tf\.lite\.Interpreter is deprecated.*"
        )
        import tensorflow as tf
        interpreter = tf.lite.Interpreter(model_path=str(model))
        interpreter.allocate_tensors()
    return interpreter


def read_text(serial: Serial, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while time.monotonic() < deadline:
        waiting = int(serial.in_waiting or 0)
        chunk = serial.read(max(1, min(waiting, 4096)))
        if chunk:
            data.extend(chunk)
    return data.decode("utf-8", errors="replace")


def rps_preflight(serial: Serial) -> tuple[dict[str, int], str]:
    """Prove that the connected SRAM image contains an initialized NPU."""
    serial.reset_input_buffer()
    serial.write(b"RPS ON\rRPS STATUS\r")
    serial.flush()
    response = read_text(serial, 1.2)
    if "Unknown command" in response:
        raise RuntimeError(
            "The connected board is running an older SRAM image without the "
            "RPS command/NPU integration. Run 10_LOAD_RAM.bat again, wait for "
            "the board to boot, and then rerun 11_HIL.bat."
        )
    match = RPS_STATUS_RE.search(response)
    if match is None:
        raise RuntimeError(
            "RPS STATUS did not return a parseable status line. Run "
            "10_LOAD_RAM.bat again and inspect training/reports/"
            "hil_validation.log if this repeats."
        )
    status = {name: int(value) for name, value in match.groupdict().items()}
    if status["enabled"] != 1:
        raise RuntimeError("RPS ON was rejected by the connected firmware.")
    if status["ready"] != 1:
        raise RuntimeError(
            "Neural-ART initialization failed on the board: "
            f"errors={status['errors']}, last_error={status['last_error']}. "
            "See training/reports/hil_validation.log and the ST-LINK UART log."
        )
    return status, response


def write_log(lines: list[str]) -> None:
    path = REPORTS_ROOT / "hil_validation.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def radio_preflight(serial: Serial, ble_scan_seconds: float) -> tuple[dict, str]:
    """Validate source flags, live NCP state/version, and enabled air interfaces."""
    flags = load_feature_flags(PROJECT_ROOT)
    contract = load_radio_contract(PROJECT_ROOT)
    commands = ["radio hardware", "radio status"]
    if flags["radio"]:
        commands.append("radio info")
    if flags["ble"]:
        commands.append("ble status")
    if flags["wifi"]:
        commands.append("wifi status")

    serial.reset_input_buffer()
    serial.write(("\r".join(commands) + "\r").encode("ascii"))
    serial.flush()
    response = read_text(serial, 2.5)
    if flags["wifi"]:
        serial.write(b"wifi scan\r")
        serial.flush()
        response += read_text(serial, 12.0)
    report = validate_radio_cli(
        response, flags, str(contract["expected_sdk_version"])
    )
    if flags["ble"]:
        report["ble_advertisement"] = scan_ble_advertisement(
            str(report["ble"]["device_name"]), ble_scan_seconds
        )
    return report, response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port")
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--no-model", action="store_true")
    parser.add_argument("--ble-scan-seconds", type=float, default=8.0)
    args = parser.parse_args()
    if args.frames < 10:
        raise RuntimeError("HIL requires at least 10 frames.")
    if args.ble_scan_seconds <= 0.0:
        raise RuntimeError("--ble-scan-seconds must be positive.")
    deployment_fingerprint = npu_deployment_fingerprint()
    ram_state = stage_state("10_ram")
    if (ram_state.get("status") != "complete" or
            ram_state.get("input_fingerprint") != deployment_fingerprint):
        raise RuntimeError(
            "The current integrated firmware has not been loaded to RAM. "
            "Run 10_LOAD_RAM.bat now, do not reset the board, and then run "
            "11_HIL.bat."
        )
    port = find_port(args.port)
    interpreter = None
    input_info = None
    output_info = None
    predictions = {name: 0 for name in class_names()}
    frame_ids = []
    payload_crcs = []
    model_tensor_crcs = []
    nonempty_model_tensors = 0
    timestamps = []
    npu_frames = 0
    npu_class_matches = 0
    npu_decision_consistent = 0
    npu_boundary_ties = 0
    npu_score_deltas = []
    npu_run_counters = []
    exact_model_tensor_frames = 0
    started = time.monotonic()

    # Initialize TensorFlow before Windows Runtime/Bleak starts a Bluetooth
    # discovery session.  On some Windows builds, loading TensorFlow's native
    # DLLs after WinRT Bluetooth teardown intermittently fails with
    # _pywrap_tensorflow_internal DLL initialization errors.
    interpreter = None if args.no_model else make_interpreter()
    input_info = interpreter.get_input_details()[0] if interpreter else None
    output_info = interpreter.get_output_details()[0] if interpreter else None

    serial = Serial(port, 115200, timeout=0.2, write_timeout=2)
    serial.dtr = True
    log_lines = [f"HIL start: {utc_now()}", f"port: {port}"]
    radio_report = None
    try:
        time.sleep(0.35)
        serial.reset_input_buffer()
        serial.write(b"\rDATASET STREAM OFF\rMAP OFF\r")
        serial.flush()
        time.sleep(0.3)
        serial.reset_input_buffer()
        try:
            radio_report, radio_text = radio_preflight(
                serial, args.ble_scan_seconds
            )
            log_lines.extend([
                "Radio preflight response:",
                radio_text.rstrip(),
                f"parsed radio report: {radio_report}",
            ])
        except Exception as exc:
            log_lines.extend(["Radio preflight failed:", str(exc)])
            write_log(log_lines)
            report_path = REPORTS_ROOT / "hil_validation.json"
            preflight_report = {
                "schema": 2,
                "created_utc": utc_now(),
                "port": port,
                "result": "fail",
                "failure_stage": "radio_preflight",
                "error": str(exc),
            }
            atomic_json(report_path, preflight_report)
            mark_stage("11_hil", status="failed",
                       inputs=deployment_fingerprint,
                       outputs=[relative(report_path)],
                       details=preflight_report)
            print(f"HIL RADIO FAIL: {exc}")
            return 8
        source_flags = radio_report["source_flags"]
        if source_flags["radio"]:
            print("Radio preflight: ready, NCP SDK "
                  f"{radio_report['observed_sdk_version']}")
        else:
            print("Radio preflight: radio disabled by app_features.h")
        if source_flags["ble"]:
            advertisement = radio_report["ble_advertisement"]
            print("BLE preflight: advertising "
                  f"{advertisement['name']} at {advertisement['rssi_dbm']} dBm")
        if source_flags["wifi"]:
            print("Wi-Fi preflight: station query and scan passed")
        try:
            rps_status, preflight_text = rps_preflight(serial)
            log_lines.extend(["RPS preflight response:", preflight_text.rstrip(),
                              f"parsed RPS status: {rps_status}"])
        except Exception as exc:
            log_lines.extend(["RPS preflight failed:", str(exc)])
            write_log(log_lines)
            report_path = REPORTS_ROOT / "hil_validation.json"
            preflight_report = {
                "schema": 2,
                "created_utc": utc_now(),
                "port": port,
                "result": "fail",
                "failure_stage": "rps_preflight",
                "error": str(exc),
            }
            atomic_json(report_path, preflight_report)
            mark_stage("11_hil", status="failed",
                       inputs=deployment_fingerprint,
                       outputs=[relative(report_path)],
                       details=preflight_report)
            print(f"HIL PRECHECK FAIL: {exc}")
            return 7
        print("RPS preflight: ready=1, "
              f"runs={rps_status['runs']}, errors={rps_status['errors']}, "
              f"last_error={rps_status['last_error']}")
        serial.reset_input_buffer()
        serial.write(b"DATASET STREAM ON\r")
        serial.flush()
        reader = FrameReader(serial)
        previous = None
        for index in range(args.frames):
            frame = reader.read_frame(timeout=3.0)
            if previous is not None:
                delta = (frame.frame_id - previous) & 0xFFFFFFFF
                if delta == 0 or delta > 1000:
                    raise RuntimeError(
                        f"Frame sequence stuck/jumped: {previous} -> {frame.frame_id}"
                    )
            previous = frame.frame_id
            frame_ids.append(frame.frame_id)
            timestamps.append(frame.timestamp_ms)
            payload_crcs.append(frame.payload_crc32)
            host_model_input = preprocess_depth(frame.depth_mm)[..., 0]
            if (frame.model_input is None or
                    frame.model_frame_id != frame.frame_id):
                raise RuntimeError(
                    f"Frame {frame.frame_id} has no exact frame-matched "
                    "N6DF v3 device model tensor"
                )
            if not np.array_equal(frame.model_input, host_model_input):
                mismatch = int(np.count_nonzero(
                    frame.model_input != host_model_input
                ))
                raise RuntimeError(
                    f"Frame {frame.frame_id}: device/Python preprocessing "
                    f"differs in {mismatch} pixels"
                )
            exact_model_tensor_frames += 1
            model_tensor_crcs.append(zlib.crc32(frame.model_input.tobytes()))
            nonempty_model_tensors += int(np.any(frame.model_input))
            if interpreter is not None:
                tensor = frame.model_input[np.newaxis, ..., np.newaxis]
                interpreter.set_tensor(input_info["index"], tensor)
                interpreter.invoke()
                output = interpreter.get_tensor(output_info["index"])[0]
                host_class = int(np.argmax(output))
                label = class_names()[host_class]
                predictions[label] += 1
                if frame.npu_valid and frame.npu_scores is not None:
                    npu_frames += 1
                    npu_run_counters.append(int(frame.npu_runs or 0))
                    npu_class_matches += int(frame.npu_class_id == host_class)
                    host_scores = np.asarray(output, dtype=np.int16)
                    device_scores = np.asarray(frame.npu_scores, dtype=np.int16)
                    frame_score_delta = int(np.max(
                        np.abs(host_scores - device_scores)
                    ))
                    npu_score_deltas.append(frame_score_delta)
                    if frame.npu_class_id == host_class:
                        npu_decision_consistent += 1
                    elif (frame.npu_class_id is not None and
                          0 <= frame.npu_class_id < len(host_scores)):
                        # A bounded backend score delta can legitimately flip
                        # argmax when the two candidates are nearly tied. The
                        # decision is still numerically consistent when the
                        # host margin is no larger than the worst-case motion
                        # of both scores (2 * L-infinity delta).
                        competing_margin = int(
                            host_scores[host_class] -
                            host_scores[frame.npu_class_id]
                        )
                        if competing_margin <= (2 * frame_score_delta):
                            npu_decision_consistent += 1
                            npu_boundary_ties += 1
            elif frame.npu_valid:
                npu_frames += 1
                npu_run_counters.append(int(frame.npu_runs or 0))
            if (index + 1) % 10 == 0:
                print(f"{index + 1}/{args.frames}: frame {frame.frame_id}")
    finally:
        try:
            serial.write(b"DATASET STREAM OFF\r")
            serial.flush()
            time.sleep(0.3)
        except Exception:
            pass
        serial.close()
    elapsed = time.monotonic() - started
    unique_crcs = len(set(payload_crcs))
    sensor_elapsed_ms = ((timestamps[-1] - timestamps[0]) & 0xFFFFFFFF)
    sensor_fps = ((len(timestamps) - 1) * 1000.0 / sensor_elapsed_ms
                  if sensor_elapsed_ms else 0.0)
    frame_span = ((frame_ids[-1] - frame_ids[0]) & 0xFFFFFFFF) + 1
    missing_frames = max(0, frame_span - len(frame_ids))
    missing_ratio = missing_frames / frame_span
    training_config = load_json(CONFIG_ROOT / "training.json")
    required_fps = float(training_config["capture"]["save_fps"])
    hil_config = training_config.get("hil", {})
    minimum_npu_coverage = float(
        hil_config.get("minimum_npu_coverage", 0.8)
    )
    minimum_decision_consistency = float(
        hil_config.get(
            "minimum_decision_consistency",
            hil_config.get("minimum_class_agreement", 0.95),
        )
    )
    maximum_raw_score_delta = int(
        hil_config.get("maximum_raw_score_delta", 16)
    )
    minimum_nonempty_model_ratio = float(
        hil_config.get("minimum_nonempty_model_ratio", 0.2)
    )
    minimum_unique_model_tensors = int(
        hil_config.get("minimum_unique_model_tensors", 4)
    )
    nonempty_model_ratio = nonempty_model_tensors / len(frame_ids)
    unique_model_tensors = len(set(model_tensor_crcs))
    npu_coverage = npu_frames / len(frame_ids)
    counters_monotonic = bool(npu_run_counters) and all(
        right > left for left, right in
        zip(npu_run_counters, npu_run_counters[1:])
    )
    class_agreement = (npu_class_matches / npu_frames
                       if npu_frames and interpreter else None)
    decision_consistency = (npu_decision_consistent / npu_frames
                            if npu_frames and interpreter else None)
    max_score_delta = max(npu_score_deltas) if npu_score_deltas else None
    npu_gate = (npu_coverage >= minimum_npu_coverage and counters_monotonic)
    if interpreter is not None:
        npu_gate = (npu_gate and decision_consistency is not None and
                    decision_consistency >= minimum_decision_consistency and
                    max_score_delta is not None and
                    max_score_delta <= maximum_raw_score_delta)
    pass_gate = (sensor_fps >= required_fps and
                 unique_crcs >= int(0.8 * len(frame_ids)) and
                 nonempty_model_ratio >= minimum_nonempty_model_ratio and
                 unique_model_tensors >= minimum_unique_model_tensors and
                 reader.crc_errors == 0 and
                 exact_model_tensor_frames == len(frame_ids) and npu_gate)
    report = {
        "schema": 2, "created_utc": utc_now(), "port": port,
        "radio": radio_report,
        "frames": len(frame_ids), "first_frame": frame_ids[0],
        "last_frame": frame_ids[-1], "elapsed_seconds": elapsed,
        "observed_fps": len(frame_ids) / elapsed,
        "effective_valid_frame_fps": sensor_fps,
        "required_capture_fps": required_fps,
        "missing_frame_ids": missing_frames,
        "missing_frame_ratio": missing_ratio,
        "parser_discarded_bytes": reader.discarded_bytes,
        "parser_crc_errors": reader.crc_errors,
        "parser_framing_candidates_rejected": reader.framing_errors,
        "unique_payload_crc32": unique_crcs,
        "nonempty_model_tensors": nonempty_model_tensors,
        "nonempty_model_tensor_ratio": nonempty_model_ratio,
        "unique_model_tensor_crc32": unique_model_tensors,
        "model_tensor_requirements": {
            "minimum_nonempty_ratio": minimum_nonempty_model_ratio,
            "minimum_unique_tensors": minimum_unique_model_tensors,
        },
        "device_python_bit_exact_model_tensors": exact_model_tensor_frames,
        "host_tflite_predictions": predictions if interpreter else None,
        "npu_comparison": {
            "preflight": rps_status,
            "valid_frame_results": npu_frames,
            "coverage": npu_coverage,
            "run_counter_monotonic": counters_monotonic,
            "class_matches": npu_class_matches if interpreter else None,
            "class_agreement": class_agreement,
            "decision_consistent_frames": (npu_decision_consistent
                                            if interpreter else None),
            "decision_consistency": decision_consistency,
            "tolerance_explained_boundary_ties": (npu_boundary_ties
                                                   if interpreter else None),
            "maximum_raw_score_delta": max_score_delta,
            "requirements": {
                "coverage": minimum_npu_coverage,
                "decision_consistency": (minimum_decision_consistency
                                         if interpreter else None),
                "maximum_raw_score_delta": (maximum_raw_score_delta
                                             if interpreter else None),
            },
        },
        "result": "pass" if pass_gate else "fail",
    }
    report_path = REPORTS_ROOT / "hil_validation.json"
    atomic_json(report_path, report)
    log_lines.extend([
        f"result: {report['result']}",
        f"frames: {len(frame_ids)}",
        f"crc_errors: {reader.crc_errors}",
        f"npu_valid_frames: {npu_frames}",
        f"device_python_bit_exact_model_tensors: {exact_model_tensor_frames}",
        f"nonempty_model_tensors: {nonempty_model_tensors}",
        f"unique_model_tensors: {unique_model_tensors}",
        f"class_agreement: {class_agreement}",
        f"decision_consistency: {decision_consistency}",
        f"tolerance_explained_boundary_ties: {npu_boundary_ties}",
        f"maximum_raw_score_delta: {max_score_delta}",
        f"radio: {radio_report}",
    ])
    write_log(log_lines)
    mark_stage("11_hil", status="complete" if pass_gate else "failed",
               inputs=deployment_fingerprint,
               outputs=[relative(report_path)],
               details=report)
    print(f"HIL {report['result'].upper()}: {len(frame_ids)} CRC-valid frames, "
          f"{unique_crcs} distinct payloads, sensor time {sensor_fps:.2f} fps, "
          f"missing IDs {missing_frames}/{frame_span}")
    print(f"Neural-ART: {npu_frames}/{len(frame_ids)} frame-matched results, "
          f"counter monotonic={counters_monotonic}, "
          f"class agreement={class_agreement}, "
          f"decision consistency={decision_consistency} "
          f"({npu_boundary_ties} boundary ties), "
          f"max raw delta={max_score_delta}")
    print("Preprocessing: "
          f"{exact_model_tensor_frames}/{len(frame_ids)} device tensors "
          f"bit-exact with Python, {nonempty_model_tensors} non-empty, "
          f"{unique_model_tensors} distinct model tensors")
    if (nonempty_model_ratio < minimum_nonempty_model_ratio or
            unique_model_tensors < minimum_unique_model_tensors):
        print("HIL INPUT FAIL: move a visible hand through ROCK, PAPER and "
              "SCISSORS during Stage 11; an empty/static scene cannot prove "
              "the live NPU input path.")
    return 0 if report["result"] == "pass" else 6


if __name__ == "__main__":
    raise SystemExit(main())
