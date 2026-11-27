"""ops.make_release: a release folder from the worker's env file, or from another release."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from milk import config, release
from ops import make_release

BASE = "long-store-v1-det+slide-v3"
ENV = (
    "# the worker's settings on the counting machine\n"
    "MILK_HUB_URL=https://hub.example\n"
    "MILK_PIPELINE=long+slide\n"
    "MILK_LONG_YOLO=C:/models/yolo/best_store_v1.pt\n"
    "MILK_LONG_TILE=1280\n"
    "MILK_SLIDE_WEIGHTS=C:/models/slide/best.pt\n"
    f"MILK_MODEL_VERSION={BASE}\n"
    "MILK_SAMPLE_EVERY_S=300\n"
)


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / "worker.env"
    path.write_text(ENV, encoding="utf-8")
    return path


@pytest.fixture
def root(tmp_path, env_file):
    releases = tmp_path / "releases"
    make_release.main(["--root", str(releases), "--id", BASE, "--kind", "baseline", "--from-env", str(env_file)])
    return releases


def test_the_first_release_holds_the_model_settings_of_the_env_file_and_becomes_live(root, env_file):
    made = release.load_release(root, BASE)
    assert made.env == {
        "MILK_PIPELINE": "long+slide",
        "MILK_LONG_YOLO": "C:/models/yolo/best_store_v1.pt",
        "MILK_LONG_TILE": "1280",
        "MILK_SLIDE_WEIGHTS": "C:/models/slide/best.pt",
    }
    assert (made.kind, made.parent) == ("baseline", None)
    assert datetime.fromisoformat(made.created_at).tzinfo is not None
    assert release.read_pointer(root) == release.Pointer(live=BASE)


def test_the_worker_reads_the_same_settings_through_the_release_as_from_the_env_file(root, env_file):
    from_file = config.read_env_file(str(env_file))
    assert release.model_env(from_file, release.load_release(root, BASE)) == from_file


def test_a_release_from_another_copies_it_and_changes_only_what_is_set(root):
    args = ["--root", str(root), "--id", "conf35", "--kind", "rules", "--from-release", BASE]
    make_release.main([*args, "--set", "MILK_SLIDE_CONF=0.35", "--criteria", '{"min_days": 1, "min_frames": 5}'])
    made = release.load_release(root, "conf35")
    assert made.env == {**release.load_release(root, BASE).env, "MILK_SLIDE_CONF": "0.35"}
    assert (made.kind, made.parent) == ("rules", BASE)
    assert (made.criteria["min_days"], made.criteria["min_frames"], made.criteria["alpha"]) == (1, 5, 0.05)
    assert release.read_pointer(root) == release.Pointer(live=BASE)  # making a release never changes what is live


def test_an_existing_release_is_never_overwritten(root, env_file):
    before = (root / BASE / "release.json").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        make_release.main(["--root", str(root), "--id", BASE, "--kind", "rules", "--from-env", str(env_file)])
    assert (root / BASE / "release.json").read_text(encoding="utf-8") == before


def test_a_setting_that_is_not_a_model_setting_is_refused_and_leaves_no_folder(root):
    args = ["--root", str(root), "--id", "bad", "--kind", "rules", "--from-release", BASE]
    with pytest.raises(SystemExit):
        make_release.main([*args, "--set", "MILK_HUB_URL=https://elsewhere"])
    assert not (root / "bad").exists()


def test_a_second_release_from_the_env_file_does_not_move_the_pointer(root, env_file):
    make_release.main(["--root", str(root), "--id", "again", "--kind", "rules", "--from-env", str(env_file)])
    assert release.read_pointer(root) == release.Pointer(live=BASE)


def test_the_file_written_is_what_load_release_reads(root):
    body = json.loads((root / BASE / "release.json").read_text(encoding="utf-8"))
    assert sorted(body) == ["created_at", "criteria", "env", "id", "kind", "parent"]
    assert body["criteria"] == release.DEFAULT_CRITERIA["baseline"]
