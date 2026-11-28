"""The gallery's read rule inside the worker: GalleryNamer renames Slide boxes and never drops, adds or reorders one."""

from __future__ import annotations

import numpy as np
import pytest

from milk.cvoutput import Detection
from milk.gallery import GALLERY_KEY, Gallery, GalleryNamer, load_namer

PRODUCT = {"cheese145": "Slide Cheese 145g", "original145": "Slide Original 145g", "hot160": "Slide Hot 160g"}
E = np.eye(144)
E1, E2, E3 = E[0], E[1], E[2]
MIXED = (E1 + E2) / np.sqrt(2)


def _feature(crop: np.ndarray) -> np.ndarray:
    """A stand-in for colour(): which of e1, e2, e3 the crop's mean blue/green/red channel says."""
    b, g, r = crop.reshape(-1, 3).mean(axis=0)
    if b > 200 and g > 200:
        return MIXED
    return E1 if b > 200 else E2 if g > 200 else E3


def _gallery() -> Gallery:
    """25 cans each of cheese145 (e1), original145 (e2) and none (e3). A little of an unused axis (e4) is mixed into
    each can so that no two cans are equally near the mixed query: the nearest ten alternate cheese, original."""
    feats, labels = [], []
    for j in range(25):
        for k, (label, vec) in enumerate((("cheese145", E1), ("original145", E2), ("none", E3))):
            v = vec + (2 * j + k % 2) * 0.01 * E[3] if k < 2 else vec
            feats.append(v / np.linalg.norm(v))
            labels.append(label)
    n = len(labels)
    return Gallery(
        np.stack(feats),
        np.array(labels),
        np.array([f"s{i}" for i in range(n)]),
        "2026-11-28T00:00:00",
        None,
        np.array([f"o{i}" for i in range(n)]),
    )


def _image() -> np.ndarray:
    """100 x 40: blue left, green middle (x 40-59), red right, a blue+green patch at x 60-79."""
    img = np.zeros((40, 100, 3), np.uint8)
    img[:, :40, 0] = 255
    img[:, 40:60, 1] = 255
    img[:, 60:80, 0:2] = 255
    img[:, 80:, 2] = 255
    return img


def _det(sku: str, box, conf: float = 0.77, name: str | None = None) -> Detection:
    return Detection(sku, name or sku, conf, box)


def test_a_sure_gallery_renames_a_box_and_keeps_its_place_and_score():
    box = (40, 0, 20, 40)  # green -> e2 -> original145
    other = _det("cheese145", (0, 0, 20, 40), 0.9)
    out = GalleryNamer(_gallery(), PRODUCT, _feature).name(_image(), [_det("cheese145", box), other])
    assert [d.box for d in out] == [box, (0, 0, 20, 40)]
    assert out[0].sku_id == "original145"
    assert out[0].sku_name == "Slide Original 145g"
    assert out[0].confidence == 0.77
    assert out[0].unsure is False
    assert out[1].sku_id == "cheese145" and out[1].unsure is False  # e1 agrees with the detector


def test_an_unsure_read_keeps_the_detector_name_and_marks_the_box():
    det = _det("cheese145", (60, 0, 20, 40), name="Slide Cheese 145g")
    (out,) = GalleryNamer(_gallery(), PRODUCT, _feature).name(_image(), [det])
    assert (out.sku_id, out.sku_name, out.box, out.confidence) == ("cheese145", "Slide Cheese 145g", det.box, 0.77)
    assert out.unsure is True


def test_a_name_with_fewer_than_20_cans_in_the_gallery_is_not_read():
    dets = [_det("hot160", (40, 0, 20, 40)), _det("TMP-MLK-TH-00", (40, 0, 20, 40))]
    out = GalleryNamer(_gallery(), PRODUCT, _feature).name(_image(), dets)
    assert out == dets
    assert not any(d.unsure for d in out)


def test_none_never_becomes_a_name_and_no_box_is_dropped():
    dets = [_det("cheese145", (80, 0, 20, 40)), _det("original145", (0, 0, 20, 40))]
    out = GalleryNamer(_gallery(), PRODUCT, _feature).name(_image(), dets)
    assert len(out) == len(dets)
    assert out[0].sku_id == "cheese145" and out[0].unsure is True
    assert out[1].sku_id == "cheese145" and out[1].unsure is False  # e1 wins there; order kept


def test_a_box_too_small_to_crop_is_kept_and_marked_unsure():
    det = _det("cheese145", (98, 0, 2, 40), name="Slide Cheese 145g")
    (out,) = GalleryNamer(_gallery(), PRODUCT, _feature).name(_image(), [det])
    assert (out.sku_id, out.sku_name, out.box) == ("cheese145", "Slide Cheese 145g", det.box)
    assert out.unsure is True


def test_load_namer_is_none_without_the_key_and_names_the_missing_file(tmp_path):
    assert load_namer({}) is None
    assert load_namer({GALLERY_KEY: ""}) is None
    missing = tmp_path / "gone.npz"
    with pytest.raises(FileNotFoundError, match="gone.npz"):
        load_namer({GALLERY_KEY: str(missing)})
    path = tmp_path / "g.npz"
    _gallery().save(path)
    assert isinstance(load_namer({GALLERY_KEY: str(path)}), GalleryNamer)
