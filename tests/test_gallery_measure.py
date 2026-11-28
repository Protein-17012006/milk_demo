"""The measure that decides whether the gallery may rename Slide flavours: with and without it, on the live detector's
own judged boxes, each day read by a gallery that never saw it. Every expected value was worked out by hand."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from milk.gallery import Gallery, GalleryNamer
from training.store_view import gallery_measure as gm
from training.store_view.gallery_measure import GroupResult, ScoredBox, decide, measure, scored_boxes

E = np.eye(144)
PRODUCT = {"cheese145": "Slide Cheese 145g", "original145": "Slide Original 145g", "hot160": "Slide Hot 160g"}
SKUS = {"cheese145", "original145"}


def _feature(crop: np.ndarray) -> np.ndarray:
    """A stand-in for colour(): blue crops are e1, green e2, red e3."""
    b, g, r = crop.reshape(-1, 3).mean(axis=0)
    if b > 100 and g > 100:
        return (E[0] + E[1]) / np.sqrt(2)
    return E[0] if b > 200 else E[1] if g > 200 else E[2]


@pytest.fixture(autouse=True)
def stand_in_feature(monkeypatch):
    monkeypatch.setattr(gm, "GalleryNamer", functools.partial(GalleryNamer, feature=_feature))


def _gallery(names=("cheese145", "original145"), n=25) -> Gallery:
    vec = {"cheese145": E[0], "original145": E[1], "hot160": E[2]}
    labels = [name for name in names for _ in range(n)]
    feats = []
    for k, name in enumerate(names):
        for j in range(n):
            v = vec[name] + (j + 1) * 0.001 * E[10 + k]
            feats.append(v / np.linalg.norm(v))
    m = len(labels)
    return Gallery(
        np.stack(feats),
        np.array(labels),
        np.array([f"s{i}" for i in range(m)]),
        "t",
        None,
        np.array([f"o{i}" for i in range(m)]),
    )


def _image() -> np.ndarray:
    """Left half (x 0-39) blue, right half (x 40-79) green."""
    img = np.zeros((40, 80, 3), np.uint8)
    img[:, :40, 0] = 255
    img[:, 40:, 1] = 255
    return img


BLUE, GREEN = (0, 0, 40, 40), (40, 0, 40, 40)


def _box(cid, day, box, live, truth):
    return ScoredBox(cid, day, box, live, truth)


def _audit(audit_id="AUD-CAM-S01-A-20261127-10", status="done", boxes=(), verdicts=(), cid="CAP-S01-20261127-100000-1"):
    return {
        "audit_id": audit_id,
        "status": status,
        "capture_id": cid,
        "ai_boxes_json": json.dumps(list(boxes)),
        "verdicts_json": json.dumps(list(verdicts)),
    }


def test_scored_boxes_use_the_live_name_and_skip_boxes_only_the_candidate_drew():
    boxes = [
        {"box_id": 1, "sku_id": "cheese145", "box": [1, 2, 3, 4]},  # plain frame
        {
            "box_id": 2,
            "sku_id": "hot160",
            "src": "both",
            "live_sku": "original145",
            "cand_sku": "hot160",
            "box": [5, 6, 7, 8],
        },
        {"box_id": 3, "sku_id": None, "src": "cand", "live_sku": None, "cand_sku": "hot160", "box": [9, 9, 9, 9]},
        {"box_id": 4, "sku_id": None, "src": "live", "live_sku": "cheese145", "box": [10, 10, 5, 5]},
        {"box_id": 5, "sku_id": None, "box": [1, 1, 1, 1]},  # no live name
        {"box_id": 6, "sku_id": "cheese145", "box": [2, 2, 2, 2]},  # not product
        {"box_id": 7, "sku_id": "cheese145", "box": [3, 3, 3, 3]},  # out of scope
        {"box_id": 8, "sku_id": "cheese145", "box": [4, 4, 4, 4]},  # no answer
    ]
    verdicts = [
        {"box_id": 1, "verdict": "wrong_sku", "true_sku_id": "original145"},
        {"box_id": 2, "verdict": "correct"},
        {"box_id": 3, "verdict": "correct"},
        {"box_id": 4, "verdict": "correct"},
        {"box_id": 5, "verdict": "correct"},
        {"box_id": 6, "verdict": "not_product"},
        {"box_id": 7, "verdict": "out_of_scope"},
    ]
    audits = [
        _audit(boxes=boxes, verdicts=verdicts),
        _audit("TRN-1", boxes=boxes, verdicts=verdicts),
        _audit("AUD-CAM-S01-A-20261127-11", status="open", boxes=boxes, verdicts=verdicts),
    ]
    got = scored_boxes(audits)
    cid = "CAP-S01-20261127-100000-1"
    assert got == [
        ScoredBox(cid, "2026-11-27", (1, 2, 3, 4), "cheese145", "original145"),
        ScoredBox(cid, "2026-11-27", (5, 6, 7, 8), "original145", "original145"),  # the live name, not the merged one
        ScoredBox(cid, "2026-11-27", (10, 10, 5, 5), "cheese145", "cheese145"),
    ]


def _measure(boxes, gallery_for_day=None, image=None, skus=SKUS):
    image = _image() if image is None else image
    return measure(
        boxes,
        gallery_for_day or (lambda day: _gallery()),
        lambda cid: image,
        skus,
        PRODUCT,
    )


def test_measure_counts_fixed_broken_and_unsure_against_people_answers():
    boxes = [
        _box("c1", "d1", BLUE, "original145", "cheese145"),  # without wrong, with right -> fixed
        _box("c1", "d1", GREEN, "original145", "original145"),  # right both
        _box("c2", "d1", BLUE, "cheese145", "cheese145"),  # right both
        _box("c3", "d1", GREEN, "cheese145", "original145"),  # fixed
        _box(
            "c4", "d1", (0, 0, 80, 40), "cheese145", "cheese145"
        ),  # half blue half green: unsure, keeps live name: right
        _box("c5", "d1", BLUE, "hot160", "hot160"),  # not in the group: not scored
    ]
    r = _measure(boxes)
    assert (r.n, r.right_without, r.right_with, r.fixed, r.broken, r.unsure, r.skipped) == (5, 3, 5, 2, 0, 1, 0)
    assert r.per_sku == {"cheese145": (3, 2, 3), "original145": (2, 1, 2)}
    assert r.names == 2 and r.days == ["d1"]


def test_measure_counts_a_box_the_gallery_breaks():
    mixed_up = _gallery()
    mixed_up.labels = np.array([{"cheese145": "original145", "original145": "cheese145"}[x] for x in mixed_up.labels])
    boxes = [_box("c1", "d1", BLUE, "cheese145", "cheese145"), _box("c2", "d1", BLUE, "cheese145", "original145")]
    r = _measure(boxes, lambda day: mixed_up)  # blue reads as original145 here
    assert (r.fixed, r.broken, r.right_without, r.right_with) == (1, 1, 1, 1)  # c1 broken, c2 fixed


def test_each_day_is_read_with_a_gallery_built_without_it():
    asked = []
    normal = _gallery()
    mixed_up = _gallery()
    mixed_up.labels = np.array([{"cheese145": "original145", "original145": "cheese145"}[x] for x in mixed_up.labels])

    def gallery_for_day(day):
        asked.append(day)
        return mixed_up if day == "d2" else normal

    boxes = [
        _box("c1", "d1", BLUE, "cheese145", "cheese145"),
        _box("c2", "d2", BLUE, "cheese145", "cheese145"),
        _box("c3", "d1", BLUE, "cheese145", "cheese145"),
    ]
    r = _measure(boxes, gallery_for_day)
    assert sorted(set(asked)) == ["d1", "d2"] and asked.count("d1") == 1  # one gallery per day, built once
    assert r.days == ["d1", "d2"] and r.names == 2  # the smallest over the galleries used
    assert (r.fixed, r.broken, r.right_without, r.right_with) == (0, 1, 3, 2)  # only the d2 box is renamed


def test_a_frame_that_cannot_be_read_is_skipped_and_counted():
    boxes = [_box("c1", "d1", BLUE, "cheese145", "cheese145"), _box("gone", "d1", BLUE, "cheese145", "cheese145")]
    r = measure(boxes, lambda d: _gallery(), lambda cid: _image() if cid == "c1" else None, SKUS, PRODUCT)
    assert (r.n, r.skipped) == (1, 1)


def test_decide_says_nothing_could_be_read_when_no_box_was_measured():
    r = GroupResult("slide", 0, 0, 0, 0, 0, 0, {}, 0, [], 7)
    assert decide(r) == (False, ["no judged box could be read: 7 skipped"])


def result(fixed=0, broken=0, names=2, per_sku=None, n=100):
    return GroupResult("slide", n, 50, 50 + fixed - broken, fixed, broken, 0, per_sku or {}, names, ["d1", "d2"])


def test_decide_needs_more_fixed_than_broken_and_p_below_005():
    assert decide(result(fixed=12, broken=2))[0] is True
    ok, why = decide(result(fixed=5, broken=3))  # p ~ 0.73
    assert ok is False and why
    assert decide(result(fixed=3, broken=3))[0] is False
    assert decide(result(fixed=2, broken=5))[0] is False


def test_decide_refuses_when_a_product_with_ten_boxes_falls_more_than_five_points():
    per_sku = {"cheese145": (20, 18, 12), "original145": (20, 10, 19)}  # cheese 0.90 -> 0.60
    ok, why = decide(result(fixed=12, broken=2, per_sku=per_sku))
    assert ok is False and any("cheese145" in w for w in why)
    small = {"cheese145": (9, 9, 0)}  # under ten boxes: not judged on its own
    assert decide(result(fixed=12, broken=2, per_sku=small))[0] is True
    edge = {"cheese145": (20, 10, 9)}  # exactly five points down: allowed
    assert decide(result(fixed=12, broken=2, per_sku=edge))[0] is True


def test_decide_refuses_a_gallery_that_knows_fewer_than_two_names():
    assert decide(result(fixed=12, broken=2, names=1)) == (False, ["cannot rename: the gallery knows 1 product names"])
    assert decide(result(fixed=12, broken=2, names=0))[1] == ["cannot rename: the gallery knows 0 product names"]


def test_decide_lists_every_failed_condition():
    per_sku = {"cheese145": (20, 18, 12)}
    ok, why = decide(result(fixed=1, broken=3, per_sku=per_sku))
    assert ok is False and len(why) == 3


def test_binomial_matches_the_parallel_run_test():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    import compare

    for k, n in [(0, 0), (0, 1), (2, 10), (5, 10), (3, 11), (12, 14), (40, 100)]:
        assert gm.binomial_two_sided(k, n) == compare.binomial_two_sided(k, n)


def test_the_command_measures_each_group_and_writes_the_result(tmp_path, capsys):
    cid = "CAP-S01-20261127-100000-1"
    (tmp_path / "f" / "2026-11-27").mkdir(parents=True)
    cv2.imwrite(str(tmp_path / "f" / "2026-11-27" / f"{cid}.jpg"), _image())
    (tmp_path / "f" / "manifest.jsonl").write_text(json.dumps({"capture_id": cid, "audit_ids": ["AUD-X"]}) + "\n")
    box = [{"box_id": 1, "sku_id": "cheese145", "box": [0, 0, 40, 40]}]
    audit = _audit(boxes=box, verdicts=[{"box_id": 1, "verdict": "correct"}], cid=cid)
    files = {"a": [audit], "t": {}, "s": [], "c": {"camera": "CAM-S01-A", "groups": {
        "slide": {"region": [0, 0, 80, 40], "skus": ["cheese145", "original145"], "gallery": {"method": "colour"}},
        "other": {"region": [0, 0, 1, 1]},
    }}}  # fmt: skip
    for k, v in files.items():
        (tmp_path / k).write_text(json.dumps(v))
    out = tmp_path / "o.json"
    gm.main(["--audits", str(tmp_path / "a"), "--truth", str(tmp_path / "t"), "--segments", str(tmp_path / "s"),
             "--frames", str(tmp_path / "f"), "--camera-config", str(tmp_path / "c"), "--out", str(out)])  # fmt: skip
    got = json.loads(out.read_text())
    assert got["camera"] == "CAM-S01-A" and list(got["groups"]) == ["slide"]
    g = got["groups"]["slide"]
    assert (g["n"], g["names"], g["enable"]) == (1, 0, False)
    assert g["reasons"] == ["cannot rename: the gallery knows 0 product names"]
    assert "DO NOT ENABLE" in capsys.readouterr().out


def _cli_files(tmp_path, groups):
    """Two scoring frames on two days, one judged box each, and the files the command reads."""
    (tmp_path / "f").mkdir()
    cids = ["CAP-S01-20261127-100000-1", "CAP-S01-20261128-100000-1"]
    audits = []
    for i, cid in enumerate(cids):
        day_dir = tmp_path / "f" / f"2026-11-{27 + i}"
        day_dir.mkdir()
        cv2.imwrite(str(day_dir / f"{cid}.jpg"), _image())
        box = [{"box_id": 1, "sku_id": "cheese145", "box": [0, 0, 40, 40]}]
        audits.append(_audit(f"AUD-X-{i}", boxes=box, verdicts=[{"box_id": 1, "verdict": "correct"}], cid=cid))
    (tmp_path / "f" / "manifest.jsonl").write_text(
        "".join(json.dumps({"capture_id": c, "audit_ids": []}) + chr(10) for c in cids)
    )
    files = {"a": audits, "t": {}, "s": [], "c": {"camera": "CAM-S01-A", "groups": groups}}
    for k, v in files.items():
        (tmp_path / k).write_text(json.dumps(v))
    return [
        "--audits", str(tmp_path / "a"), "--truth", str(tmp_path / "t"), "--segments", str(tmp_path / "s"),
        "--frames", str(tmp_path / "f"), "--camera-config", str(tmp_path / "c"), "--out", str(tmp_path / "o.json"),
    ]  # fmt: skip


SLIDE = {"region": [0, 0, 80, 40], "skus": ["cheese145", "original145"], "gallery": {"method": "colour"}}


def test_each_day_gets_a_gallery_built_without_it_for_the_groups_skus_and_region(tmp_path, monkeypatch):
    calls = []

    def spy(truth, segments, frames, audits, exclude_holdout, **kw):
        calls.append((exclude_holdout, kw))
        return _gallery()

    monkeypatch.setattr(gm, "build", spy)
    gm.main(_cli_files(tmp_path, {"slide": SLIDE}))
    assert len(calls) == 2
    assert [kw["exclude_days"] for _, kw in calls] == [frozenset({"2026-11-27"}), frozenset({"2026-11-28"})]
    for holdout, kw in calls:
        assert holdout is True
        assert kw["skus"] == frozenset(SLIDE["skus"]) and kw["region"] == (0, 0, 80, 40)
    g = json.loads((tmp_path / "o.json").read_text())["groups"]["slide"]
    assert (g["n"], g["names"], g["days"]) == (2, 2, ["2026-11-27", "2026-11-28"])


def test_a_non_colour_group_whose_gallery_knows_two_names_stops_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(gm, "build", lambda *a, **kw: _gallery())
    th = {**SLIDE, "gallery": {"method": "dinov2+colour"}}
    with pytest.raises(SystemExit, match="not built yet"):
        gm.main(_cli_files(tmp_path, {"th": th}))
