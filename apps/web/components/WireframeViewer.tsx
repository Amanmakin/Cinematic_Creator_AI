"use client";

import { Suspense, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, useGLTF, Center } from "@react-three/drei";
import * as THREE from "three";

function WireframeModel({ url }: { url: string }) {
  const { scene } = useGLTF(url);

  const wireScene = useMemo(() => {
    const clone = scene.clone(true);
    const mat = new THREE.MeshBasicMaterial({ color: 0x818cf8, wireframe: true });
    clone.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        (child as THREE.Mesh).material = mat;
      }
    });
    return clone;
  }, [scene]);

  return (
    <Center>
      <primitive object={wireScene} />
    </Center>
  );
}

function RotatingRing() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.z += delta * 0.8;
  });
  return (
    <mesh ref={ref}>
      <torusGeometry args={[0.3, 0.02, 8, 32]} />
      <meshBasicMaterial color={0x818cf8} />
    </mesh>
  );
}

function LoadingFallback() {
  return (
    <Canvas camera={{ position: [0, 0, 2], fov: 50 }}>
      <RotatingRing />
    </Canvas>
  );
}

interface WireframeViewerProps {
  url: string;
  className?: string;
}

export function WireframeViewer({ url, className }: WireframeViewerProps) {
  return (
    <div
      className={
        className ?? "w-full aspect-video rounded-lg overflow-hidden border border-zinc-700 bg-[#0c0c14]"
      }
    >
      <Suspense fallback={<LoadingFallback />}>
        <Canvas
          camera={{ position: [2.5, 1.5, 2.5], fov: 50 }}
          gl={{ antialias: true }}
        >
          <color attach="background" args={["#0c0c14"]} />
          <ambientLight intensity={0.3} />
          <WireframeModel url={url} />
          <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
        </Canvas>
      </Suspense>
    </div>
  );
}
