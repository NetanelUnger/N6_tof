"""Stage 06: full-integer TFLite conversion and test-set equivalence report."""

from __future__ import annotations

import argparse
import os

import numpy as np

from common import (CONFIG_ROOT, MODELS_ROOT, PREPARED_ROOT, REPORTS_ROOT,
                    atomic_json, class_names, file_fingerprint, load_json,
                    is_stage_current, mark_stage, relative, sha256_file,
                    stable_hash, utc_now)


QUANTIZATION_CONTRACT_REVISION = 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf

    source_model = MODELS_ROOT / "rps_float.keras"
    if not source_model.exists():
        raise RuntimeError("Run 05_TRAIN.bat first.")
    with np.load(PREPARED_ROOT / "train.npz", allow_pickle=False) as archive:
        representative_x = archive["x"]
    with np.load(PREPARED_ROOT / "test.npz", allow_pickle=False) as archive:
        test_x, test_y = archive["x"], archive["y"]
    fingerprint = stable_hash({
        "model": sha256_file(source_model),
        "prepared": file_fingerprint(PREPARED_ROOT.glob("*.npz")),
        "quantization_contract_revision": QUANTIZATION_CONTRACT_REVISION,
    })
    output_model = MODELS_ROOT / "rps_int8.tflite"
    contract_path = MODELS_ROOT / "model_contract.json"
    report_path = REPORTS_ROOT / "quantized_model_evaluation.json"
    if (not args.force and
            is_stage_current("06_quantize", fingerprint,
                             [output_model, contract_path, report_path])):
        print("Quantized model is current; reusing it. Pass --force to rebuild.")
        return 0
    model = tf.keras.models.load_model(source_model)
    source_input_dtype = tf.as_dtype(model.inputs[0].dtype)
    if source_input_dtype != tf.float32:
        raise RuntimeError(
            "The Keras source still has a uint8 input, which leaves an "
            "expanding UINT8-to-FLOAT Cast inside the STEdgeAI graph and "
            "corrupts non-zero STM32N6 inputs. Rerun 05_TRAIN.bat; the "
            "updated architecture automatically rejects the old checkpoint."
        )

    def representative_dataset():
        # Deterministic stride covers the dataset without loading new copies.
        limit = min(200, len(representative_x))
        indexes = np.linspace(0, len(representative_x) - 1, limit,
                              dtype=np.int64)
        for index in indexes:
            # The Keras boundary is float32 in the original 0..255 pixel
            # domain. The converter uses these real values to derive a uint8
            # input scale of exactly 1 and a zero-point of 0.
            yield [representative_x[index:index + 1].astype(np.float32)]

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.uint8
    converter.inference_output_type = tf.int8
    tflite = converter.convert()
    output_model.write_bytes(tflite)
    interpreter = tf.lite.Interpreter(model_content=tflite)
    interpreter.allocate_tensors()
    input_info = interpreter.get_input_details()[0]
    output_info = interpreter.get_output_details()[0]
    if input_info["dtype"] != np.uint8 or output_info["dtype"] != np.int8:
        raise RuntimeError(
            f"Model is not fully integer: input={input_info['dtype']}, "
            f"output={output_info['dtype']}"
        )
    predictions = []
    raw_outputs = []
    for sample in test_x:
        interpreter.set_tensor(input_info["index"], sample[np.newaxis].astype(np.uint8))
        interpreter.invoke()
        output = interpreter.get_tensor(output_info["index"])[0]
        predictions.append(int(np.argmax(output)))
        raw_outputs.append(output)
    predictions_array = np.asarray(predictions)
    accuracy = float(np.mean(predictions_array == test_y))
    per_class_accuracy = {}
    for index, name in enumerate(class_names()):
        mask = test_y == index
        per_class_accuracy[name] = float(
            np.mean(predictions_array[mask] == test_y[mask])
        )
    macro_accuracy = float(np.mean(list(per_class_accuracy.values())))
    input_scale, input_zero = input_info["quantization"]
    output_scale, output_zero = output_info["quantization"]
    if (not np.isfinite(input_scale) or
            not np.isclose(input_scale, 1.0, rtol=0.0, atol=1e-6) or
            int(input_zero) != 0):
        raise RuntimeError(
            "Unsafe TFLite input contract: expected uint8 scale=1 and "
            f"zero_point=0, got scale={input_scale}, "
            f"zero_point={input_zero}. Refusing a model that cannot consume "
            "the firmware's exact 0/255 bytes directly."
        )
    operation_names = [
        operation["op_name"] for operation in interpreter._get_ops_details()
    ]
    if "CAST" in operation_names:
        raise RuntimeError(
            "Unsafe TFLite graph: CAST remains at the quantized input. "
            "STEdgeAI may expand it in-place and corrupt non-zero input."
        )
    contract = {
        "schema": 2, "created_utc": utc_now(),
        "quantization_contract_revision": QUANTIZATION_CONTRACT_REVISION,
        "model_sha256": sha256_file(output_model),
        "model_size_bytes": output_model.stat().st_size,
        "classes": class_names(),
        "input": {"name": input_info["name"],
                  "shape": input_info["shape"].astype(int).tolist(),
                  "dtype": "uint8", "scale": float(input_scale),
                  "zero_point": int(input_zero)},
        "output": {"name": output_info["name"],
                   "shape": output_info["shape"].astype(int).tolist(),
                   "dtype": "int8", "scale": float(output_scale),
                   "zero_point": int(output_zero)},
        "preprocessing": load_json(CONFIG_ROOT / "preprocessing.json"),
        "tflite_operations": operation_names,
        "test_accuracy": accuracy,
        "test_macro_accuracy": macro_accuracy,
        "test_per_class_accuracy": per_class_accuracy,
    }
    float_report_path = REPORTS_ROOT / "float_model_evaluation.json"
    float_report = (load_json(float_report_path)
                    if float_report_path.exists() else None)
    float_accuracy = (float(float_report.get("test_macro_accuracy",
                                             float_report["test_accuracy"]))
                      if float_report else None)
    drop = (float_accuracy - macro_accuracy
            if float_accuracy is not None else None)
    contract["float_test_macro_accuracy"] = float_accuracy
    contract["quantization_accuracy_drop"] = drop
    atomic_json(contract_path, contract)
    np.savez_compressed(MODELS_ROOT / "quantized_test_outputs.npz",
                        predictions=predictions_array,
                        labels=test_y, raw_outputs=np.asarray(raw_outputs))
    atomic_json(report_path, contract)
    mark_stage("06_quantize", status="complete", inputs=fingerprint,
               outputs=[relative(output_model), relative(contract_path),
                        relative(report_path)], details=contract)
    print(f"Fully integer model: {output_model.stat().st_size} bytes; "
          f"test accuracy overall={accuracy:.3%}, macro={macro_accuracy:.3%}, "
          f"per-class={per_class_accuracy}")
    training_cfg = load_json(CONFIG_ROOT / "training.json")
    if (drop is not None and
            drop > training_cfg["maximum_quantization_accuracy_drop"]):
        mark_stage("06_quantize", status="quality_gate_failed",
                   inputs=fingerprint,
                   outputs=[relative(output_model), relative(contract_path),
                            relative(report_path)], details=contract)
        print(f"QUALITY GATE FAILED: quantization lost {drop:.1%}, maximum is "
              f"{training_cfg['maximum_quantization_accuracy_drop']:.1%}.")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
