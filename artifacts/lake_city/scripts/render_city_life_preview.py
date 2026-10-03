"""Render the saved city animation at human scale without resaving the source."""
import bpy
from pathlib import Path
from mathutils import Vector
import math

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT / "Lake_City.blend"))
scene = bpy.context.scene
camera_data = bpy.data.cameras.new("LifePreviewCamera")
camera = bpy.data.objects.new("LifePreviewCamera", camera_data)
scene.collection.objects.link(camera)
camera_data.lens = 42
camera_data.clip_start = .05
scene.camera = camera
scene.render.resolution_x = 1280
scene.render.resolution_y = 900
out = ROOT / "renders/life_blender"
out.mkdir(exist_ok=True)
for frame in (1, 301):
    scene.frame_set(frame)
    actor = bpy.data.objects["pedestrian_002"]
    angle = actor.rotation_euler.z
    camera.location = actor.location + Vector((math.sin(angle) * 6, -math.cos(angle) * 6, 1.65))
    target = actor.location + Vector((0, 0, .9))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out / f"walk_{frame:03}.png")
    bpy.ops.render.render(write_still=True)
print("Saved-source animated previews rendered without modifying the Blender file.", flush=True)
