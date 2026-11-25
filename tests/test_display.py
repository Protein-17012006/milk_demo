import numpy as np
import pytest

from milk.cvoutput import Detection
from milk.display import DESC_LEN, DisplayCheck, zone_crop

ZONE = (0.336, 0.083, 0.242, 0.361)
W, H = 2560, 1440
ZX0, ZY0 = int(ZONE[0] * W), int(ZONE[1] * H)
ZX1, ZY1 = int((ZONE[0] + ZONE[2]) * W), int((ZONE[1] + ZONE[3]) * H)
COLOURS = [(0, 128, 255), (0, 255, 255), (0, 200, 0)]  # orange, yellow, green (BGR)


def display_img() -> np.ndarray:
    """Grey room with vertical orange, yellow and green stripes where the cabinet is."""
    img = np.full((H, W, 3), 128, np.uint8)
    for i, x in enumerate(range(ZX0, ZX1, 20)):
        img[ZY0:ZY1, x : x + 20] = COLOURS[i % 3]
    return img


def floor_img() -> np.ndarray:
    """Grey noise over the whole frame: the cabinet is packed away."""
    noise = np.random.default_rng(7).integers(90, 170, (H, W, 1), dtype=np.uint8)
    return np.repeat(noise, 3, axis=2)


def dark_img() -> np.ndarray:
    """Lights off or the lens covered: nothing to see."""
    return np.zeros((H, W, 3), np.uint8)


def lying_img() -> np.ndarray:
    """The cabinet's colours in the same places, without its shape: the same stripes lying flat."""
    img = np.full((H, W, 3), 128, np.uint8)
    for i, y in enumerate(range(ZY0, ZY1, 20)):
        img[y : y + 20, ZX0:ZX1] = COLOURS[i % 3]
    return img


def bands_img() -> np.ndarray:
    """The cabinet's colours in other places and without its shape: one wide band per colour."""
    img = np.full((H, W, 3), 128, np.uint8)
    cuts = np.linspace(ZY0, ZY1, len(COLOURS) + 1).astype(int)
    for i, colour in enumerate(COLOURS):
        img[cuts[i] : cuts[i + 1], ZX0:ZX1] = colour
    return img


def cans(n: int, conf: float = 0.9, inside: bool = True) -> list[Detection]:
    x0 = ZX0 + 40 if inside else 100
    y = ZY0 + 100 if inside else 800
    return [Detection("cheese145", "x", conf, (x0 + i * 80, y, 60, 150)) for i in range(n)]


def test_no_references_means_seen_without_a_score():
    assert DisplayCheck(ZONE).check(display_img(), [], now=0.0) == (None, True)


def test_confident_cans_inside_the_zone_teach_a_reference():
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    score, seen = d.check(display_img(), [], now=1.0)
    assert d.n_refs == 1 and 0.99 < score <= 1.0 and seen


@pytest.mark.parametrize("gone", [floor_img, dark_img])
def test_the_display_gone_scores_low(gone):
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    score, seen = d.check(gone(), [], now=1.0)
    assert 0.0 <= score < 0.5 and not seen


@pytest.mark.parametrize("other_goods", [lying_img, bands_img])
def test_the_cabinet_colours_without_the_cabinet_are_not_in_view(other_goods):
    """23/11 20:50-21:20: after the cabinet was packed away its place held fruit, sweets and red snack packets,
    whose colours matched the cabinet as well as the cabinet itself did the next morning. The same colours without
    the cabinet's shape must not count, and colour alone gives at most half the score."""
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    score, seen = d.check(other_goods(), [], now=1.0)
    assert score < 0.5 and not seen


def test_unsure_or_outside_cans_teach_nothing():
    d = DisplayCheck(ZONE)
    for dets in (cans(2), cans(3, conf=0.79), cans(3, inside=False)):
        d.check(display_img(), dets, now=0.0)
    assert d.n_refs == 0


def test_one_reference_per_ten_minutes_and_at_most_fifty():
    d = DisplayCheck(ZONE)
    d.check(display_img(), cans(3), now=0.0)
    d.check(display_img(), cans(3), now=599.0)
    assert d.n_refs == 1
    for k in range(1, 60):
        d.check(display_img(), cans(3), now=600.0 * k)
    assert d.n_refs == 50


def test_references_survive_a_restart(tmp_path):
    path = str(tmp_path / "refs.npz")
    DisplayCheck(ZONE, refs_path=path).check(display_img(), cans(3), now=0.0)
    assert DisplayCheck(ZONE, refs_path=path).n_refs == 1


def test_a_zone_partly_outside_the_frame_is_cut_to_the_frame():
    assert zone_crop(np.zeros((100, 200, 3), np.uint8), (0.9, 0.9, 0.5, 0.5)).shape == (10, 20, 3)


def _garbage(path):
    path.write_bytes(b"this is not an npz file")


def _missing_key(path):
    np.savez(path, refs=np.zeros((1, DESC_LEN), np.float32))


def _mismatched(path):
    np.savez(path, refs=np.zeros((2, DESC_LEN), np.float32), times=np.array([0.0]))


def _wrong_size(path):
    """References described another way (the colour-only histograms of 480 values) cannot be compared."""
    np.savez(path, refs=np.zeros((1, 480), np.float32), times=np.array([0.0]))


def _first_format(path):
    """A file from the first display check, which kept colour histograms."""
    np.savez(path, hists=np.zeros((1, 480), np.float32), times=np.array([0.0]))


@pytest.mark.parametrize("write_bad_file", [_garbage, _missing_key, _mismatched, _wrong_size, _first_format])
def test_a_bad_references_file_starts_empty_and_is_replaced(tmp_path, caplog, write_bad_file):
    path = tmp_path / "refs.npz"
    write_bad_file(path)
    d = DisplayCheck(ZONE, refs_path=str(path))
    assert d.n_refs == 0
    assert "references" in caplog.text
    assert d.check(display_img(), cans(3), now=0.0) == (None, True)
    assert DisplayCheck(ZONE, refs_path=str(path)).n_refs == 1
