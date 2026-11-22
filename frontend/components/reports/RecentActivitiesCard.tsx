"use client";

import React, { useMemo, useState } from "react";
import type { ActivityStatus, ShelfActivity } from "@/lib/reports-ui";

type ActivityFilter = "all" | "alerts" | "restocked";

interface RecentActivitiesCardProps {
  activities: ShelfActivity[];
  onOpenFullLog?: () => void;
}

const BADGE_STYLES: Record<ActivityStatus, { bg: string; text: string }> = {
  OOS: { bg: "bg-[#FEE2E2]", text: "text-[#DC2626]" },
  RESTOCKED: { bg: "bg-[#E8F5E9]", text: "text-[#2E7D32]" },
  DEPLETED: { bg: "bg-[#FFF3E0]", text: "text-[#E65100]" },
  "LOW STOCK": { bg: "bg-[#FEF3C7]", text: "text-[#D97706]" },
};

const FILTER_OPTIONS: { id: ActivityFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "alerts", label: "Alerts Only" },
  { id: "restocked", label: "Restocked" },
];

export function RecentActivitiesCard({
  activities,
  onOpenFullLog,
}: RecentActivitiesCardProps) {
  const [filter, setFilter] = useState<ActivityFilter>("all");

  const filteredActivities = useMemo(() => {
    if (filter === "all") return activities;
    if (filter === "restocked") {
      return activities.filter((item) => item.status === "RESTOCKED");
    }
    return activities.filter((item) => item.status !== "RESTOCKED");
  }, [activities, filter]);

  return (
    <div className="flex h-[440px] flex-col overflow-hidden rounded-[18px] border border-[#EFF0F6] bg-white">
      {/* Header */}
      <div className="shrink-0 border-b border-[#EFF0F6] px-[20px] pt-[14px] pb-[12px]">
        <h2 className="text-[18px] font-semibold leading-[1.3] text-[#111827]">
          Recent Shelf Activities
        </h2>

        {/* Filter Pills */}
        <div className="mt-[8px] flex flex-wrap items-center gap-[8px]">
          {FILTER_OPTIONS.map((opt) => {
            const active = filter === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => setFilter(opt.id)}
                className={`rounded-full px-[10px] py-[4px] text-[12px] leading-tight transition-colors cursor-pointer ${
                  active
                    ? "bg-[#F3F4F6] font-semibold text-[#111827]"
                    : "border border-[#EFF0F6] bg-white font-medium text-[#6B7280] hover:bg-[#F9FAFB]"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Scrollable Feed */}
      <div className="flex-1 overflow-y-auto px-[20px] py-[6px]">
        {filteredActivities.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[13px] text-[#9CA3AF]">
            {activities.length === 0
              ? "No shelf activity history yet: the API does not serve shelf events."
              : "No matching shelf activities found."}
          </div>
        ) : (
          <div className="divide-y divide-[#EFF0F6]">
            {filteredActivities.map((item) => {
              const badge = BADGE_STYLES[item.status];
              return (
                <article key={item.id} className="flex flex-col gap-[4px] py-[9px]">
                  <div className="flex items-center gap-[8px]">
                    <span
                      className={`shrink-0 rounded-full px-[24px] py-[2px] text-[11px] font-semibold leading-tight ${badge.bg} ${badge.text}`}
                    >
                      {item.status}
                    </span>
                    <h3 className="truncate text-[13px] font-semibold leading-[18px] text-[#111827]">
                      {item.productName}
                    </h3>
                  </div>

                  <div className="flex flex-col gap-[2px]">
                    <span className="text-[12px] font-normal leading-[16px] text-[#9CA3AF]">
                      {item.timeAgo}
                    </span>
                    <span className="text-[12px] font-normal leading-[16px] text-[#6B7280]">
                      {item.storeName}
                    </span>
                    <span className="text-[12px] font-medium leading-[16px] text-[#374151]">
                      {item.deltaText}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="shrink-0 border-t border-[#EFF0F6] px-[20px] py-[12px]">
        <button
          type="button"
          onClick={onOpenFullLog}
          className="text-[13px] font-medium text-[#6B7280] hover:text-[#111827] transition-colors cursor-pointer"
        >
          View Full Audit Log &rarr;
        </button>
      </div>
    </div>
  );
}
