"""Scores frames the team labelled on the Model page the way Datagent's Accuracy Report reads.

An audit is one frame: the model's boxes (`ai_boxes`, each with the model label `sku_id`, None when
UNRECOGNIZED), one verdict per box and the units the model missed. Verdicts:

    correct      named box: one unit of that SKU; UNRECOGNIZED box: goods outside the catalogue
    wrong_sku    one unit of catalogue SKU `true_sku_id`, not what the model said
    not_product  named box: not any catalogue SKU; UNRECOGNIZED box: not goods at all
    out_of_scope a real can that labelling rule A does not count (lower tier, almost hidden, flavour unclear):
                 the box and its verdict are dropped from every number

The formulas follow the column descriptions of "Validation - Accuracy Report" (the sheet's formula cells
show #ERROR!), as written in docs/superpowers/specs/2026-11-23-model-quality-page-design.md, section 5.

Every number over frames is a sum of per-frame numerators over a sum of per-frame denominators (frame_tallies), so
its 95% interval comes from resampling whole frames (ratio_ci): boxes of one frame are not independent. The two-way
numbers per SKU, present or absent, by time of day and the check level follow
docs/superpowers/specs/2026-11-24-reliability-design.md, section 1.2c.
Nothing here touches AWS, so the API can call it on whatever audits it loaded.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from functools import lru_cache, wraps
from numbers import Number
from operator import itemgetter

VERDICTS = ("correct", "wrong_sku", "not_product", "out_of_scope")
SKIP_REASONS = ("blurry", "blocked", "camera_moved", "display_away", "other")

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

# "Not enough samples" for a SKU below any of these: frames with a true unit, true units, days of those frames
MIN_FRAMES, MIN_TRUE_UNITS, MIN_DAYS = 10, 20, 2
# Reliability badge: both intervals of a SKU (named right, found right) start at or above BADGE_HIGH for "high", or
# BADGE_MEDIUM for "medium"; below that "low"
BADGE_HIGH, BADGE_MEDIUM = 0.90, 0.70
BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED = 400, 20261124
ICT = timezone(timedelta(hours=7))
PERIODS = ("morning", "afternoon", "evening")  # ICT hour of the frame: before 12, 12 to 17, from 17
PRESENCE = {"agree": "presence_agree", "false_empty": "false_empty", "missed_empty": "missed_empty"}

Tally = tuple[float, float]  # (numerator, denominator) of one frame
# the SKUs a frame must show (model labels): one set for every frame, or each store's own set by store_id
Expected = set[str] | Mapping[str, set[str]] | None


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


def scoped(audit: dict) -> dict:
    """The audit as rule A scores it: a copy without the out_of_scope boxes and their verdicts."""
    dropped = {v["box_id"] for v in audit.get("verdicts", []) if v.get("verdict") == "out_of_scope"}
    if not dropped:
        return audit
    return {
        **audit,
        "ai_boxes": [b for b in audit.get("ai_boxes", []) if b["box_id"] not in dropped],
        "verdicts": [v for v in audit.get("verdicts", []) if v["box_id"] not in dropped],
    }


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
    audit = scoped(audit)
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
        rows.append(
            {
                "sku_id": sku,
                "ai_unit_count": a,
                "human_unit_count": h,
                "count_difference": diff,
                "count_accuracy_pct": max(0.0, 1 - abs(diff) / h) if h > 0 else 0.0,
                "discrepancy_category": category,
            }
        )
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


def _kpi_tallies(audit: dict, top: set[str] | None) -> dict[str, Tally]:
    """One scoped frame's numerator and denominator of KPIs #1-#10 and #12, and of exact_or_minor (what KPI #6 is
    judged on). top: the SKUs KPI #1 counts, None for all."""
    labels = _verdicts_by_box(audit)
    judged = [(b, labels[b["box_id"]]) for b in audit.get("ai_boxes", []) if b["box_id"] in labels]
    ident = []  # (true sku, named right) of every box whose truth is a catalogue SKU
    for b, v in judged:
        if v["verdict"] == "correct" and b["sku_id"] is not None:
            ident.append((b["sku_id"], True))
        elif v["verdict"] == "wrong_sku":
            ident.append((v["true_sku_id"], False))
    ident_top = [ok for sku, ok in ident if top is None or sku in top]
    rows = comparison_rows(audit)
    with_truth = [r for r in rows if r["human_unit_count"] > 0]
    category = Counter(r["discrepancy_category"] for r in rows)
    conf_right = [b["conf"] for b, v in judged if v["verdict"] == "correct" and b["sku_id"] is not None]
    conf_wrong = [b["conf"] for b, v in judged if v["verdict"] in ("wrong_sku", "not_product")]
    return {
        "sku_identification_accuracy": (sum(ident_top), len(ident_top)),
        "overall_identification_accuracy": (sum(ok for _, ok in ident), len(ident)),
        "unit_count_mae": (sum(abs(r["count_difference"]) for r in rows), len(rows)),
        "unit_count_accuracy_avg": (math.fsum(r["count_accuracy_pct"] for r in with_truth), len(with_truth)),
        "exact_match_rate": (category["Exact Match"], len(rows)),
        "minor_error_rate": (category["Minor"], len(rows)),
        "exact_or_minor": (category["Exact Match"] + category["Minor"], len(rows)),
        "missed_sku_rate": (category["Missed SKU"], len(with_truth)),
        "false_detection_rate": (sum(v["verdict"] == "not_product" for _, v in judged), len(judged)),
        "avg_confidence_correct": (math.fsum(conf_right), len(conf_right)),
        "avg_confidence_incorrect": (math.fsum(conf_wrong), len(conf_wrong)),
        "unrecognized_product_rate": (sum(b["sku_id"] is None for b, _ in judged), len(judged)),
    }


def _presence(model: Mapping[str, int], truth: Mapping[str, int], expected: set[str] | None) -> dict[str, Tally]:
    """Present-or-absent pairs of one frame, one per SKU: the expected SKUs plus any SKU either side counted."""
    skus = set(expected or ()) | {s for s, n in model.items() if n > 0} | {s for s, n in truth.items() if n > 0}
    said = {s for s in skus if model.get(s, 0) > 0}
    real = {s for s in skus if truth.get(s, 0) > 0}
    return {
        "presence_agree": (len(skus) - len(said ^ real), len(skus)),
        "false_empty": (len(real - said), len(skus - said)),
        "missed_empty": (len(said - real), len(skus - real)),
    }


def frame_tallies(audit: dict, expected: set[str] | None = None, top: set[str] | None = None) -> dict[str, Tally]:
    """(numerator, denominator) pairs of one frame, scored as rule A scores it. Every ratio of the Model page is the
    sum of a key's numerators over the sum of its denominators across frames.

        named_right:<sku>  boxes named <sku> and right / boxes named <sku>
        found_right:<sku>  boxes named <sku> and right / true units of <sku>
        bias:<sku>         model units - true units / 1
        presence_agree     SKUs both sides call present, or both absent / SKUs considered
        false_empty        SKUs the model calls absent that are there / SKUs the model calls absent
        missed_empty       SKUs the model calls present that are not there / SKUs really absent
        kpi:<name>         the frame's part of KPI #1-#10 and #12 (kpi:exact_or_minor: what KPI #6 is judged on)

    <sku> keys exist for the SKUs either side counted; SKUs considered are those plus `expected`. top: the SKUs KPI
    #1 counts (None: all)."""
    audit = scoped(audit)
    labels = _verdicts_by_box(audit)
    named = [b for b in audit.get("ai_boxes", []) if b["sku_id"] is not None]
    model = Counter(b["sku_id"] for b in named)
    right = Counter(b["sku_id"] for b in named if labels.get(b["box_id"], {}).get("verdict") == "correct")
    truth = _truth_counts(audit)
    tallies: dict[str, Tally] = {}
    for sku in model.keys() | truth.keys():
        tallies[f"named_right:{sku}"] = (right[sku], model[sku])
        tallies[f"found_right:{sku}"] = (right[sku], truth[sku])
        tallies[f"bias:{sku}"] = (model[sku] - truth[sku], 1)
    tallies.update(_presence(model, truth, expected))
    tallies.update({f"kpi:{name}": pair for name, pair in _kpi_tallies(audit, top).items()})
    return tallies


def _expected_of(expected: Expected, audit: dict) -> set[str] | None:
    """The SKUs one frame must show: its own store's list when the lists are given per store (none for a store
    without one), else the one list."""
    return expected.get(audit.get("store_id")) if isinstance(expected, Mapping) else expected


def _top_skus(audits: list[dict]) -> set[str]:
    """The TOP_N SKUs with the most true units in these frames: the SKUs KPI #1 counts."""
    truth: Counter = Counter()
    for a in audits:
        truth.update(_truth_counts(scoped(a)))
    return {sku for sku, _ in sorted(truth.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]}


def _column(tallies: list[dict[str, Tally]], key: str) -> list[Tally]:
    """One key's pairs across frames; a frame without the key adds nothing."""
    return [t[key] for t in tallies if key in t]


def _sums(pairs: list[Tally]) -> tuple[float, int]:
    return math.fsum(num for num, _ in pairs), sum(den for _, den in pairs)


def _value(pairs: list[Tally]) -> float | None:
    num, den = _sums(pairs)
    return num / den if den else None


def _stat(pairs: list[Tally]) -> dict:
    """{value, ci, n} of one ratio over frames: n is the sum of denominators; value None when it is 0."""
    return {"value": _value(pairs), "ci": ratio_ci(pairs), "n": _sums(pairs)[1]}


@lru_cache(maxsize=8)
def _resamples(frames: int, samples: int, seed: int) -> tuple[Callable, ...]:
    """`samples` draws of `frames` frame positions with replacement, by random.Random(seed): one getter per draw,
    picking the drawn items out of a list. The same arguments always give the same draws, so they are kept for every
    ratio over the same number of frames, within one call of a function marked _frees_draws."""
    rng = random.Random(seed)
    positions = range(frames)
    return tuple(itemgetter(*rng.choices(positions, k=frames)) for _ in range(samples))


def _frees_draws(fn: Callable) -> Callable:
    """Drops the kept bootstrap draws when `fn` returns or raises. The API Lambda (256 MB) stays warm between
    requests, and the draws of 1,440 frames took about 99 MB; inside one call they are still shared."""

    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            _resamples.cache_clear()

    return call


def ratio_ci(tallies: list[Tally], samples: int = BOOTSTRAP_SAMPLES, seed: int = BOOTSTRAP_SEED) -> list[float] | None:
    """95% interval of sum(numerators) / sum(denominators) by resampling whole frames (frame bootstrap): the 2.5th
    and 97.5th percentiles, 4 decimals. Only frames with a denominator count; None below 2 such frames. The pairs are
    worked out once per frame, so a resample only adds them up."""
    kept = [(num, den) for num, den in tallies if den > 0]
    if len(kept) < 2:
        return None
    nums, dens = [num for num, _ in kept], [den for _, den in kept]
    values = []
    for pick in _resamples(len(kept), samples, seed):
        den = sum(pick(dens))
        if den > 0:
            values.append(sum(pick(nums)) / den)
    if len(values) < 2:
        return None
    cuts = statistics.quantiles(values, n=40, method="inclusive")  # every 2.5%
    return [round(cuts[0], 4), round(cuts[-1], 4)]


def enough(frames: int, true_units: int, days: int) -> bool:
    """Enough samples to speak of one SKU: MIN_FRAMES frames with a true unit, MIN_TRUE_UNITS true units, and those
    frames on MIN_DAYS days or more (an interval over one day's frames says nothing about other days)."""
    return frames >= MIN_FRAMES and true_units >= MIN_TRUE_UNITS and days >= MIN_DAYS


def kpis(audits: list[dict], processing_ms: list[int], tallies: list[dict] | None = None) -> dict:
    """Datagent's 12 KPIs, without intervals. Each one but #11 is the sum of the frames' numerators over the sum of
    their denominators; tallies: the frames' frame_tallies (with the top SKUs of the same frames), when the caller
    has them already."""
    if tallies is None:
        top = _top_skus(audits)
        tallies = [frame_tallies(a, top=top) for a in audits]
    exact_or_minor = _value(_column(tallies, "kpi:exact_or_minor"))
    out = {}
    for name in KPI_TARGETS:
        if name == "avg_processing_time_ms":
            out[name] = _kpi(name, _mean(processing_ms), len(processing_ms))
            continue
        num, den = _sums(_column(tallies, f"kpi:{name}"))
        judged = exact_or_minor if name == "minor_error_rate" else None
        out[name] = _kpi(name, num / den if den else None, den, judged=judged)
    out["minor_error_rate"]["exact_or_minor"] = exact_or_minor
    return out


def _per_sku(audits: list[dict], tallies: list[dict], days: list[str]) -> list[dict]:
    audits = [scoped(a) for a in audits]
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
        row = _two_way(tallies, days, sku)
        out.append(
            {
                "sku_id": sku,
                "model_units": model_units[sku],
                "true_units": true_units[sku],
                "id_accuracy": right[sku] / model_units[sku] if model_units[sku] else None,
                "missed_units": missed[sku],
                "confused_as": top[0][0] if top else None,
                "confused_count": top[0][1] if top else 0,
                **row,
                "badge": badge(row),
            }
        )
    return out


def _sample(tallies: list[dict], days: list[str], sku: str) -> tuple[int, int, int]:
    """(true units, frames with a true unit, distinct days of those frames) of one SKU."""
    key = f"found_right:{sku}"
    seen = [(t[key][1], day) for t, day in zip(tallies, days, strict=True) if key in t and t[key][1] > 0]
    return sum(units for units, _ in seen), len(seen), len({day for _, day in seen})


def _two_way(tallies: list[dict], days: list[str], sku: str, with_bias: bool = True) -> dict:
    """Found right and the bias per frame of one SKU with their intervals, the interval of named right, and whether
    there are enough samples to speak of it. with_bias=False leaves the bias out (its interval costs a resampling)."""
    named, found, bias = (_column(tallies, f"{kind}:{sku}") for kind in ("named_right", "found_right", "bias"))
    true_units, frames, n_days = _sample(tallies, days, sku)
    out = {
        "found_right": _value(found),
        "found_right_ci": ratio_ci(found),
        "id_accuracy_ci": ratio_ci(named),
        "frames": frames,
        "days": n_days,
        "enough": enough(frames, true_units, n_days),
    }
    if with_bias:
        out.update(bias_per_frame=_value(bias), bias_per_frame_ci=ratio_ci(bias))
    return out


def badge(row: dict) -> str:
    """Reliability of one SKU (spec 1.3): "insufficient" below the sample rule or without an interval of found right;
    else the lower ends of the intervals of named right and found right decide: both from BADGE_HIGH "high", both
    from BADGE_MEDIUM "medium", otherwise "low". A SKU the model never names has true cans but no interval of named
    right: that counts as a lower end of 0, so "low" (its cans are all read as something else)."""
    named, found = row.get("id_accuracy_ci"), row.get("found_right_ci")
    if not row.get("enough") or not found:
        return "insufficient"
    low = min(named[0] if named else 0.0, found[0])
    return "high" if low >= BADGE_HIGH else "medium" if low >= BADGE_MEDIUM else "low"


def _often_read_as(cells: Mapping[str, int], sku: str) -> str | None:
    """The label the model most often gave to the true cans of `sku` (confusion cells "given|true"), None when it
    never gave them another label; ties go to the first label in order."""
    given: Counter = Counter()
    for key, n in cells.items():
        label, _, true = key.rpartition("|")
        if true == sku and label not in (sku, UNRECOGNIZED, MISSED):
            given[label] += n
    return min(given, key=lambda lb: (-given[lb], lb)) if given else None


@_frees_draws
def sku_reliability(audits: list[dict]) -> dict[str, dict]:
    """What the reliability badge of each model label needs, from these frames and nothing more (no KPIs, no bias):
    {label: {badge, named_right, found_right, true_units, frames, confused_as}}. A number without samples is None;
    true_units and frames are the sample the badge is judged on."""
    tallies = [frame_tallies(a) for a in audits]
    days = [_day_of(a) for a in audits]
    cells = _confusion(audits)["cells"]
    skus = sorted({k.split(":", 1)[1] for t in tallies for k in t if k.startswith("found_right:")})
    out = {}
    for sku in skus:
        row = _two_way(tallies, days, sku, with_bias=False)
        out[sku] = {
            "badge": badge(row),
            "named_right": _value(_column(tallies, f"named_right:{sku}")),
            "found_right": row["found_right"],
            "true_units": _sample(tallies, days, sku)[0],
            "frames": row["frames"],
            "confused_as": _often_read_as(cells, sku),
        }
    return out


def _confusion(audits: list[dict]) -> dict:
    audits = [scoped(a) for a in audits]
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


def _ict(capture_ts: str) -> datetime:
    """A capture timestamp in ICT; one without an offset is taken as ICT already."""
    t = datetime.fromisoformat(capture_ts)
    return t.astimezone(ICT) if t.tzinfo else t.replace(tzinfo=ICT)


def _day_of(audit: dict) -> str:
    return _ict(audit["capture_timestamp"]).date().isoformat()


def period_of(capture_ts: str) -> str:
    """The time of day of a frame, by its ICT hour: morning before 12:00, afternoon 12:00-17:00, evening from 17:00."""
    hour = _ict(capture_ts).hour
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def _period_sku(tallies: list[dict], days: list[str], sku: str) -> dict:
    named, found = _column(tallies, f"named_right:{sku}"), _column(tallies, f"found_right:{sku}")
    true_units, frames, n_days = _sample(tallies, days, sku)
    return {
        "named_right": _value(named),
        "found_right": _value(found),
        "model_units": _sums(named)[1],
        "true_units": true_units,
        "frames": frames,
        "days": n_days,
        "enough": enough(frames, true_units, n_days),
    }


def _by_period(audits: list[dict], tallies: list[dict], days: list[str]) -> dict:
    """Per time of day: frames, identification and present-or-absent agreement with intervals, both ways per SKU."""
    periods = [period_of(a["capture_timestamp"]) for a in audits]
    out = {}
    for period in PERIODS:
        picked = [i for i, p in enumerate(periods) if p == period]
        part, part_days = [tallies[i] for i in picked], [days[i] for i in picked]
        skus = sorted({key.split(":", 1)[1] for t in part for key in t if key.startswith("found_right:")})
        out[period] = {
            "frames": len(part),
            "overall_identification_accuracy": _stat(_column(part, "kpi:overall_identification_accuracy")),
            "presence_agree": _stat(_column(part, "presence_agree")),
            "per_sku": {sku: _period_sku(part, part_days, sku) for sku in skus},
        }
    return out


def by_day(audits: list[dict]) -> list[dict]:
    """Per ICT day: frames, identification, count MAE and the exact + minor rate (no intervals)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in audits:
        groups[_day_of(a)].append(a)
    days = []
    for day in sorted(groups):
        k = kpis(groups[day], [])
        days.append(
            {
                "day": day,
                "audits": len(groups[day]),
                "overall_identification_accuracy": k["overall_identification_accuracy"]["value"],
                "unit_count_mae": k["unit_count_mae"]["value"],
                "exact_or_minor_rate": k["minor_error_rate"]["exact_or_minor"],
            }
        )
    return days


@_frees_draws
def summarize(audits: list[dict], processing_ms: list[int], expected: Expected = None) -> dict:
    """Everything the Model page shows from labelled frames. A number without samples is None, with n 0. Every KPI
    but #11, the two ways per SKU, present or absent and the time-of-day numbers carry a 95% frame-bootstrap
    interval `ci` (None below 2 frames). expected: model labels of the SKUs that must be on the shelf, one set for
    every frame or a set per store_id, so that each frame is held to its own store's list."""
    top = _top_skus(audits)
    tallies = [frame_tallies(a, _expected_of(expected, a), top) for a in audits]
    days = [_day_of(a) for a in audits]
    k = kpis(audits, processing_ms, tallies)
    for name, kpi in k.items():
        if name != "avg_processing_time_ms":
            kpi["ci"] = ratio_ci(_column(tallies, f"kpi:{name}"))
    n_boxes = sum(len(a.get("ai_boxes", [])) for a in audits)
    n_out = sum(v.get("verdict") == "out_of_scope" for a in audits for v in a.get("verdicts", []))
    return {
        "n_audits": len(audits),
        "out_of_scope_share": {"value": _share(n_out, n_boxes), "n": n_boxes},
        "kpis": k,
        "per_sku": _per_sku(audits, tallies, days),
        "confusion": _confusion(audits),
        "by_day": by_day(audits),
        "presence": {name: _stat(_column(tallies, key)) for name, key in PRESENCE.items()},
        "by_period": _by_period(audits, tallies, days),
    }


def _off_by(model: Mapping[str, int], truth: Mapping[str, int]) -> dict[str, Tally]:
    """Units off (model minus truth) over the SKUs either side counted: absolute and signed."""
    counted = [s for s in model.keys() | truth.keys() if model.get(s, 0) > 0 or truth.get(s, 0) > 0]
    diffs = [model.get(s, 0) - truth.get(s, 0) for s in counted]
    return {"count_mae": (sum(map(abs, diffs)), len(diffs)), "count_bias": (sum(diffs), len(diffs))}


@_frees_draws
def check_level(pairs: list[tuple[dict, dict[str, int]]], expected: Expected = None) -> dict:
    """The Dashboard's 5-minute numbers against the truth. Each pair is a scoring frame and the counts, by model
    label, of the check that holds it. Units off per SKU either side counted (absolute and signed: positive counts
    too many) and present-or-absent agreement over the frame's expected SKUs (as in summarize) plus those SKUs, each
    with its interval."""
    tallies = []
    for audit, counts in pairs:
        truth = _truth_counts(scoped(audit))
        tallies.append({**_off_by(counts, truth), **_presence(counts, truth, _expected_of(expected, audit))})
    return {
        "frames": len(pairs),
        **{key: _stat(_column(tallies, key)) for key in ("count_mae", "count_bias", "presence_agree")},
    }


def judged_by_display_check(audit: dict) -> bool:
    """Whether the worker's display check judged this frame: the audit carries the capture's display_score, or
    display_visible False (only a check that ran says False). Frames from before the check, frames whose True was
    copied from an older worker's capture (24/11 13:50-19:03) and frames taken before the worker had learnt the
    display carry neither, and say nothing about the check."""
    score = audit.get("display_score")
    return (isinstance(score, Number) and not isinstance(score, bool)) or audit.get("display_visible") is False


@_frees_draws
def display_agreement(audits: list[dict]) -> dict:
    """The worker's display check against the labellers on the scoring frames it judged: a labelled frame saw the
    display, one skipped as display_away did not; frames skipped for other reasons say nothing about it. Below
    MIN_FRAMES judged frames the agreement is None, with its n."""
    pairs = []  # (the labeller saw the display, the check said it was in view)
    for a in audits:
        labelled = a.get("status") == "done"
        away = a.get("status") == "skipped" and a.get("skip_reason") == "display_away"
        if (labelled or away) and judged_by_display_check(a):
            pairs.append((labelled, a.get("display_visible", True) is not False))
    if len(pairs) < MIN_FRAMES:
        agree = {"value": None, "ci": None, "n": len(pairs)}
    else:
        agree = _stat([(int(seen == said), 1) for seen, said in pairs])
    return {
        "agree": agree,
        "false_not_visible": sum(seen and not said for seen, said in pairs),
        "false_visible": sum(said and not seen for seen, said in pairs),
    }
