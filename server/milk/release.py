"""Releases: everything the worker reads the shelf with, kept as one named set.

A release is a folder <MILK_RELEASES_DIR>/<id>/ with a release.json: the model settings (MILK_PIPELINE and the
MILK_LONG_* and MILK_SLIDE_* keys) and the criteria a parallel run of it is judged by. live.json beside the folders
says which release is live, which one was live before it (for a roll-back) and which one, if any, runs as the
candidate next to the live one. The release's id is the model_version written on every capture.

A release holds every model setting: a model key that it leaves out is unset, whatever worker.env says, so that the
same release reads the same way on any day. A live.json or a live release that cannot be read stops the worker; it
never falls back to older settings without saying so.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

POINTER_FILE = "live.json"
RELEASE_FILE = "release.json"
WORKER_STATUS_FILE = "worker-status.json"  # what the worker loaded at its last start, for the job runner
CANDIDATE_STATUS_FILE = "candidate-status.json"  # what the worker says about the candidate it runs
MODEL_KEYS = {"MILK_PIPELINE", "MILK_MODEL_VERSION"}
MODEL_PREFIXES = ("MILK_LONG_", "MILK_SLIDE_")

_DETECTOR = {"min_days": 3, "min_frames": 30, "min_diff_boxes": 0, "alpha": 0.05, "max_sku_drop": 0.05}
# What a parallel run must reach before a person may decide (operations-loop design 5.2), by kind of change
DEFAULT_CRITERIA: dict[str, dict] = {
    "baseline": _DETECTOR,
    "detector": _DETECTOR,
    "rules": _DETECTOR,
    "gallery": {**_DETECTOR, "min_days": 1, "min_frames": 0, "min_diff_boxes": 30},
}


@dataclass(frozen=True)
class Release:
    id: str
    parent: str | None
    kind: str
    env: dict[str, str]
    criteria: dict
    created_at: str | None = None


@dataclass(frozen=True)
class Pointer:
    live: str
    previous: str | None = None
    candidate: str | None = None


def is_model_key(key: str) -> bool:
    return key in MODEL_KEYS or key.startswith(MODEL_PREFIXES)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold an object")
    return data


def load_release(root: Path, release_id: str) -> Release:
    path = Path(root) / release_id / RELEASE_FILE
    data = _read_json(path)
    if data.get("id") != release_id:
        raise ValueError(f"{path}: its id {data.get('id')!r} is not its folder {release_id!r}")
    kind = data.get("kind")
    if kind not in DEFAULT_CRITERIA:
        raise ValueError(f"{path}: kind {kind!r} is not one of {sorted(DEFAULT_CRITERIA)}")
    env = data.get("env")
    if not isinstance(env, dict):
        raise ValueError(f"{path}: env must be an object of model settings")
    foreign = sorted(k for k in env if k == "MILK_MODEL_VERSION" or not is_model_key(k))
    if foreign:
        raise ValueError(f"{path}: a release may only set MILK_PIPELINE, MILK_LONG_* and MILK_SLIDE_*, not {foreign}")
    return Release(
        id=release_id,
        parent=data.get("parent") or None,
        kind=kind,
        env={k: str(v) for k, v in env.items()},
        criteria={**DEFAULT_CRITERIA[kind], **(data.get("criteria") or {})},
        created_at=data.get("created_at") or None,
    )


def release_ids(root: Path) -> list[str]:
    """The releases on disk: every folder under `root` that holds a release.json, by name."""
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if (p / RELEASE_FILE).is_file())


def read_pointer(root: Path) -> Pointer:
    path = Path(root) / POINTER_FILE
    data = _read_json(path)
    if not data.get("live"):
        raise ValueError(f"{path} names no live release")
    return Pointer(live=data["live"], previous=data.get("previous") or None, candidate=data.get("candidate") or None)


def write_pointer(root: Path, pointer: Pointer) -> None:
    """Replaces live.json in one step, so a reader never finds half a file."""
    path = Path(root) / POINTER_FILE
    tmp = path.with_name(POINTER_FILE + ".tmp")
    tmp.write_text(json.dumps(asdict(pointer)), encoding="utf-8")
    os.replace(tmp, path)


def write_worker_status(root: Path, live: str, candidate: str | None) -> None:
    """The worker's start record: which release it has loaded, which candidate beside it, and when (UTC). It is
    written once the models are loaded, so the job runner can tell that a switch it asked for has happened."""
    record = {"live": live, "candidate": candidate, "started_at": datetime.now(UTC).isoformat(timespec="seconds")}
    path = Path(root) / WORKER_STATUS_FILE
    tmp = path.with_name(WORKER_STATUS_FILE + ".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, path)


def read_worker_status(root: Path) -> dict | None:
    """The worker's start record, or None when there is none or it cannot be read."""
    try:
        return _read_json(Path(root) / WORKER_STATUS_FILE)
    except ValueError:
        return None


def model_env(base: Mapping[str, str], release: Release) -> dict[str, str]:
    """`base` with every model setting taken out, then the release's own, then its id as the model version."""
    env = {k: v for k, v in base.items() if not is_model_key(k)}
    env.update(release.env)
    env["MILK_MODEL_VERSION"] = release.id
    return env
