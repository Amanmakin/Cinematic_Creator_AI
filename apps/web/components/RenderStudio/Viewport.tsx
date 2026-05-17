"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import CameraRig from "./CameraRig";
import GltfScene from "./GltfScene";
import ControlsOverlay from "./ControlsOverlay";
import { useProjectStore } from "@/state/projectStore";
import type { OtOp } from "@/lib/sceneGraph/diff";

interface ViewportProps {
  glbUrl?: string | null;
}

function SceneLights() {
  // Default lights shown before a scene_graph arrives
  return (
    <>
      <ambientLight intensity={0.3} />
      <directionalLight position={[5, 8, 5]} intensity={1.2} />
    </>
  );
}

export default function Viewport({ glbUrl }: ViewportProps) {
  const { projectId, otSceneGraph, otVersion, agentState, applyOt } = useProjectStore();

  const graph = otSceneGraph ?? agentState?.scene_graph ?? null;
  const lockedPaths = new Set(
    (agentState?.semantic_locks ?? []).map((l) => l.path),
  );

  function handleCommit(ops: OtOp[]) {
    if (!projectId || !graph) return;
    applyOt(ops);
  }

  return (
    <div className="relative w-full h-full min-h-[400px]">
      <Canvas
        camera={{ fov: 50, position: [0, 1, 5], near: 0.01, far: 1000 }}
        style={{ background: "#0a0a0f" }}
      >
        <Suspense fallback={null}>
          <CameraRig graph={graph} />
          <SceneLights />
          {glbUrl ? <GltfScene url={glbUrl} /> : <WireframePlaceholder />}
          <OrbitControls makeDefault />
        </Suspense>
      </Canvas>

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
      <div className="absolute bottom-2 left-2 text-[10px] text-zinc-600 select-none">
        v{otVersion}
      </div>
    </div>
  );
}

function WireframePlaceholder() {
  return (
    <group>
      <mesh position={[0, 0.9, 0]}>
        <boxGeometry args={[1, 1.8, 0.6]} />
        <meshBasicMaterial color="#4f46e5" wireframe />
      </mesh>
      <gridHelper args={[10, 10, "#333", "#222"]} />
    </group>
  );
}
