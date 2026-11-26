// The sidebar's two rules: when it is collapsed, and which item is the current page.

/** A phone-width screen: the sidebar would take 216 of about 390 px, so it starts collapsed there. */
export const NARROW_QUERY = "(max-width: 767px)";

/** choice: what the user last pressed (true = collapsed), null until they press; their choice wins over the width. */
export function isCollapsed(choice: boolean | null, narrow: boolean): boolean {
  return choice ?? narrow;
}

/** Whether a sidebar item is the current page. "/" shows the Dashboard, so the Dashboard item is current there too. */
export function isNavActive(href: string, pathname: string): boolean {
  if (href === "/dashboard" && pathname === "/") return true;
  return pathname === href || pathname.startsWith(`${href}/`);
}
