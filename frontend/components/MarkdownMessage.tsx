"use client";

import Markdown from "react-markdown";

/**
 * Renders assistant markdown (bold, lists, emphasis) as real HTML instead of
 * showing the raw markdown syntax. RTL-aware: direction follows the first
 * strong-direction character so French and Arabic answers both render well.
 */
export function MarkdownMessage({ text }: { text: string }) {
  return (
    <div
      dir="auto"
      className="text-sm leading-relaxed [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_ol]:list-decimal [&_ol]:ps-5 [&_ol]:my-2 [&_ul]:list-disc [&_ul]:ps-5 [&_ul]:my-2 [&_strong]:font-semibold [&_strong]:text-emerald-100 [&_h1]:text-base [&_h1]:font-bold [&_h2]:text-base [&_h2]:font-bold [&_h3]:text-sm [&_h3]:font-semibold [&_a]:underline [&_a]:text-emerald-300"
    >
      <Markdown>{text}</Markdown>
    </div>
  );
}