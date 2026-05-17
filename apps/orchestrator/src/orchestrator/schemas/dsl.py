from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class Vec3(BaseModel):
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Camera(BaseModel):
    focal_mm: float = Field(gt=0, le=1000)
    sensor_mm: float = 36.0
    position: Vec3
    # Plan1 compat: look_at optional; Plan4 preferred: rotation_euler
    look_at: Vec3 | None = None
    rotation_euler: Vec3 | None = None
    f_stop: float = Field(default=2.8, gt=0)
    clip_start: float = 0.01
    clip_end: float = 1000.0


class Light(BaseModel):
    kind: Literal["key", "fill", "rim", "ambient"]
    position: Vec3
    intensity: float = Field(ge=0, le=10000)
    color_kelvin: int = Field(ge=1000, le=20000)


class SubjectPlaceholder(BaseModel):
    kind: Literal["subject_placeholder"] = "subject_placeholder"
    aabb_min: Vec3
    aabb_max: Vec3
    description: str
    asset_ref: str | None = None

    def contains(self, p: Vec3) -> bool:
        return (
            self.aabb_min.x <= p.x <= self.aabb_max.x
            and self.aabb_min.y <= p.y <= self.aabb_max.y
            and self.aabb_min.z <= p.z <= self.aabb_max.z
        )


class Transform(BaseModel):
    position: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=0, z=0))
    rotation_euler: Vec3 = Field(default_factory=lambda: Vec3(x=0, y=0, z=0))
    scale: Vec3 = Field(default_factory=lambda: Vec3(x=1, y=1, z=1))

    def aabb(self, half_thickness: float = 0.005) -> tuple[Vec3, Vec3]:
        """Axis-aligned bounding box for a plane card; treated as extruded along Z by half_thickness."""
        sx, sy = self.scale.x, self.scale.y
        px, py, pz = self.position.x, self.position.y, self.position.z
        return (
            Vec3(x=px - sx / 2, y=py - sy / 2, z=pz - half_thickness),
            Vec3(x=px + sx / 2, y=py + sy / 2, z=pz + half_thickness),
        )


class PlaneCard(BaseModel):
    kind: Literal["plane_card"] = "plane_card"
    asset_id: str
    transform: Transform = Field(default_factory=Transform)
    use_depth_map: bool = False


class Mesh(BaseModel):
    kind: Literal["mesh"] = "mesh"
    name: str
    transform: Transform = Field(default_factory=Transform)
    mesh_ref: str | None = None


SceneObject = Annotated[Union[PlaneCard, Mesh], Field(discriminator="kind")]


class AnimationTrack(BaseModel):
    target_path: str
    times: list[float]
    values: list[Any]
    interp: Literal["linear", "bezier", "step"] = "linear"


class WorldEnv(BaseModel):
    background_color: tuple[float, float, float] = (0.05, 0.05, 0.05)
    hdri_ref: str | None = None


class Scene(BaseModel):
    duration_s: float = Field(gt=0)
    fps: Literal[24, 30, 60]
    resolution: tuple[int, int]
    camera: Camera
    lights: list[Light] = Field(default_factory=list)
    # Plan1 subjects kept for backward compat
    subjects: list[SubjectPlaceholder] = Field(default_factory=list)
    # Plan4 extended fields
    objects: list[SceneObject] = Field(default_factory=list)
    animations: list[AnimationTrack] = Field(default_factory=list)
    world: WorldEnv = Field(default_factory=WorldEnv)


class BlenderDsl(BaseModel):
    dsl_version: Literal["1.0.0"] = "1.0.0"
    scene: Scene
