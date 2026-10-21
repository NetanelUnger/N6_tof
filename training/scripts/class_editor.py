"""Small shared Tk editor for stable classes and reversible sample labels."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from label_service import LabelService


class ClassEditor:
    def __init__(self, projects, slug, window):
        self.projects, self.slug, self.window = projects, slug, window
        self.labels = LabelService(projects, slug)
        window.title("N6 — Classes and labels / מחלקות ותוויות")
        window.geometry("960x620")
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.names = tk.StringVar()
        self.status = tk.StringVar(value="Select a class and action. Sensor files remain immutable.")
        self.profile = tk.StringVar(value=projects.open(slug)["input_profile"])
        frame = ttk.Frame(window, padding=15)
        frame.pack(fill="both", expand=True)
        self.summary = ttk.Label(frame, font=("Segoe UI", 13))
        self.summary.pack(anchor="w", pady=8)
        profiles = ttk.Frame(frame)
        profiles.pack(fill="x", pady=5)
        ttk.Combobox(profiles, textvariable=self.profile, state="readonly",
            values=["rps_silhouette_v1", "spatial_depth_v1"], width=30).pack(side="left")
        ttk.Button(profiles, text="Apply input profile", command=self.set_profile).pack(side="left", padx=8)
        columns = ttk.Frame(frame)
        columns.pack(fill="x")
        ttk.Label(columns, text="Source class / מחלקה").grid(row=0, column=0, sticky="w")
        ttk.Label(columns, text="Destination / יעד").grid(row=0, column=1, sticky="w", padx=10)
        self.source_box = ttk.Combobox(columns, textvariable=self.source, state="readonly", width=42)
        self.source_box.grid(row=1, column=0, sticky="ew")
        self.target_box = ttk.Combobox(columns, textvariable=self.target, state="readonly", width=42)
        self.target_box.grid(row=1, column=1, sticky="ew", padx=10)
        ttk.Label(frame, text="Display name; for split, separate two or more names with | ").pack(anchor="w", pady=(12, 0))
        ttk.Entry(frame, textvariable=self.names).pack(fill="x")
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=12)
        self.buttons = {}
        for action, text in (("rename", "Rename"), ("add", "Add"), ("merge", "Merge → destination"),
                             ("delete", "Retire → destination / unlabeled"), ("split", "Split → pending review")):
            button = ttk.Button(bar, text=text, command=lambda a=action: self.change(a))
            button.pack(side="left", padx=3)
            self.buttons[action] = button
        ttk.Label(frame, text="Samples / דגימות — select one or more, then assign a destination").pack(anchor="w")
        self.samples = tk.Listbox(frame, selectmode="extended", exportselection=False, height=15)
        self.samples.pack(fill="both", expand=True, pady=6)
        self.samples.bind("<<ListboxSelect>>", self.preview)
        self.preview_label = ttk.Label(frame)
        self.preview_label.pack(anchor="w")
        tools = ttk.Frame(frame)
        tools.pack(fill="x")
        for action, text in (("label", "Assign label and accept"), ("reject", "Reject selected"),
                             ("unlabel", "Leave unlabeled")):
            button = ttk.Button(tools, text=text, command=lambda a=action: self.review(a))
            button.pack(side="left", padx=3)
            self.buttons[action] = button
        ttk.Label(frame, textvariable=self.status, wraplength=900).pack(anchor="w", pady=10)
        ttk.Button(frame, text="Close / סגירה", command=window.destroy).pack(anchor="e")
        self.events = []
        self.refresh()

    def set_profile(self):
        try:
            self.projects.set_profile(self.slug, self.profile.get())
            self.status.set("PASS — input profile changed; existing model artifacts are stale. Next: 03_VALIDATE.bat")
            self.refresh()
        except (OSError, ValueError, RuntimeError) as exc:
            self.status.set(f"BLOCKED: {exc}")

    def refresh(self):
        manifest = self.projects.open(self.slug)
        self.mapping = {c.get('display_name', c['name']): c["stable_id"]
                        for c in manifest["classes"]}
        self.source_box["values"] = list(self.mapping)
        self.target_box["values"] = ["UNLABELED / ללא תווית", *self.mapping]
        self.rows = self.labels.rows()
        names = {c["stable_id"]: c.get("display_name", c["name"]) for c in manifest["classes"]}
        self.samples.delete(0, "end")
        for row in self.rows:
            label = names.get(row["class_id"], "UNLABELED / pending review")
            state = "accepted" if row.get("accepted", True) else "REJECTED"
            self.samples.insert("end", f"{label} | {state} | {row['npz']} | {row['sample_id'][:10]}")
        pending = sum(r["class_id"] is None for r in self.rows)
        self.summary["text"] = f"{manifest['name']} [{self.slug}] — {len(manifest['classes'])} classes, {len(self.rows)} samples, {pending} pending"

    def change(self, action):
        try:
            if action in {"merge", "delete"} and not self.target.get():
                raise ValueError("Choose a destination or explicitly choose UNLABELED.")
            source = self.mapping.get(self.source.get())
            target = self.mapping.get(self.target.get())
            result = self.labels.change(action, source, target=target, name=self.names.get(),
                                        names=[x.strip() for x in self.names.get().split("|")])
            self.events.append({"action": action, "result": "PASS", "affected_samples": result["affected_samples"]})
            self.status.set(f"PASS — {action}; {result['affected_samples']} samples. Original data preserved. Next: 03_VALIDATE.bat")
            self.refresh()
        except (OSError, ValueError, RuntimeError) as exc:
            self.events.append({"action": action, "result": "FAIL", "reason": str(exc)})
            self.status.set(f"BLOCKED: {exc}")

    def review(self, action):
        try:
            indices = list(self.samples.curselection())
            if not indices:
                raise ValueError("Select samples first.")
            identities = [self.rows[i]["sample_id"] for i in indices]
            destination = self.mapping.get(self.target.get())
            if action == "label":
                if destination is None:
                    raise ValueError("Choose an active destination class.")
                self.labels.label(identities, destination, accepted=True)
            elif action == "unlabel":
                self.labels.label(identities, None)
            else:
                # Preserve each sample's label while recording rejection.
                for i in indices:
                    self.labels.label([self.rows[i]["sample_id"]], self.rows[i]["class_id"], accepted=False)
            self.events.append({"action": action, "result": "PASS", "samples": len(identities)})
            self.status.set(f"PASS — {action}: {len(identities)} samples. Next: 03_VALIDATE.bat")
            self.refresh()
        except (OSError, ValueError, RuntimeError) as exc:
            self.events.append({"action": action, "result": "FAIL", "reason": str(exc)})
            self.status.set(f"BLOCKED: {exc}")

    def preview(self, _event=None):
        selected = self.samples.curselection()
        if not selected:
            return
        row = self.rows[selected[0]]
        try:
            from PIL import Image, ImageTk
            image = Image.open(self.labels.root / row["preview_png"])
            image.thumbnail((160, 100))
            self.photo = ImageTk.PhotoImage(image)
            self.preview_label.configure(image=self.photo, text="")
        except (OSError, KeyError):
            self.preview_label.configure(image="", text=f"Original record: {row['npz']}")
