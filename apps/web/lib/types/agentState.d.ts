// Auto-generated from Pydantic models — run `pnpm build:schemas` to regenerate.
// Source: apps/orchestrator/src/orchestrator/state.py + schemas/*.py

export type AspectRatio = "9:16" | "16:9" | "1:1" | "4:5";

export type GenerationMode = "wireframe" | "model" | "video";

export type ExecutionStage =
  | "idle"
  | "intent_validated"
  | "awaiting_human_approval"
  | "speculative_batching"
  | "semantic_lock_applied"
  | "scene_graph_generated"
  | "previsualization_generated"
  | "previsualization_approved"
  | "previsualization_feedback"
  | "model_generated"
  | "model_approved"
  | "model_feedback"
  | "creative_dispatching"
  | "visual_generating"
  | "budget_exceeded"
  | "physical_validation_failed"
  | "dsl_compiled"
  | "dsl_validation_failed"
  | "gltf_assembled"
  | "render_progress"
  | "render_timed_out"
  | "render_completed"
  | "completed"
  | "failed";

export interface CameraTransform {
  position: [number, number, number];
  rotation: [number, number, number];
  focal_length_mm: number;
}

export interface LightingInfo {
  key_light_direction: [number, number, number];
  fill_intensity: number;
  rim_enabled: boolean;
}

export interface WireframeFrame {
  frame_index: number;
  time_start_s: number;
  time_end_s: number;
  camera: CameraTransform;
  lighting: LightingInfo;
  viewport_image_path: string;
  viewport_thumbnail_path: string;
  notes?: string;
}

export interface Previsualization {
  frames: WireframeFrame[];
  mood: string;
  palette_hint: string;
  render_engine: "blender_eevee" | "opengl";
  wireframe_sheet_path?: string | null;
  wireframe_glb_path?: string | null;
}

export interface ProjectCanon {
  aspect_ratio: AspectRatio;
  duration_seconds_max: number;
  aesthetic_tags: string[];
  style_guide: string;
  banned_terms: string[];
}

export interface SemanticLock {
  path: string;
  asset_id: string | null;
  reason: string;
}

export interface ValidationFinding {
  severity: "error" | "warning";
  code: string;
  message: string;
  path: string | null;
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Camera {
  focal_mm: number;
  sensor_mm: number;
  position: Vec3;
  look_at: Vec3;
  f_stop: number;
}

export interface Light {
  kind: "key" | "fill" | "rim" | "ambient";
  position: Vec3;
  intensity: number;
  color_kelvin: number;
}

export interface SubjectPlaceholder {
  kind: "subject_placeholder";
  aabb_min: Vec3;
  aabb_max: Vec3;
  description: string;
}

export interface Scene {
  duration_s: number;
  fps: 24 | 30 | 60;
  resolution: [number, number];
  camera: Camera;
  lights: Light[];
  subjects: SubjectPlaceholder[];
}

export interface BlenderDsl {
  dsl_version: "1.0.0";
  scene: Scene;
}

export interface CameraHint {
  focal_mm: number | null;
  movement: string | null;
}

export interface AmbiguityHints {
  underspecified_fields: string[];
  conflicting_directives: string[];
  confidence: number;
}

export interface IntentSpec {
  subject: string;
  setting: string;
  mood_tags: string[];
  duration_seconds: number;
  aspect_ratio: AspectRatio;
  motion_hints: string[];
  camera_hint: CameraHint | null;
  ambiguity_hints: AmbiguityHints;
}

export interface AgentState {
  user_prompt: string;
  project_canon: ProjectCanon;
  intent: IntentSpec | null;
  ambiguity_score: number;
  semantic_locks: SemanticLock[];
  scene_graph: BlenderDsl | null;
  speculative_variants: BlenderDsl[];
  validation_findings: ValidationFinding[];
  execution_status: ExecutionStage;
  retry_count: number;
  error_log: string[];
  generation_mode: GenerationMode;
  previsualization?: Previsualization;
  model_renders?: string[];
}

export interface StateCheckpoint {
  checkpoint_id: string;
  node: string;
  timestamp: string;
  execution_status: ExecutionStage;
}
