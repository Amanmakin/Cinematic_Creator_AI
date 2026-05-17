"use client";

import { Suspense, useEffect, useRef } from "react";
import { useGLTF } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";

interface GltfSceneProps {
  url: string;
}

function GltfModel({ url }: GltfSceneProps) {
  const { scene: gltfScene } = useGLTF(url);
  const { scene } = useThree();
  const addedRef = useRef<THREE.Group | null>(null);

  useEffect(() => {
    const clone = gltfScene.clone(true);
    scene.add(clone);
    addedRef.current = clone as unknown as THREE.Group;
    return () => {
      scene.remove(clone);
    };
  }, [gltfScene, scene]);

  return null;
}

function WireframeStub() {
  return (
    <mesh>
      <boxGeometry args={[1, 1.8, 0.6]} />
      <meshBasicMaterial color="#4f46e5" wireframe />
    </mesh>
  );
}

export default function GltfScene({ url }: GltfSceneProps) {
  return (
    <Suspense fallback={<WireframeStub />}>
      <GltfModel url={url} />
    </Suspense>
  );
}
