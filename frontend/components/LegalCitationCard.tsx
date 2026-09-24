"use client";

import { useState } from "react";
import type { Citation } from "@/hooks/useWebSocket";

interface LegalCitationCardProps {
  citation: Citation;
  index: number;
}

/** Show the first characters of the citation article, with a see-more toggle. */
const COLLAPSE_AT = 220;

export function LegalCitationCard({ citation, index }: LegalCitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const codeName = citation.category || citation.source;
  const fullContent = citation.content ?? "";
  const isLong = fullContent.length > COLLAPSE_AT;
  const shownContent =
    isLong && !expanded ? `${fullContent.slice(0, COLLAPSE_AT)}…` : fullContent;

  return (
    <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/50 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1.5">
        <span className="flex items-center justify-center h-5 w-5 rounded-full bg-emerald-600/20 text-emerald-400 text-xs font-bold">
          {index + 1}
        </span>
        {codeName && (
          <span className="text-emerald-400 font-medium text-xs">
            <span className="text-zinc-500">المجلة:</span> {codeName}
          </span>
        )}
        {citation.article && (
          <>
            <span className="text-zinc-600" aria-hidden>
              |
            </span>
            <span className="text-amber-400 font-medium text-xs">
              <span className="text-zinc-500">الفصل:</span> {citation.article}
            </span>
          </>
        )}
      </div>
      <p className="text-zinc-300 leading-relaxed text-xs" dir="auto">
        {shownContent}
      </p>
      {isLong && (
        <button
          onClick={() => setExpanded((prev) => !prev)}
          className="mt-2 text-xs font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
        >
          {expanded ? "عرض أقل ▲" : "عرض المزيد ▼"}
        </button>
      )}
    </div>
  );
}