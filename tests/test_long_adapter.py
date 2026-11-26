"""How the milk adapter names each box and scores it (server/milk/long_adapter.py), without the models."""

import sys
from pathlib import Path

import numpy as np
import pytest

from milk.catalog import product_names
from milk.cvoutput import Detection
from milk.long_adapter import LABEL_OF_CLASS, LongPipeline, _settings, _th_confirm, decide, needs_lookup, readings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import common  # noqa: E402


def test_unknown_to_the_database_is_unrecognized():
    for cls in ("th_true_milk", "th_true_milk_sweetened", "vinamilk_soy"):
        assert decide(cls, 0.9, "unknown", {"th_true_milk": 1.0}, False) == (None, 0.0)
        assert decide(cls, 0.9, "unknown", {"th_true_milk": 1.0}, True) == (None, 0.0)


def test_old_classes_score_like_read_units():
    # cv_output.read_units: the detector's class names the SKU, the database only backs it
    assert decide("vinamilk_soy", 0.8, "vinamilk", {"vinamilk_soy": 0.5, "vinamilk_melon": 0.5}, False) == (
        "TMP-MLK-VNM-07",
        pytest.approx(0.4),
    )
    assert decide("th_true_milk_sweetened", 0.9, "vinamilk", {"vinamilk_soy": 1.0}, False) == ("TMP-MLK-TH-01", 0.0)


def test_brand_level_th_adds_up_every_th_kind():
    share = {"th_true_milk": 0.5, "th_true_milk_less_sugar": 0.25, "vinamilk_soy": 0.25}
    label, score = decide("th_true_milk", 0.8, "th_true_milk", share, False)
    assert label == "TMP-MLK-TH-00" and score == pytest.approx(0.6)


def test_variants_named_only_when_one_kind_clearly_leads():
    lead = {"th_true_milk_sweetened": 0.8, "th_true_milk_less_sugar": 0.2}
    even = {"th_true_milk_sweetened": 0.5, "th_true_milk_less_sugar": 0.5}
    store_crops = {"th_true_milk": 0.6, "th_true_milk_sweetened": 0.4}  # real crops carry no type
    assert decide("th_true_milk", 0.9, "th_true_milk", lead, True)[0] == "TMP-MLK-TH-01"
    assert decide("th_true_milk", 0.9, "th_true_milk", even, True)[0] == "TMP-MLK-TH-00"
    assert decide("th_true_milk", 0.9, "th_true_milk", store_crops, True)[0] == "TMP-MLK-TH-00"
    assert decide("th_true_milk", 0.9, "th_true_milk", lead, False)[0] == "TMP-MLK-TH-00"


def test_readings_turn_detector_rows_into_detections():
    rows = np.array([[100.2, 50.0, 140.4, 110.0, 0.9, 0, 0], [300.0, 50.0, 330.0, 110.0, 0.7, 2, 1]])
    names = {0: "th_true_milk", 2: "vinamilk_soy"}
    lookups = [{"brand": "th_true_milk"}, {"brand": "unknown"}]
    shares = [{"th_true_milk": 1.0}, {"vinamilk_soy": 1.0}]
    out = readings(rows, names, lookups, shares, {"TMP-MLK-TH-00": "TH gộp"}, variants=False)
    assert out == [
        Detection("TMP-MLK-TH-00", "TH gộp", pytest.approx(0.9), (100, 50, 40, 60)),
        Detection(None, None, 0.0, (300, 50, 30, 60)),
    ]


def test_every_label_has_a_product_name():
    names = product_names()
    assert [label for label in LABEL_OF_CLASS.values() if label not in names] == []


def test_worker_names_match_the_backend_alias_names():
    # the website maps a label to its product by the alias table; the worker's own name must say the same
    names = product_names()
    for label, meta in common.DEFAULT_ALIAS_MAP.items():
        if label.startswith("TMP-MLK-") and label != "TMP-MLK-TH-00":
            assert names[label] == meta["sku_name_vi"], label


def test_tile_and_variants_settings(monkeypatch):
    monkeypatch.delenv("MILK_LONG_TILE", raising=False)
    monkeypatch.delenv("MILK_LONG_VARIANTS", raising=False)
    assert _settings() == (0, False)
    monkeypatch.setenv("MILK_LONG_TILE", "1280")
    monkeypatch.setenv("MILK_LONG_VARIANTS", "1")
    assert _settings() == (1280, True)
    monkeypatch.setenv("MILK_LONG_VARIANTS", "0")
    assert _settings() == (1280, False)


def test_worker_and_backend_name_the_merged_th_row_alike():
    assert product_names()["TMP-MLK-TH-00"] == common.DEFAULT_ALIAS_MAP["TMP-MLK-TH-00"]["sku_name_vi"]


def test_th_confirm_setting(monkeypatch):
    monkeypatch.delenv("MILK_LONG_TH_CONFIRM", raising=False)
    assert _th_confirm() == "database"
    for raw, want in (
        ("", "database"),
        ("detector", "detector"),
        (" Detector\r", "detector"),
        ("DATABASE", "database"),
    ):
        monkeypatch.setenv("MILK_LONG_TH_CONFIRM", raw)
        assert _th_confirm() == want


def test_a_misspelt_th_confirm_stops_the_worker(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "detecter")
    with pytest.raises(ValueError, match="MILK_LONG_TH_CONFIRM"):
        _th_confirm()


def test_only_merged_th_boxes_skip_the_database():
    assert needs_lookup("th_true_milk", False, "detector") is False
    assert needs_lookup("th_true_milk", True, "detector") is True  # variants: the database names the type
    assert needs_lookup("th_true_milk", False, "database") is True
    assert needs_lookup("vinamilk_soy", False, "detector") is True
    assert needs_lookup("th_true_milk_sweetened", False, "detector") is True  # the old 12-class model


def test_detector_confirm_keeps_a_th_box_the_database_rejects():
    assert decide("th_true_milk", 0.83, "unknown", {}, False, "detector") == ("TMP-MLK-TH-00", pytest.approx(0.83))
    share = {"th_true_milk": 0.5, "vinamilk_soy": 0.5}
    assert decide("th_true_milk", 0.8, "th_true_milk", share, False, "detector") == (
        "TMP-MLK-TH-00",
        pytest.approx(0.8),
    )


def test_detector_confirm_leaves_every_other_class_to_the_database():
    for cls in ("th_true_milk_sweetened", "vinamilk_soy"):
        assert decide(cls, 0.9, "unknown", {cls: 1.0}, False, "detector") == (None, 0.0)
    share = {"vinamilk_soy": 0.5, "vinamilk_melon": 0.5}
    assert decide("vinamilk_soy", 0.8, "vinamilk", share, False, "detector") == ("TMP-MLK-VNM-07", pytest.approx(0.4))
    assert decide("th_true_milk_sweetened", 0.9, "vinamilk", {"vinamilk_soy": 1.0}, False, "detector") == (
        "TMP-MLK-TH-01",
        0.0,
    )


def test_detector_confirm_with_variants_names_but_never_rejects():
    lead = {"th_true_milk_sweetened": 0.8, "th_true_milk_less_sugar": 0.2}
    assert decide("th_true_milk", 0.9, "th_true_milk", lead, True, "detector") == ("TMP-MLK-TH-01", pytest.approx(0.9))
    assert decide("th_true_milk", 0.9, "unknown", lead, True, "detector") == ("TMP-MLK-TH-00", pytest.approx(0.9))


def test_readings_pass_the_confirm_mode_on():
    rows = np.array([[100.2, 50.0, 140.4, 110.0, 0.9, 0, 0], [300.0, 50.0, 330.0, 110.0, 0.7, 2, 1]])
    names = {0: "th_true_milk", 2: "vinamilk_soy"}
    lookups = [{"brand": "unknown"}, {"brand": "unknown"}]
    out = readings(rows, names, lookups, [{}, {"vinamilk_soy": 1.0}], {"TMP-MLK-TH-00": "TH gộp"}, False, "detector")
    assert out == [
        Detection("TMP-MLK-TH-00", "TH gộp", pytest.approx(0.9), (100, 50, 40, 60)),
        Detection(None, None, 0.0, (300, 50, 30, 60)),
    ]


ROWS = np.array([[100.0, 50.0, 140.0, 110.0, 0.9, 0, 0], [300.0, 50.0, 330.0, 110.0, 0.7, 2, 0]])  # TH, Vinamilk


def _pipeline_with_fakes(rows, th_confirm, variants=False):
    """A LongPipeline around stand-ins for the detector, the embedder and the database; calls["crops"] counts the
    crops sent to the database."""
    calls = {"crops": 0}

    class Embedder:
        device = "cpu"

        def embed(self, crops):
            calls["crops"] += len(crops)
            return np.zeros((len(crops), 4), np.float32)

    class Rec:
        embedder = Embedder()

        def lookup(self, vectors):
            return [{"brand": "vinamilk"} for _ in vectors]

    class Cvo:
        detect = staticmethod(lambda image, yolo, device, conf, imgsz, tile=0: rows)
        one_box_per_unit = staticmethod(lambda det: det)
        crop_box = staticmethod(lambda image, box: np.zeros((2, 2, 3), np.uint8))
        type_support = staticmethod(lambda rec, vectors: [{"vinamilk_soy": 1.0} for _ in vectors])

    class Yolo:
        names = {0: "th_true_milk", 2: "vinamilk_soy"}

    pipe = object.__new__(LongPipeline)
    pipe._cvo, pipe._rec, pipe._yolo, pipe._product = Cvo, Rec(), Yolo(), {}
    pipe._conf, pipe._imgsz, pipe._tile, pipe._variants, pipe._th_confirm = 0.25, 1280, 0, variants, th_confirm
    return pipe, calls


FRAME = np.zeros((8, 8, 3), np.uint8)


def test_detector_mode_sends_only_other_classes_to_the_database():
    pipe, calls = _pipeline_with_fakes(ROWS, "detector")
    out = pipe.detect(FRAME)
    assert calls["crops"] == 1
    assert [(d.sku_id, d.confidence) for d in out] == [
        ("TMP-MLK-TH-00", pytest.approx(0.9)),
        ("TMP-MLK-VNM-07", pytest.approx(0.7)),
    ]


def test_a_frame_of_only_th_boxes_never_calls_the_database():
    pipe, calls = _pipeline_with_fakes(ROWS[:1], "detector")
    assert [d.sku_id for d in pipe.detect(FRAME)] == ["TMP-MLK-TH-00"]
    assert calls["crops"] == 0


def test_database_mode_still_sends_every_box():
    pipe, calls = _pipeline_with_fakes(ROWS, "database")
    pipe.detect(FRAME)
    assert calls["crops"] == 2


def test_detector_mode_with_variants_asks_the_database_for_the_name():
    pipe, calls = _pipeline_with_fakes(ROWS[:1], "detector", variants=True)
    assert [d.sku_id for d in pipe.detect(FRAME)] == ["TMP-MLK-TH-00"]
    assert calls["crops"] == 1
