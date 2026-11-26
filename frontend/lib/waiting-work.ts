// The team's waiting work, gathered in one line of the Dashboard: readings to review (Category), frames to label
// (Model) and shelf events nobody confirmed yet (Recent Shelf Activities). Each item is a link to where the work
// is done; the three tools stay on their own pages.

export interface WaitingItem {
  key: "readings" | "frames" | "events";
  text: string;
  href: string;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** The waiting work as links, in this order. A count of 0, or null (not loaded), gives no item; moreEvents: the
 * events counted are only the latest page and older ones wait too. */
export function waitingWork(counts: {
  readings: number | null;
  frames: number | null;
  events: number | null;
  moreEvents?: boolean;
}): WaitingItem[] {
  const items: WaitingItem[] = [];
  const { readings, frames, events } = counts;
  if (readings) {
    items.push({ key: "readings", text: `${readings} ${plural(readings, "reading", "readings")} to review`, href: "/category" });
  }
  if (frames) {
    items.push({ key: "frames", text: `${frames} ${plural(frames, "frame", "frames")} to label`, href: "/model" });
  }
  if (events) {
    const shown = counts.moreEvents ? `${events}+` : String(events);
    items.push({
      key: "events",
      text: `${shown} ${counts.moreEvents ? "shelf events" : plural(events, "shelf event", "shelf events")} to confirm`,
      href: "#recent-shelf-activities",
    });
  }
  return items;
}

/** Events without a verdict among those given (the latest page of Recent Shelf Activities). */
export function unconfirmedEvents(items: { verdict?: string }[]): number {
  return items.filter((item) => !item.verdict).length;
}
