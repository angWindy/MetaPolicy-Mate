"use client";

import { Fragment, type ReactNode } from "react";

/**
 * Parse an answer string and silently strip any bracketed citation
 * markers left over from older prompts (e.g. ``[1]``, ``[2][3]``).
 *
 * The new system prompt instructs the LLM to cite by-prose — naming the
 * document number and article directly in the sentence — so this
 * component no longer renders clickable superscript chips. We keep the
 * strip pass as a safety net so historic answers persisted in chat
 * history don't leak markers into the UI.
 */
export interface InlineCitationProps {
  /** Answer text from the RAG pipeline. May still contain legacy ``[N]`` markers. */
  answer: string;
  /** No-op in the current UI; kept for backward compatibility with existing callers. */
  citations?: unknown;
  /** No-op in the current UI; kept for backward compatibility with existing callers. */
  onCitationClick?: (chunkId: string) => void;
  /** No-op in the current UI; kept for backward compatibility with existing callers. */
  activeChunkId?: string | null;
}

const MARKER_PATTERN = /\[\d+(?:\]\[\d+)*\]/g;

export function InlineCitation({ answer }: InlineCitationProps): ReactNode {
  const parts: ReactNode[] = [];
  let lastIndex = 0;

  MARKER_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyCounter = 0;

  while ((match = MARKER_PATTERN.exec(answer)) !== null) {
    const [whole] = match;
    const start = match.index;
    if (start > lastIndex) {
      parts.push(
        <Fragment key={`text-${keyCounter++}`}>
          {answer.slice(lastIndex, start)}
        </Fragment>,
      );
    }
    lastIndex = start + whole.length;
  }

  if (lastIndex < answer.length) {
    parts.push(
      <Fragment key={`text-${keyCounter++}`}>
        {answer.slice(lastIndex)}
      </Fragment>,
    );
  }

  return <>{parts}</>;
}