/**
 * Pure function: applies a canonical SceneGraph (BlenderDsl) to live Three.js
 * objects. Idempotent — safe to call on every store version increment.
 *
 * Camera, lights, and animation tracks are driven by the JSON overlay; the
 * .glb is geometry-only.
 */

import * as THREE from "three";
import type { BlenderDsl, Light } from "@/lib/types/agentState";

export interface ThreeTargets {
  camera: THREE.PerspectiveCamera;
  lights: THREE.Light[];
  scene: THREE.Scene;
}

const DEG2RAD = Math.PI / 180;

function focalMmToFov(focalMm: number, sensorMm: number): number {
  return 2 * Math.atan(sensorMm / (2 * focalMm)) * (180 / Math.PI);
}

function kelvinToColor(kelvin: number): THREE.Color {
  // Simplified Planckian locus approximation
  const t = kelvin / 100;
  let r: number, g: number, b: number;

  if (t <= 66) {
    r = 255;
    g = t <= 19 ? 0 : 99.4708025861 * Math.log(t - 10) - 161.1195681661;
    b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  } else {
    r = 329.698727446 * Math.pow(t - 60, -0.1332047592);
    g = 288.1221695283 * Math.pow(t - 60, -0.0755148492);
    b = 255;
  }

  return new THREE.Color(
    Math.max(0, Math.min(255, r)) / 255,
    Math.max(0, Math.min(255, g)) / 255,
    Math.max(0, Math.min(255, b)) / 255,
  );
}

export function applyToR3F(graph: BlenderDsl, targets: ThreeTargets): void {
  const { camera: cam, lights } = graph.scene;
  const { camera, lights: threeLights, scene } = targets;

  // Camera
  camera.fov = focalMmToFov(cam.focal_mm, cam.sensor_mm);
  camera.position.set(cam.position.x, cam.position.y, cam.position.z);
  camera.lookAt(new THREE.Vector3(cam.look_at.x, cam.look_at.y, cam.look_at.z));
  camera.updateProjectionMatrix();

  // Lights — synchronise count and properties
  // Remove old managed lights
  for (const l of threeLights) {
    scene.remove(l);
  }
  threeLights.length = 0;

  for (const lightDef of lights) {
    const light = buildLight(lightDef);
    scene.add(light);
    threeLights.push(light);
  }
}

function buildLight(def: Light): THREE.Light {
  const color = kelvinToColor(def.color_kelvin);

  if (def.kind === "ambient") {
    const al = new THREE.AmbientLight(color, def.intensity);
    return al;
  }

  const pl = new THREE.PointLight(color, def.intensity * 100, 0, 2);
  pl.position.set(def.position.x, def.position.y, def.position.z);
  return pl;
}
