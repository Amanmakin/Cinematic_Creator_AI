"use client";

import { useState } from "react";
import { GenerationSettingsPanel } from "./GenerationSettingsPanel";
import { LLMSettingsPanel } from "./LLMSettingsPanel";

interface Props {
  projectId: string;
}

export function SettingsDrawer({ projectId }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded px-1 py-1 text-xs font-medium uppercase tracking-widest text-slate-400 hover:text-slate-200 transition-colors"
      >
        <span>Settings</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="mt-2 space-y-4">
          <LLMSettingsPanel />
          <GenerationSettingsPanel projectId={projectId} />
        </div>
      )}
    </div>
  );
}
