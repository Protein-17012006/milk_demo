"""Splitting a camera's frames into runs of one arrangement (training/store_view/segments.py)."""

from datetime import datetime, timedelta

import numpy as np

from training.store_view.segments import holdout, signature, similarity, split

RNG = np.random.default_rng(7)
A, B, C = (RNG.normal(size=3072).astype(np.float32) for _ in range(3))


def frames(start, looks, step_s=60, visible=True):
    """Rows and signatures of consecutive frames, one per look, step_s seconds apart."""
    t0 = datetime.fromisoformat(start)
    rows, sigs = [], []
    for k, look in enumerate(looks):
        t = t0 + timedelta(seconds=k * step_s)
        rows.append(
            {
                "capture_id": f"CAP-S01-{t:%Y%m%d-%H%M%S}",
                "capture_timestamp": t.isoformat(),
                "display_visible": visible,
            }
        )
        sigs.append(look)
    return rows, sigs


def day_segments(segments):
    return [s for s in segments if s["kind"] == "day"]


def test_a_brief_occlusion_is_skipped_not_a_new_segment():
    rows, sigs = frames("2026-11-24T13:00:00+07:00", [A, A, A, C, A, A])
    (seg,) = split(rows, sigs)
    assert seg["kind"] == "day" and len(seg["members"]) == 5
    assert rows[3]["capture_id"] not in seg["members"]


def test_a_lasting_change_starts_a_new_segment():
    rows, sigs = frames("2026-11-24T13:00:00+07:00", [A, A, A, B, B, B, B])
    assert [len(s["members"]) for s in day_segments(split(rows, sigs))] == [3, 4]


def test_a_time_gap_splits():
    first, first_sigs = frames("2026-11-24T12:00:00+07:00", [A, A, A])
    later, later_sigs = frames("2026-11-24T12:22:00+07:00", [A, A, A])
    assert len(day_segments(split(first + later, first_sigs + later_sigs, max_gap_s=900))) == 2


def test_keyframe_is_the_member_most_like_the_others():
    e = RNG.normal(scale=0.3, size=3072).astype(np.float32)
    rows, sigs = frames("2026-11-24T13:00:00+07:00", [A, A + e, A + 2 * e])
    (seg,) = split(rows, sigs)
    assert seg["keyframe"] == rows[1]["capture_id"]


def test_short_segments_are_transient():
    rows, sigs = frames("2026-11-24T13:00:00+07:00", [A, A, A, B])
    assert [s["kind"] for s in split(rows, sigs)] == ["day", "transient"]


def test_frames_without_the_display_are_negative():
    day, day_sigs = frames("2026-11-24T19:50:00+07:00", [A, A, A])
    night, night_sigs = frames("2026-11-24T19:53:00+07:00", [B, C, A], visible=False)
    segments = split(day + night, day_sigs + night_sigs)
    assert [(s["kind"], len(s["members"])) for s in segments] == [("day", 3), ("negative", 3)]


def test_holdout_window_marks_segments():
    assert holdout("2026-11-25T08:00:00+07:00") and holdout("2026-11-23T19:00:00+07:00")
    assert not holdout("2026-11-24T10:00:00+07:00") and not holdout("2026-11-23T17:59:59+07:00")
    rows, sigs = frames("2026-11-25T08:00:00+07:00", [A, A, A])
    assert [s["split"] for s in split(rows, sigs)] == ["holdout"]


def test_a_segment_never_spans_a_holdout_boundary():
    # one arrangement from 17:55 to 18:10 on 23/11: the part from 18:00 is held out, so it must be its own segment
    rows, sigs = frames("2026-11-23T17:55:00+07:00", [A] * 6, step_s=180)
    for seg in split(rows, sigs, min_len=1):
        assert len({holdout(r["capture_timestamp"]) for r in rows if r["capture_id"] in seg["members"]}) == 1


def test_signature_ignores_overall_brightness():
    image = RNG.integers(40, 200, size=(200, 300, 3)).astype(np.uint8)
    darker = (image * 0.6).astype(np.uint8)
    assert similarity(signature(image, (50, 20, 250, 180)), signature(darker, (50, 20, 250, 180))) > 0.99


def test_signature_reads_only_the_region():
    image = RNG.integers(40, 200, size=(200, 300, 3)).astype(np.uint8)
    changed = image.copy()
    changed[:, 260:] = 0  # outside the region
    assert similarity(signature(image, (50, 20, 250, 180)), signature(changed, (50, 20, 250, 180))) > 0.999
