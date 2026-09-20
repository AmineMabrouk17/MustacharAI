"use client";

import type { PipelineStatus } from "@/hooks/useWebSocket";

interface PipelineStatusIndicatorProps {
  status: PipelineStatus;
}

const statusConfig: Record<PipelineStatus, { label: string; color: string; icon: string }> = {
  idle: {
    label: "جاهز",
    color: "text-zinc-400",
    icon: "●",
  },
  processing: {
    label: "يعالج",
    color: "text-amber-400",
    icon: "⚡",
  },
};

export function PipelineStatusIndicator({ status }: PipelineStatusIndicatorProps) {
  const config = statusConfig[status];

  return (
    <div className="flex items-center gap-2">
      <span className={`text-sm font-medium ${config.color} transition-colors duration-200`}>
        {config.icon} {config.label}
      </span>
      {status !== "idle" && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
        </span>
      )}
    </div>
  );
}