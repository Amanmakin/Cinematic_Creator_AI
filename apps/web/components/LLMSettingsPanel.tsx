"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface LLMConfig {
  provider: string;
  model: string;
  base_url: string;
}

const PRESETS: { key: string; label: string; description: string; config: LLMConfig }[] = [
  {
    key: "openai_mini",
    label: "GPT-4o mini (OpenAI)",
    description: "Default. Fast and cheap. Requires OPENAI_API_KEY.",
    config: { provider: "openai", model: "gpt-4o-mini", base_url: "" },
  },
  {
    key: "openai_4o",
    label: "GPT-4o (OpenAI)",
    description: "Best quality. Higher cost. Requires OPENAI_API_KEY.",
    config: { provider: "openai", model: "gpt-4o", base_url: "" },
  },
  {
    key: "ollama_llama3",
    label: "Llama 3 (Local / Ollama)",
    description: "Free, offline. Requires Ollama running at localhost:11434.",
    config: { provider: "ollama", model: "llama3", base_url: "http://localhost:11434/v1" },
  },
  {
    key: "ollama_mistral",
    label: "Mistral (Local / Ollama)",
    description: "Free, offline. Requires Ollama running at localhost:11434.",
    config: { provider: "ollama", model: "mistral", base_url: "http://localhost:11434/v1" },
  },
  {
    key: "custom",
    label: "Custom",
    description: "Any OpenAI-compatible endpoint.",
    config: { provider: "custom", model: "", base_url: "" },
  },
];

function matchPreset(cfg: LLMConfig): string {
  for (const p of PRESETS) {
    if (p.key === "custom") continue;
    if (p.config.model === cfg.model && p.config.base_url === cfg.base_url) return p.key;
  }
  return "custom";
}

export function LLMSettingsPanel() {
  const [config, setConfig] = useState<LLMConfig | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<string>("openai_mini");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch(`${BASE}/llm-settings`)
      .then((r) => r.json())
      .then((cfg: LLMConfig) => {
        setConfig(cfg);
        setSelectedPreset(matchPreset(cfg));
      })
      .catch((e) => setError(e.message));
  }, []);

  async function applyPreset(key: string) {
    const preset = PRESETS.find((p) => p.key === key);
    if (!preset) return;
    setSelectedPreset(key);
    if (key !== "custom") {
      await save(preset.config);
    } else {
      setConfig((prev) => prev ?? { provider: "custom", model: "", base_url: "" });
    }
  }

  async function save(cfg: LLMConfig) {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`${BASE}/llm-settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg),
      });
      if (!res.ok) throw new Error(`Save failed: ${res.status}`);
      setConfig(cfg);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!config) {
    return <p className="text-sm text-gray-500">{error ?? "Loading…"}</p>;
  }

  const isCustom = selectedPreset === "custom";

  return (
    <div className="rounded-lg border border-border bg-surface p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide">LLM Model</h3>
        {saving && <span className="text-xs text-slate-500">Saving…</span>}
        {saved && <span className="text-xs text-green-500">Saved</span>}
      </div>

      <div className="space-y-2">
        {PRESETS.map((p) => (
          <label key={p.key} className="flex items-start gap-3 cursor-pointer">
            <input
              type="radio"
              name="llm_preset"
              value={p.key}
              checked={selectedPreset === p.key}
              onChange={() => applyPreset(p.key)}
              disabled={saving}
              className="mt-1 accent-accent"
            />
            <div>
              <p className="text-sm font-medium text-slate-200">{p.label}</p>
              <p className="text-xs text-slate-500">{p.description}</p>
            </div>
          </label>
        ))}
      </div>

      {isCustom && (
        <div className="space-y-2 pt-1">
          <input
            className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-accent"
            placeholder="Model name (e.g. gpt-4-turbo)"
            value={config.model}
            onChange={(e) => setConfig({ ...config, model: e.target.value })}
          />
          <input
            className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-accent"
            placeholder="Base URL (empty = OpenAI default)"
            value={config.base_url}
            onChange={(e) => setConfig({ ...config, base_url: e.target.value })}
          />
          <button
            onClick={() => save(config)}
            disabled={saving || !config.model}
            className="w-full rounded-md bg-accent py-1.5 text-xs font-medium text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
          >
            Apply
          </button>
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
