"""Lower-tier cans added to the Slide truth (training/store_view/truth_lower.py)."""

from training.store_view.truth_lower import add_lower, candidates

ROWS = [{"box": [100, 200, 70, 160], "sku": "cheese145", "kind": "face"}, {"box": [300, 100, 60, 30], "sku": "unknown", "kind": "ignore"}]


def test_candidates_are_the_boxes_no_truth_row_holds():
    drafts = [[105, 210, 60, 150], [310, 105, 40, 20], [120, 600, 70, 120]]
    assert candidates(ROWS, drafts) == [[120, 600, 70, 120]]


def test_add_lower_keeps_the_old_rows_and_marks_the_new_ones_lower():
    truth = {"K": list(ROWS)}
    out = add_lower(truth, "K", [([120, 600, 70, 120], "original145"), ([200, 610, 70, 120], "unknown")])
    assert out["K"][:2] == ROWS
    assert out["K"][2:] == [
        {"box": [120, 600, 70, 120], "sku": "original145", "kind": "lower"},
        {"box": [200, 610, 70, 120], "sku": "unknown", "kind": "lower"},
    ]
    assert truth["K"] == ROWS  # the input is not changed
