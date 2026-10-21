"""Stable class identities and reversible, sample-specific label provenance."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import uuid

from project_context import digest, now, read, validate_manifest


def sample_id(row):
    # Paths identify original sample records; content hashes alone conflate
    # two physically distinct frames whose depth pixels happen to be equal.
    path = str(row.get("npz", "")).replace("\\", "/")
    if not path or path.startswith("/") or ":" in path or ".." in Path(path).parts:
        raise ValueError("Sample needs a project-relative original NPZ path.")
    return digest({"original_record": path, "depth_sha256": row.get("depth_sha256")})


def load_labels(root, manifest):
    revision = manifest.get("label_revision")
    if revision is None:
        return {"schema": 1, "decisions": {}, "retired": {}, "history": []}
    if not re.fullmatch(r"[a-f0-9]{64}", revision):
        raise ValueError("Invalid label revision.")
    value = read(root / "review/labels" / (revision + ".json"))
    if digest(value) != revision or value.get("schema") != 1:
        raise ValueError("Label snapshot integrity failure.")
    return value


def class_registry(manifest):
    registry = {c["stable_id"]: c for c in manifest.get("class_history", [])}
    registry.update({c["stable_id"]: c for c in manifest["classes"]})
    return registry


def resolve_label(row, manifest, labels):
    registry = class_registry(manifest)
    source = next((c["stable_id"] for c in registry.values() if c["name"] == row.get("label")), None)
    decision = labels["decisions"].get(sample_id(row))
    if decision is not None:
        source = decision["class_id"]
    seen = set()
    while source in labels["retired"]:
        if source in seen:
            raise ValueError("Class mapping cycle.")
        seen.add(source)
        source = labels["retired"][source]
    active = {c["stable_id"]: c for c in manifest["classes"]}
    if source is not None and source not in active:
        raise ValueError("Sample references an unknown class identity.")
    output = dict(row)
    output["class_id"] = source
    output["sample_id"] = sample_id(row)
    output["label"] = active[source]["name"] if source else None
    if decision is not None and "accepted" in decision:
        output["accepted"] = decision["accepted"]
    output["label_provenance"] = decision or {"source": "original-or-legacy-review", "class_id": source}
    return output


class LabelService:
    def __init__(self, projects, slug):
        self.projects, self.slug = projects, slug
        self.root = projects.root / slug

    def rows(self, manifest=None, labels=None):
        manifest = manifest or self.projects.open(self.slug)
        labels = labels or load_labels(self.root, manifest)
        legacy_path = self.root / "review/dataset_review.json"
        legacy = read(legacy_path).get("decisions", {}) if legacy_path.exists() else {}
        rows = []
        for path in sorted((self.root / "data/raw").glob("*/metadata.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                decision = legacy.get(row.get("depth_sha256"))
                if decision:
                    row = {**row, "accepted": decision["accepted"],
                           "label": decision.get("label") or row.get("label")}
                rows.append(resolve_label(row, manifest, labels))
        return rows

    def change(self, action, source=None, *, target=None, name=None, names=None):
        manifest = self.projects.open(self.slug)
        candidate = deepcopy(manifest)
        labels = deepcopy(load_labels(self.root, manifest))
        classes = candidate["classes"]
        chosen = next((c for c in classes if c["stable_id"] == source), None)
        if action != "add" and chosen is None:
            raise ValueError("Select an existing stable class ID.")
        registry = class_registry(candidate)
        before_rows = self.rows(manifest, labels)
        affected = [r for r in before_rows if r["class_id"] == source] if source else []

        def add_class(display_name):
            display_name = str(display_name or "").strip()
            if (not display_name or len(display_name.encode("utf-8")) > 80 or
                    any(ord(c) < 32 or ord(c) == 127 for c in display_name)):
                raise ValueError("Class display name must contain 1-80 characters.")
            if any(c.get("display_name", c["name"]) == display_name for c in classes):
                raise ValueError("Class display name already exists.")
            # The internal label is immutable and portable; display names may
            # contain Hebrew and may be renamed without reindexing samples.
            stable = str(uuid.uuid4())
            label = "class_" + stable.replace("-", "")[:12]
            keys = {c["key"] for c in classes}
            key = next((k for k in "abcdefghijklmnopqrstuvwxyz0123456789" if k not in keys), None)
            value = {"stable_id": stable, "name": label, "display_name": display_name,
                     "key": key, "output_index": len(classes)}
            classes.append(value)
            registry[stable] = value
            return value

        target_id = None
        if action == "rename":
            display_name = str(name or "").strip()
            if (not display_name or len(display_name.encode("utf-8")) > 80 or
                    any(ord(c) < 32 or ord(c) == 127 for c in display_name)):
                raise ValueError("Class display name must contain 1-80 characters.")
            if any(c["stable_id"] != source and c.get("display_name", c["name"]) == display_name for c in classes):
                raise ValueError("Class display name already exists.")
            chosen["display_name"] = display_name
        elif action == "add":
            target_id = add_class(name)["stable_id"]
        elif action in {"merge", "delete", "split"}:
            if action == "merge" or target is not None:
                destination = next((c for c in classes if c["stable_id"] == target), None)
                if destination is None or target == source:
                    raise ValueError("Choose a different active destination class.")
                target_id = destination["stable_id"]
            labels["retired"][source] = target_id
            for row in affected:
                labels["decisions"][row["sample_id"]] = {"class_id": target_id,
                    "source": action, "pending_review": action == "split" or target_id is None,
                    "accepted": row.get("accepted", True),
                    "original_class_id": source, "updated_utc": now()}
            registry[source] = deepcopy(chosen)
            classes.remove(chosen)
            if action == "split":
                if not names or len(names) < 2:
                    raise ValueError("Split requires at least two new class names.")
                for display_name in names:
                    add_class(display_name)
        else:
            raise ValueError("Unsupported class action.")
        for index, entry in enumerate(classes):
            entry["output_index"] = index
        candidate["class_history"] = list(registry.values())
        candidate["capture"]["guided_order"] = [c["name"] for c in classes]
        # Renaming only changes display metadata, not labels or semantics.
        labels["history"].append({"action": action, "source_class_id": source,
            "target_class_id": target_id, "affected_samples": len(affected),
            "updated_utc": now(), "previous_label_revision": manifest.get("label_revision")})
        validate_manifest(candidate)
        candidate = self.projects.commit_revision(self.slug, candidate, labels=labels)
        return {"project": candidate, "affected_samples": len(affected),
                "samples": len(before_rows), "action": action}

    def label(self, selected_sample_ids, class_id, *, accepted=None):
        manifest = self.projects.open(self.slug)
        if class_id is not None and class_id not in {c["stable_id"] for c in manifest["classes"]}:
            raise ValueError("Unknown destination class.")
        labels = deepcopy(load_labels(self.root, manifest))
        known = {r["sample_id"]: r for r in self.rows(manifest, labels)}
        if not selected_sample_ids or not set(selected_sample_ids) <= known.keys():
            raise ValueError("Select existing sample IDs.")
        for identity in selected_sample_ids:
            previous = labels["decisions"].get(identity, {})
            labels["decisions"][identity] = {"class_id": class_id, "source": "human-review",
                "pending_review": class_id is None, "updated_utc": now(),
                "accepted": known[identity].get("accepted", True) if accepted is None else bool(accepted)}
        labels["history"].append({"action": "label", "sample_ids": sorted(selected_sample_ids),
                                  "target_class_id": class_id, "updated_utc": now()})
        return self.projects.commit_revision(self.slug, manifest, labels=labels)
