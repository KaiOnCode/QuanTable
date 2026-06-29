"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

/** Shared markdown renderer with table support via remark-gfm.
 *  Always use this instead of raw ReactMarkdown. */
export function Markdown({
  children,
  components,
  className,
}: {
  children: string;
  components?: Components;
  className?: string;
}) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
