"use client";

import { Suspense, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF, Center } from "@react-three/drei";
import * as THREE from "three";
import CameraRig from "./CameraRig";
import GltfScene from "./GltfScene";
import ControlsOverlay from "./ControlsOverlay";
import StageLoadingOverlay from "./StageLoadingOverlay";
import { useProjectStore } from "@/state/projectStore";
import type { OtOp } from "@/lib/sceneGraph/diff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
function previsUrl(path: string) {
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

interface ViewportProps {
  glbUrl?: string | null;
}

function SceneLights() {
  return (
    <>
      <ambientLight intensity={0.55} />
      <directionalLight position={[5, 8, 5]} intensity={1.4} castShadow />
      <directionalLight position={[-4, 4, -3]} intensity={0.4} />
      <directionalLight position={[0, -3, 6]} intensity={0.25} />
    </>
  );
}

export default function Viewport({ glbUrl }: ViewportProps) {
  const { projectId, otSceneGraph, otVersion, agentState, applyOt } = useProjectStore();

  const graph = otSceneGraph ?? agentState?.scene_graph ?? null;
  const lockedPaths = new Set(
    (agentState?.semantic_locks ?? []).map((l) => l.path),
  );

  // The previsualization object is replaced on every pipeline run, but the GLB
  // URL is stable — drei's useGLTF caches by URL, so a regenerated mesh would
  // keep showing the previous one. Bump a token whenever previs changes to force
  // a fresh fetch.
  const previs = agentState?.previsualization;
  const prevPrevisRef = useRef(previs);
  const cacheBustRef = useRef(0);
  if (previs !== prevPrevisRef.current) {
    prevPrevisRef.current = previs;
    cacheBustRef.current += 1;
  }

  const wireGlbPath = previs?.wireframe_glb_path;
  const wireGlbUrl = wireGlbPath
    ? `${previsUrl(wireGlbPath)}?cb=${cacheBustRef.current}`
    : null;

  const modelRenders = agentState?.model_renders ?? [];
  // Show 2-D model renders only while waiting for model approval — once the
  // GLB is assembled (glbUrl is set) Three.js takes over and the overlay hides.
  const showModelRenders =
    agentState?.execution_status === "model_generated" &&
    modelRenders.length > 0 &&
    !glbUrl;

  function handleCommit(ops: OtOp[]) {
    if (!projectId || !graph) return;
    applyOt(ops);
  }

  return (
    <div className="relative w-full h-full min-h-[400px]">
      <Canvas
        camera={{ fov: 50, position: [0, 1, 5], near: 0.01, far: 1000 }}
        style={{ background: "#0c0c14" }}
      >
        <Suspense fallback={null}>
          <CameraRig graph={graph} />
          <SceneLights />
          {glbUrl ? (
            <GltfScene url={glbUrl} />
          ) : wireGlbUrl ? (
            <WireframeGlb url={wireGlbUrl} />
          ) : (
            <WireframePlaceholder />
          )}
          <OrbitControls makeDefault />
        </Suspense>
      </Canvas>

      {/* Model renders overlay — replaces wireframe view when models are ready */}
      {showModelRenders && (
        <ModelRendersOverlay renders={modelRenders} />
      )}

      {/* Phase loading overlay */}
      <StageLoadingOverlay />

      {/* HUD overlay */}
      <div className="absolute top-3 right-3 pointer-events-auto">
        <ControlsOverlay
          graph={graph}
          version={otVersion}
          projectId={projectId ?? ""}
          onCommit={handleCommit}
          lockedPaths={lockedPaths}
        />
      </div>

      {/* Version badge */}
      <div className="absolute bottom-2 left-2 text-[10px] text-zinc-500 select-none">
        v{otVersion}
      </div>
    </div>
  );
}

function WireframeGlb({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const wireScene = useMemo(() => {
    const clone = scene.clone(true);
    const wireMat = new THREE.MeshBasicMaterial({
      color: 0x818cf8,
      wireframe: true,
    });
    clone.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.material = wireMat;
    });
    return clone;
  }, [scene]);
  return (
    <Center>
      <primitive object={wireScene} />
      <gridHelper args={[10, 10, "#2a2a3e", "#1a1a28"]} position={[0, -0.01, 0]} />
    </Center>
  );
}

function WireframePlaceholder() {
  return (
    <group>
      <mesh position={[0, 0.9, 0]}>
        <boxGeometry args={[1, 1.8, 0.6]} />
        <meshBasicMaterial color="#818cf8" wireframe />
      </mesh>
      <gridHelper args={[10, 10, "#3f3f46", "#27272a"]} />
    </group>
  );
}

function ModelRendersOverlay({ renders }: { renders: string[] }) {
  const [selected, setSelected] = useState(0);

  const toUrl = (path: string) =>
    path.startsWith("http") ? path : `${API_BASE}${path}`;

  return (
    <div className="absolute inset-0 flex flex-col bg-zinc-950/95 z-10">
      {/* Primary render */}
      <div className="flex-1 flex items-center justify-center overflow-hidden p-3">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={toUrl(renders[selected])}
          alt="Model render"
          className="max-w-full max-h-full object-contain rounded-lg shadow-2xl ring-1 ring-indigo-500/30"
        />
      </div>

      {/* Thumbnail strip — only shown when there are multiple renders */}
      {renders.length > 1 && (
        <div className="flex gap-2 px-4 pb-3 justify-center">
          {renders.map((src, i) => (
            <button
              key={i}
              onClick={() => setSelected(i)}
              className={[
                "w-16 h-12 rounded-md overflow-hidden border-2 transition-colors shrink-0",
                i === selected ? "border-indigo-400" : "border-zinc-700 hover:border-zinc-500",
              ].join(" ")}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={toUrl(src)} alt={`Render ${i}`} className="w-full h-full object-cover" />
            </button>
          ))}
        </div>
      )}

      {/* Label */}
      <div className="absolute top-3 left-3 flex items-center gap-2 bg-zinc-900/80 rounded-lg px-3 py-1.5 border border-zinc-700">
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
        <span className="text-xs font-medium text-zinc-200">
          Model Render {renders.length > 1 ? `${selected + 1} / ${renders.length}` : ""}
        </span>
      </div>
    </div>
  );
}
