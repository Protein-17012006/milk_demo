"""Whether the person-labelled gallery may rename Slide can flavours: the measure and the rule that reads it.

Each judged box of the live detector (the scoring audits, AUD-) is named twice: by the live release alone ("without")
and after the gallery has read the same box ("with"), against what the person answered. A day's boxes are read only by a
gallery built without that day, so the numbers are about days the gallery never saw. The rule was fixed before any
number was seen; the gallery is enabled for a product group only when all three hold:

    1. it fixes more boxes than it breaks;
    2. the two-sided binomial test on fixed vs broken gives p < 0.05;
    3. no product with at least 10 boxes is right more than 5 points less often with the gallery than without it.

And it cannot rename at all when it knows fewer than 2 product names (each with at least 20 cans).

    python -m training.store_view.gallery_measure --audits A --truth T --segments S --frames F [F ...] ^
        --camera-config C --out O.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

from milk.cvoutput import Detection  # noqa: E402
from milk.gallery import MIN_IMAGES, Gallery, GalleryNamer  # noqa: E402
from training.store_view.slide_gallery import build, day_of  # noqa: E402

ALPHA = 0.05
MIN_SKU_BOXES = 10
MAX_SKU_DROP = 0.05
MIN_NAMES = 2


@dataclass(frozen=True)
class ScoredBox:
    capture_id: str
    day: str
    box: tuple[int, int, int, int]
    live: str  # the name the live release gave the box
    truth: str  # the name the person says it is


@dataclass
class GroupResult:
    group: str
    n: int
    right_without: int
    right_with: int
    fixed: int
    broken: int
    unsure: int
    per_sku: dict[str, tuple[int, int, int]]  # truth -> (boxes, right without the gallery, right with it)
    names: int  # product names with at least MIN_IMAGES cans, the smallest over the galleries used
    days: list[str] = field(default_factory=list)
    skipped: int = 0  # boxes whose frame image could not be read
    p: float = 1.0  # two-sided binomial p of fixed against broken
    fixed_boxes: list[dict] = field(default_factory=list)  # {capture_id, box, live, gallery, truth}, for a check by eye
    broken_boxes: list[dict] = field(default_factory=list)


def binomial_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial test with p = 1/2 (a copy of backend/compare.py's, which pulls in model_health)."""
    if n <= 0:
        return 1.0
    low = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(low + 1)) / 2**n
    return min(1.0, 2 * tail)


def scored_boxes(audits: list[dict]) -> list[ScoredBox]:
    """The judged boxes of the done scoring audits (AUD-) that the person called correct or wrong_sku, with the name the
    live release gave them (a merged frame keeps it in live_sku; boxes only the candidate drew are left out)."""
    out = []
    for a in audits:
        if not str(a.get("audit_id", "")).startswith("AUD-") or a.get("status") != "done":
            continue
        boxes = {b["box_id"]: b for b in json.loads(a.get("ai_boxes_json") or "[]")}
        for v in json.loads(a.get("verdicts_json") or "[]"):
            b = boxes.get(v.get("box_id"))
            if b is None or v.get("verdict") not in ("correct", "wrong_sku") or b.get("src") == "cand":
                continue
            live = b.get("live_sku") if "src" in b else b.get("sku_id")
            if not live:
                continue
            truth = live if v["verdict"] == "correct" else v.get("true_sku_id")
            if truth:
                out.append(
                    ScoredBox(a["capture_id"], day_of(a["capture_id"]), tuple(int(x) for x in b["box"]), live, truth)
                )
    return out


def names_known(gallery: Gallery) -> int:
    """How many product names (not "none") the gallery has at least MIN_IMAGES cans of."""
    return sum(1 for label, n in gallery.counts().items() if label != "none" and n >= MIN_IMAGES)


def measure(
    boxes: list[ScoredBox],
    gallery_for_day: Callable[[str], Gallery],
    image_of: Callable[[str], np.ndarray | None],
    skus: set[str],
    product: Mapping[str, str],
    group: str = "",
) -> GroupResult:
    """With and without the gallery over the boxes whose live name is in skus. gallery_for_day(day) must give a gallery
    that never saw that day; it is asked once per day, and each frame image once. A frame that cannot be read has its
    boxes skipped and counted."""
    namers: dict[str, GalleryNamer] = {}
    names: list[int] = []
    by_frame: dict[str, list[ScoredBox]] = defaultdict(list)
    for b in boxes:
        if b.live in skus:
            by_frame[b.capture_id].append(b)
    n = rw = rwith = fixed = broken = unsure = skipped = 0
    per: dict[str, list[int]] = {}
    days: set[str] = set()
    fixed_boxes: list[dict] = []
    broken_boxes: list[dict] = []
    for cid in sorted(by_frame):
        image = image_of(cid)
        if image is None:
            skipped += len(by_frame[cid])
            continue
        for b in by_frame[cid]:
            if b.day not in namers:
                gallery = gallery_for_day(b.day)
                namers[b.day] = GalleryNamer(gallery, product)
                names.append(names_known(gallery))
            det = namers[b.day].name(image, [Detection(b.live, product.get(b.live, b.live), 1.0, b.box)])[0]
            without, with_ = b.live == b.truth, det.sku_id == b.truth
            n += 1
            rw += without
            rwith += with_
            fixed += with_ and not without
            broken += without and not with_
            if with_ != without:
                listed = {
                    "capture_id": b.capture_id,
                    "box": list(b.box),
                    "live": b.live,
                    "gallery": det.sku_id,
                    "truth": b.truth,
                }
                (fixed_boxes if with_ else broken_boxes).append(listed)
            unsure += det.unsure
            row = per.setdefault(b.truth, [0, 0, 0])
            row[0] += 1
            row[1] += without
            row[2] += with_
            days.add(b.day)
    return GroupResult(
        group,
        n,
        rw,
        rwith,
        fixed,
        broken,
        unsure,
        {k: (v[0], v[1], v[2]) for k, v in sorted(per.items())},
        min(names, default=0),
        sorted(days),
        skipped,
        binomial_two_sided(min(fixed, broken), fixed + broken),
        fixed_boxes,
        broken_boxes,
    )


def decide(r: GroupResult) -> tuple[bool, list[str]]:
    """Whether the gallery may rename this group's boxes, and the reasons it may not (empty when it may)."""
    if r.n == 0:
        return False, [f"no judged box could be read: {r.skipped} skipped"]
    if r.names < MIN_NAMES:
        return False, [f"cannot rename: the gallery knows {r.names} product names"]
    why = []
    if not r.fixed > r.broken:
        why.append(f"it fixes {r.fixed} boxes and breaks {r.broken}: it must fix more than it breaks")
    p = binomial_two_sided(min(r.fixed, r.broken), r.fixed + r.broken)
    if not p < ALPHA:
        why.append(f"p = {p:.3f} for {r.fixed} fixed against {r.broken} broken: it must be below {ALPHA}")
    for sku, (n, without, with_) in sorted(r.per_sku.items()):
        if n >= MIN_SKU_BOXES and (without - with_) / n > MAX_SKU_DROP + 1e-9:
            why.append(
                f"{sku} falls from {without}/{n} right to {with_}/{n}: more than {MAX_SKU_DROP * 100:.0f} points"
            )
    return not why, why


def _table(r: GroupResult, enable: bool, why: list[str]) -> str:
    p = binomial_two_sided(min(r.fixed, r.broken), r.fixed + r.broken)
    lines = [
        f"== {r.group}: days {', '.join(r.days) or '-'}",
        f"n {r.n}  right without {r.right_without}  right with {r.right_with}  fixed {r.fixed}  broken {r.broken}"
        f"  unsure {r.unsure}  skipped {r.skipped}  p {p:.3f}  names {r.names}",
    ]
    lines += [f"  {sku}: n {n}, without {a}, with {b}" for sku, (n, a, b) in sorted(r.per_sku.items())]
    lines.append("decision: " + ("ENABLE" if enable else "DO NOT ENABLE: " + "; ".join(why)))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    import cv2

    from milk.catalog import product_names

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audits", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--frames", type=Path, nargs="+", required=True)
    ap.add_argument("--camera-config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    audits = json.loads(args.audits.read_text(encoding="utf-8"))
    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    segments = json.loads(args.segments.read_text(encoding="utf-8"))
    config = json.loads(args.camera_config.read_text(encoding="utf-8"))
    paths = {p.stem: p for f in args.frames for p in f.glob("*/*.jpg")}
    product = product_names()
    scored = scored_boxes(audits)
    results = {}
    for name, group in config["groups"].items():
        skus = set(group.get("skus") or [])
        method = (group.get("gallery") or {}).get("method")
        if not skus or not method:
            continue
        galleries: dict[str, Gallery] = {}

        def gallery_for_day(day: str, group=group, skus=skus, method=method, name=name, galleries=galleries) -> Gallery:
            if day not in galleries:
                g = build(
                    truth,
                    segments,
                    args.frames,
                    audits,
                    True,
                    exclude_days=frozenset({day}),
                    skus=frozenset(skus),
                    region=tuple(group["region"]),
                )
                if method != "colour" and names_known(g) >= MIN_NAMES:
                    sys.exit(
                        f"{name}: the {method!r} method is not built yet, and this gallery knows enough names to need it"
                    )
                galleries[day] = g
            return galleries[day]

        def image_of(cid: str) -> np.ndarray | None:
            return cv2.imread(str(paths[cid])) if cid in paths else None

        r = measure([b for b in scored if b.live in skus], gallery_for_day, image_of, skus, product, name)
        enable, why = decide(r)
        print(_table(r, enable, why))
        results[name] = {**asdict(r), "enable": enable, "reasons": why}
    out = {"camera": config.get("camera"), "built_at": datetime.now().isoformat(timespec="seconds"), "groups": results}
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
