import json
from pathlib import Path

import pytest

from milk.cvoutput import Detection
from milk.pipeline import CombinedPipeline, NullPipeline, load_pipeline, merge
from milk.slide_adapter import product_names, to_detections


def det(sku, box, conf=0.9):
    return Detection(sku, sku, conf, box)


def test_merge_drops_a_milk_box_lying_on_a_slide_can():
    milk = [det(None, (100, 100, 60, 150)), det("TMP-MLK-TH-01", (400, 100, 40, 80))]
    slide = [det("hot160", (104, 96, 62, 160))]
    out = merge(milk, slide)
    assert [d.sku_id for d in out] == ["TMP-MLK-TH-01", "hot160"]


def test_merge_keeps_boxes_that_only_touch():
    milk = [det("TMP-MLK-VNM-01", (100, 100, 50, 100))]
    slide = [det("cheese145", (140, 100, 50, 100))]  # 10 of 50 px wide shared: 20% of the smaller box
    assert len(merge(milk, slide)) == 2


def test_merge_judges_by_the_smaller_box():
    # a lid box (small) inside a carton box (large): most of the lid is covered, so they are one object
    milk = [det(None, (100, 100, 80, 200))]
    slide = [det("sourcream150", (110, 110, 60, 35))]
    assert [d.sku_id for d in merge(milk, slide)] == ["sourcream150"]


class Fixed:
    def __init__(self, name, dets, device="cuda"):
        self.name, self._dets, self.device = name, dets, device

    def detect(self, image):
        return list(self._dets)


def test_combined_pipeline_names_and_merges_in_order():
    p = CombinedPipeline(
        [Fixed("long", [det(None, (0, 0, 50, 100))]), Fixed("slide", [det("hot160", (2, 2, 50, 100))])]
    )
    assert p.name == "long+slide"
    assert p.device == "cuda"
    assert [d.sku_id for d in p.detect(None)] == ["hot160"]


def test_load_pipeline_parts():
    assert isinstance(load_pipeline("null", ""), NullPipeline)
    both = load_pipeline("null + null", "")
    assert isinstance(both, CombinedPipeline) and both.name == "null+null"
    with pytest.raises(ValueError):
        load_pipeline("milk", "")


def test_to_detections_turns_corners_into_width_and_height():
    names = {0: "original145", 3: "hot160"}
    out = to_detections([3.0], [0.87], [[10.0, 20.0, 70.0, 180.0]], names, {"hot160": "Slide Hot & Spicy 160g"})
    assert out == [Detection("hot160", "Slide Hot & Spicy 160g", 0.87, (10.0, 20.0, 60.0, 160.0))]


def test_to_detections_keeps_one_box_for_a_can_found_as_two_flavours():
    # store frame 23/11 12:57:45: one can came back as hot160 and as original145 on the same box
    names = {0: "original145", 3: "hot160"}
    out = to_detections([3.0, 0.0], [0.61, 0.87], [[947, 326, 1021, 492], [947, 326, 1021, 491]], names, {})
    assert out == [Detection("original145", "original145", 0.87, (947.0, 326.0, 74.0, 165.0))]


def test_to_detections_keeps_one_box_for_a_can_found_twice():
    # store frame 23/11 12:56:54: one lid came back twice as cheese145, one pixel apart
    names = {2: "cheese145"}
    out = to_detections([2.0, 2.0], [0.80, 0.85], [[957, 210, 1026, 256], [957, 210, 1026, 257]], names, {})
    assert out == [Detection("cheese145", "cheese145", 0.85, (957.0, 210.0, 69.0, 47.0))]


def test_to_detections_keeps_neighbouring_cans():
    # two cans side by side: 20 of 60 px wide shared, IoU 0.2, as close as neighbours got on 23/11
    names = {1: "sourcream150"}
    out = to_detections([1.0, 1.0], [0.9, 0.8], [[100, 100, 160, 250], [140, 100, 200, 250]], names, {})
    assert [d.box for d in out] == [(100.0, 100.0, 60.0, 150.0), (140.0, 100.0, 60.0, 150.0)]


def test_every_slide_class_has_a_product_name():
    product = product_names()
    for label in ("original145", "sourcream150", "cheese145", "hot160"):
        assert product[label].startswith("Slide ")


def test_skus_json_ids_are_unique():
    skus = json.loads((Path(__file__).resolve().parents[1] / "server" / "milk" / "skus.json").read_text("utf-8"))
    ids = [s["id"] for s in skus]
    assert len(ids) == len(set(ids))
