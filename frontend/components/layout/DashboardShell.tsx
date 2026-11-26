"use client";

import React, { createContext, useContext, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { WAITING_TEXT, shellState } from "@/lib/shell-ui";
import { Sidebar } from "./Sidebar";

interface DashboardShellProps {
  children: React.ReactNode;
}

const AUTH_PATHS = ["/login", "/register"];

// Prevents duplicate sidebars if a stale dev HMR root layout wraps a route-group layout
const InsideDashboardShellContext = createContext(false);

export function DashboardShell({ children }: DashboardShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isAlreadyInsideShell = useContext(InsideDashboardShellContext);
  const { user, isLoading, isAuthenticated, isApproved } = useAuth();

  const passThrough =
    isAlreadyInsideShell || AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const state = shellState({ isLoading, isAuthenticated, isApproved });
  const toLogin = !passThrough && state === "to-login";

  // Signed out, every page would be empty: go to the login page instead.
  useEffect(() => {
    if (toLogin) router.replace("/login");
  }, [toLogin, router]);

  if (passThrough) {
    return <>{children}</>;
  }
  if (toLogin) {
    return <div className="h-screen w-full bg-white" aria-busy="true" />;
  }

  return (
    <InsideDashboardShellContext.Provider value={true}>
      <div className="flex h-screen w-full overflow-hidden bg-white">
        <Sidebar />
        <main className="flex-1 min-w-0 h-full overflow-y-auto bg-white">
          {state === "waiting" && (
            <div
              data-waiting-banner
              role="status"
              className="flex flex-wrap items-center gap-2 border-b border-[#FED7AA] bg-[#FFF7ED] px-5 py-2.5 text-[12.5px] text-[#7C2D12]"
            >
              <AlertTriangle className="h-4 w-4 shrink-0 text-[#C2560A]" />
              <span>
                Signed in as <strong>{user?.email}</strong>. {WAITING_TEXT}
              </span>
            </div>
          )}

          {children}
        </main>
      </div>
    </InsideDashboardShellContext.Provider>
  );
}
