"use client";

import { useState } from "react";
import { useProjectStore } from "@/state/projectStore";

export default function LockManager() {
  const { agentState, addLock, removeLock } = useProjectStore();
  const locks = agentState?.semantic_locks ?? [];
  const [path, setPath] = useState("");
  const [reason, setReason] = useState("");

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!path.trim() || !reason.trim()) return;
    await addLock(path.trim(), reason.trim());
    setPath("");
    setReason("");
  };

  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs font-medium text-slate-400 uppercase tracking-wide">Semantic Locks</label>

      {locks.length === 0 ? (
        <p className="text-xs text-slate-600 italic">No locks active.</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {locks.map((lock) => (
            <li
              key={lock.path}
              className="flex items-center justify-between text-xs bg-surface border border-border rounded-md px-3 py-2"
            >
              <span className="font-mono text-cyan-400 truncate">{lock.path}</span>
              <button
                onClick={() => removeLock(lock.path)}
                className="text-slate-600 hover:text-red-400 ml-2 transition-colors"
                title="Remove lock"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={handleAdd} className="flex flex-col gap-1 mt-1">
        <input
          className="bg-surface border border-border rounded-md px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-accent"
          placeholder="scene.camera.focal_mm"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <input
          className="bg-surface border border-border rounded-md px-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-accent"
          placeholder="Reason for locking"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button
          type="submit"
          disabled={!path.trim() || !reason.trim()}
          className="bg-surface border border-border hover:border-accent disabled:opacity-40 text-xs text-slate-300 rounded-md py-1.5 transition-colors"
        >
          Add Lock
        </button>
      </form>
    </div>
  );
}
