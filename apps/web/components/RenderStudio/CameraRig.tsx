"use client";

import { useEffect } from "react";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import type { BlenderDsl } from "@/lib/types/agentState";

interface CameraRigProps {
  graph: BlenderDsl | null;
}

function focalMmToFov(focalMm: number, sensorMm: number): number {
  return 2 * Math.atan(sensorMm / (2 * focalMm)) * (180 / Math.PI);
}

export default function CameraRig({ graph }: CameraRigProps) {
  const { camera } = useThree();

  useEffect(() => {
    if (!graph || !(camera instanceof THREE.PerspectiveCamera)) return;
    const cam = graph.scene.camera;
    camera.fov = focalMmToFov(cam.focal_mm, cam.sensor_mm);
    camera.position.set(cam.position.x, cam.position.y, cam.position.z);
    camera.lookAt(new THREE.Vector3(cam.look_at.x, cam.look_at.y, cam.look_at.z));
    camera.updateProjectionMatrix();
  }, [graph, camera]);

  return null;
}
