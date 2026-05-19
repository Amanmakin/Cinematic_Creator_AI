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
      <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Prompt</label>
      <textarea
        className="bg-zinc-800 border border-zinc-600 rounded-md p-3 text-sm text-zinc-100 resize-none h-24 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500 transition-all"
        placeholder="Describe the cinematic scene…"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={isRunning}
      />
      <button
        type="submit"
        disabled={isRunning || !prompt.trim() || !projectId}
        className="bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm font-medium rounded-md py-2.5 transition-colors shadow-md shadow-indigo-500/20"
      >
        {isRunning ? "Running…" : "Generate"}
      </button>
    </form>
  );
}
