"""Which capture of an hour becomes the training frame (operations-loop design 5.4, signals 3 and 5)."""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from label_signals import count_jumps, pick_training, windows  # noqa: E402


def cap(hhmmss: str, **counts: int) -> dict:
    return {
        "capture_id": f"CAP-S01-20261121-{hhmmss}",
        "capture_timestamp": f"2026-11-21T{hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:6]}+07:00",
        "boxes": [{"sku_id": sku} for sku, n in counts.items() for _ in range(n)],
    }


def boxes_of(item: dict) -> list[dict]:
    return item["boxes"]


def test_a_gap_of_more_than_a_minute_starts_a_new_window():
    items = [cap("140000"), cap("140010"), cap("140500"), cap("140505")]
    assert [[c["capture_id"][-6:] for c in w] for w in windows(items)] == [["140000", "140010"], ["140500", "140505"]]


def test_windows_follow_the_time_not_the_order_given():
    items = [cap("140505"), cap("140000"), cap("140500"), cap("140010")]
    assert [[c["capture_id"][-6:] for c in w] for w in windows(items)] == [["140000", "140010"], ["140500", "140505"]]


def test_the_frame_that_strays_from_its_window_has_the_jump():
    items = [cap("140000", hot160=5), cap("140005", hot160=5), cap("140010", hot160=2), cap("140015", hot160=5)]
    assert count_jumps(items, boxes_of) == {
        items[0]["capture_id"]: 0,
        items[1]["capture_id"]: 0,
        items[2]["capture_id"]: 3,
        items[3]["capture_id"]: 0,
    }


def test_a_window_of_one_frame_has_no_jump():
    assert count_jumps([cap("140000", hot160=7)], boxes_of) == {"CAP-S01-20261121-140000": 0}


def test_a_product_missing_from_one_frame_counts_as_zero_there():
    items = [cap("140000", hot160=3, cheese145=2), cap("140005", hot160=3), cap("140010", hot160=3, cheese145=2)]
    assert count_jumps(items, boxes_of)[items[1]["capture_id"]] == 2


def test_a_box_without_a_name_is_not_counted():
    items = [cap("140000", hot160=3), cap("140005", hot160=3), cap("140010", hot160=3)]
    items[1]["boxes"] += [{"sku_id": None}] * 4
    assert set(count_jumps(items, boxes_of).values()) == {0}


def test_a_jump_is_measured_inside_its_own_window():
    items = [cap("140000", hot160=5), cap("140005", hot160=5), cap("140500", hot160=1), cap("140505", hot160=1)]
    assert set(count_jumps(items, boxes_of).values()) == {0}


def test_the_largest_jump_is_picked():
    items = [cap("140000", hot160=5), cap("140005", hot160=5), cap("140010", hot160=2)]
    assert pick_training(items, count_jumps(items, boxes_of), random.Random(0)) == (items[2], "count_jump")


def test_a_jump_of_one_is_not_a_signal_and_the_draw_is_the_plain_one():
    items = [cap("140000", hot160=5), cap("140005", hot160=4), cap("140010", hot160=5)]
    assert pick_training(items, count_jumps(items, boxes_of), random.Random(7)) == (
        random.Random(7).choice(items),
        "random",
    )


def test_equal_jumps_go_to_the_earliest_capture_without_a_draw():
    items = [cap("140000", hot160=5), cap("140005", hot160=2), cap("140010", hot160=5), cap("140015", hot160=8)]
    rng = random.Random(3)
    before = rng.getstate()
    assert pick_training(items, count_jumps(items, boxes_of), rng) == (items[1], "count_jump")
    assert rng.getstate() == before
