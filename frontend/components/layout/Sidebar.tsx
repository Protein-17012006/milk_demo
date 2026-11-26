"use client";

import React, { useEffect, useRef, useState, useSyncExternalStore } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  PieChart,
  Box,
  Gauge,
  Settings,
  ArrowUpDown,
  ArrowLeftToLine,
  LogIn,
  LogOut,
  UserPlus,
} from "lucide-react";
import { useAuth, type CognitoGroup } from "@/lib/auth";
import { NARROW_QUERY, isCollapsed, isNavActive } from "@/lib/sidebar-ui";

export type NavItemId = "dashboard" | "category" | "model" | "settings";

const PRIMARY_NAV_ITEMS: {
  id: NavItemId;
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  /** Only these groups see the item; none means everyone. */
  groups?: CognitoGroup[];
}[] = [
  { id: "dashboard", label: "Dashboard", href: "/dashboard", icon: PieChart },
  { id: "category", label: "Category", href: "/category", icon: Box },
  { id: "model", label: "Model", href: "/model", icon: Gauge, groups: ["team_admin", "field_team"] },
];

function subscribeNarrow(onChange: () => void) {
  const query = window.matchMedia(NARROW_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
const readNarrow = () => window.matchMedia(NARROW_QUERY).matches;
// The prerendered page has no screen: it is drawn wide, and the CSS below narrows it on a phone before React starts.
const narrowWhenPrerendered = () => false;

export function Sidebar() {
  // null until the user presses the collapse button; from then on their choice wins over the screen width.
  const [choice, setChoice] = useState<boolean | null>(null);
  const narrow = useSyncExternalStore(subscribeNarrow, readNarrow, narrowWhenPrerendered);
  const collapsed = isCollapsed(choice, narrow);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const { user, isAuthenticated, signOut, hasGroup } = useAuth();
  const pathname = usePathname();
  const accountMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (
        accountMenuRef.current &&
        !accountMenuRef.current.contains(e.target as Node)
      ) {
        setAccountMenuOpen(false);
      }
    }
    if (accountMenuOpen) {
      document.addEventListener("mousedown", handleOutside);
    }
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [accountMenuOpen]);

  const handleToggleCollapse = () => {
    setAccountMenuOpen(false);
    setChoice(!collapsed);
  };

  const settingsActive = isNavActive("/settings", pathname);
  // Until the user chooses, the width also follows the screen in CSS, so a phone never shows the wide bar first.
  const widthClass =
    choice === null ? "w-[216px] max-md:w-[56px]" : collapsed ? "w-[56px]" : "w-[216px]";

  return (
    <aside
      aria-label="Primary navigation"
      data-sidebar={collapsed ? "collapsed" : "open"}
      className={`relative flex h-full shrink-0 flex-col overflow-hidden bg-white border-r border-[#676767]/25 transition-[width] duration-200 ease-[cubic-bezier(0.2,0,0,1)] will-change-[width] select-none ${widthClass}`}
    >
      {/* Top Account / Brand Section — icon stays locked at x=14px (centered in 56px) */}
      <div
        ref={accountMenuRef}
        className="relative flex h-[61px] shrink-0 items-center border-b border-[#676767]/15 px-[14px]"
      >
        <Link href="/" className="relative h-[28px] w-[28px] shrink-0">
          <Image
            src="/images/logo-database.png"
            alt="Project A logo"
            width={28}
            height={28}
            className="h-[28px] w-[28px] object-contain"
            priority
          />
        </Link>
        <button
          type="button"
          tabIndex={collapsed ? -1 : 0}
          aria-hidden={collapsed}
          aria-expanded={accountMenuOpen}
          onClick={() => setAccountMenuOpen((prev) => !prev)}
          className={`ml-[10px] flex min-w-0 flex-1 items-center justify-between gap-1 rounded-md py-1 pr-1 text-left hover:bg-black/[0.03] transition-opacity duration-150 whitespace-nowrap cursor-pointer ${
            collapsed ? "pointer-events-none opacity-0" : "opacity-100"
          }`}
          title="Account options"
        >
          <span className="truncate text-[12px] font-normal text-black">
            {isAuthenticated && user?.email ? user.email : "Not signed in"}
          </span>
          <ArrowUpDown
            className="h-[13px] w-[13px] shrink-0 text-black/55"
            strokeWidth={1.7}
          />
        </button>

        {accountMenuOpen && !collapsed && (
          <div className="absolute left-2.5 right-2.5 top-[55px] z-40 rounded-[8px] border border-[#E5E7EB] bg-white p-1 shadow-[0_8px_22px_rgba(0,0,0,0.08)]">
            {isAuthenticated && user ? (
              <>
                <div className="border-b border-[#F3F4F6] px-2.5 py-1.5">
                  <p className="truncate text-[11.5px] font-medium text-[#111827]">
                    {user.email}
                  </p>
                  <p className="mt-0.5 text-[10.5px] font-medium text-[#EE730A]">
                    {user.groups.length > 0
                      ? user.groups.join(", ")
                      : "Waiting for approval"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAccountMenuOpen(false);
                    signOut();
                  }}
                  className="mt-0.5 flex w-full items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-left text-[12.5px] font-medium text-[#B91C1C] hover:bg-[#FEF2F2] cursor-pointer"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Sign out</span>
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setAccountMenuOpen(false)}
                  className="flex items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-[12.5px] font-medium text-[#111827] hover:bg-[#F7F8FA]"
                >
                  <LogIn className="h-3.5 w-3.5 text-[#6B7280]" />
                  <span>Log in</span>
                </Link>
                <Link
                  href="/register"
                  onClick={() => setAccountMenuOpen(false)}
                  className="flex items-center gap-2 rounded-[6px] px-2.5 py-1.5 text-[12.5px] font-medium text-[#111827] hover:bg-[#F7F8FA]"
                >
                  <UserPlus className="h-3.5 w-3.5 text-[#6B7280]" />
                  <span>Sign up</span>
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      {/* Navigation Items — every icon stays locked in a 32px left slot at x=12px */}
      <nav className="flex flex-1 flex-col pt-[10px] overflow-y-auto overflow-x-hidden">
        <ul className="flex flex-col gap-[5px] px-[12px]">
          {PRIMARY_NAV_ITEMS.filter((item) => !item.groups || hasGroup(...item.groups)).map((item) => {
            const Icon = item.icon;
            const isActive = isNavActive(item.href, pathname);
            return (
              <li key={item.id}>
                <Link
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex h-[34px] w-full items-center overflow-hidden rounded-[7px] transition-colors duration-150 ${
                    isActive
                      ? "bg-[#C4C4C4]/30 font-medium text-black"
                      : "font-normal text-black/70 hover:bg-black/[0.04] hover:text-black"
                  }`}
                >
                  <span className="flex h-[34px] w-[32px] shrink-0 items-center justify-center">
                    <Icon
                      className={
                        item.id === "dashboard"
                          ? "h-[17px] w-[17px]"
                          : "h-[16px] w-[16px]"
                      }
                      strokeWidth={isActive ? 1.9 : 1.5}
                    />
                  </span>
                  <span
                    className={`ml-[6px] truncate whitespace-nowrap text-[14px] transition-opacity duration-150 ${
                      collapsed ? "opacity-0" : "opacity-100"
                    }`}
                  >
                    {item.label}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Divider before Settings */}
        <div className="mx-[12px] my-[8px] h-px bg-black/20" />

        {/* Settings */}
        <div className="px-[12px]">
          <Link
            href="/settings"
            title={collapsed ? "Settings" : undefined}
            aria-current={settingsActive ? "page" : undefined}
            className={`flex h-[34px] w-full items-center overflow-hidden rounded-[7px] transition-colors duration-150 ${
              settingsActive
                ? "bg-[#C4C4C4]/30 font-medium text-black"
                : "font-normal text-black/70 hover:bg-black/[0.04] hover:text-black"
            }`}
          >
            <span className="flex h-[34px] w-[32px] shrink-0 items-center justify-center">
              <Settings
                className="h-[17px] w-[17px]"
                strokeWidth={settingsActive ? 1.9 : 1.5}
              />
            </span>
            <span
              className={`ml-[6px] truncate whitespace-nowrap text-[14px] transition-opacity duration-150 ${
                collapsed ? "opacity-0" : "opacity-100"
              }`}
            >
              Settings
            </span>
          </Link>
        </div>
      </nav>

      {/* Bottom Collapse / Expand Section — button stays locked at x=12px */}
      <div className="flex h-[46px] shrink-0 items-center border-t border-[#676767]/25 px-[12px]">
        <button
          type="button"
          onClick={handleToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-[32px] w-[32px] shrink-0 items-center justify-center rounded-[6px] text-black/70 hover:bg-black/[0.05] hover:text-black transition-colors cursor-pointer"
        >
          <ArrowLeftToLine
            className={`h-[17px] w-[17px] transition-transform duration-200 ease-[cubic-bezier(0.2,0,0,1)] ${
              collapsed ? "rotate-180" : "rotate-0"
            }`}
            strokeWidth={1.7}
          />
        </button>
      </div>
    </aside>
  );
}
