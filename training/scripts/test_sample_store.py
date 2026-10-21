import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
from protocol import FrameReader, build_test_record, VERSION_V1, VERSION_V4
from sample_sources import Sample
from sample_store import SampleStore, DuplicateSample, IntegrityError


class LosslessStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg = json.loads((Path(__file__).parents[1] / "config/preprocessing.json").read_text(encoding="utf-8"))
        self.manifest = {"project_id": "test-project", "classes": [{"name": "rock"}]}

    def tearDown(self):
        self.temp.cleanup()

    def sample(self, frame_id=9, timestamp_ms=100, tensor=False):
        depth = np.full((42, 54), 350, dtype=np.uint16)
        wire = build_test_record(depth, protocol_version=VERSION_V4 if tensor else VERSION_V1, frame_id=frame_id,
                                timestamp_ms=timestamp_ms, npu_scores=(-100, 100),
                                model_input=np.zeros((50, 64), dtype=np.uint8) if tensor else None)
        frame = FrameReader(io.BytesIO(wire)).read_frame()
        return Sample(frame, "n6:40:82:7b:03:b8:fa", "ab" * 16, "connection1", "usb", "2026-10-21T12:00:00Z", 100)

    def store(self):
        return SampleStore(self.root, self.manifest, self.cfg, "capture")

    def test_lossless_unlabeled_and_dedupe_across_connections(self):
        store = self.store()
        try:
            sample = self.sample()
            row = store.commit(sample)
            store.verify(row)
            self.assertIsNone(row["label"])
            self.assertFalse(row["tensor_received"])
            self.assertIsNone(row["model_input_png"])
            with self.assertRaises(DuplicateSample):
                store.commit(replace(sample, connection_id="reconnected", source="ble"))
            store.commit(self.sample(frame_id=1, timestamp_ms=200))
            store.commit(replace(sample, boot_id="cd" * 16))
            self.assertEqual(len(store.records()), 3)
        finally:
            store.close()

    def test_wire_or_identity_tampering_is_never_published(self):
        store = self.store()
        try:
            sample = self.sample()
            with self.assertRaises(IntegrityError):
                store.commit(replace(sample, frame=replace(sample.frame, frame_id=99)))
            bad = bytearray(sample.frame.wire_record); bad[-1] ^= 1
            with self.assertRaises(IntegrityError):
                store.commit(replace(sample, frame=replace(sample.frame, wire_record=bytes(bad))))
            self.assertEqual(store.records(), [])
        finally:
            store.close()

    def test_reopen_repairs_interrupted_index_and_jsonl(self):
        store = self.store()
        row = store.commit(self.sample(tensor=True))
        store.database.execute("DELETE FROM samples"); store.database.commit()
        store.close()
        (self.root / "data/raw/capture/metadata.jsonl").write_text('{"partial":', encoding="utf-8")
        store = self.store()
        try:
            self.assertEqual(store.recovered, 1)
            self.assertEqual(store.records()[0]["sample_id"], row["sample_id"])
            store.verify(store.records()[0])
        finally:
            store.close()

    def test_corrupt_reopen_releases_lock(self):
        store = self.store(); row = store.commit(self.sample()); store.close()
        path = self.root / row["npz"]
        original = path.read_bytes(); path.write_bytes(b"broken")
        with self.assertRaises(IntegrityError): self.store()
        path.write_bytes(original)
        store = self.store(); store.close()

    def test_label_overlay_preserves_canonical_source_identity(self):
        from label_service import sample_id
        store = self.store()
        try:
            row = store.commit(self.sample())
            self.assertEqual(sample_id(row), row['sample_id'])
            row['label'] = 'rock'
            store.verify(row)
            row['units'] = 'cm'
            with self.assertRaises(IntegrityError): store.verify(row)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
