"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface GenerationConfig {
  strategy: string;
  use_smaller_models: boolean;
  timeout_local_sec: number;
}

const STRATEGIES: { value: string; label: string; description: string }[] = [
  {
    value: "local_fallback",
    label: "Local first (with retry)",
    description: "Try local Docker inference; retries on transient errors. (Default)",
  },
  {
    value: "local_only",
    label: "Local only",
    description: "Docker inference only — offline, no API key needed. Fails if Docker is down.",
  },
  {
    value: "openai_dalle",
    label: "OpenAI (gpt-image-1)",
    description: "Cloud generation via OpenAI gpt-image-1. Requires OPENAI_API_KEY. ~$0.04/image.",
  },
];

async function fetchConfig(projectId: string): Promise<GenerationConfig> {
  const res = await fetch(`${BASE}/projects/${projectId}/generation-settings`);
  if (!res.ok) throw new Error(`fetchConfig failed: ${res.status}`);
  return res.json();
}

async function saveConfig(projectId: string, config: GenerationConfig): Promise<void> {
  const res = await fetch(`${BASE}/projects/${projectId}/generation-settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error(`saveConfig failed: ${res.status}`);
}

interface Props {
  projectId: string;
}

export function GenerationSettingsPanel({ projectId }: Props) {
  const [config, setConfig] = useState<GenerationConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchConfig(projectId)
      .then(setConfig)
      .catch((e) => setError(e.message));
  }, [projectId]);

  async function handleChange(patch: Partial<GenerationConfig>) {
    if (!config) return;
    const updated = { ...config, ...patch };
    setConfig(updated);
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await saveConfig(projectId, updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
      setConfig(config); // revert optimistic update on failure
    } finally {
      setSaving(false);
    }
  }

  if (!config) {
    return (
      <p className="text-xs text-zinc-400">
        {error ? (
          <span className="text-red-400">Error: {error}</span>
        ) : (
          "Loading…"
        )}
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-800/50 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-zinc-300 uppercase tracking-wide">Image Generation</h3>
        {saving && <span className="text-xs text-zinc-400">Saving…</span>}
        {!saving && saved && <span className="text-xs text-emerald-400">Saved</span>}
      </div>

      <div className="space-y-2">
        {STRATEGIES.map((s) => (
          <label key={s.value} className="flex items-start gap-3 cursor-pointer">
            <input
              type="radio"
              name="strategy"
              value={s.value}
              checked={config.strategy === s.value}
              onChange={() => handleChange({ strategy: s.value })}
              disabled={saving}
              className="mt-1 accent-indigo-400"
            />
            <div>
              <p className="text-sm font-medium text-zinc-100">{s.label}</p>
              <p className="text-xs text-zinc-400">{s.description}</p>
            </div>
          </label>
        ))}
      </div>

      <hr className="border-zinc-700" />

      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={config.use_smaller_models}
          onChange={(e) => handleChange({ use_smaller_models: e.target.checked })}
          disabled={saving}
          className="accent-indigo-400"
        />
        <div>
          <p className="text-sm font-medium text-zinc-100">Use faster SD 1.5 locally</p>
          <p className="text-xs text-zinc-400">
            ~60 s/image instead of ~180 s for SDXL. Lower quality but much faster on Mac M-series.
          </p>
        </div>
      </label>

      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2">
          <p className="text-xs text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
}
