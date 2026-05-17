"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface GenerationConfig {
  strategy: string;
  use_smaller_models: boolean;
  timeout_local_sec: number;
  timeout_replicate_sec: number;
}

const STRATEGIES: { value: string; label: string; description: string }[] = [
  {
    value: "local_fallback",
    label: "Local first, cloud fallback",
    description: "Free local inference via Docker; falls back to Replicate on error. (Default)",
  },
  {
    value: "replicate_only",
    label: "Replicate only",
    description: "Always use Replicate cloud. Fastest, ~$0.05–0.30 per image.",
  },
  {
    value: "local_only",
    label: "Local only",
    description: "Docker inference only — offline, no API key needed. Fails if Docker is down.",
  },
  {
    value: "replicate_fallback",
    label: "Cloud first, local fallback",
    description: "Use Replicate; fall back to local Docker if cloud is unavailable.",
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
    try {
      await saveConfig(projectId, updated);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!config) {
    return <p className="text-sm text-gray-500">{error ?? "Loading…"}</p>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">Image Generation Strategy</h3>
        {saving && <span className="text-xs text-gray-400">Saving…</span>}
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
              className="mt-1"
            />
            <div>
              <p className="text-sm font-medium text-gray-700">{s.label}</p>
              <p className="text-xs text-gray-500">{s.description}</p>
            </div>
          </label>
        ))}
      </div>

      <hr className="border-gray-200" />

      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={config.use_smaller_models}
          onChange={(e) => handleChange({ use_smaller_models: e.target.checked })}
          disabled={saving}
        />
        <div>
          <p className="text-sm font-medium text-gray-700">Use faster SD 1.5 locally</p>
          <p className="text-xs text-gray-500">
            ~60 s/image instead of ~180 s for SDXL. Lower quality but much faster on Mac M-series.
          </p>
        </div>
      </label>

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
