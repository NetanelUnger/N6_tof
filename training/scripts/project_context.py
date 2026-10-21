"""Versioned project service used by the wizard and every training stage.

Original legacy files are never moved. A project is published only after its
complete staging tree exists. Config revisions are immutable; a small atomic
manifest selects one revision. A durable journal finishes interrupted commits.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

SCHEMA = 1
FOLDERS = ("config", "data", "review", "models", "generated", "reports", "state")
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}\Z")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def replace(source, destination):
    # Dropbox/antivirus briefly holds newly-created files and directories.
    # Keep the durable journal; never delete/recreate the destination to retry.
    for attempt in range(40):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(min(0.05 * (attempt + 1), 0.25))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=".project-", delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    try:
        replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                          separators=(",", ":")).encode()).hexdigest()


def validate_slug(slug):
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("Project ID must use 1-48 lowercase letters, digits, - or _.")
    if slug.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(
            f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10))}:
        raise ValueError("Reserved Windows project ID.")
    return slug


def validate_manifest(value):
    if value.get("schema") != SCHEMA:
        raise ValueError("Unsupported project schema; open with a compatible platform.")
    validate_slug(value["slug"])
    uuid.UUID(value["project_id"])
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        raise ValueError("Project display name is required.")
    if not isinstance(value.get("revision"), int) or value["revision"] < 1:
        raise ValueError("Invalid project revision.")
    classes = value["classes"]
    if not 2 <= len(classes) <= 16:
        raise ValueError("Classification projects require 2-16 classes.")
    for field in ("stable_id", "name", "key"):
        values = [entry[field] for entry in classes]
        if len(values) != len(set(values)) or any(not str(x).strip() for x in values):
            raise ValueError(f"Classes require unique nonempty {field} values.")
    if [x["output_index"] for x in classes] != list(range(len(classes))):
        raise ValueError("Output mapping must be contiguous and explicit.")
    if value["input_profile"] not in {"rps_silhouette_v1", "spatial_depth_v1"}:
        raise ValueError("Unsupported input profile.")
    if value["input_shape"] != [50, 64, 1]:
        raise ValueError("Unsupported model input shape.")
    for field in ("preprocessing", "training", "tools", "capture", "acceptance"):
        if not isinstance(value.get(field), dict):
            raise ValueError(f"Missing project section: {field}")
    pre = value["preprocessing"]
    if not (0 < int(pre["near_mm"]) < int(pre["far_mm"]) < int(pre["invalid_mm"]) <= 65535):
        raise ValueError("Invalid preprocessing distance bounds.")
    if pre.get("profile", "rps_silhouette_v1") != value["input_profile"]:
        raise ValueError("Input profile/preprocessing mismatch.")
    return value


def semantic_hash(value):
    """Display-only changes never force preparation/training to run again."""
    return digest({k: value[k] for k in ("input_profile", "input_shape",
        "preprocessing", "training", "tools", "capture", "acceptance")} | {
        "classes": [{k: c[k] for k in ("stable_id", "name", "output_index")}
                    for c in value["classes"]],
        "labels": value.get("label_semantics", digest({"decisions": {}, "retired": {}}))})


def derived_config(value):
    validate_manifest(value)
    training = deepcopy(value["training"])
    training["capture"] = deepcopy(value["capture"])
    training["hil"] = deepcopy(value["acceptance"])
    return {
        "classes.json": {"classes": [{"id": c["output_index"],
            "stable_id": c["stable_id"], "name": c["name"],
            "hebrew": c.get("display_name", c["name"]), "key": c["key"]}
            for c in value["classes"]]},
        "preprocessing.json": value["preprocessing"],
        "training.json": training, "tools.json": value["tools"],
    }


def config_directory(value):
    return digest(derived_config(value))


class ProjectService:
    def __init__(self, training_root):
        self.training = Path(training_root).resolve()
        self.root = self.training / "projects"
        self.active = self.root / "active.json"

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        # The lock file remains; the OS lock, not existence, proves ownership.
        with (self.root / ".service.lock").open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) != b"1":
                stream.seek(0); stream.write(b"1"); stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise RuntimeError("BLOCKED: another project editor holds the lock.") from exc
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self._recover()
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _recover(self):
        for journal in sorted(self.root.glob(".transactions/*/journal.json")):
            state = read(journal)
            if state["status"] == "complete":
                continue
            slug = validate_slug(state["slug"])
            stage = journal.parent / "project"
            destination = self.root / slug
            if state["operation"] == "publish":
                if not destination.exists():
                    if not stage.is_dir():
                        raise RuntimeError(f"BLOCKED: incomplete project transaction {journal.parent.name}")
                    validate_manifest(read(stage / "project.json"))
                    replace(stage, destination)
                if read(destination / "project.json")["project_id"] != state["project_id"]:
                    raise RuntimeError("BLOCKED: transaction destination identity conflict.")
            elif state["operation"] == "edit":
                candidate = validate_manifest(read(journal.parent / "next.json"))
                current = read(destination / "project.json")
                if current["project_id"] != candidate["project_id"]:
                    raise RuntimeError("BLOCKED: edit transaction identity conflict.")
                self._write_config(destination, candidate)
                label_source = journal.parent / "labels.json"
                if label_source.exists():
                    labels = read(label_source)
                    if digest(labels) != candidate.get("label_revision"):
                        raise RuntimeError("BLOCKED: label transaction hash conflict.")
                    atomic(destination / "review/labels" / (candidate["label_revision"] + ".json"), labels)
                atomic(destination / "project.json", candidate)
                self._refresh_display_contract(destination, candidate)
            else:
                raise RuntimeError("BLOCKED: unknown recovery operation.")
            if state.get("select"):
                atomic(self.active, {"schema": SCHEMA, "slug": slug,
                                     "project_id": state["project_id"]})
            state.update(status="complete", completed_utc=now())
            atomic(journal, state)

    def recover(self):
        with self.locked():
            pass

    def _refresh_display_contract(self, destination, candidate):
        path = destination / "models/model_contract.json"
        if not path.exists():
            return
        previous = read(path)
        if (previous.get("schema") != 3 or previous.get("project_id") != candidate["project_id"] or
                previous.get("project_semantics") != semantic_hash(candidate)):
            return
        if previous.get("classes") == candidate["classes"]:
            return
        # Only matching semantic identity may reuse existing model bytes.
        # Stage 08 explicitly regenerates the firmware/display definitions.
        from model_contract import create
        model = destination / "models/rps_int8.tflite"
        if model.exists():
            atomic(path, create(candidate, previous, model))

    def _transaction(self):
        path = self.root / ".transactions" / uuid.uuid4().hex
        path.mkdir(parents=True)
        return path

    def _write_config(self, root, value):
        target = root / "config" / config_directory(value)
        for filename, payload in derived_config(value).items():
            path = target / filename
            if path.exists() and read(path) != payload:
                raise RuntimeError("BLOCKED: immutable config revision conflict.")
            if not path.exists():
                atomic(path, payload)

    def _default(self, slug, name):
        cfg = self.training / "config"
        training = read(cfg / "training.json")
        classes = read(cfg / "classes.json")["classes"]
        return {"schema": SCHEMA, "project_id": str(uuid.uuid4()), "slug": slug,
            "name": name.strip(), "revision": 1, "created_utc": now(),
            "input_profile": "rps_silhouette_v1", "input_shape": [50, 64, 1],
            "preprocessing": read(cfg / "preprocessing.json"),
            "model_template": training["model_architecture"],
            "training": training, "capture": training["capture"],
            "acceptance": training["hil"], "tools": read(cfg / "tools.json"),
            "classes": [{"stable_id": str(uuid.uuid4()), "output_index": i,
                "name": c["name"], "display_name": (c.get("hebrew", c["name"])
                    if "?" not in c.get("hebrew", "?") else
                    "NOTHING" if c["name"] == "none" else c["name"].upper()),
                "key": c["key"]} for i, c in enumerate(classes)]}

    def _publish(self, value, *, source=None, select=True, legacy=False):
        validate_manifest(value)
        slug = value["slug"]
        if (self.root / slug).exists():
            raise ValueError(f"Project already exists: {slug}")
        transaction = self._transaction()
        stage = transaction / "project"
        stage.mkdir()
        copied = {}
        for folder in FOLDERS:
            destination = stage / folder
            if source is not None and folder != "config" and (source / folder).is_dir():
                shutil.copytree(source / folder, destination)
                # Fail before publication if copied bytes differ. The legacy
                # source remains the recoverable backup, never moved/deleted.
                for path in sorted((source / folder).rglob("*")):
                    if path.is_file():
                        relative = path.relative_to(source)
                        expected = hashlib.sha256(path.read_bytes()).hexdigest()
                        actual = hashlib.sha256((stage / relative).read_bytes()).hexdigest()
                        if actual != expected:
                            raise RuntimeError(f"Copy verification failed: {relative}")
                        copied[str(relative)] = expected
            else:
                destination.mkdir()
        for folder in ("data/raw", "data/prepared"):
            (stage / folder).mkdir(parents=True, exist_ok=True)
        if source is not None:
            atomic(stage / "import_manifest.json", {"schema": SCHEMA,
                "source": str(source), "legacy_rps": legacy, "files": copied,
                "source_preserved": True, "created_utc": now()})
            # Preserve the original acceptance as history, but never transfer
            # deployment authority or absolute-path fingerprints to a project.
            for path in (stage / "state").glob("*.json"):
                previous = read(path)
                atomic(path, {**previous, "status": "stale",
                    "imported_status": previous.get("status"),
                    "reason": "Project copy requires revalidation of artifact association."})
        self._write_config(stage, value)
        atomic(stage / "project.json", value)
        atomic(transaction / "journal.json", {"schema": SCHEMA,
            "operation": "publish", "status": "prepared", "slug": slug,
            "project_id": value["project_id"], "select": select})
        self._recover()
        return value

    def create(self, slug, name, *, select=True):
        slug = validate_slug(slug)
        with self.locked():
            return self._publish(self._default(slug, name), select=select)

    def import_rps(self, *, select=True):
        with self.locked():
            return self._publish(self._default("rps", "Rock Paper Scissors"),
                                 source=self.training, select=select, legacy=True)

    def duplicate(self, source_slug, slug, name, *, select=True):
        slug = validate_slug(slug)
        with self.locked():
            source = self.open(source_slug)
            value = deepcopy(source)
            value.update(project_id=str(uuid.uuid4()), slug=slug, name=name.strip(),
                         revision=1, created_utc=now(), copied_from=source["project_id"])
            return self._publish(value, source=self.root / source_slug, select=select)

    def open(self, slug):
        slug = validate_slug(slug)
        root = self.root / slug
        if root.is_symlink() or root.resolve().parent != self.root.resolve():
            raise ValueError("Project path escapes the project root.")
        value = validate_manifest(read(root / "project.json"))
        if value["slug"] != slug:
            raise ValueError("Project directory/manifest mismatch.")
        for filename, expected in derived_config(value).items():
            actual = read(root / "config" / config_directory(value) / filename)
            if actual != expected:
                raise ValueError("Derived project configuration changed; recover through 00_PROJECT.")
        return value

    def list_projects(self):
        return [self.open(p.parent.name) for p in sorted(self.root.glob("*/project.json"))
                if not p.parent.name.startswith(".")]

    def select(self, slug):
        with self.locked():
            value = self.open(slug)
            atomic(self.active, {"schema": SCHEMA, "slug": value["slug"],
                                 "project_id": value["project_id"]})
        return value

    def edit(self, slug, *, name=None):
        with self.locked():
            value = self.open(slug)
            candidate = deepcopy(value)
            if name is not None:
                candidate["name"] = name.strip()
            candidate.update(revision=value["revision"] + 1, updated_utc=now())
            validate_manifest(candidate)
            candidate["invalidation"] = {"semantic_change": semantic_hash(value) != semantic_hash(candidate),
                "display_metadata_changed": value["name"] != candidate["name"]}
            transaction = self._transaction()
            atomic(transaction / "backup.json", value)
            atomic(transaction / "next.json", candidate)
            atomic(transaction / "journal.json", {"schema": SCHEMA,
                "operation": "edit", "status": "prepared", "slug": slug,
                "project_id": value["project_id"], "select": False})
            self._recover()
            return candidate

    def commit_revision(self, slug, candidate, *, labels=None):
        """Publish an already-reviewed config/label revision as one transaction.

        Callers do not hold the lock across UI interactions. Recheck the expected
        revision here so a stale editor cannot overwrite another editor's work.
        """
        with self.locked():
            current = self.open(slug)
            candidate = deepcopy(candidate)
            for key in ("schema", "project_id", "slug", "created_utc"):
                if candidate.get(key) != current.get(key):
                    raise ValueError("Project identity may not change during edit.")
            if candidate["revision"] != current["revision"]:
                raise RuntimeError("BLOCKED: project changed; reopen the editor.")
            candidate.update(revision=current["revision"] + 1, updated_utc=now())
            if labels is not None:
                candidate["label_revision"] = digest(labels)
                candidate["label_semantics"] = digest({
                    "decisions": {key: item["class_id"] for key, item in labels["decisions"].items()},
                    "retired": labels["retired"]})
            validate_manifest(candidate)
            candidate["invalidation"] = {
                "semantic_change": semantic_hash(current) != semantic_hash(candidate),
                "labels_changed": current.get("label_revision") != candidate.get("label_revision"),
                "display_metadata_changed": digest(derived_config(current)) != digest(derived_config(candidate))}
            transaction = self._transaction()
            atomic(transaction / "backup.json", current)
            atomic(transaction / "next.json", candidate)
            if labels is not None:
                atomic(transaction / "labels.json", labels)
            atomic(transaction / "journal.json", {"schema": SCHEMA, "operation": "edit",
                "status": "prepared", "slug": slug, "project_id": current["project_id"], "select": False})
            self._recover()
            return candidate

    def set_profile(self, slug, profile):
        candidate = deepcopy(self.open(slug))
        if profile not in {"rps_silhouette_v1", "spatial_depth_v1"}:
            raise ValueError("Unsupported input profile.")
        # Start from the frozen baseline, so switching back restores exactly
        # the production silhouette parameters rather than accumulating edits.
        pre = read(self.training / "config/preprocessing.json")
        pre["profile"] = profile
        candidate.update(input_profile=profile, preprocessing=pre)
        return self.commit_revision(slug, candidate)


def resolve_context(training_root, requested=None):
    service = ProjectService(training_root)
    if requested is None and service.active.exists():
        selection = read(service.active)
        if selection.get("schema") != SCHEMA:
            raise ValueError("Unsupported active-project selection.")
        requested = selection["slug"]
    if requested is None:
        return service.training, service.training / "config", None
    value = service.open(requested)
    if service.active.exists() and requested == read(service.active).get("slug"):
        if value["project_id"] != read(service.active).get("project_id"):
            raise ValueError("Active project identity mismatch.")
    root = service.root / requested
    return root, root / "config" / config_directory(value), value
