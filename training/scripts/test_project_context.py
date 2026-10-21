"""M1 service checks: isolation, legacy preservation and interrupted commits."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from project_context import (ProjectService, atomic, config_directory,
                             derived_config, read, resolve_context, semantic_hash, replace)


SOURCE = Path(__file__).resolve().parents[1] / "config"


def fixture(path):
    path = Path(path)
    shutil.copytree(SOURCE, path / "config")
    (path / "data/raw/session").mkdir(parents=True)
    (path / "data/raw/session/original.npz").write_bytes(b"immutable sensor fixture\x00\xff")
    (path / "models").mkdir()
    (path / "models/rps_int8.tflite").write_bytes(b"existing model fixture")
    atomic(path / "state/11_hil.json", {"status": "complete", "input_fingerprint": "old"})
    return path


class Projects(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = fixture(Path(self.temp.name) / "training")
        self.service = ProjectService(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_reopen_switch_and_isolation(self):
        a = self.service.create("alpha", "Alpha")
        b = self.service.create("beta", "Beta")
        self.assertNotEqual(a["project_id"], b["project_id"])
        reopened = ProjectService(self.root)
        self.assertEqual(reopened.open("alpha"), a)
        self.assertEqual(len(reopened.list_projects()), 2)
        reopened.select("alpha")
        active_root, cfg, selected = resolve_context(self.root)
        self.assertEqual(selected["project_id"], a["project_id"])
        self.assertEqual(read(cfg / "classes.json"), derived_config(a)["classes.json"])
        (active_root / "data/raw/alpha-only").write_bytes(b"alpha")
        reopened.select("beta")
        beta_root, _, _ = resolve_context(self.root)
        self.assertFalse((beta_root / "data/raw/alpha-only").exists())
        self.assertFalse((beta_root / "models/rps_int8.tflite").exists())

    def test_import_keeps_every_original_and_stales_old_acceptance(self):
        original = self.root / "data/raw/session/original.npz"
        before = original.read_bytes()
        value = self.service.import_rps()
        root, _, active = resolve_context(self.root)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual((root / "data/raw/session/original.npz").read_bytes(), before)
        self.assertEqual((root / "models/rps_int8.tflite").read_bytes(), b"existing model fixture")
        self.assertEqual(read(root / "state/11_hil.json")["status"], "stale")
        self.assertTrue(read(root / "import_manifest.json")["source_preserved"])
        self.assertEqual(value, active)

    def test_duplicate_has_new_identity_but_unchanged_sensor_bytes(self):
        source = self.service.import_rps()
        copied = self.service.duplicate("rps", "copy", "Copy")
        self.assertNotEqual(copied["project_id"], source["project_id"])
        for part in ("data", "review", "models", "generated", "reports", "state", "config"):
            self.assertTrue((self.root / "projects/copy" / part).is_dir())
        self.assertEqual((self.root / "projects/copy/data/raw/session/original.npz").read_bytes(),
                         (self.root / "data/raw/session/original.npz").read_bytes())

    def test_display_edit_preserves_semantics_config_and_backup(self):
        old = self.service.create("alpha", "Old")
        old_config = config_directory(old)
        new = self.service.edit("alpha", name="New name")
        self.assertEqual(semantic_hash(old), semantic_hash(new))
        self.assertEqual(config_directory(new), old_config)
        self.assertEqual(new["invalidation"], {"semantic_change": False, "display_metadata_changed": True})
        backups = list(self.service.root.glob(".transactions/*/backup.json"))
        self.assertEqual(read(backups[0]), old)
        self.assertEqual(self.service.open("alpha")["name"], "New name")

    def test_interrupted_publish_is_recoverable(self):
        # Stop after durable preparation, before publication/selection.
        with patch.object(self.service, "_recover", side_effect=[None, RuntimeError("interrupted")]):
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                self.service.create("alpha", "Alpha")
        self.assertFalse((self.service.root / "alpha").exists())
        reopened = ProjectService(self.root)
        reopened.recover()
        self.assertEqual(resolve_context(self.root)[2]["slug"], "alpha")
        self.assertEqual(reopened.open("alpha")["revision"], 1)

    def test_interrupted_edit_finishes_from_journal(self):
        self.service.create("alpha", "Old")
        with patch.object(self.service, "_write_config", side_effect=OSError("interrupted")):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.service.edit("alpha", name="New")
        self.assertEqual(self.service.open("alpha")["name"], "Old")
        reopened = ProjectService(self.root)
        reopened.recover()
        self.assertEqual(reopened.open("alpha")["name"], "New")

    def test_invalid_identity_and_derived_tampering_reject(self):
        for slug in ("../other", "..", "a/b", "con", "", "A"):
            with self.assertRaises(ValueError):
                self.service.create(slug, "Bad")
        value = self.service.create("alpha", "Alpha")
        root, cfg, _ = resolve_context(self.root)
        atomic(cfg / "classes.json", {"classes": []})
        with self.assertRaisesRegex(ValueError, "Derived"):
            self.service.open("alpha")

    def test_transient_windows_sharing_violation_retries_same_commit(self):
        import os
        real_replace = os.replace
        attempts = []
        def sharing_violation(source, target):
            attempts.append((source, target))
            if len(attempts) < 3:
                raise PermissionError("simulated Dropbox sharing violation")
            real_replace(source, target)
        source, target = self.root / "old", self.root / "new"
        source.mkdir()
        (source / "payload").write_bytes(b"same transaction")
        with patch("project_context.os.replace", side_effect=sharing_violation):
            replace(source, target)
        self.assertEqual(len(attempts), 3)
        self.assertEqual((target / "payload").read_bytes(), b"same transaction")


if __name__ == "__main__":
    unittest.main()
