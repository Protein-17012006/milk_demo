"""How the milk adapter names each box and scores it (server/milk/long_adapter.py), without the models."""

import sys
from pathlib import Path

import numpy as np
import pytest

from milk.catalog import product_names
from milk.cvoutput import Detection
from milk.long_adapter import LABEL_OF_CLASS, _settings, decide, readings

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
