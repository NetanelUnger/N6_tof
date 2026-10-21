"""M2 class semantics checks against immutable small sensor fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from label_service import LabelService, load_labels
from project_context import ProjectService, atomic, derived_config, read, semantic_hash


class Labels(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name) / "training"
        source = Path(__file__).resolve().parents[1] / "config"
        shutil.copytree(source, root / "config")
        self.projects = ProjectService(root)
        self.manifest = self.projects.create("fixture", "Fixture")
        self.root = self.projects.root / "fixture"
        self.sensor = self.root / "data/raw/session"
        self.sensor.mkdir()
        records = []
        self.originals = {}
        for c in self.manifest["classes"]:
            for index in range(2):
                path = self.sensor / f"{c['name']}_{index}.npz"
                content = f"{c['name']}-{index}-sensor-data".encode()
                path.write_bytes(content)
                self.originals[path] = content
                records.append({"npz": path.relative_to(self.root).as_posix(),
                    "label": c["name"], "depth_sha256": "a" * 64, "frame_id": len(records)})
        self.metadata = self.sensor / "metadata.jsonl"
        self.metadata.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
        self.metadata_original = self.metadata.read_bytes()
        self.labels = LabelService(self.projects, "fixture")

    def tearDown(self):
        self.temp.cleanup()

    def assert_originals(self):
        self.assertEqual(self.metadata.read_bytes(), self.metadata_original)
        for path, data in self.originals.items():
            self.assertEqual(path.read_bytes(), data)

    def test_rename_merge_delete_and_split_preserve_identity_and_data(self):
        initial = self.labels.rows()
        ids = [r["sample_id"] for r in initial]
        self.assertEqual(len(ids), len(set(ids)))  # same pixel hash, distinct frames
        source, destination, deleted, split = [c["stable_id"] for c in self.manifest["classes"]]
        result = self.labels.change("rename", source, name="תצוגה חדשה")
        self.assertEqual(semantic_hash(self.manifest), semantic_hash(result["project"]))
        self.assertEqual([r["sample_id"] for r in self.labels.rows()], ids)
        self.labels.change("merge", source, target=destination)
        rows = self.labels.rows()
        self.assertEqual(sum(r["class_id"] == destination for r in rows), 4)
        self.labels.change("delete", deleted)
        self.assertEqual(sum(r["class_id"] is None for r in self.labels.rows()), 2)
        self.labels.change("split", split, names=["First part", "Second part"])
        rows = self.labels.rows()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(r["class_id"] is None for r in rows), 4)
        self.assertEqual([r["sample_id"] for r in rows], ids)
        current = self.projects.open("fixture")
        config = derived_config(current)["classes.json"]["classes"]
        self.assertEqual([c["id"] for c in config], list(range(len(current["classes"]))))
        self.assertEqual([c["stable_id"] for c in config], [c["stable_id"] for c in current["classes"]])
        history = load_labels(self.root, current)["history"]
        self.assertEqual([h["action"] for h in history], ["rename", "merge", "delete", "split"])
        self.assert_originals()

    def test_new_class_and_explicit_human_label(self):
        added = self.labels.change("add", name="New class")["project"]["classes"][-1]
        first = self.labels.rows()[0]
        self.labels.label([first["sample_id"]], added["stable_id"])
        rows = self.labels.rows()
        self.assertEqual(rows[0]["class_id"], added["stable_id"])
        self.assertEqual(rows[0]["label_provenance"]["source"], "human-review")
        self.assertNotEqual(rows[1]["class_id"], added["stable_id"])
        self.assert_originals()

    def test_invalid_operations_leave_active_revision_unchanged(self):
        before = self.projects.open("fixture")
        first = before["classes"][0]["stable_id"]
        for action, kwargs in (("merge", {"target": first}), ("split", {"names": ["one"]}),
                               ("rename", {"name": ""})):
            with self.assertRaises(ValueError):
                self.labels.change(action, first, **kwargs)
            self.assertEqual(self.projects.open("fixture"), before)
        with self.assertRaises(ValueError):
            self.labels.label(["missing"], first)
        self.assert_originals()

    def test_two_class_configuration_and_display_refresh_reuse_model_bytes(self):
        from model_contract import create, generate_header, validate
        # Both retirements go through the same service the UI invokes.
        for entry in self.manifest["classes"][2:]:
            self.labels.change("delete", entry["stable_id"])
        current = self.projects.open("fixture")
        self.assertEqual(len(current["classes"]), 2)
        model = self.root / "models/rps_int8.tflite"
        model.write_bytes(b"synthetic model identity fixture")
        metrics = {"input": {"shape": [1,50,64,1], "dtype": "uint8", "scale": 1.0, "zero_point": 0},
                   "output": {"shape": [1,2], "dtype": "int8", "scale": 1/256, "zero_point": -128}}
        before = create(current, metrics, model)
        atomic(model.parent / "model_contract.json", before)
        self.labels.change("rename", current["classes"][0]["stable_id"], name="Updated visible label")
        after = read(model.parent / "model_contract.json")
        changed = self.projects.open("fixture")
        self.assertEqual(before["model_sha256"], after["model_sha256"])
        self.assertEqual(before["project_semantics"], after["project_semantics"])
        self.assertNotEqual(before["contract_sha256"], after["contract_sha256"])
        self.assertIn("Updated visible label", generate_header(after))
        validate(after, manifest=changed, model_path=model)
        self.assertEqual(sum(r["class_id"] is None for r in self.labels.rows()), 4)
        self.assert_originals()


if __name__ == "__main__":
    unittest.main()
