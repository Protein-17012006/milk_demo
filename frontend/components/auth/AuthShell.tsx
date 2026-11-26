"use client";

import React from "react";
import Image from "next/image";
import Link from "next/link";

interface AuthShellProps {
  children: React.ReactNode;
}

/** The frame of the login and register pages: the brand bar, the centred form, and the copyright line. */
export function AuthShell({ children }: AuthShellProps) {
  return (
    <div className="flex min-h-screen w-full flex-col bg-white text-[#1D1F20]">
      <header className="flex h-[64px] w-full shrink-0 items-center border-b border-[#E5E7EB] bg-white px-5 sm:px-8">
        <Link
          href="/"
          className="flex items-center gap-2.5 text-[#1D1F20] hover:opacity-90 transition-opacity"
        >
          <Image
            src="/images/logo-database.png"
            alt="Project A logo"
            width={28}
            height={28}
            className="h-[28px] w-[28px] object-contain"
            priority
          />
          <span className="text-[18px] font-semibold tracking-[-0.02em]">
            Project A
          </span>
        </Link>
      </header>

      {/* Main Centered Auth Column */}
      <main className="flex flex-1 flex-col items-center justify-center px-5 py-12">
        <div className="w-full max-w-[420px]">{children}</div>
      </main>

      <footer className="w-full shrink-0 border-t border-[#E5E7EB] bg-white px-5 py-4">
        <p className="text-center text-[12px] text-[#595959]">&copy; 2026 Project A, Inc.</p>
      </footer>
    </div>
  );
}
