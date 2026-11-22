"use client";

import React, { createContext, useContext } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertTriangle, Cloud, LogIn } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Sidebar } from "./Sidebar";
import { SidebarSearchProvider } from "./SidebarContext";

interface DashboardShellProps {
  children: React.ReactNode;
}

const AUTH_PATHS = ["/login", "/register"];

// Prevents duplicate sidebars if a stale dev HMR root layout wraps a route-group layout
const InsideDashboardShellContext = createContext(false);

export function DashboardShell({ children }: DashboardShellProps) {
  const pathname = usePathname();
  const isAlreadyInsideShell = useContext(InsideDashboardShellContext);
  const { user, isLoading, isAuthenticated, isApproved } = useAuth();

  if (
    isAlreadyInsideShell ||
    AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))
  ) {
    return <>{children}</>;
  }

  return (
    <InsideDashboardShellContext.Provider value={true}>
      <SidebarSearchProvider>
        <div className="flex h-screen w-full overflow-hidden bg-white">
          <Sidebar />
          <main className="flex-1 min-w-0 h-full overflow-y-auto bg-white">
            {!isLoading && !isAuthenticated && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#E5E7EB] bg-[#F9FAFB] px-5 py-2 text-[12px] text-[#374151]">
                <span className="inline-flex items-center gap-2">
                  <Cloud className="h-3.5 w-3.5 text-[#EE730A]" />
                  <span>
                    Not signed in — sign in with AWS Cognito to load live
                    shelf data from{" "}
                    <strong>ap-southeast-1</strong>.
                  </span>
                </span>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 rounded-[6px] bg-[#EE730A] px-2.5 py-1 text-[11.5px] font-semibold text-white hover:bg-[#D96504] transition-colors"
                >
                  <LogIn className="h-3 w-3" />
                  <span>Log in</span>
                </Link>
              </div>
            )}

            {!isLoading && isAuthenticated && !isApproved && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#FED7AA] bg-[#FFF7ED] px-5 py-2.5 text-[12.5px] text-[#7C2D12]">
                <span className="inline-flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-[#C2560A]" />
                  <span>
                    Signed in as <strong>{user?.email}</strong>, awaiting{" "}
                    <code>team_admin</code> role assignment (API returns{" "}
                    <code>403 PENDING_ROLE_ASSIGNMENT</code>).
                  </span>
                </span>
              </div>
            )}

            {children}
          </main>
        </div>
      </SidebarSearchProvider>
    </InsideDashboardShellContext.Provider>
  );
}
