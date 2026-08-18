"use client";

import type { Citation } from "@/hooks/useWebSocket";

interface LegalCitationCardProps {
  citation: Citation;
  index: number;
}

export function LegalCitationCard({ citation, index }: LegalCitationCardProps) {
  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/50 p-3 text-sm">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="flex items-center justify-center h-5 w-5 rounded-full bg-emerald-600/20 text-emerald-400 text-xs font-bold">
          {index + 1}
        </span>
        <span className="text-emerald-400 font-medium text-xs">
          {citation.source}
        </span>
        {citation.article && (
          <>
            <span className="text-zinc-600">|</span>
            <span className="text-amber-400 font-medium text-xs">
              {citation.article}
            </span>
          </>
        )}
      </div>
      <p className="text-zinc-300 leading-relaxed text-xs">
        {citation.content}
      </p>
    </div>
  );
}
