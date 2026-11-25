"""The auto-labeller's core (auto-label design 5.3-5.4): the boxes of a segment gathered into cans, and the decision
for each can. Pure functions; models and files live in auto_label_run.py.

Within a day segment the arrangement does not change, so a can stands in one place: its boxes from both sources and
every frame are gathered by position into a Track. A box joins the track it overlaps best when they are the same can:
IoU >= 0.5, or the smaller box lies (80% of it) inside the larger, as a body-only box from the detector does inside
YOLOE's lid-and-body box.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from training.store_view.proposers import Proposal
from training.store_view.slide_gallery import GalleryVote


def _overlap(a, b) -> tuple[float, float]:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area_a, area_b = a[2] * a[3], b[2] * b[3]
    return inter / max(area_a + area_b - inter, 1e-9), inter / max(min(area_a, area_b), 1e-9)


def same_can(a_box, b_box) -> bool:
    iou, inside = _overlap(a_box, b_box)
    return iou >= 0.5 or inside >= 0.8


@dataclass
class Track:
    id: str
    box: tuple[float, float, float, float]
    seen: dict[str, dict[str, Proposal]] = field(default_factory=dict)
    votes: dict[str, GalleryVote] = field(default_factory=dict)

    def proposals(self) -> list[Proposal]:
        return [p for slot in self.seen.values() for p in slot.values()]

    def box_in(self, capture_id: str) -> tuple[float, float, float, float] | None:
        """The track's own box in that frame: the detector's, else YOLOE's; None when it was not seen there."""
        slot = self.seen.get(capture_id, {})
        p = slot.get("A") or slot.get("B")
        return p.box if p else None


def cluster(frames: dict[str, list[Proposal]], segment_id: str) -> list[Track]:
    """The cans of a segment, frames taken in time order (capture ids sort by time); each source keeps its surer box
    per frame; a track's box is the median of all its boxes."""
    tracks: list[Track] = []
    for cid in sorted(frames):
        touched = set()
        for p in sorted(frames[cid], key=lambda p: -p.conf):
            matches = [(t, _overlap(p.box, t.box)[0]) for t in tracks if same_can(p.box, t.box)]
            if matches:
                track = max(matches, key=lambda m: m[1])[0]
            else:
                track = Track(f"{segment_id}-t{len(tracks)}", tuple(float(v) for v in p.box))
                tracks.append(track)
            slot = track.seen.setdefault(cid, {})
            if p.source not in slot:
                slot[p.source] = p
                touched.add(track.id)
        for track in tracks:
            if track.id in touched:
                boxes = np.array([p.box for p in track.proposals()], dtype=float)
                track.box = tuple(float(v) for v in np.median(boxes, axis=0))
    return tracks
