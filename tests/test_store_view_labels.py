"""Keyframe boxes and the label files made from them (training/store_view/labels.py)."""

import numpy as np

from training.store_view.labels import (
    boxes_of,
    clip_box,
    draw,
    from_yolo,
    grid_boxes,
    pack_area,
    to_yolo,
    write_labels,
    zoom_view,
)


def test_grid_boxes_of_an_upright_rectangle():
    quad = [(0, 0), (40, 0), (40, 20), (0, 20)]
    assert grid_boxes(quad, 1, 4) == [[0, 0, 10, 20], [10, 0, 10, 20], [20, 0, 10, 20], [30, 0, 10, 20]]


def test_grid_boxes_of_a_slanted_quad_cover_it_row_by_row():
    quad = [(100, 50), (180, 60), (175, 110), (95, 100)]
    boxes = grid_boxes(quad, 2, 4)
    assert len(boxes) == 8
    assert min(b[0] for b in boxes) == 95 and min(b[1] for b in boxes) == 50
    assert max(b[0] + b[2] for b in boxes) == 180 and max(b[1] + b[3] for b in boxes) == 110
    centres = [(b[0] + b[2] / 2, b[1] + b[3] / 2) for b in boxes]
    first, second = centres[:4], centres[4:]
    assert all(a[0] < b[0] for a, b in zip(first, first[1:], strict=False))  # left to right
    assert all(top[1] < bottom[1] for top, bottom in zip(first, second, strict=True))  # first row above


def test_yolo_round_trip():
    lines = to_yolo([[100, 50, 40, 60]], 2560, 1440)
    assert lines == ["0 0.046875 0.055556 0.015625 0.041667"]
    assert from_yolo(lines, 2560, 1440) == [(0, [100, 50, 40, 60])]


def test_clip_box_trims_overhang_and_drops_empty():
    assert clip_box([-10, 5, 30, 20], 100, 100) == [0, 5, 20, 20]
    assert clip_box([95, 95, 20, 20], 100, 100) == [95, 95, 5, 5]
    assert clip_box([120, 5, 10, 10], 100, 100) is None
    assert clip_box([10, 10, 0, 5], 100, 100) is None


def test_a_keyframe_entry_gives_its_boxes_and_its_packs_cells():
    entry = {"boxes": [[1, 2, 3, 4]], "packs": [{"quad": [(0, 0), (40, 0), (40, 20), (0, 20)], "rows": 1, "cols": 2}]}
    assert boxes_of(entry, 2560, 1440) == [[1, 2, 3, 4], [0, 0, 20, 20], [20, 0, 20, 20]]


def test_write_labels_gives_each_member_its_keyframes_boxes(tmp_path):
    segments = [
        {"id": "seg-0001", "kind": "day", "keyframe": "K", "members": ["K", "M"]},
        {"id": "seg-0002", "kind": "negative", "keyframe": "N1", "members": ["N1"]},
        {"id": "seg-0003", "kind": "transient", "keyframe": "T", "members": ["T"]},
        {"id": "seg-0004", "kind": "day", "keyframe": "U", "members": ["U", "V"]},  # keyframe not labelled yet
    ]
    keyframes = {"K": {"boxes": [[100, 50, 40, 60], [200, 50, 40, 60]]}}
    counts = write_labels(segments, keyframes, tmp_path, (2560, 1440))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["K.txt", "M.txt", "N1.txt"]
    assert (tmp_path / "M.txt").read_text().splitlines() == (tmp_path / "K.txt").read_text().splitlines()
    assert len((tmp_path / "K.txt").read_text().splitlines()) == 2
    assert (tmp_path / "N1.txt").read_text() == ""
    assert counts == {"labelled": 2, "negative": 1, "unlabelled_segments": 1, "dropped": 0}


def test_a_keyframe_labelled_empty_means_no_th_in_its_segment(tmp_path):
    segments = [{"id": "seg-0001", "kind": "day", "keyframe": "K", "members": ["K", "M"]}]
    write_labels(segments, {"K": {"boxes": []}}, tmp_path, (2560, 1440))
    assert (tmp_path / "M.txt").read_text() == ""


def test_zoom_view_enlarges_the_region():
    image = np.zeros((100, 200, 3), np.uint8)
    assert zoom_view(image, (10, 20, 60, 50), scale=4, grid=10).shape == (120, 200, 3)


def test_draw_marks_the_box_edges_and_leaves_the_input_alone():
    image = np.zeros((50, 50, 3), np.uint8)
    out = draw(image, [[10, 10, 20, 20]])
    assert out[10, 15].any() and not out[25, 25].any()
    assert not image.any()


def test_pack_area_is_the_boxes_with_a_margin_inside_the_frame():
    assert pack_area([[100, 50, 40, 60], [150, 40, 30, 60]], 2560, 1440, margin=16) == (84, 24, 196, 126)
    assert pack_area([[5, 5, 10, 10]], 2560, 1440, margin=16) == (0, 0, 31, 31)


def test_a_member_whose_pack_area_changed_gets_no_label(tmp_path):
    segments = [{"id": "seg-0001", "kind": "day", "keyframe": "K", "members": ["K", "M", "P"]}]
    keyframes = {"K": {"boxes": [[100, 50, 40, 60]]}}
    asked = []

    def keep(member, keyframe, area):
        asked.append((member, keyframe, area))
        return member != "P"  # a person stands in front of the pack in P

    counts = write_labels(segments, keyframes, tmp_path, (2560, 1440), keep=keep, zone=(0, 0, 10, 10))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["K.txt", "M.txt"]
    assert counts["dropped"] == 1
    assert ("M", "K", (84, 34, 156, 126)) in asked and all(m != "K" for m, _, _ in asked)  # the keyframe is not asked


def test_an_empty_keyframe_is_checked_on_the_zone_where_packs_stand(tmp_path):
    segments = [{"id": "seg-0001", "kind": "day", "keyframe": "K", "members": ["K", "M"]}]
    asked = []
    write_labels(
        segments,
        {"K": {"boxes": []}},
        tmp_path,
        (2560, 1440),
        keep=lambda m, k, a: asked.append(a) or True,
        zone=(780, 0, 1110, 280),
    )
    assert asked == [(780, 0, 1110, 280)]
