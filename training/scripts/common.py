"""Shared, side-effect-free helpers for the resumable training stages."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

TRAINING_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TRAINING_ROOT.parent
CONFIG_ROOT = TRAINING_ROOT / "config"
DATA_ROOT = TRAINING_ROOT / "data"
RAW_ROOT = DATA_ROOT / "raw"
PREPARED_ROOT = DATA_ROOT / "prepared"
MODELS_ROOT = TRAINING_ROOT / "models"
GENERATED_ROOT = TRAINING_ROOT / "generated"
REPORTS_ROOT = TRAINING_ROOT / "reports"
STATE_ROOT = TRAINING_ROOT / "state"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_layout() -> None:
    for path in (RAW_ROOT, PREPARED_ROOT, MODELS_ROOT, GENERATED_ROOT,
                 REPORTS_ROOT, STATE_ROOT):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False,
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    ) as handle:
        handle.write(encoded)
        handle.write("\n")
        temporary = Path(handle.name)
    # Dropbox/antivirus may briefly open the destination between close and
    # replace on Windows. Preserve the atomic same-directory replacement, but
    # tolerate that transient sharing violation instead of losing an epoch.
    last_error: PermissionError | None = None
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 39:
                time.sleep(min(0.05 * (attempt + 1), 0.25))
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass
    assert last_error is not None
    raise last_error


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid JSONL at {path}:{line_number}: {exc}"
                    ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_fingerprint(paths: Iterable[Path]) -> str:
    records = []
    for path in sorted((Path(p) for p in paths), key=lambda item: str(item)):
        if path.exists() and path.is_file():
            stat = path.stat()
            records.append((str(path.resolve()), stat.st_size,
                            stat.st_mtime_ns, sha256_file(path)))
        else:
            records.append((str(path.resolve()), None, None, None))
    return stable_hash(records)


def stage_state(stage: str) -> dict[str, Any]:
    path = STATE_ROOT / f"{stage}.json"
    return load_json(path) if path.exists() else {}


def mark_stage(stage: str, *, status: str, inputs: str = "",
               outputs: list[str] | None = None,
               details: dict[str, Any] | None = None) -> None:
    atomic_json(STATE_ROOT / f"{stage}.json", {
        "stage": stage,
        "status": status,
        "updated_utc": utc_now(),
        "input_fingerprint": inputs,
        "outputs": outputs or [],
        "details": details or {},
    })


def is_stage_current(stage: str, fingerprint: str,
                     outputs: Iterable[Path]) -> bool:
    state = stage_state(stage)
    return (state.get("status") == "complete" and
            state.get("input_fingerprint") == fingerprint and
            all(path.exists() for path in outputs))


def class_config() -> list[dict[str, Any]]:
    return load_json(CONFIG_ROOT / "classes.json")["classes"]


def class_names() -> list[str]:
    return [entry["name"] for entry in class_config()]


def run(command: list[str], *, cwd: Path | None = None,
        env: dict[str, str] | None = None) -> None:
    printable = subprocess.list2cmdline(command)
    print(f"\n> {printable}", flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {printable}"
        )


def find_executable(name: str, env_var: str | None = None) -> Path | None:
    if env_var and os.environ.get(env_var):
        candidate = Path(os.environ[env_var]).expanduser()
        if candidate.is_dir():
            direct = candidate / name
            if direct.is_file():
                return direct.resolve()
            nested = sorted(candidate.glob(f"*/Utilities/windows/{name}"),
                            reverse=True)
            if nested:
                return nested[0].resolve()
        if candidate.is_file():
            return candidate.resolve()
    resolved = shutil.which(name)
    if resolved:
        return Path(resolved).resolve()
    if platform.system() == "Windows" and name.lower() == "stedgeai.exe":
        # The standalone Windows installer uses this versioned layout but does
        # not add the CLI to PATH. Prefer the newest installed directory.
        install_root = Path("C:/ST/STEdgeAI")
        installed = sorted(install_root.glob(f"*/Utilities/windows/{name}"),
                           reverse=True)
        if installed:
            return installed[0].resolve()
    return None


def environment_report() -> dict[str, Any]:
    modules = {}
    for module_name in ("numpy", "PIL", "serial", "yaml", "tensorflow"):
        try:
            module = __import__(module_name)
            modules[module_name] = getattr(module, "__version__", "installed")
        except Exception as exc:  # diagnostics must survive partial installs
            modules[module_name] = f"missing: {type(exc).__name__}"
    tools = load_json(CONFIG_ROOT / "tools.json")
    edge = find_executable(tools["stedgeai_executable"],
                           tools["stedgeai_env"])
    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "modules": modules,
        "stedgeai": str(edge) if edge else None,
    }


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(TRAINING_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def npu_deployment_fingerprint() -> str:
    """Hash the model/runtime contract that a frame-level HIL run proves."""
    integration = stage_state("08_integrate")
    if (integration.get("status") != "complete"):
        raise RuntimeError("Stage 08 firmware integration is not complete.")
    paths = (
        MODELS_ROOT / "rps_int8.tflite",
        MODELS_ROOT / "model_contract.json",
        PROJECT_ROOT / "AppliNonSecure" / "AI" / "Model" / "rps_tof.c",
        PROJECT_ROOT / "AppliNonSecure" / "AI" / "Model" / "stai_rps_tof.c",
        PROJECT_ROOT / "AppliNonSecure" / "AI" / "Model" / "rps_model_weights.c",
        PROJECT_ROOT / "AppliNonSecure" / "Core" / "Src" / "rps_ai.c",
        PROJECT_ROOT / "AppliNonSecure" / "Core" / "Src" / "tof_app.c",
        PROJECT_ROOT / "AppliNonSecure" / "Core" / "Src" / "npu_shared_memory.c",
        PROJECT_ROOT / "AppliNonSecure" / "Core" / "Inc" / "app_features.h",
        PROJECT_ROOT / "AppliNonSecure" / ".cproject",
        PROJECT_ROOT / "AppliNonSecure" / "STM32N657X0HXQ_LRUN.ld",
        PROJECT_ROOT / "AppliSecure" / "Core" / "Src" / "main.c",
    )
    missing = [relative(path) for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "The integrated NPU deployment is incomplete; missing: "
            + ", ".join(missing)
        )
    return stable_hash({
        "stage08_inputs": integration.get("input_fingerprint"),
        "files": {relative(path): sha256_file(path) for path in paths},
    })


ensure_layout()
