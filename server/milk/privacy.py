"""Hiding people before any frame is stored or shown.

The team keeps this as its own requirement (Sprint Report 15/11). Two blurrers can be
chained:

- PersonBlurrer pixelates whole people found by a COCO detector (class 0, "person"),
  for example the stock YOLO26s weights. It also covers people seen from above, whose
  faces a face detector misses. Needs ultralytics, so it runs on the GPU worker.
- FaceBlurrer pixelates faces found by OpenCV's YuNet, on a downscaled copy for speed.
  It is light enough for the hub's CPU and catches faces the person detector missed.

Both can still miss someone; stored frames are reviewed with that limit in mind.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def pixelate(image: np.ndarray, x0: int, y0: int, x1: int, y1: int, blocks: int = 6) -> bool:
    """Replaces the region with a coarse mosaic, in place. False if the region is empty."""
    import cv2

    h, w = image.shape[:2]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return False
    region = image[y0:y1, x0:x1]
    tiny = cv2.resize(region, (blocks, blocks), interpolation=cv2.INTER_AREA)
    image[y0:y1, x0:x1] = cv2.resize(tiny, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
    return True


class FaceBlurrer:
    def __init__(self, model_path: str, score_threshold: float = 0.6, detect_max_side: int = 1280) -> None:
        import cv2

        if not Path(model_path).is_file():
            raise FileNotFoundError(model_path)
        self._cv2 = cv2
        self._detector = cv2.FaceDetectorYN.create(model_path, "", (320, 320), score_threshold, 0.3, 5000)
        self._max_side = detect_max_side

    def blur(self, image: np.ndarray) -> tuple[np.ndarray, int]:
        cv2 = self._cv2
        h, w = image.shape[:2]
        scale = min(1.0, self._max_side / max(h, w))
        small = (
            cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
            if scale < 1
            else image
        )
        self._detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = self._detector.detect(small)
        if faces is None:
            return image, 0
        out = image.copy()
        count = 0
        for face in faces:
            x, y, fw, fh = (float(v) / scale for v in face[:4])
            pad_w, pad_h = 0.3 * fw, 0.3 * fh
            if pixelate(out, int(x - pad_w), int(y - pad_h), int(x + fw + pad_w), int(y + fh + pad_h)):
                count += 1
        return out, count


def person_regions(boxes, image_height: int, mode: str = "head") -> list[tuple[int, int, int, int]]:
    """Regions to hide for person boxes (x0, y0, x1, y1).

    head: the top 40% of each person (head and shoulders), as carton_recognition's blur_people does,
    so the shelf behind or below a shopper stays visible; a box shorter than a quarter of the image
    (often a head alone, or someone far away) is hidden whole. body: every person box whole."""
    regions = []
    for x0, y0, x1, y1 in boxes:
        w, h = x1 - x0, y1 - y0
        if mode == "body" or h < 0.25 * image_height:
            regions.append((x0 - 0.1 * w, y0 - 0.1 * h, x1 + 0.1 * w, y1 + 0.1 * h))
        else:
            regions.append((x0 - 0.1 * w, y0 - 0.03 * h, x1 + 0.1 * w, y0 + 0.40 * h))
    return [tuple(int(round(v)) for v in r) for r in regions]


class PersonBlurrer:
    def __init__(
        self, model_path: str, conf: float = 0.25, imgsz: int = 1280, device: str | None = None, mode: str = "head"
    ) -> None:
        from ultralytics import YOLO  # only on machines that run the model

        if not Path(model_path).is_file():
            raise FileNotFoundError(model_path)
        if mode not in ("head", "body"):
            raise ValueError(f"person blur mode must be head or body, not {mode!r}")
        self._model = YOLO(model_path)
        self._conf, self._imgsz, self._device, self._mode = conf, imgsz, device or None, mode

    def blur(self, image: np.ndarray) -> tuple[np.ndarray, int]:
        result = self._model.predict(
            image, classes=[0], conf=self._conf, imgsz=self._imgsz, device=self._device, verbose=False
        )[0]
        boxes = [] if result.boxes is None else result.boxes.xyxy.cpu().numpy()
        if len(boxes) == 0:
            return image, 0
        out = image.copy()
        count = 0
        for x0, y0, x1, y1 in person_regions(boxes, image.shape[0], self._mode):
            if pixelate(out, x0, y0, x1, y1, blocks=8):
                count += 1
        return out, count


class ChainBlurrer:
    """Runs blurrers one after another; the count is the total of what they hid."""

    def __init__(self, blurrers: list) -> None:
        self._blurrers = blurrers

    def blur(self, image: np.ndarray) -> tuple[np.ndarray, int]:
        total = 0
        for blurrer in self._blurrers:
            image, n = blurrer.blur(image)
            total += n
        return image, total


def load_blurrer(
    face_model: str, person_model: str | None = None, device: str | None = None, person_mode: str = "head"
) -> ChainBlurrer | None:
    """Every blurrer that can load. None only if none can: then nothing is stored."""
    blurrers = []
    if person_model:
        try:
            blurrers.append(PersonBlurrer(person_model, device=device, mode=person_mode))
            log.info("person blurring on (%s, %s)", person_model, person_mode)
        except Exception as exc:  # noqa: BLE001
            log.warning("person blurring unavailable (%s); faces only", exc)
    try:
        blurrers.append(FaceBlurrer(face_model))
    except Exception as exc:  # noqa: BLE001
        log.warning("face blurring unavailable (%s)", exc)
    if not blurrers:
        log.error("no blurring available; frames will not be stored")
        return None
    return ChainBlurrer(blurrers)
