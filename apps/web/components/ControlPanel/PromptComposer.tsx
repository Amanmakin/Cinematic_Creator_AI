"use client";

import { useState } from "react";
import { useProjectStore } from "@/state/projectStore";

export default function PromptComposer() {
  const { submitPrompt, isRunning, projectId } = useProjectStore();
  const [prompt, setPrompt] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || !projectId) return;
    await submitPrompt(prompt.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Prompt</label>
      <textarea
        className="bg-surface border border-border rounded-md p-3 text-sm text-slate-200 resize-none h-24 focus:outline-none focus:ring-1 focus:ring-accent placeholder:text-slate-600"
        placeholder="Describe the cinematic scene…"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={isRunning}
      />
      <button
        type="submit"
        disabled={isRunning || !prompt.trim() || !projectId}
        className="bg-accent hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-medium rounded-md py-2 transition-colors"
      >
        {isRunning ? "Running…" : "Generate"}
      </button>
    </form>
  );
}
