"use client";

import { useState } from "react";

export interface LayerAsset {
  id: string;
  kind: "subject" | "background" | "fx";
  rgba_path: string;
  alpha_mask_path: string;
  depth_map_path: string;
  adapter: string;
  adapter_version: string;
  created_at: number;
}

type LayerType = "rgba" | "alpha" | "depth";

interface LayerPreviewProps {
  projectId: string;
  assets: LayerAsset[];
  apiBase?: string;
}

const KIND_LABEL: Record<LayerAsset["kind"], string> = {
  subject: "Subject",
  background: "Background",
  fx: "FX",
};

const LAYER_TABS: { key: LayerType; label: string }[] = [
  { key: "rgba", label: "RGBA" },
  { key: "alpha", label: "Alpha" },
  { key: "depth", label: "Depth" },
];

export default function LayerPreview({
  projectId,
  assets,
  apiBase = "http://localhost:8000",
}: LayerPreviewProps) {
  const [activeLayer, setActiveLayer] = useState<LayerType>("rgba");

  if (assets.length === 0) {
    return (
      <div className="text-sm text-zinc-500 italic p-4">
        No assets generated yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          Layer
        </span>
        <div className="flex gap-1">
          {LAYER_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveLayer(tab.key)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                activeLayer === tab.key
                  ? "bg-indigo-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {assets.map((asset) => (
          <AssetCard
            key={asset.id}
            asset={asset}
            layerType={activeLayer}
            projectId={projectId}
            apiBase={apiBase}
          />
        ))}
      </div>
    </div>
  );
}

function AssetCard({
  asset,
  layerType,
  projectId,
  apiBase,
}: {
  asset: LayerAsset;
  layerType: LayerType;
  projectId: string;
  apiBase: string;
}) {
  const src = `${apiBase}/projects/${projectId}/assets/${asset.id}/${layerType}`;

  return (
    <div className="flex flex-col gap-1 rounded-lg overflow-hidden bg-zinc-900 border border-zinc-800">
      <div className="relative aspect-square bg-zinc-950 flex items-center justify-center">
        {/* Checkerboard for transparency */}
        <div
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "repeating-conic-gradient(#666 0% 25%, transparent 0% 50%)",
            backgroundSize: "16px 16px",
          }}
        />
        <img
          src={src}
          alt={`${asset.kind} ${layerType}`}
          className="relative z-10 object-contain w-full h-full"
          loading="lazy"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      </div>
      <div className="px-2 py-1.5">
        <span className="text-xs font-medium text-zinc-300">
          {KIND_LABEL[asset.kind]}
        </span>
        <p className="text-[10px] text-zinc-500 truncate" title={asset.id}>
          {asset.id}
        </p>
        <p className="text-[10px] text-zinc-600">
          {asset.adapter} v{asset.adapter_version}
        </p>
      </div>
    </div>
  );
}
