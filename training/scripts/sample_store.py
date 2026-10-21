"""Lossless, integrity-first sample commits and restart-safe frame identity."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import numpy as np
from PIL import Image

from dataset import preprocess_depth, preview_rgb
from model_contract import identity as contract_identity
from project_context import atomic, digest, read, replace
from protocol import FrameReader


class DuplicateSample(RuntimeError):
    pass


class IntegrityError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_identity(sample):
    if not sample.device_id or not re.fullmatch(r"[a-f0-9]{32}", sample.boot_id or ""):
        raise IntegrityError("Device and verified RAM boot identity are required.")
    # A sensor-local counter can restart without restarting the MCU. The
    # original device timestamp is part of the logical frame identity; the
    # native counter remains separately available for inference matching.
    return {"device": sample.device_id, "device_session": sample.boot_id,
            "frame": {"counter": sample.frame.frame_id, "timestamp_ms": sample.frame.timestamp_ms},
            "channel": sample.channel}


def verify_record(root, record, manifest=None):
    """Read-only verification also used before label/rejection filtering."""
    if manifest and record.get("project_id") not in {
            manifest["project_id"], manifest.get("copied_from"),
            *manifest.get("origin_project_ids", [])}:
        raise IntegrityError("Sample belongs to another project without copy provenance.")
    verifier = SampleStore.__new__(SampleStore)
    verifier.root = Path(root).resolve()
    return verifier.verify(record)


class SampleStore:
    def __init__(self, root, manifest, config, session, *, contract_roots=()):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", session) or session in {".", ".."}:
            raise ValueError("Invalid capture session ID.")
        self.root, self.manifest, self.config = Path(root).resolve(), manifest, config
        self.session = session
        self.folder = self.root / "data/raw" / session
        self.folder.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.folder / "metadata.jsonl"
        self.contract_roots = [Path(p) for p in contract_roots]
        self.contracts = {}
        self.lock = (self.folder / ".capture.lock").open("a+b")
        self.lock.seek(0)
        if not self.lock.read(1):
            self.lock.write(b"1"); self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            raise IntegrityError("BLOCKED: another recorder owns this capture session.") from exc
        (self.root / "state").mkdir(exist_ok=True)
        self.database = sqlite3.connect(self.root / "state/sample_index.sqlite3")
        self.database.execute("PRAGMA synchronous=FULL")
        self.database.execute("CREATE TABLE IF NOT EXISTS samples (sample_id TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL)")
        self.accepted = self.duplicates = self.recovered = 0
        try:
            self.recover()
        except Exception:
            self.close()
            raise

    def known_contract(self, identifier):
        if not identifier:
            return None
        if identifier in self.contracts:
            return self.contracts[identifier]
        for root in self.contract_roots:
            paths = [root / "models/model_contract.json", *root.glob("projects/*/models/model_contract.json")]
            for path in paths:
                if path.is_file():
                    value = read(path)
                    if value.get("schema") == 3 and value.get("contract_sha256") == identifier:
                        if contract_identity(value) != identifier:
                            raise IntegrityError("Known source contract hash is invalid.")
                        self.contracts[identifier] = value
                        return value
        return None

    def _path(self, relative):
        path = (self.root / relative).resolve()
        if self.root not in path.parents:
            raise IntegrityError("Sample path escapes its project.")
        return path

    def verify(self, record):
        canonical_path = self._path(record["wire_record"]).parent / "sample.json"
        canonical = read(canonical_path)
        for key, value in canonical.items():
            if key not in {"label", "accepted", "label_provenance"}:
                # JSON normalizes tuples; compare the serialized values too.
                if json.dumps(record.get(key), sort_keys=True) != json.dumps(value, sort_keys=True):
                    raise IntegrityError(f"Immutable sample metadata differs: {key}")
        for relative, expected in record["integrity"]["files"].items():
            if sha(self._path(relative)) != expected:
                raise IntegrityError(f"Stored file hash differs: {relative}")
        wire = self._path(record["wire_record"]).read_bytes()
        try:
            frame = FrameReader(io.BytesIO(wire)).read_frame(timeout=.1)
        except (RuntimeError, TimeoutError) as exc:
            raise IntegrityError("Stored source record failed header/payload integrity.") from exc
        with np.load(self._path(record["npz"]), allow_pickle=False) as data:
            if not np.array_equal(data["depth_mm"], frame.depth_mm):
                raise IntegrityError("Stored numeric depth differs from received source bytes.")
            present = "device_model_input_u8" in data
            if present != record["tensor_received"] or present != (frame.model_input is not None):
                raise IntegrityError("Exact tensor presence is inconsistent.")
            if present and not np.array_equal(data["device_model_input_u8"], frame.model_input):
                raise IntegrityError("Stored exact tensor differs from received source bytes.")
        with Image.open(self._path(record["depth_png"])) as image:
            if not np.array_equal(np.asarray(image), frame.depth_mm):
                raise IntegrityError("Numeric depth PNG differs from original source bytes.")
        if digest(record["identity"]) != record["sample_id"]:
            raise IntegrityError("Logical sample identity differs from its metadata.")
        if record["identity"]["frame"] != {"counter": frame.frame_id, "timestamp_ms": frame.timestamp_ms}:
            raise IntegrityError("Logical frame identity differs from source bytes.")
        if hashlib.sha256(wire).hexdigest() != record["integrity"]["wire_sha256"]:
            raise IntegrityError("Original wire record hash differs.")
        if record["device"]["id"] != record["identity"]["device"] or record["device"]["boot_id"] != record["identity"]["device_session"]:
            raise IntegrityError("Device/session metadata differs from logical sample identity.")
        if record["source_contract_sha256"] != frame.contract_sha256:
            raise IntegrityError("Source contract differs from the wire identifier.")
        if record.get("source_contract") and contract_identity(record["source_contract"]) != frame.contract_sha256:
            raise IntegrityError("Source model contract hash differs from its content.")
        return frame

    def recover(self):
        # Only complete, atomically published sample directories are indexed.
        # Unpublished .pending trees remain diagnostic evidence and are ignored.
        for path in sorted((self.folder / "records").glob("*/sample.json")):
            record = read(path)
            self.verify(record)
            found = self.database.execute("SELECT payload FROM samples WHERE sample_id=?", (record["sample_id"],)).fetchone()
            if not found:
                self.database.execute("INSERT INTO samples VALUES (?,?,?)",
                    (record["sample_id"], self.session, json.dumps(record, ensure_ascii=False, sort_keys=True)))
                self.recovered += 1
            elif json.loads(found[0]) != record:
                raise IntegrityError("Published sample metadata differs from its durable index.")
        self.database.commit()
        records = [json.loads(row[0]) for row in self.database.execute(
            "SELECT payload FROM samples WHERE session=? ORDER BY rowid", (self.session,))]
        # Recovery replaces a possibly interrupted JSONL append with canonical
        # committed records; original data and review decisions never change.
        if records or (self.folder / "records").exists():
            self._rewrite_metadata(records)

    def _rewrite_metadata(self, records):
        temporary = self.metadata_path.with_name(".metadata-" + uuid.uuid4().hex + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush(); os.fsync(stream.fileno())
        replace(temporary, self.metadata_path)

    def commit(self, sample, *, label=None, group=None):
        frame = sample.frame
        wire = frame.wire_record
        if not wire:
            raise IntegrityError("No validated original wire record; sample not committed.")
        try:
            verified = FrameReader(io.BytesIO(wire)).read_frame(timeout=.1)
        except (RuntimeError, TimeoutError) as exc:
            raise IntegrityError("Source record integrity failed before commit.") from exc
        if not np.array_equal(frame.depth_mm, verified.depth_mm):
            raise IntegrityError("Decoded numeric depth differs from original source bytes.")
        if (frame.frame_id, frame.timestamp_ms) != (verified.frame_id, verified.timestamp_ms):
            raise IntegrityError("Decoded frame identity differs from original source bytes.")
        identity = record_identity(sample)
        identifier = digest(identity)
        found = self.database.execute("SELECT payload FROM samples WHERE sample_id=?", (identifier,)).fetchone()
        if found:
            old = json.loads(found[0])
            if old["integrity"]["wire_sha256"] != hashlib.sha256(wire).hexdigest():
                raise IntegrityError("Same sample identity carries different source bytes.")
            self.duplicates += 1
            raise DuplicateSample(identifier)
        allowed = {c["name"] for c in self.manifest["classes"]} if self.manifest else set()
        if label is not None and label not in allowed:
            raise ValueError("Unknown capture label.")
        final = self.folder / "records" / identifier
        pending = self.folder / ".pending" / (identifier + "-" + uuid.uuid4().hex)
        pending.mkdir(parents=True)
        payload = {"depth_mm": np.asarray(verified.depth_mm, dtype="<u2")}
        if verified.model_input is not None:
            payload["device_model_input_u8"] = verified.model_input
        np.savez_compressed(pending / "raw.npz", **payload)
        Image.fromarray(verified.depth_mm).save(pending / "depth.png")
        preview = preview_rgb(verified.depth_mm, self.config["near_mm"], self.config["far_mm"], verified.invalid_mm)
        Image.fromarray(preview).save(pending / "preview.png")
        if verified.model_input is not None:
            Image.fromarray(verified.model_input).save(pending / "model.png")
        (pending / "source.n6df").write_bytes(wire)
        target_tensor = preprocess_depth(verified.depth_mm, self.config)[..., 0]
        compatible = verified.model_input is not None and np.array_equal(target_tensor, verified.model_input)
        source_contract = self.known_contract(verified.contract_sha256)
        source_verified = None
        if source_contract and verified.model_input is not None:
            expected_source = preprocess_depth(verified.depth_mm, source_contract["preprocessing"])[..., 0]
            if not np.array_equal(expected_source, verified.model_input):
                raise IntegrityError("Device/source-contract preprocessing mismatch; sample remains unpublished.")
            source_verified = "bit_exact_source_contract"
        elif compatible:
            source_verified = "bit_exact_target_comparison_for_this_frame"
        relative = lambda name: (final / name).relative_to(self.root).as_posix()
        record = {"schema": 2, "sample_schema": 1, "sample_id": identifier,
            "identity": identity, "project_id": self.manifest["project_id"] if self.manifest else "legacy-rps",
            "session_id": self.session, "connection_id": sample.connection_id, "burst_id": group,
            "device": {"id": sample.device_id, "boot_id": sample.boot_id,
                       "boot_identity_source": "RAM_once_per_MCU_boot", **(sample.device_info or {})},
            "source": sample.source, "captured_utc": sample.received_utc,
            "received_monotonic_ns": sample.received_monotonic_ns,
            "firmware_frame_id": verified.frame_id, "firmware_timestamp_ms": verified.timestamp_ms,
            "source_clock": "device_ms_modulo_2^32", "channel": sample.channel, "units": "mm",
            "lossless": True, "dtype": "uint16_mm", "shape": list(verified.depth_mm.shape),
            "encoding": {"sensor": "uint16_le_mm", "storage": "lossless_npz_and_png16",
                         "tensor": "uint8" if verified.model_input is not None else None,
                         "tensor_quantization": {"scale": 1., "zero_point": 0} if verified.model_input is not None else None,
                         "score_quantization": {"dtype": "int8", "scale": 1/256, "zero_point": -128} if verified.protocol_version >= 2 else None},
            "label": label, "accepted": True, "label_provenance": "capture_user" if label else "unlabeled",
            "npz": relative("raw.npz"), "depth_png": relative("depth.png"), "preview_png": relative("preview.png"),
            "model_input_png": relative("model.png") if verified.model_input is not None else None,
            "preview_only": True, "wire_record": relative("source.n6df"),
            "depth_sha256": hashlib.sha256(verified.depth_mm.astype("<u2").tobytes()).hexdigest(),
            "protocol_version": verified.protocol_version, "source_contract_sha256": verified.contract_sha256,
            "source_contract": source_contract, "tensor_received": verified.model_input is not None,
            "tensor_compatible_with_project": compatible, "device_tensor_verification": source_verified,
            "model_input_source": f"device_n6df_v{verified.protocol_version}" if verified.model_input is not None else "absent",
            "device_model_input_sha256": hashlib.sha256(verified.model_input.tobytes()).hexdigest() if verified.model_input is not None else None,
            "inference": {"valid": verified.npu_valid, "frame_id": verified.npu_frame_id,
                          "class_index": verified.npu_class_id, "class_count": verified.class_count,
                          "scores": verified.npu_scores, "runs": verified.npu_runs},
            "integrity": {"header_and_payload_crcs_verified": True,
                          "wire_sha256": hashlib.sha256(wire).hexdigest(), "files": {}}}
        for path in pending.iterdir():
            record["integrity"]["files"][relative(path.name)] = sha(path)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        atomic(pending / "sample.json", record)
        final.parent.mkdir(exist_ok=True)
        replace(pending, final)
        with self.database:
            self.database.execute("INSERT INTO samples VALUES (?,?,?)",
                (identifier, self.session, json.dumps(record, ensure_ascii=False, sort_keys=True)))
            with self.metadata_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                stream.flush(); os.fsync(stream.fileno())
        self.accepted += 1
        return record

    def records(self):
        return [json.loads(row[0]) for row in self.database.execute(
            "SELECT payload FROM samples WHERE session=? ORDER BY rowid", (self.session,))]

    def close(self):
        self.database.close()
        self.lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
        self.lock.close()
