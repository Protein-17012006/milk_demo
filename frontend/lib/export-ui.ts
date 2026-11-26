// The date range of a CSV export and the lines the export button shows.
// Days are days of the store's clock (UTC+7), written YYYY-MM-DD. The backend keeps a capture for 7 days, so a
// range holds at most 7 days and cannot start earlier than 6 days ago.

export type ExportKind = "cv-output" | "capture-log";

/** Both ends are included. */
export interface ExportRange {
  from: string;
  to: string;
}

export const EXPORT_MAX_DAYS = 7;

const DAY_MS = 86_400_000;
const ICT_OFFSET_MS = 7 * 3_600_000;

/** The UTC+7 day of a moment. */
export function ictDay(now: Date): string {
  return new Date(now.getTime() + ICT_OFFSET_MS).toISOString().slice(0, 10);
}

const shiftDay = (day: string, days: number) =>
  new Date(Date.parse(`${day}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);

/** "2026-11-26" as "26/11". */
const shortDay = (day: string) => `${day.slice(8, 10)}/${day.slice(5, 7)}`;

export function defaultExportRange(now: Date): ExportRange {
  const today = ictDay(now);
  return { from: today, to: today };
}

/** The oldest day that still has captures. */
export function earliestExportDay(now: Date): string {
  return shiftDay(ictDay(now), -(EXPORT_MAX_DAYS - 1));
}

/** Why this range cannot be exported, or null when it can. A range that passes is at most EXPORT_MAX_DAYS long. */
export function exportRangeError(range: ExportRange, now: Date): string | null {
  const { from, to } = range;
  if (!from || !to) return "Choose the first and the last day.";
  if (from > to) return "The first day is after the last day.";
  if (to > ictDay(now)) return "The last day is in the future.";
  const earliest = earliestExportDay(now);
  if (from < earliest) {
    return `Captures are kept for ${EXPORT_MAX_DAYS} days. Choose days from ${shortDay(earliest)} on.`;
  }
  return null;
}

/** The line shown once the file is on its way. rows: data rows in the file, the header not counted. */
export function exportDoneText(rows: number, range: ExportRange): string {
  const oneDay = range.from === range.to;
  if (rows === 0) {
    const when = oneDay ? `on ${shortDay(range.to)}` : `from ${shortDay(range.from)} to ${shortDay(range.to)}`;
    return `No captures ${when}: the file has only the header row.`;
  }
  const span = oneDay ? shortDay(range.to) : `${shortDay(range.from)} to ${shortDay(range.to)}`;
  return `Downloaded ${rows.toLocaleString("en-US")} ${rows === 1 ? "row" : "rows"} for ${span}.`;
}
