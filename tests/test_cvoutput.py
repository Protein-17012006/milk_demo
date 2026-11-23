"""CV Output must match the format of the 17/10 sample sent to Datagent, byte for byte."""

from datetime import datetime, timedelta, timezone

from milk.cvoutput import (
    CAPTURE_LOG_COLUMNS,
    CV_OUTPUT_COLUMNS,
    CaptureIdAllocator,
    Detection,
    build_capture,
    counts_of,
    to_csv,
)

ICT = timezone(timedelta(hours=7))

# Rows of CV_Output_Example_1_image.csv (17/10/2026), image PHONE-S02-A_20261012_083216-2.jpg:
# (sku_id, sku_name, row confidence, boxes) in the order the file lists them.
SAMPLE = [
    (
        "TMP-MLK-TH-01",
        "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml",
        0.45,
        [
            [121, 466, 38, 73],
            [195, 430, 33, 67],
            [179, 439, 33, 68],
            [212, 419, 32, 69],
            [155, 444, 39, 74],
            [137, 454, 40, 75],
            [150, 548, 87, 97],
        ],
    ),
    (
        "TMP-MLK-VNM-08",
        "Vinamilk Sữa Hạt Đậu Nành Hạnh Nhân Ít Đường 180ml",
        0.68,
        [[277, 302, 23, 63], [335, 277, 23, 57], [347, 273, 22, 56], [289, 296, 24, 60], [360, 269, 19, 55]],
    ),
    (
        "TMP-MLK-VNM-10",
        "Vinamilk Sữa Hạt 9 Loại Hạt Ít Đường 180ml",
        0.58,
        [[262, 308, 25, 64], [246, 314, 25, 63], [372, 264, 18, 53], [387, 259, 18, 53]],
    ),
    (
        "TMP-MLK-VNM-06",
        "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Dưa Lưới 180ml",
        0.75,
        [[213, 326, 29, 64], [196, 333, 30, 67], [405, 251, 15, 52]],
    ),
    (
        "TMP-MLK-VNM-01",
        "Vinamilk 100% Sữa Tươi Tiệt Trùng Không Đường 180ml",
        0.95,
        [[1, 411, 38, 84], [22, 399, 40, 81]],
    ),
    (
        "TMP-MLK-VNM-02",
        "Vinamilk 100% Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        0.93,
        [[44, 388, 39, 82], [68, 380, 34, 80]],
    ),
    (
        "TMP-MLK-VNM-03",
        "Vinamilk 100% Sữa Tươi Tiệt Trùng Có Đường 180ml",
        0.89,
        [[106, 365, 35, 78], [89, 373, 34, 79]],
    ),
    (
        "TMP-MLK-VNM-04",
        "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Sôcôla Đậm Đặc 180ml",
        0.86,
        [[142, 353, 34, 71], [123, 359, 33, 74]],
    ),
    (
        "TMP-MLK-VNM-05",
        "Vinamilk 100% Sữa Tươi Tiệt Trùng Giảm Béo Chuối 180ml",
        0.91,
        [[179, 340, 31, 68], [162, 348, 32, 68]],
    ),
    (
        "TMP-MLK-VNM-09",
        "Vinamilk Sữa Hạt Đậu Nành Mè Đen Ít Đường 180ml",
        0.7,
        [[319, 282, 24, 60], [303, 289, 24, 62]],
    ),
    ("TMP-MLK-VNM-07", "Vinamilk Sữa Đậu Nành Cao Canxi Ít Đường 180ml", 0.51, [[231, 321, 28, 64]]),
    (None, None, 0.3, [[64, 580, 102, 109], [108, 566, 97, 106]]),
]

EXPECTED_CSV = """\
reading_id,capture_id,store_id,camera_id,capture_timestamp,capture_source,image_filename,sku_id,sku_name,unit_count,confidence_score,detection_method,bounding_box,is_flagged,flag_reason,processing_time_ms
RD-S02-20261012-083216-2-001,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-TH-01,TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml,7,0.45,Visual,"[[121,466,38,73],[195,430,33,67],[179,439,33,68],[212,419,32,69],[155,444,39,74],[137,454,40,75],[150,548,87,97]]",TRUE,Low Confidence,1037
RD-S02-20261012-083216-2-002,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-08,Vinamilk Sữa Hạt Đậu Nành Hạnh Nhân Ít Đường 180ml,5,0.68,Visual,"[[277,302,23,63],[335,277,23,57],[347,273,22,56],[289,296,24,60],[360,269,19,55]]",TRUE,Low Confidence,1037
RD-S02-20261012-083216-2-003,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-10,Vinamilk Sữa Hạt 9 Loại Hạt Ít Đường 180ml,4,0.58,Visual,"[[262,308,25,64],[246,314,25,63],[372,264,18,53],[387,259,18,53]]",TRUE,Low Confidence,1037
RD-S02-20261012-083216-2-004,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-06,Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Dưa Lưới 180ml,3,0.75,Visual,"[[213,326,29,64],[196,333,30,67],[405,251,15,52]]",FALSE,,1037
RD-S02-20261012-083216-2-005,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-01,Vinamilk 100% Sữa Tươi Tiệt Trùng Không Đường 180ml,2,0.95,Visual,"[[1,411,38,84],[22,399,40,81]]",FALSE,,1037
RD-S02-20261012-083216-2-006,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-02,Vinamilk 100% Sữa Tươi Tiệt Trùng Ít Đường 180ml,2,0.93,Visual,"[[44,388,39,82],[68,380,34,80]]",FALSE,,1037
RD-S02-20261012-083216-2-007,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-03,Vinamilk 100% Sữa Tươi Tiệt Trùng Có Đường 180ml,2,0.89,Visual,"[[106,365,35,78],[89,373,34,79]]",FALSE,,1037
RD-S02-20261012-083216-2-008,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-04,Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Sôcôla Đậm Đặc 180ml,2,0.86,Visual,"[[142,353,34,71],[123,359,33,74]]",FALSE,,1037
RD-S02-20261012-083216-2-009,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-05,Vinamilk 100% Sữa Tươi Tiệt Trùng Giảm Béo Chuối 180ml,2,0.91,Visual,"[[179,340,31,68],[162,348,32,68]]",FALSE,,1037
RD-S02-20261012-083216-2-010,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-09,Vinamilk Sữa Hạt Đậu Nành Mè Đen Ít Đường 180ml,2,0.7,Visual,"[[319,282,24,60],[303,289,24,62]]",FALSE,,1037
RD-S02-20261012-083216-2-011,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,TMP-MLK-VNM-07,Vinamilk Sữa Đậu Nành Cao Canxi Ít Đường 180ml,1,0.51,Visual,"[[231,321,28,64]]",TRUE,Low Confidence,1037
RD-S02-20261012-083216-2-012,CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,PHONE-S02-A_20261012_083216-2.jpg,,,2,0.0,Visual,"[[64,580,102,109],[108,566,97,106]]",TRUE,Unrecognized,1037
"""


def _sample_detections(reverse_groups: bool = False):
    groups = list(reversed(SAMPLE)) if reverse_groups else SAMPLE
    dets = []
    for sku_id, name, conf, boxes in groups:
        dets += [Detection(sku_id, name, conf, tuple(b)) for b in boxes]
    return dets


def _build(reverse_groups: bool = False):
    ts = datetime(2026, 10, 12, 8, 32, 16, tzinfo=ICT)
    alloc = CaptureIdAllocator()
    alloc.stem("S02", ts)  # the first capture of that second has no suffix
    stem = alloc.stem("S02", ts)
    return build_capture(
        _sample_detections(reverse_groups),
        stem=stem,
        store_id="TEST-S02",
        camera_id="PHONE-S02-A",
        capture_source="Phone",
        ts=ts,
        processing_time_ms=1037,
    )


def test_rows_match_the_17_10_sample_exactly():
    rows, _ = _build()
    assert to_csv(rows, CV_OUTPUT_COLUMNS, bom=False) == EXPECTED_CSV


def test_output_does_not_depend_on_the_order_the_model_lists_skus():
    rows, _ = _build(reverse_groups=True)
    assert to_csv(rows, CV_OUTPUT_COLUMNS, bom=False) == EXPECTED_CSV


def test_capture_log_matches_the_17_10_sample():
    _, log = _build()
    expected = (
        "capture_id,store_id,camera_id,capture_timestamp,capture_source,image_filename,"
        "rows_written,units_found,flagged_rows,processing_time_ms\n"
        "CAP-S02-20261012-083216-2,TEST-S02,PHONE-S02-A,2026-10-12T08:32:16+07:00,Phone,"
        "PHONE-S02-A_20261012_083216-2.jpg,12,34,5,1037\n"
    )
    assert to_csv([log], CAPTURE_LOG_COLUMNS, bom=False) == expected


def test_csv_starts_with_bom_for_excel():
    rows, _ = _build()
    assert to_csv(rows, CV_OUTPUT_COLUMNS).startswith("﻿reading_id,")


def test_empty_frame_gives_no_rows_but_a_log_line():
    ts = datetime(2026, 11, 18, 17, 9, 0, tzinfo=ICT)
    stem = CaptureIdAllocator().stem("S01", ts)
    rows, log = build_capture(
        [], stem=stem, store_id="DEMO-S01", camera_id="CAM-S01-A", capture_source="CCTV", ts=ts, processing_time_ms=99
    )
    assert rows == []
    assert log["capture_id"] == "CAP-S01-20261118-170900"
    assert log["image_filename"] == "CAM-S01-A_20261118_170900.jpg"
    assert (log["rows_written"], log["units_found"], log["flagged_rows"]) == (0, 0, 0)


def test_allocator_suffixes_reset_each_second():
    alloc = CaptureIdAllocator()
    t0 = datetime(2026, 11, 18, 17, 9, 0, tzinfo=ICT)
    t1 = t0 + timedelta(seconds=1)
    assert [alloc.stem("S01", t).time for t in (t0, t0, t0, t1)] == ["170900", "170900-2", "170900-3", "170901"]


def _one_row(confidences):
    ts = datetime(2026, 11, 18, 18, 0, 0, tzinfo=ICT)
    dets = [Detection("TMP-MLK-VNM-01", "x", c, (i, 0, 10, 20)) for i, c in enumerate(confidences)]
    rows, _ = build_capture(
        dets,
        stem=CaptureIdAllocator().stem("S01", ts),
        store_id="DEMO-S01",
        camera_id="CAM-S01-A",
        capture_source="CCTV",
        ts=ts,
        processing_time_ms=1,
    )
    return rows[0]


def test_score_is_rounded_down_and_the_flag_uses_the_raw_mean():
    # mean 0.6995: round() would store 0.70 yet flag it; the pipeline stores 0.69 and flags it
    row = _one_row([0.695, 0.704])
    assert row["confidence_score"] == 0.69 and row["is_flagged"] and row["flag_reason"] == "Low Confidence"


def test_a_mean_of_exactly_0_70_is_accepted():
    row = _one_row([0.7, 0.7])
    assert row["confidence_score"] == 0.7 and not row["is_flagged"] and row["flag_reason"] == ""


def test_three_cartons_at_0_70_fall_just_below_in_floating_point_and_are_flagged():
    # 0.7 + 0.7 + 0.7 = 2.0999999999999996 in floating point, exactly as in the pipeline's np.mean
    row = _one_row([0.7, 0.7, 0.7])
    assert row["confidence_score"] == 0.7 and row["is_flagged"]


def test_counts_use_unrecognized_key():
    rows, _ = _build()
    counts = counts_of(rows)
    assert counts["TMP-MLK-TH-01"] == 7
    assert counts["UNRECOGNIZED"] == 2
    assert sum(counts.values()) == 34
