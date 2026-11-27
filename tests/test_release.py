import json

import pytest

from milk import release


def write_release(root, release_id, env, kind="rules", criteria=None, parent=None, file_id=None):
    """A release folder as ops.make_release writes it."""
    folder = root / release_id
    folder.mkdir(parents=True)
    body = {"id": file_id or release_id, "parent": parent, "kind": kind, "env": env}
    if criteria is not None:
        body["criteria"] = criteria
    (folder / "release.json").write_text(json.dumps(body), encoding="utf-8")


def test_model_env_replaces_every_model_key(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_PIPELINE": "long", "MILK_LONG_TILE": "1280"})
    base = {"MILK_HUB_URL": "https://hub", "MILK_PIPELINE": "long+slide", "MILK_SLIDE_WEIGHTS": "old.pt"}
    env = release.model_env(base, release.load_release(tmp_path, "v2"))
    assert env == {
        "MILK_HUB_URL": "https://hub",
        "MILK_PIPELINE": "long",
        "MILK_LONG_TILE": "1280",
        "MILK_MODEL_VERSION": "v2",
    }


def test_model_env_drops_a_version_set_by_hand(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_PIPELINE": "null"})
    env = release.model_env({"MILK_MODEL_VERSION": "by-hand"}, release.load_release(tmp_path, "v2"))
    assert env["MILK_MODEL_VERSION"] == "v2"


def test_release_with_a_foreign_key_is_refused(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_HUB_URL": "https://elsewhere"})
    with pytest.raises(ValueError, match="MILK_HUB_URL"):
        release.load_release(tmp_path, "v2")


def test_release_may_not_set_the_version_itself(tmp_path):
    write_release(tmp_path, "v2", env={"MILK_MODEL_VERSION": "other"})
    with pytest.raises(ValueError, match="MILK_MODEL_VERSION"):
        release.load_release(tmp_path, "v2")


def test_missing_release_names_its_folder(tmp_path):
    with pytest.raises(ValueError, match="gone"):
        release.load_release(tmp_path, "gone")


def test_release_whose_id_differs_from_its_folder_is_refused(tmp_path):
    write_release(tmp_path, "v2", env={}, file_id="v3")
    with pytest.raises(ValueError, match="v3"):
        release.load_release(tmp_path, "v2")


def test_broken_release_file_names_the_file(tmp_path):
    (tmp_path / "v2").mkdir()
    (tmp_path / "v2" / "release.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="release.json"):
        release.load_release(tmp_path, "v2")


def test_pointer_round_trip_leaves_no_partial_file(tmp_path):
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate="v2"))
    assert release.read_pointer(tmp_path) == release.Pointer(live="v1", previous=None, candidate="v2")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["live.json"]


def test_pointer_is_replaced_whole(tmp_path):
    release.write_pointer(tmp_path, release.Pointer(live="v1", previous=None, candidate=None))
    release.write_pointer(tmp_path, release.Pointer(live="v2", previous="v1", candidate=None))
    assert json.loads((tmp_path / "live.json").read_text(encoding="utf-8")) == {
        "live": "v2",
        "previous": "v1",
        "candidate": None,
    }


def test_broken_pointer_names_the_file(tmp_path):
    (tmp_path / "live.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="live.json"):
        release.read_pointer(tmp_path)


def test_pointer_without_a_live_release_is_refused(tmp_path):
    (tmp_path / "live.json").write_text('{"previous": "v1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="live.json"):
        release.read_pointer(tmp_path)


def test_missing_pointer_names_the_file(tmp_path):
    with pytest.raises(ValueError, match="live.json"):
        release.read_pointer(tmp_path)


def test_criteria_default_by_kind_and_partial_override(tmp_path):
    write_release(tmp_path, "g1", kind="gallery", env={})
    write_release(tmp_path, "d1", kind="rules", env={}, criteria={"min_days": 1, "min_frames": 5})
    assert release.load_release(tmp_path, "g1").criteria["min_diff_boxes"] == 30
    assert release.load_release(tmp_path, "d1").criteria == {
        "min_days": 1,
        "min_frames": 5,
        "min_diff_boxes": 0,
        "alpha": 0.05,
        "max_sku_drop": 0.05,
    }


def test_unknown_kind_is_refused(tmp_path):
    write_release(tmp_path, "x1", kind="magic", env={})
    with pytest.raises(ValueError, match="magic"):
        release.load_release(tmp_path, "x1")


def test_a_release_keeps_the_moment_it_was_made(tmp_path):
    write_release(tmp_path, "v2", env={})
    assert release.load_release(tmp_path, "v2").created_at is None
    body = json.loads((tmp_path / "v2" / "release.json").read_text(encoding="utf-8"))
    body["created_at"] = "2026-11-27T15:00:00+07:00"
    (tmp_path / "v2" / "release.json").write_text(json.dumps(body), encoding="utf-8")
    assert release.load_release(tmp_path, "v2").created_at == "2026-11-27T15:00:00+07:00"


def test_the_worker_says_what_it_started_with(tmp_path):
    assert release.read_worker_status(tmp_path) is None
    release.write_worker_status(tmp_path, live="v1", candidate="v2")
    status = release.read_worker_status(tmp_path)
    assert (status["live"], status["candidate"]) == ("v1", "v2")
    assert status["started_at"].endswith("+00:00")
    release.write_worker_status(tmp_path, live="v2", candidate=None)
    assert release.read_worker_status(tmp_path)["candidate"] is None


def test_a_start_record_that_cannot_be_read_counts_as_none(tmp_path):
    (tmp_path / release.WORKER_STATUS_FILE).write_text("{", encoding="utf-8")
    assert release.read_worker_status(tmp_path) is None


def test_release_folders_are_those_with_a_release_file(tmp_path):
    write_release(tmp_path, "v2", env={})
    write_release(tmp_path, "v1", env={})
    (tmp_path / "notes").mkdir()
    (tmp_path / "live.json").write_text("{}", encoding="utf-8")
    assert release.release_ids(tmp_path) == ["v1", "v2"]
