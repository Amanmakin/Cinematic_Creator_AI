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
    // Ensure vertex colors from the GLB are honoured and lighting looks good.
    clone.traverse((child) => {
      const mesh = child as THREE.Mesh;
      if (!mesh.isMesh) return;
      const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      mats.forEach((m) => {
        if (m instanceof THREE.MeshStandardMaterial) {
          if (mesh.geometry.attributes.color) {
            m.vertexColors = true;
            // White base so vertex color shows without tinting
            m.color.set(0xffffff);
          }
          m.roughness = Math.max(m.roughness, 0.55);
          m.needsUpdate = true;
        }
      });
    });
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
