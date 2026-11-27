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
from pathlib import Path

POINTER_FILE = "live.json"
RELEASE_FILE = "release.json"
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
    )


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


def model_env(base: Mapping[str, str], release: Release) -> dict[str, str]:
    """`base` with every model setting taken out, then the release's own, then its id as the model version."""
    env = {k: v for k, v in base.items() if not is_model_key(k)}
    env.update(release.env)
    env["MILK_MODEL_VERSION"] = release.id
    return env
