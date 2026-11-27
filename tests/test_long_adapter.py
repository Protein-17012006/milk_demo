"""How the milk adapter names each box and scores it (server/milk/long_adapter.py), without the models."""

import sys
from pathlib import Path

import numpy as np
import pytest

from milk.catalog import product_names
from milk.cvoutput import Detection
from milk.long_adapter import (
    LABEL_OF_CLASS,
    LongPipeline,
    _settings,
    _th_confirm,
    _th_overlap,
    decide,
    drop_shared,
    needs_lookup,
    readings,
)

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


def _pipeline_with_fakes(rows, th_confirm, variants=False, th_overlap=0.0):
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
    pipe._th_overlap = th_overlap
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


def _rows(*boxes):
    """Detector rows (x0, y0, x1, y1, confidence, class 0, 0) from (x0, y0, x1, y1, confidence)."""
    return np.array([[*b, 0, 0] for b in boxes], dtype=float)


ACROSS = _rows((0, 0, 30, 24, 0.94), (26, 0, 56, 24, 0.92), (12, 0, 44, 24, 0.80))  # two cartons, a box across the seam


def test_a_box_lying_across_two_cartons_is_dropped():
    # its IoU with each carton is 0.41, so one_box_per_unit keeps it; it shares 0.6 of the box of each carton
    assert drop_shared(ACROSS, [True, True, True], 0.5)[:, 4].tolist() == [0.94, 0.92]


def test_the_cartons_of_a_real_pack_are_all_kept():
    # the eight cells of the pack as it lay on 25/11 (keyframe truth): neighbours overlap, never by half
    from training.store_view.labels import grid_boxes

    cells = grid_boxes([(876, 84), (918, 70), (972, 128), (930, 146)], 4, 2)
    det = _rows(*[(x, y, x + w, y + h, 0.95 - 0.01 * n) for n, (x, y, w, h) in enumerate(cells)])
    assert len(drop_shared(det, [True] * 8, 0.5)) == 8


def test_the_surer_box_stays_and_the_order_of_rows_is_kept():
    det = _rows((12, 0, 44, 24, 0.80), (26, 0, 56, 24, 0.92), (0, 0, 30, 24, 0.94))
    assert drop_shared(det, [True, True, True], 0.5)[:, 4].tolist() == [0.92, 0.94]


def test_only_merged_th_boxes_are_compared():
    det = _rows((0, 0, 30, 24, 0.94), (2, 2, 28, 22, 0.60), (4, 4, 26, 20, 0.50))  # each inside the one before
    assert drop_shared(det, [True, False, True], 0.5)[:, 4].tolist() == [0.94, 0.60]  # the other class stays
    assert len(drop_shared(det, [False, False, True], 0.5)) == 3  # another class never removes a TH box
    assert len(drop_shared(det, [False, False, False], 0.5)) == 3


def test_limit_zero_turns_the_rule_off():
    assert np.array_equal(drop_shared(ACROSS, [True, True, True], 0.0), ACROSS)


def test_th_overlap_setting(monkeypatch):
    monkeypatch.delenv("MILK_LONG_TH_OVERLAP", raising=False)
    assert _th_overlap() == 0.0
    for raw, want in (("", 0.0), ("0", 0.0), ("0.5", 0.5), (" 0.5\r", 0.5), ("1", 1.0)):
        monkeypatch.setenv("MILK_LONG_TH_OVERLAP", raw)
        assert _th_overlap() == want


@pytest.mark.parametrize("raw", ["half", "-0.1", "1.5", "50", "nan"])
def test_a_bad_th_overlap_stops_the_worker(monkeypatch, raw):
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", raw)
    with pytest.raises(ValueError, match="MILK_LONG_TH_OVERLAP"):
        _th_overlap()


def test_the_pipeline_drops_th_duplicates_before_the_database():
    pipe, calls = _pipeline_with_fakes(ACROSS, "detector", th_overlap=0.5)
    assert [d.confidence for d in pipe.detect(FRAME)] == [pytest.approx(0.94), pytest.approx(0.92)]
    pipe, calls = _pipeline_with_fakes(ACROSS, "database", th_overlap=0.5)
    pipe.detect(FRAME)
    assert calls["crops"] == 2


def test_the_pipeline_keeps_every_box_with_the_rule_off():
    pipe, _ = _pipeline_with_fakes(ACROSS, "detector")
    assert len(pipe.detect(FRAME)) == 3


def test_th_settings_read_the_mapping_not_the_process(monkeypatch):
    monkeypatch.setenv("MILK_LONG_TH_CONFIRM", "database")
    monkeypatch.setenv("MILK_LONG_TH_OVERLAP", "0")
    env = {"MILK_LONG_TH_CONFIRM": "detector", "MILK_LONG_TH_OVERLAP": "0.5", "MILK_LONG_TILE": "1280"}
    assert _th_confirm(env) == "detector"
    assert _th_overlap(env) == 0.5
    assert _settings(env) == (1280, False)


def test_adapters_read_the_process_environment_in_one_place_only():
    # A candidate release is loaded beside the live one: an adapter that still read os.environ somewhere would
    # quietly give the candidate the live release's setting.
    import milk

    for name in ("long_adapter.py", "slide_adapter.py"):
        source = (Path(milk.__file__).parent / name).read_text(encoding="utf-8")
        assert source.count("os.environ") == 1, name
