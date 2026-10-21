"""Project wizard and unattended interface use the same ProjectService."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from project_context import ProjectService, resolve_context


class ProjectWizard:
    def __init__(self, service, root):
        import tkinter as tk
        from tkinter import ttk
        self.service, self.root = service, root
        root.title("N6 Training — Project / פרויקט")
        root.geometry("670x460")
        self.slug = tk.StringVar()
        self.name = tk.StringVar()
        self.source = tk.StringVar()
        self.result = tk.StringVar(value="Create, select or import a project. Next: 01_CAPTURE.bat")
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="N6 — בחירת פרויקט", font=("Segoe UI", 17)).pack(anchor="w")
        self.current = ttk.Label(frame)
        self.current.pack(anchor="w", pady=10)
        ttk.Label(frame, text="Saved project / פרויקט קיים").pack(anchor="w")
        self.selector = ttk.Combobox(frame, textvariable=self.source, state="readonly")
        self.selector.pack(fill="x")
        ttk.Label(frame, text="New project ID (a-z, 0-9, - or _)").pack(anchor="w", pady=(12, 0))
        ttk.Entry(frame, textvariable=self.slug).pack(fill="x")
        ttk.Label(frame, text="Display name / שם לתצוגה").pack(anchor="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.name).pack(fill="x")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=16)
        self.buttons = {}
        for action, text in (("create", "Create / יצירה"), ("select", "Open / פתיחה"),
                             ("duplicate", "Duplicate / שכפול"), ("edit", "Rename / שינוי שם"),
                             ("import-rps", "Import existing RPS")):
            button = ttk.Button(buttons, text=text, command=lambda a=action: self.perform(a))
            button.pack(side="left", padx=2)
            self.buttons[action] = button
        ttk.Label(frame, textvariable=self.result, wraplength=620).pack(anchor="w")
        ttk.Button(frame, text="Close / סגירה", command=root.destroy).pack(anchor="e", pady=10)
        self.events = []
        self.refresh()

    def refresh(self):
        self.selector["values"] = [p["slug"] for p in self.service.list_projects()]
        _, _, active = resolve_context(self.service.training)
        self.current["text"] = (f"Active: {active['name']} [{active['slug']}]" if active
                                else "Active: legacy RPS (original files preserved)")

    def perform(self, action):
        try:
            value = execute(self.service, action, self.slug.get(), self.name.get(), self.source.get())
            self.source.set(value["slug"])
            self.events.append({"action": action, "project_id": value["project_id"], "result": "PASS"})
            self.result.set(f"PASS — {value['name']} [{value['slug']}]. Next: 01_CAPTURE.bat")
            self.refresh()
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            self.events.append({"action": action, "result": "FAIL", "reason": str(exc)})
            self.result.set(f"BLOCKED: {exc}")


def execute(service, action, slug=None, name=None, source=None):
    if action == "create":
        return service.create(slug, name or "")
    if action == "select":
        return service.select(source or slug)
    if action == "duplicate":
        return service.duplicate(source, slug, name or "")
    if action == "edit":
        return service.edit(source or slug, name=name)
    if action == "import-rps":
        return service.import_rps()
    raise ValueError("An explicit project action is required.")


def main():
    # BAT uses UTF-8; redirected Windows Python output otherwise uses the
    # machine ANSI code page and can fail after a successful transaction.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--training-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--action", choices=("create", "select", "duplicate", "edit", "import-rps", "list"))
    parser.add_argument("--id")
    parser.add_argument("--name")
    parser.add_argument("--source")
    parser.add_argument("--ui-smoke", action="store_true", help="Test actual Tk buttons against a temporary fixture only")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    service = ProjectService(args.training_root)
    try:
        service.recover()
        if args.ui_smoke:
            # Prevent test automation from creating demo projects in real data.
            import tempfile
            if Path(tempfile.gettempdir()).resolve() not in service.training.parents:
                raise ValueError("UI smoke requires --training-root under the OS temporary directory.")
        if args.non_interactive:
            if not args.action:
                print("BLOCKED: --non-interactive requires --action.")
                return 2
            value = (service.list_projects() if args.action == "list" else
                     execute(service, args.action, args.id, args.name, args.source))
            print(json.dumps({"result": "PASS", "action": args.action, "project": value}, ensure_ascii=False))
            return 0
        import tkinter as tk
        root = tk.Tk()
        wizard = ProjectWizard(service, root)
        if args.ui_smoke:
            def exercise():
                wizard.slug.set("ui-project-a")
                wizard.name.set("UI Project A")
                wizard.buttons["create"].invoke()
                root.update_idletasks()
                wizard.slug.set("ui-project-b")
                wizard.name.set("UI Project B")
                wizard.buttons["create"].invoke()
                root.update_idletasks()
                wizard.source.set("ui-project-a")
                wizard.buttons["select"].invoke()
                root.update_idletasks()
                root.after(100, root.destroy)
            root.after(300, exercise)
        root.mainloop()
        if args.ui_smoke:
            _, _, active = resolve_context(service.training)
            passed = (len(wizard.events) == 3 and all(e["result"] == "PASS" for e in wizard.events)
                      and active["slug"] == "ui-project-a")
            report = {"schema": 1, "result": "PASS" if passed else "FAIL",
                "verification": "Real Tk window and button invocation through BAT; no native mouse/keyboard or visual assertion.",
                "events": wizard.events, "active_project": active["slug"]}
            if args.report:
                from project_context import atomic
                atomic(args.report, report)
            print(json.dumps(report))
            return 0 if passed else 1
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
