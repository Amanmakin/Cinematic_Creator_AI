"use client";

export type ViewMode = "viewport" | "preview";

interface ViewToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  previewAvailable?: boolean;
}

export default function ViewToggle({ mode, onChange, previewAvailable = false }: ViewToggleProps) {
  return (
    <div className="flex rounded-md overflow-hidden border border-border text-xs font-medium">
      <button
        className={`px-3 py-1.5 transition-colors ${
          mode === "viewport"
            ? "bg-accent text-white"
            : "bg-surface text-slate-400 hover:text-slate-200"
        }`}
        onClick={() => onChange("viewport")}
      >
        3D Viewport
      </button>
      <button
        className={`px-3 py-1.5 transition-colors ${
          mode === "preview"
            ? "bg-accent text-white"
            : "bg-surface text-slate-400 hover:text-slate-200"
        } ${!previewAvailable ? "opacity-40 cursor-not-allowed" : ""}`}
        disabled={!previewAvailable}
        onClick={() => previewAvailable && onChange("preview")}
      >
        Render Preview
      </button>
    </div>
  );
}
