"use client";

import { useState } from "react";
import { pinStyleOverride } from "@/lib/api";
import { useProjectStore } from "@/state/projectStore";

interface Props {
  /** Human-readable description of what to pin, e.g. "golden-hour side lighting". */
  description: string;
  /** Optional label override for the button text. */
  label?: string;
}

/**
 * Star-shaped button that pins a style description into the project's memory
 * so it's injected into every subsequent LLM call via the retrieval tier.
 */
export default function StylePinButton({ description, label = "Pin Style" }: Props) {
  const { projectId } = useProjectStore();
  const [pinned, setPinned] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!projectId) return null;

  async function handlePin() {
    if (pinned || loading || !description.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await pinStyleOverride(projectId!, description.trim());
      setPinned(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Pin failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        title={pinned ? "Style pinned to memory" : `Pin: "${description}"`}
        disabled={loading || pinned}
        onClick={handlePin}
        className={[
          "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors border",
          pinned
            ? "bg-amber-900/40 border-amber-600 text-amber-300 cursor-default"
            : "bg-surface border-border hover:border-amber-500 hover:text-amber-300 text-slate-400",
          loading ? "opacity-60" : "",
        ].join(" ")}
      >
        <StarIcon filled={pinned} />
        {loading ? "Pinning…" : pinned ? "Pinned" : label}
      </button>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  );
}

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      className="shrink-0"
    >
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}
