"use client";

import { useCallback, useRef } from "react";
import type { BlenderDsl } from "@/lib/types/agentState";
import type { OtOp } from "@/lib/sceneGraph/diff";

interface ControlsOverlayProps {
  graph: BlenderDsl | null;
  version: number;
  projectId: string;
  onCommit: (ops: OtOp[]) => void;
  lockedPaths: Set<string>;
}

const LENS_OPTIONS: { label: string; value: number }[] = [
  { label: "24mm", value: 24 },
  { label: "35mm", value: 35 },
  { label: "50mm", value: 50 },
  { label: "85mm", value: 85 },
];

function isPathLocked(path: string, lockedPaths: Set<string>): boolean {
  for (const lp of lockedPaths) {
    if (path === lp || path.startsWith(lp + ".") || path.startsWith(lp + "[")) return true;
  }
  return false;
}

function useDebounced<T extends (...args: any[]) => void>(fn: T, ms: number): T {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  return useCallback(
    (...args: Parameters<T>) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => fn(...args), ms);
    },
    [fn, ms],
  ) as T;
}

interface SliderProps {
  label: string;
  path: string;
  value: number;
  min: number;
  max: number;
  step: number;
  locked: boolean;
  onChange: (path: string, value: number) => void;
}

function Slider({ label, path, value, min, max, step, locked, onChange }: SliderProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between items-center">
        <label className="text-[11px] text-zinc-400 font-medium">{label}</label>
        {locked && (
          <span className="text-[10px] text-amber-500 font-semibold">LOCKED</span>
        )}
        <span className="text-[11px] text-zinc-300 tabular-nums">{value.toFixed(1)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={locked}
        onChange={(e) => onChange(path, parseFloat(e.target.value))}
        className={`w-full h-1 rounded accent-indigo-500 ${locked ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
      />
    </div>
  );
}

export default function ControlsOverlay({
  graph,
  version,
  projectId,
  onCommit,
  lockedPaths,
}: ControlsOverlayProps) {
  const commit = useCallback(
    (path: string, value: unknown) => {
      onCommit([{ op: "set", path, value }]);
    },
    [onCommit],
  );

  const debouncedCommit = useDebounced(commit, 100);

  if (!graph) {
    return (
      <div className="text-xs text-zinc-500 italic p-3">
        No scene graph — run a prompt first.
      </div>
    );
  }

  const cam = graph.scene.camera;
  const lights = graph.scene.lights;

  return (
    <div className="flex flex-col gap-4 p-3 bg-zinc-900/80 backdrop-blur rounded-lg border border-zinc-700 text-sm min-w-[220px]">
      {/* Camera */}
      <section>
        <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">Camera</h3>

        <div className="mb-2">
          <label className="text-[11px] text-zinc-400 mb-1 block">Lens</label>
          <select
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-200 disabled:opacity-40"
            value={LENS_OPTIONS.find((o) => Math.abs(o.value - cam.focal_mm) < 2)?.value ?? cam.focal_mm}
            disabled={isPathLocked("scene.camera.focal_mm", lockedPaths)}
            onChange={(e) => commit("scene.camera.focal_mm", parseFloat(e.target.value))}
          >
            {LENS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <Slider
          label="Dolly (Z)"
          path="scene.camera.position.z"
          value={cam.position.z}
          min={1}
          max={20}
          step={0.1}
          locked={isPathLocked("scene.camera.position.z", lockedPaths)}
          onChange={debouncedCommit}
        />
      </section>

      {/* Lights */}
      {lights.length > 0 && (
        <section>
          <h3 className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider mb-2">Lights</h3>
          <div className="flex flex-col gap-3">
            {lights.map((light, i) => (
              <Slider
                key={i}
                label={`${light.kind} intensity`}
                path={`scene.lights[${i}].intensity`}
                value={light.intensity}
                min={0}
                max={5}
                step={0.05}
                locked={isPathLocked(`scene.lights[${i}].intensity`, lockedPaths)}
                onChange={debouncedCommit}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
