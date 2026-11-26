"""The colour gallery: Slide can crops labelled by people, and how it reads a can's flavour (auto-label design 5.4,
slide-fusion design 5.1).

A crop is described by its colour: the middle 70% of its height and 60% of its width, grey-world balanced, a hue x
saturation histogram (18 x 8) of it, square-rooted and of unit length. A can is read by its 10 nearest crops (cosine):
a flavour is named only when it holds at least 60% of their weight, at least 3 of the 10, and the gallery has at
least 20 crops of it; otherwise the read is unsure. Only people's labels enter: the hand-drawn truth and the training
frames (TRN) labelled on the Model page, never automatic labels, never a scoring frame (AUD), and, for a gallery used
to measure, never a held-out frame.

    python -m training.store_view.slide_gallery export-trn --out trn_done.json            (laptop: reads the audits)
    python -m training.store_view.slide_gallery build --truth T --segments S --frames F --trn trn_done.json ^
        [--exclude-holdout] --out slide_gallery_CAM-S01-A_<YYYYMMDD>.npz
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

MIN_IMAGES = 20
K = 10
MIN_SHARE = 0.6
MIN_VOTES = 3
AUDITS_TABLE = "milk-backend-development-audits"
REGION_NAME = "ap-southeast-1"


def _grey_world(img: np.ndarray) -> np.ndarray:
    m = img.reshape(-1, 3).mean(axis=0)
    return np.clip(img * (m.mean() / np.maximum(m, 1)), 0, 255).astype(np.uint8)


def colour(crop: np.ndarray) -> np.ndarray:
    """Unit 144-vector of the crop's middle colours."""
    import cv2

    h, w = crop.shape[:2]
    mid = _grey_world(crop[int(h * 0.15) : int(h * 0.85), int(w * 0.2) : int(w * 0.8)])
    hsv = cv2.cvtColor(mid, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]).ravel()
    hist = np.sqrt(hist / max(float(hist.sum()), 1.0))
    return hist / max(float(np.linalg.norm(hist)), 1e-9)


def mean_colour(feats: list[np.ndarray]) -> np.ndarray | None:
    """The colour of a can seen in several crops: their mean, of unit length again; None when there is no crop."""
    if not feats:
        return None
    m = np.mean(np.stack(feats), axis=0)
    return m / max(float(np.linalg.norm(m)), 1e-9)


@dataclass
class Gallery:
    features: np.ndarray
    labels: np.ndarray
    sources: np.ndarray
    built_at: str
    none_threshold: float | None = None
    objects: np.ndarray | None = None  # the can each crop shows: one truth box cut from many frames is one can

    def save(self, path: Path) -> None:
        np.savez(
            path,
            features=self.features,
            labels=self.labels.astype(str),
            sources=self.sources.astype(str),
            built_at=np.array(self.built_at),
            none_threshold=np.array(np.nan if self.none_threshold is None else self.none_threshold),
            objects=(self.objects if self.objects is not None else self.sources).astype(str),
        )

    @classmethod
    def load(cls, path: Path) -> Gallery:
        d = np.load(path, allow_pickle=False)
        nt = float(d["none_threshold"])
        objects = d["objects"] if "objects" in d.files else None
        return cls(d["features"], d["labels"], d["sources"], str(d["built_at"]), None if np.isnan(nt) else nt, objects)

    def counts(self) -> dict[str, int]:
        """Cans per label (MIN_IMAGES counts cans, not crops); crops when the gallery does not know its cans."""
        if self.objects is None:
            return dict(Counter(self.labels.tolist()))
        return dict(Counter(label for label, _ in set(zip(self.labels.tolist(), self.objects.tolist(), strict=True))))


@dataclass(frozen=True)
class GalleryVote:
    sku: str | None
    share: float
    votes: int
    none_hit: bool


def read(gallery: Gallery, feature: np.ndarray, k: int = K) -> GalleryVote:
    """The flavour the k nearest crops name, or sku None when they are not sure enough (see the module text)."""
    if not len(gallery.labels):
        return GalleryVote(None, 0.0, 0, False)
    sims = gallery.features @ feature
    idx = np.argsort(-sims)[:k]
    weight: Counter = Counter()
    count: Counter = Counter()
    for i in idx:
        weight[gallery.labels[i]] += max(float(sims[i]), 0.0)
        count[gallery.labels[i]] += 1
    top, top_weight = weight.most_common(1)[0]
    share = top_weight / max(sum(weight.values()), 1e-9)
    counts = gallery.counts()
    sure = top != "none" and share >= MIN_SHARE and count[top] >= MIN_VOTES and counts.get(top, 0) >= MIN_IMAGES
    first = idx[0]
    none_hit = (
        gallery.none_threshold is not None
        and gallery.labels[first] == "none"
        and float(sims[first]) >= gallery.none_threshold
    )
    return GalleryVote(top if sure else None, share, count[top], bool(none_hit))


def trn_rows(audits: list[dict]) -> list[tuple[str, list[int], str]]:
    """(capture_id, box x y w h, label) of each judged box of the done training audits: correct -> the model's label,
    wrong_sku -> the true one, not_product -> "none"; out of scope and anything not judged are left out."""
    out = []
    for a in audits:
        if not str(a.get("audit_id", "")).startswith("TRN-") or a.get("status") != "done":
            continue
        boxes = {b["box_id"]: b for b in json.loads(a.get("ai_boxes_json") or "[]")}
        for v in json.loads(a.get("verdicts_json") or "[]"):
            b = boxes.get(v.get("box_id"))
            if b is None:
                continue
            label = {"correct": b.get("sku_id"), "wrong_sku": v.get("true_sku_id"), "not_product": "none"}.get(
                v.get("verdict")
            )
            if label:
                out.append((a["capture_id"], [int(x) for x in b["box"]], label))
    return out


def crop_of(image: np.ndarray, box) -> np.ndarray | None:
    x, y, w, h = (int(round(v)) for v in box)
    crop = image[max(y, 0) : y + h, max(x, 0) : x + w]
    return crop if crop.size and crop.shape[0] >= 4 and crop.shape[1] >= 4 else None


def build(
    truth: dict[str, list[dict]],
    segments: list[dict],
    frames_dir: Path,
    trn: list[dict],
    exclude_holdout: bool,
    per_keyframe: int = 30,
    min_sim: float = 0.85,
) -> Gallery:
    """The gallery from the hand-drawn truth (each box cut from up to per_keyframe frames of its segment whose box area
    still looks like the keyframe's) and from the done TRN audits. Scoring frames never enter; with exclude_holdout,
    held-out keyframes and held-out TRN frames do not either."""
    import cv2

    from training.store_view.dataset import read_scoring_frames, spread
    from training.store_view.segments import holdout, signature, similarity

    scoring = read_scoring_frames(frames_dir)
    paths = {p.stem: p for p in frames_dir.glob("*/*.jpg")}
    feats, labels, sources, objects = [], [], [], []

    def add(image, box, label, source, obj):
        crop = crop_of(image, box)
        if crop is not None:
            feats.append(colour(crop))
            labels.append(label)
            sources.append(source)
            objects.append(obj)

    seg_of = {s["keyframe"]: s for s in segments if s.get("kind") == "day"}
    for key, rows in truth.items():
        seg = seg_of.get(key)
        if seg is None or key not in paths or (exclude_holdout and seg.get("split") == "holdout"):
            continue
        key_grey = cv2.imread(str(paths[key]), cv2.IMREAD_GRAYSCALE)
        usable = [
            (i, r) for i, r in enumerate(rows) if r.get("kind") != "ignore" and r.get("sku") not in (None, "unknown")
        ]
        for cid in spread([c for c in seg["members"] if c not in scoring and c in paths], per_keyframe):
            image = cv2.imread(str(paths[cid]))
            grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            for i, r in usable:
                x, y, w, h = r["box"]
                area = (max(0, x - 8), max(0, y - 8), x + w + 8, y + h + 8)
                if cid != key and similarity(signature(grey, area), signature(key_grey, area)) < min_sim:
                    continue
                add(image, r["box"], r["sku"], cid, f"truth:{key}#{i}")
    stamp = {a["capture_id"]: a.get("capture_timestamp", "") for a in trn}
    cache: dict[str, np.ndarray] = {}
    for cid, box, label in trn_rows(trn):
        if cid in scoring or cid not in paths or (exclude_holdout and stamp.get(cid) and holdout(stamp[cid])):
            continue
        if cid not in cache:
            cache.clear()
            cache[cid] = cv2.imread(str(paths[cid]))
        add(cache[cid], box, label, cid, f"trn:{cid}@{box[0]},{box[1]}")
    return Gallery(
        np.stack(feats) if feats else np.zeros((0, 144)),
        np.array(labels, dtype=str),
        np.array(sources, dtype=str),
        datetime.now().isoformat(timespec="seconds"),
        None,
        np.array(objects, dtype=str),
    )


def _export_trn(out: Path) -> int:
    import boto3
    from boto3.dynamodb.conditions import Attr

    table = boto3.resource("dynamodb", region_name=REGION_NAME).Table(AUDITS_TABLE)
    kw = {"FilterExpression": Attr("status").eq("done") & Attr("audit_id").begins_with("TRN-")}
    items, resp = [], table.scan(**kw)
    items += resp["Items"]
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kw)
        items += resp["Items"]
    keep = ("audit_id", "status", "capture_id", "capture_timestamp", "ai_boxes_json", "verdicts_json")
    out.write_text(json.dumps([{k: str(i.get(k, "")) for k in keep} for i in items], indent=1), encoding="utf-8")
    return len(items)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    e = sub.add_parser("export-trn")
    e.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build")
    b.add_argument("--truth", type=Path, required=True)
    b.add_argument("--segments", type=Path, required=True)
    b.add_argument("--frames", type=Path, required=True)
    b.add_argument("--trn", type=Path, required=True)
    b.add_argument("--exclude-holdout", action="store_true")
    b.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.command == "export-trn":
        print(f"{_export_trn(args.out)} done TRN audits -> {args.out}")
        return
    g = build(
        json.loads(args.truth.read_text(encoding="utf-8")),
        json.loads(args.segments.read_text(encoding="utf-8")),
        args.frames,
        json.loads(args.trn.read_text(encoding="utf-8")),
        args.exclude_holdout,
    )
    g.save(args.out)
    print(f"{len(g.labels)} crops -> {args.out}: {dict(sorted(g.counts().items()))}")


if __name__ == "__main__":
    main()
