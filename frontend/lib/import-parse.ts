// Reads a catalog file chosen in Settings (SKU master, store list) into the rows the import API takes.

/**
 * `.json`: a list of rows, or an object whose `items` is that list. Any other file is read as CSV: the first line
 * names the columns, a leading BOM and the quotes around a cell are dropped, an empty cell sets no key, and blank
 * lines are skipped. A cell cannot hold a comma. Returns [] when the file has no rows; invalid JSON throws.
 */
export function parseImportFile(fileName: string, text: string): Record<string, unknown>[] {
  if (fileName.toLowerCase().endsWith(".json")) {
    const parsed: unknown = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed as Record<string, unknown>[];
    const items = (parsed as { items?: unknown } | null)?.items;
    return Array.isArray(items) ? (items as Record<string, unknown>[]) : [];
  }
  const cells = (line: string) => line.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
  const lines = text
    .replace(/^﻿/, "")
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "");
  if (lines.length < 2) return [];
  const headers = cells(lines[0]);
  return lines.slice(1).map((line) => {
    const values = cells(line);
    const row: Record<string, unknown> = {};
    headers.forEach((header, i) => {
      if (values[i] !== undefined && values[i] !== "") row[header] = values[i];
    });
    return row;
  });
}
