"use client";

import { Suspense, useMemo } from "react";
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

  const wireGlbPath = agentState?.previsualization?.wireframe_glb_path;
  const wireGlbUrl = wireGlbPath ? previsUrl(wireGlbPath) : null;

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
    const mat = new THREE.MeshBasicMaterial({ color: 0x818cf8, wireframe: true });
    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) (child as THREE.Mesh).material = mat;
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
