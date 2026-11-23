"""Shared schema constants, alias mapping, smoothing, validation and CSV helpers.

Zero third-party dependencies so Lambda deployment zips stay minimal and OS-independent.
CSV column order and formatting match server/milk/cvoutput.py byte-for-byte.
"""
from __future__ import annotations

import csv
import io
import json
import math
from decimal import Decimal
from typing import Any

MILK_FLAG_THRESHOLD = 0.70
UNRECOGNIZED = "UNRECOGNIZED"

CV_OUTPUT_COLUMNS = [
    "reading_id",
    "capture_id",
    "store_id",
    "camera_id",
    "capture_timestamp",
    "capture_source",
    "image_filename",
    "sku_id",
    "sku_name",
    "unit_count",
    "confidence_score",
    "detection_method",
    "bounding_box",
    "is_flagged",
    "flag_reason",
    "processing_time_ms",
]

CAPTURE_LOG_COLUMNS = [
    "capture_id",
    "store_id",
    "camera_id",
    "capture_timestamp",
    "capture_source",
    "image_filename",
    "rows_written",
    "units_found",
    "flagged_rows",
    "processing_time_ms",
]

# Decision 21/11 (hoang): sku_id is the exact product name printed on packaging;
# model labels (TMP-MLK-* and Slide snack classes) map via alias table.
DEFAULT_ALIAS_MAP: dict[str, dict[str, Any]] = {
    "TMP-MLK-TH-01": {
        "sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml",
        "sku_name_vi": "TH true MILK Sữa Tươi Tiệt Trùng Có Đường 180ml",
        "sku_name_en": "TH true MILK Fresh Milk Sweetened 180ml",
        "brand": "TH true MILK",
        "manufacturer": "TH Group",
        "category": "Milk",
        "subcategory": "Fresh Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-TH-02": {
        "sku_id": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "sku_name_vi": "TH true MILK Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "sku_name_en": "TH true MILK Fresh Milk Low Sugar 180ml",
        "brand": "TH true MILK",
        "manufacturer": "TH Group",
        "category": "Milk",
        "subcategory": "Fresh Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-01": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tiệt Trùng Không Đường 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tiệt Trùng Không Đường 180ml",
        "sku_name_en": "Vinamilk 100% Fresh Milk Unsweetened 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Fresh Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-02": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tiệt Trùng Ít Đường 180ml",
        "sku_name_en": "Vinamilk 100% Fresh Milk Low Sugar 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Fresh Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-03": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tiệt Trùng Có Đường 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tiệt Trùng Có Đường 180ml",
        "sku_name_en": "Vinamilk 100% Fresh Milk Sweetened 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Fresh Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-04": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Sôcôla Đậm Đặc 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Sôcôla Đậm Đặc 180ml",
        "sku_name_en": "Vinamilk 100% Skimmed Chocolate Milk 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Flavored Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-05": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tiệt Trùng Giảm Béo Chuối 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tiệt Trùng Giảm Béo Chuối 180ml",
        "sku_name_en": "Vinamilk 100% Low Fat Banana Milk 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Flavored Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-06": {
        "sku_id": "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Dưa Lưới 180ml",
        "sku_name_vi": "Vinamilk 100% Sữa Tươi Tách Béo Tiệt Trùng Dưa Lưới 180ml",
        "sku_name_en": "Vinamilk 100% Skimmed Melon Milk 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Flavored Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-07": {
        "sku_id": "Vinamilk Sữa Đậu Nành Cao Canxi Ít Đường 180ml",
        "sku_name_vi": "Vinamilk Sữa Đậu Nành Cao Canxi Ít Đường 180ml",
        "sku_name_en": "Vinamilk High Calcium Soy Milk Low Sugar 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Plant Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-08": {
        "sku_id": "Vinamilk Sữa Hạt Đậu Nành Hạnh Nhân Ít Đường 180ml",
        "sku_name_vi": "Vinamilk Sữa Hạt Đậu Nành Hạnh Nhân Ít Đường 180ml",
        "sku_name_en": "Vinamilk Almond Soy Milk Low Sugar 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Plant Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-09": {
        "sku_id": "Vinamilk Sữa Hạt Đậu Nành Mè Đen Ít Đường 180ml",
        "sku_name_vi": "Vinamilk Sữa Hạt Đậu Nành Mè Đen Ít Đường 180ml",
        "sku_name_en": "Vinamilk Black Sesame Soy Milk Low Sugar 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Plant Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    "TMP-MLK-VNM-10": {
        "sku_id": "Vinamilk Sữa Hạt 9 Loại Hạt Ít Đường 180ml",
        "sku_name_vi": "Vinamilk Sữa Hạt 9 Loại Hạt Ít Đường 180ml",
        "sku_name_en": "Vinamilk 9 Nuts Milk Low Sugar 180ml",
        "brand": "Vinamilk",
        "manufacturer": "Vinamilk JSC",
        "category": "Milk",
        "subcategory": "Plant Milk",
        "pack_type": "Box",
        "pack_size": "180 ml",
    },
    # 4 Slide snack SKUs trained on 20/11 (HOANG-P09)
    "original145": {
        "sku_id": "Slide Original 145g",
        "sku_name_vi": "Slide Original 145g",
        "sku_name_en": "Slide Original 145g",
        "brand": "Slide",
        "manufacturer": "Kinh Do",
        "category": "Snacks",
        "subcategory": "Potato Crisps",
        "pack_type": "Can",
        "pack_size": "145 g",
    },
    "sourcream150": {
        "sku_id": "Slide Sour Cream & Onion 150g",
        "sku_name_vi": "Slide Sour Cream & Onion 150g",
        "sku_name_en": "Slide Sour Cream & Onion 150g",
        "brand": "Slide",
        "manufacturer": "Kinh Do",
        "category": "Snacks",
        "subcategory": "Potato Crisps",
        "pack_type": "Can",
        "pack_size": "150 g",
    },
    "cheese145": {
        "sku_id": "Slide Cheese 145g",
        "sku_name_vi": "Slide Cheese 145g",
        "sku_name_en": "Slide Cheese 145g",
        "brand": "Slide",
        "manufacturer": "Kinh Do",
        "category": "Snacks",
        "subcategory": "Potato Crisps",
        "pack_type": "Can",
        "pack_size": "145 g",
    },
    "hot160": {
        "sku_id": "Slide Hot & Spicy 160g",
        "sku_name_vi": "Slide Hot & Spicy 160g",
        "sku_name_en": "Slide Hot & Spicy 160g",
        "brand": "Slide",
        "manufacturer": "Kinh Do",
        "category": "Snacks",
        "subcategory": "Potato Crisps",
        "pack_type": "Can",
        "pack_size": "160 g",
    },
}


def resolve_sku_alias(raw_sku_id: str | None, raw_sku_name: str | None = None) -> tuple[str | None, str | None]:
    """Map model label (e.g. TMP-MLK-TH-02) to official packaging product name sku_id."""
    if not raw_sku_id:
        return None, None
    entry = DEFAULT_ALIAS_MAP.get(raw_sku_id)
    if entry:
        return entry["sku_id"], entry["sku_name_vi"]
    # Unknown/new SKU not yet in SKU Master must still be accepted and displayed
    clean_name = raw_sku_name or raw_sku_id
    return clean_name, clean_name


def lower_median(values: list[int]) -> int:
    """Lower median of recent counts (matches smoothing of last 3 captures)."""
    if not values:
        return 0
    ordered = sorted(int(v) for v in values)
    idx = (len(ordered) - 1) // 2
    return ordered[idx]


def floor_two_decimals(value: float) -> float:
    return math.floor(float(value) * 100 + 1e-9) / 100


def validate_capture_payload(record: dict[str, Any]) -> list[str]:
    """Validate 16-column CV Output rows and 10-column Capture Log."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["Record must be a JSON object"]

    log = record.get("log")
    if isinstance(log, str):
        log = json.loads(log)
    if not isinstance(log, dict):
        errors.append("Missing or invalid 'log' object")
    else:
        missing_log = [col for col in CAPTURE_LOG_COLUMNS if col not in log]
        if missing_log:
            errors.append(f"Capture log missing columns: {missing_log}")

    rows = record.get("rows")
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not isinstance(rows, list):
        errors.append("Missing or invalid 'rows' list")
    else:
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"Row {i} is not an object")
                continue
            missing_cols = [col for col in CV_OUTPUT_COLUMNS if col not in row]
            if missing_cols:
                errors.append(f"Row {i} missing CV Output columns: {missing_cols}")

    return errors


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, Decimal):
        return str(int(value) if value == int(value) else float(value))
    return str(value)


def to_csv(records: list[dict[str, Any]], columns: list[str], bom: bool = True) -> str:
    """Serialize rows to Datagent CSV format with UTF-8 BOM for Vietnamese Excel."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for rec in records:
        writer.writerow([_csv_cell(rec.get(col)) for col in columns])
    return ("\ufeff" if bom else "") + out.getvalue()


def to_dynamodb_safe(obj: Any) -> Any:
    """Convert floats to Decimal recursively for DynamoDB put_item."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_dynamodb_safe(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [to_dynamodb_safe(v) for v in obj]
    return obj


def from_dynamodb(obj: Any) -> Any:
    """Convert DynamoDB Decimals to plain int/float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    if isinstance(obj, dict):
        return {k: from_dynamodb(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_dynamodb(v) for v in obj]
    return obj


def compute_validation_result(sku_match_correct: bool | None, discrepancy_category: str | None) -> str:
    """Validation Card Result rule (NHAT-P01 / doc p.14):
    'Đạt' when sku_match_correct == True and discrepancy_category in ('Exact Match', 'Minor');
    otherwise 'Không đạt'. Returns 'Pending' if not yet audited.
    """
    if sku_match_correct is None and not discrepancy_category:
        return "Pending"
    if sku_match_correct and discrepancy_category in ("Exact Match", "Minor"):
        return "Đạt"
    return "Không đạt"
