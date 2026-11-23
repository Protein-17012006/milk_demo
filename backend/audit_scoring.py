"""Scores frames the team labelled on the Model page the way Datagent's Accuracy Report reads.

An audit is one frame: the model's boxes (`ai_boxes`, each with the model label `sku_id`, None when
UNRECOGNIZED), one verdict per box and the units the model missed. Verdicts:

    correct      named box: one unit of that SKU; UNRECOGNIZED box: goods outside the catalogue
    wrong_sku    one unit of catalogue SKU `true_sku_id`, not what the model said
    not_product  named box: not any catalogue SKU; UNRECOGNIZED box: not goods at all

The formulas follow the column descriptions of "Validation - Accuracy Report" (the sheet's formula cells
show #ERROR!), as written in docs/superpowers/specs/2026-11-23-model-quality-page-design.md, section 5.
Nothing here touches AWS, so the API can call it on whatever audits it loaded.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

VERDICTS = ("correct", "wrong_sku", "not_product")
SKIP_REASONS = ("blurry", "blocked", "camera_moved", "other")

# Pilot targets of the Accuracy Report, part B. minor_error_rate's target applies to exact + minor.
KPI_TARGETS: dict[str, tuple[str, float]] = {
    "sku_identification_accuracy": (">=", 0.80),
    "overall_identification_accuracy": (">=", 0.60),
    "unit_count_mae": ("<=", 2),
    "unit_count_accuracy_avg": (">=", 0.75),
    "exact_match_rate": (">=", 0.40),
    "minor_error_rate": (">=", 0.75),
    "missed_sku_rate": ("<=", 0.20),
    "false_detection_rate": ("<=", 0.10),
    "avg_confidence_correct": (">", 0.8),
    "avg_confidence_incorrect": ("<", 0.5),
    "avg_processing_time_ms": ("<=", 30000),
    "unrecognized_product_rate": ("<=", 0.20),
}
TOP_N = 50
NOT_PRODUCT = "NOT_PRODUCT"
OTHER_GOODS = "OTHER_GOODS"
UNRECOGNIZED = "UNRECOGNIZED"
MISSED = "MISSED"


def validate_labels(ai_boxes: list[dict], verdicts: list[dict], missed: list[dict], catalog: set[str]) -> list[str]:
    """What is wrong with a labelling before it is saved; an empty list means it can be saved."""
    errors: list[str] = []
    box_ids = {b["box_id"] for b in ai_boxes}
    seen: set = set()
    for v in verdicts:
        box_id = v.get("box_id")
        if box_id not in box_ids:
            errors.append(f"box {box_id} is not in this frame")
            continue
        if box_id in seen:
            errors.append(f"box {box_id} has more than one verdict")
        seen.add(box_id)
        if v.get("verdict") not in VERDICTS:
            errors.append(f"box {box_id} has an unknown verdict {v.get('verdict')!r}")
        elif v["verdict"] == "wrong_sku":
            sku = v.get("true_sku_id")
            if not sku:
                errors.append(f"box {box_id} needs the right sku")
            elif sku not in catalog:
                errors.append(f"unknown sku {sku!r}")
    for b in ai_boxes:
        if b["box_id"] not in seen:
            errors.append(f"box {b['box_id']} has no verdict")
    for m in missed:
        if m.get("sku_id") not in catalog:
            errors.append(f"unknown sku {m.get('sku_id')!r}")
    return errors


def _verdicts_by_box(audit: dict) -> dict:
    return {v["box_id"]: v for v in audit.get("verdicts", [])}


def _truth_counts(audit: dict) -> Counter:
    """Units of each catalogue SKU that are really in the frame."""
    labels = _verdicts_by_box(audit)
    truth: Counter = Counter()
    for b in audit.get("ai_boxes", []):
        v = labels.get(b["box_id"])
        if not v:
            continue
        if v["verdict"] == "correct" and b["sku_id"] is not None:
            truth[b["sku_id"]] += 1
        elif v["verdict"] == "wrong_sku":
            truth[v["true_sku_id"]] += 1
    for m in audit.get("missed", []):
        truth[m["sku_id"]] += 1
    return truth


def comparison_rows(audit: dict) -> list[dict]:
    """Part A of the Accuracy Report: one row per catalogue SKU the model or the labeller found in the frame.
    UNRECOGNIZED boxes get no row (no truth exists for goods outside the catalogue)."""
    labels = _verdicts_by_box(audit)
    boxes = audit.get("ai_boxes", [])
    ai = Counter(b["sku_id"] for b in boxes if b["sku_id"] is not None)
    truth = _truth_counts(audit)
    rows = []
    for sku in sorted(set(ai) | set(truth)):
        a, h = ai[sku], truth[sku]
        verdicts = [labels[b["box_id"]]["verdict"] for b in boxes if b["sku_id"] == sku and b["box_id"] in labels]
        diff = a - h
        if a == 0 and h > 0:
            category = "Missed SKU"
        elif h == 0 and verdicts and all(v == "not_product" for v in verdicts):
            category = "False Detection"
        elif "wrong_sku" in verdicts:
            category = "Wrong SKU"
        elif diff == 0:
            category = "Exact Match"
        elif abs(diff) <= 2:
            category = "Minor"
        else:
            category = "Major"
        rows.append({
            "sku_id": sku,
            "ai_unit_count": a,
            "human_unit_count": h,
            "count_difference": diff,
            "count_accuracy_pct": max(0.0, 1 - abs(diff) / h) if h > 0 else 0.0,
            "discrepancy_category": category,
        })
    return rows


def _kpi(name: str, value: float | None, n: int, judged: float | None = None) -> dict:
    op, threshold = KPI_TARGETS[name]
    judged = value if judged is None else judged
    if value is None or judged is None:
        return {"value": None, "target": [op, threshold], "met": None, "n": 0}
    met = {">=": judged >= threshold, "<=": judged <= threshold, ">": judged > threshold, "<": judged < threshold}[op]
    return {"value": value, "target": [op, threshold], "met": met, "n": n}


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _kpis(audits: list[dict], processing_ms: list[int]) -> dict:
    rows = [r for a in audits for r in comparison_rows(a)]
    boxes = []  # (box, verdict) of every labelled box
    for a in audits:
        labels = _verdicts_by_box(a)
        boxes.extend((b, labels.get(b["box_id"])) for b in a.get("ai_boxes", []))

    # Identification: boxes whose truth is a catalogue SKU, and whether the model named that SKU
    truth_total: Counter = Counter()
    for r in rows:
        truth_total[r["sku_id"]] += r["human_unit_count"]
    top = {sku for sku, _ in sorted(truth_total.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]}
    ident = []  # (true sku, named right)
    for b, v in boxes:
        if not v:
            continue
        if v["verdict"] == "correct" and b["sku_id"] is not None:
            ident.append((b["sku_id"], True))
        elif v["verdict"] == "wrong_sku":
            ident.append((v["true_sku_id"], False))
    ident_top = [ok for sku, ok in ident if sku in top]

    with_truth = [r for r in rows if r["human_unit_count"] > 0]
    category = Counter(r["discrepancy_category"] for r in rows)
    judged = [(b, v) for b, v in boxes if v]
    conf_right = [b["conf"] for b, v in judged if v["verdict"] == "correct" and b["sku_id"] is not None]
    conf_wrong = [b["conf"] for b, v in judged if v["verdict"] in ("wrong_sku", "not_product")]
    exact_or_minor = _share(category["Exact Match"] + category["Minor"], len(rows))

    minor = _kpi("minor_error_rate", _share(category["Minor"], len(rows)), len(rows), judged=exact_or_minor)
    minor["exact_or_minor"] = exact_or_minor
    return {
        "sku_identification_accuracy": _kpi(
            "sku_identification_accuracy", _share(sum(ident_top), len(ident_top)), len(ident_top)),
        "overall_identification_accuracy": _kpi(
            "overall_identification_accuracy", _share(sum(ok for _, ok in ident), len(ident)), len(ident)),
        "unit_count_mae": _kpi("unit_count_mae", _mean([abs(r["count_difference"]) for r in rows]), len(rows)),
        "unit_count_accuracy_avg": _kpi(
            "unit_count_accuracy_avg", _mean([r["count_accuracy_pct"] for r in with_truth]), len(with_truth)),
        "exact_match_rate": _kpi("exact_match_rate", _share(category["Exact Match"], len(rows)), len(rows)),
        "minor_error_rate": minor,
        "missed_sku_rate": _kpi(
            "missed_sku_rate", _share(category["Missed SKU"], len(with_truth)), len(with_truth)),
        "false_detection_rate": _kpi(
            "false_detection_rate", _share(sum(v["verdict"] == "not_product" for _, v in judged), len(judged)),
            len(judged)),
        "avg_confidence_correct": _kpi("avg_confidence_correct", _mean(conf_right), len(conf_right)),
        "avg_confidence_incorrect": _kpi("avg_confidence_incorrect", _mean(conf_wrong), len(conf_wrong)),
        "avg_processing_time_ms": _kpi("avg_processing_time_ms", _mean(processing_ms), len(processing_ms)),
        "unrecognized_product_rate": _kpi(
            "unrecognized_product_rate", _share(sum(b["sku_id"] is None for b, _ in judged), len(judged)),
            len(judged)),
    }


def _per_sku(audits: list[dict]) -> list[dict]:
    model_units: Counter = Counter()
    true_units: Counter = Counter()
    right: Counter = Counter()
    missed: Counter = Counter()
    confused: dict[str, Counter] = defaultdict(Counter)
    for a in audits:
        labels = _verdicts_by_box(a)
        for r in comparison_rows(a):
            true_units[r["sku_id"]] += r["human_unit_count"]
        for b in a.get("ai_boxes", []):
            if b["sku_id"] is None:
                continue
            model_units[b["sku_id"]] += 1
            v = labels.get(b["box_id"])
            if v and v["verdict"] == "correct":
                right[b["sku_id"]] += 1
            elif v and v["verdict"] == "wrong_sku":
                confused[b["sku_id"]][v["true_sku_id"]] += 1
        for m in a.get("missed", []):
            missed[m["sku_id"]] += 1
    out = []
    for sku in sorted(set(model_units) | set(true_units)):
        top = confused[sku].most_common(1)
        out.append({
            "sku_id": sku,
            "model_units": model_units[sku],
            "true_units": true_units[sku],
            "id_accuracy": right[sku] / model_units[sku] if model_units[sku] else None,
            "missed_units": missed[sku],
            "confused_as": top[0][0] if top else None,
            "confused_count": top[0][1] if top else 0,
        })
    return out


def _confusion(audits: list[dict]) -> dict:
    cells: Counter = Counter()
    for a in audits:
        labels = _verdicts_by_box(a)
        for b in a.get("ai_boxes", []):
            v = labels.get(b["box_id"])
            if not v:
                continue
            row = b["sku_id"] or UNRECOGNIZED
            if v["verdict"] == "correct":
                col = b["sku_id"] or OTHER_GOODS
            elif v["verdict"] == "wrong_sku":
                col = v["true_sku_id"]
            else:
                col = NOT_PRODUCT
            cells[f"{row}|{col}"] += 1
        for m in a.get("missed", []):
            cells[f"{MISSED}|{m['sku_id']}"] += 1
    rows = sorted({k.split("|")[0] for k in cells} - {UNRECOGNIZED, MISSED})
    rows += [r for r in (UNRECOGNIZED, MISSED) if any(k.startswith(f"{r}|") for k in cells)]
    cols = sorted({k.split("|")[1] for k in cells} - {NOT_PRODUCT, OTHER_GOODS})
    cols += [c for c in (OTHER_GOODS, NOT_PRODUCT) if any(k.endswith(f"|{c}") for k in cells)]
    return {"rows": rows, "cols": cols, "cells": dict(cells)}


def summarize(audits: list[dict], processing_ms: list[int]) -> dict:
    """Everything the Model page shows from labelled frames. A KPI without samples has value None and n 0."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for a in audits:
        by_day[a["capture_timestamp"][:10]].append(a)
    days = []
    for day in sorted(by_day):
        k = _kpis(by_day[day], [])
        days.append({
            "day": day,
            "audits": len(by_day[day]),
            "overall_identification_accuracy": k["overall_identification_accuracy"]["value"],
            "unit_count_mae": k["unit_count_mae"]["value"],
            "exact_or_minor_rate": k["minor_error_rate"]["exact_or_minor"],
        })
    return {
        "n_audits": len(audits),
        "kpis": _kpis(audits, processing_ms),
        "per_sku": _per_sku(audits),
        "confusion": _confusion(audits),
        "by_day": days,
    }
