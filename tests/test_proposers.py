"""The two box sources of the auto-labeller: Slide v3 and YOLOE with visual prompts (training/store_view/proposers.py)."""

import json
import os
from pathlib import Path

import pytest

from training.store_view.proposers import Proposal, in_region, region_prompts, union_nms

REGION = (880, 120, 1520, 720)


def test_region_prompts_shift_boxes_into_the_crop():
    rows = [{"box": [900, 200, 70, 160], "kind": "face"}, {"box": [1, 1, 5, 5], "kind": "ignore"}]
    assert region_prompts(rows, REGION).tolist() == [[20, 80, 90, 240]]


def test_in_region_uses_the_box_centre():
    assert in_region((870, 110, 20, 20), REGION)  # centre (880, 120) on the corner
    assert not in_region((850, 100, 20, 20), REGION)  # centre (860, 110) outside
    assert in_region((1500, 700, 100, 100), REGION) is False  # centre (1550, 750)


def test_union_nms_keeps_the_surer_of_two_overlapping_boxes():
    a = Proposal("B", (0, 0, 10, 10), 0.5, None)
    b = Proposal("B", (1, 1, 10, 10), 0.9, None)
    c = Proposal("B", (50, 50, 10, 10), 0.4, None)
    assert union_nms([a, b, c]) == [b, c]


def test_sources_find_cans_on_a_store_frame():
    pytest.importorskip("ultralytics")
    root = os.environ.get("MILK_AUTOLABEL_MODELS")
    if not root:
        pytest.skip("MILK_AUTOLABEL_MODELS (the Datagent folder on the counting machine) is not set")
    import cv2

    from training.store_view.proposers import Sources

    root = Path(root)
    truth = json.loads((root / "store_labels" / "slide" / "truth.json").read_text(encoding="utf-8"))
    key = "CAP-S01-20261123-151304-2"
    sources = Sources(
        str(root / "slide_pilot" / "runs_v3" / "best.pt"),
        str(root / "_sam3" / "yoloe-11l-seg.pt"),
        [cv2.imread(str(root / "store_frames" / "CAM-S01-A" / "2026-11-23" / f"{key}.jpg"))],
        [region_prompts(truth[key], REGION)],
        REGION,
    )
    image = cv2.imread(str(root / "store_frames" / "CAM-S01-A" / "2026-11-24" / "CAP-S01-20261124-112017-2.jpg"))
    found = sources.frame(image)
    assert sum(p.source == "A" for p in found) >= 6 and sum(p.source == "B" for p in found) >= 6
    assert all(in_region(p.box, REGION) for p in found)


def test_the_sources_find_the_server_package_outside_pytest():
    # `python -m training.store_view.auto_label_run` runs without pytest's pythonpath: Sources imports milk.slide_adapter
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    code = "from training.store_view.proposers import ensure_server_path; ensure_server_path(); import milk.catalog"
    r = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
