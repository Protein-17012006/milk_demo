// Zoom region for the frame viewer: boxes in a 2560×1440 store frame are tiny, so the viewer opens on
// the area around them. Pure and dependency-free so Node can unit-test it.

/** [x, y, width, height] in frame pixels, as the CV Output bounding_box column. */
export type Box = [number, number, number, number];

export interface Region {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * The union of the boxes, grown on every side by the largest box side, at least 1/6 of the frame wide,
 * widened to the frame's aspect ratio around its centre and kept inside the frame.
 * No boxes, or a region as large as the frame, gives the full frame.
 */
export function focusRegion(boxes: Box[], frameW: number, frameH: number): Region {
  const full = { x: 0, y: 0, w: frameW, h: frameH };
  if (boxes.length === 0) return full;

  const margin = Math.max(...boxes.map(([, , w, h]) => Math.max(w, h)));
  const x0 = Math.min(...boxes.map(([x]) => x)) - margin;
  const y0 = Math.min(...boxes.map(([, y]) => y)) - margin;
  const x1 = Math.max(...boxes.map(([x, , w]) => x + w)) + margin;
  const y1 = Math.max(...boxes.map(([, y, , h]) => y + h)) + margin;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;

  const aspect = frameW / frameH;
  let w = Math.max(x1 - x0, frameW / 6);
  let h = y1 - y0;
  if (w / h > aspect) h = w / aspect;
  else w = h * aspect;
  if (w >= frameW || h >= frameH) return full;

  const x = Math.min(Math.max(cx - w / 2, 0), frameW - w);
  const y = Math.min(Math.max(cy - h / 2, 0), frameH - h);
  return { x, y, w, h };
}
