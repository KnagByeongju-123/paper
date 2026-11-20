"""[Blender] 오일 정압 원형 패드 베어링 3D 반단면 (무광, 막 두께 과장).

make_figures.py --only hydro 가 대신 실행한다.
구성: 안내면(레일) / 오일 막 / 패드(리세스·랜드) / 공급 구멍 / 모세관 리스트릭터
"""
import argparse
import json
import math
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--anchors", required=True)
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--width", type=int, default=1400)
ap.add_argument("--height", type=int, default=1100)
args = ap.parse_args(argv)

R, R0 = 40.0, 20.0        # 패드·리세스 반지름 (mm)
H = 2.5                   # 오일 막 두께 (그림용 과장)
DEPTH = 5.0               # 리세스 깊이
PAD_H = 34.0              # 패드 높이
RAIL_H = 22.0

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def matte(name, rgb, rough=0.8, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = 0.0      # 무광 규칙
    b.inputs["Roughness"].default_value = rough
    return m


def cyl(name, r, h, z0, verts=160):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(0, 0, z0 + h / 2))
    o = bpy.context.active_object
    o.name = name
    return o


def box(name, sx, sy, sz, loc):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    o.name = name
    return o


def boolean(t, c, op="DIFFERENCE"):
    m = t.modifiers.new("b", "BOOLEAN")
    m.operation, m.object, m.solver = op, c, "EXACT"
    bpy.context.view_layer.objects.active = t
    bpy.ops.object.modifier_apply(modifier=m.name)


# ---- 안내면(레일) ----
rail = box("Rail", 2 * R + 50, 2 * R + 30, RAIL_H, (0, 0, -RAIL_H / 2))

# ---- 오일: 막(랜드 아래) + 리세스 + 공급 통로 ----
oil = cyl("Oil", R, H, 0)
pocket_oil = cyl("PocketOil", R0, DEPTH, H)
boolean(oil, pocket_oil, "UNION"); bpy.data.objects.remove(pocket_oil)
cap_oil = cyl("CapOil", 1.0, 12, H + DEPTH)                       # 모세관
boolean(oil, cap_oil, "UNION"); bpy.data.objects.remove(cap_oil)
sup_oil = cyl("SupOil", 3.2, PAD_H - DEPTH - 12, H + DEPTH + 12)  # 공급 구멍
boolean(oil, sup_oil, "UNION"); bpy.data.objects.remove(sup_oil)

# ---- 패드: 원기둥에서 리세스·통로를 뺌 ----
pad = cyl("Pad", R, PAD_H, H)
for r, h, z in ((R0, DEPTH, H - 0.01), (1.0, 12, H + DEPTH - 0.01), (3.2, PAD_H, H + DEPTH + 12 - 0.01)):
    c = cyl("cut", r, h + 0.02, z)
    boolean(pad, c); bpy.data.objects.remove(c)

# ---- 반단면 ----
for o in (rail, oil, pad):
    cutter = box("Cutter", 400, 200, 400, (0, -100, 0))
    boolean(o, cutter); bpy.data.objects.remove(cutter)

rail.data.materials.append(matte("Rail", (0.38, 0.47, 0.60)))
pad.data.materials.append(matte("Pad", (0.74, 0.76, 0.80)))
oil.data.materials.append(matte("Oil", (0.93, 0.55, 0.10), rough=0.6))
for o in (rail, pad):
    o.data.materials.append(matte(o.name + "Sec", (0.30, 0.33, 0.38) if o is rail else (0.55, 0.57, 0.62)))
    for p in o.data.polygons:
        if abs(p.normal.y + 1) < 1e-3 and abs(p.center.y) < 1e-3:
            p.material_index = 1      # 잘린 단면은 짙게

# ---- 조명·카메라 ----
bpy.ops.object.light_add(type="AREA", location=(70, -110, 120))
key = bpy.context.active_object
key.data.energy, key.data.size = 9000, 90
key.rotation_euler = (math.radians(40), 0, math.radians(30))
bpy.ops.object.light_add(type="SUN", location=(-60, -60, 80))
sun = bpy.context.active_object
sun.data.energy = 1.2
sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-35))

target = Vector((0, 8, 6))
bpy.ops.object.camera_add(location=(120, -175, 150))
cam = bpy.context.active_object
cam.data.lens = 55
cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = cam

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = args.samples
scene.cycles.use_denoising = False
scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
scene.view_settings.view_transform = "Standard"
scene.render.filepath = args.out
bpy.context.view_layer.update()


def px(p):
    v = world_to_camera_view(scene, cam, Vector(p))
    return [round(v.x * args.width), round((1 - v.y) * args.height)]


anchors = {
    "pad": px((R * 0.75, 0, H + PAD_H * 0.6)),
    "recess": px((-R0 * 0.5, 0, H + DEPTH * 0.5)),
    "land": px((R0 + (R - R0) * 0.45, 0, H + 1.2)),
    "film": px((R * 0.92, 0, H * 0.5)),
    "cap": px((0, 0, H + DEPTH + 6)),
    "supply": px((0, 0, H + PAD_H - 3)),
    "rail": px((R + 15, 0, -RAIL_H * 0.5)),
    "size": [args.width, args.height],
}
with open(args.anchors, "w", encoding="utf-8") as f:
    json.dump(anchors, f, indent=1)
bpy.ops.render.render(write_still=True)
print("RENDERED", args.out)
