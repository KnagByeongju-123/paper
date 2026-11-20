"""[Blender] 블랭킹된 판재(슬러그)의 전단면 구성 3D 반단면 그림.

make_figures.py 가 대신 실행한다.
  blender -b -P scripts/figures/sheared_edge_3d.py -- --out raw.png --anchors out.json

영역 비율(판 두께 대비)은 옵션으로 바꿀 수 있다. 기본값은 개념 설명용이다.
  --roll 0.10  --burnish 0.40  --fracture 0.50  --burr 0.12  --thick 4.0
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
ap.add_argument("--thick", type=float, default=4.0)
ap.add_argument("--radius", type=float, default=14.0)
ap.add_argument("--roll", type=float, default=0.10)
ap.add_argument("--burnish", type=float, default=0.40)
ap.add_argument("--fracture", type=float, default=0.50)
ap.add_argument("--burr", type=float, default=0.12)
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--width", type=int, default=1400)
ap.add_argument("--height", type=int, default=1100)
args = ap.parse_args(argv)

T, R = args.thick, args.radius
h_roll, h_bur, h_fr = T * args.roll, T * args.burnish, T * args.fracture
roll_in = T * 0.18          # 처짐으로 모서리가 안쪽으로 둥글게 들어간 폭
fr_out = T * 0.10           # 파단면이 바깥으로 벌어진 폭 (파단 각)
burr_h = T * args.burr

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, rgb, metallic, rough, bump=0.0, scale=60.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if bump > 0:   # 파단면의 거친 질감
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 8.0
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(noise.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def revolve(name, profile, segs=192):
    """(r, z) 단면 프로파일을 z축으로 돌려 회전체를 만든다 (닫힌 다각형)."""
    verts, faces = [], []
    n = len(profile)
    for i in range(segs):
        a = 2 * math.pi * i / segs
        for r, z in profile:
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for i in range(segs):
        j = (i + 1) % segs
        for k in range(n):
            k2 = (k + 1) % n
            faces.append((i * n + k, j * n + k, j * n + k2, i * n + k2))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True
    return o


# 영역별 회전체 (위 → 아래): 처짐 / 전단면 / 파단면 / 버
z0 = T
z_roll, z_bur, z_fr = z0 - h_roll, z0 - h_roll - h_bur, 0.0
arc = [(R - roll_in + roll_in * math.sin(math.pi / 2 * i / 8), z0 - h_roll * (1 - math.cos(math.pi / 2 * i / 8)))
       for i in range(9)]
parts = {
    "Rollover": [(0, z0), *arc, (0, z_roll)],
    "Burnish": [(0, z_roll), (R, z_roll), (R, z_bur), (0, z_bur)],
    "Fracture": [(0, z_bur), (R, z_bur), (R + fr_out, z_fr), (0, z_fr)],
    "Burr": [(R + fr_out - T * 0.05, z_fr), (R + fr_out + T * 0.02, z_fr), (R + fr_out - T * 0.01, z_fr - burr_h)],
}
mats = {
    "Rollover": material("Roll", (0.93, 0.80, 0.55), 0.0, 0.75),
    "Burnish": material("Bur", (0.70, 0.79, 0.90), 0.0, 0.65),
    "Fracture": material("Fr", (0.78, 0.62, 0.60), 0.0, 0.90, bump=0.6),
    "Burr": material("Burr", (0.30, 0.30, 0.33), 0.0, 0.75),
}
objs = {}
for name, prof in parts.items():
    o = revolve(name, prof)
    o.data.materials.append(mats[name])
    objs[name] = o

# 앞쪽 절반을 잘라 단면을 보이게 함
for o in objs.values():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -100, 0))
    cut = bpy.context.active_object
    cut.scale = (400, 200, 400)
    mod = o.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", cut, "EXACT"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cut)
    o.data.materials.append(material(o.name + "_sec", (0.42, 0.44, 0.48), 0.0, 0.8))
    o.data.materials.append(material(o.name + "_flat", (0.72, 0.74, 0.77), 0.0, 0.75))
    for p in o.data.polygons:
        if abs(p.normal.y + 1) < 1e-3 and abs(p.center.y) < 1e-3:
            p.material_index = 1   # 잘린 면(단면)은 짙은 회색
        elif abs(p.normal.z) > 0.99:
            p.material_index = 2   # 위·아래 평평한 면은 판재 본래 색 (영역 색은 가장자리에만)

# 조명·카메라·배경
bpy.ops.object.light_add(type="AREA", location=(R + 35, -10, T + 30))
key = bpy.context.active_object
key.data.energy, key.data.size = 1800, 30
key.rotation_euler = (math.radians(50), 0, math.radians(35))
bpy.ops.object.light_add(type="SUN", location=(-30, -30, 50))
sun = bpy.context.active_object
sun.data.energy = 1.0
sun.rotation_euler = (math.radians(45), math.radians(-25), math.radians(-30))

target = Vector((R + 0.3, 3.2, T * 0.42))
bpy.ops.object.camera_add(location=(R + 22, -13, T + 9))
cam = bpy.context.active_object
cam.data.lens = 58
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


def to_px(p):
    v = world_to_camera_view(scene, cam, Vector(p))
    return [round(v.x * args.width), round((1 - v.y) * args.height)]


ang = math.radians(16)    # 바깥 둘레 쪽, 카메라에 보이는 방향
cx, sy = math.cos(ang), math.sin(ang)
anchors = {
    "Rollover": to_px(((R - roll_in / 2) * cx, (R - roll_in / 2) * sy, z0 - h_roll * 0.4)),
    "Burnish": to_px((R * cx, R * sy, (z_roll + z_bur) / 2)),
    "Fracture": to_px(((R + fr_out / 2) * cx, (R + fr_out / 2) * sy, z_bur / 2)),
    "Burr": to_px(((R + fr_out) * cx, (R + fr_out) * sy, -burr_h * 0.6)),
    "t_top": to_px((R + fr_out + 1.2, 0, z0)),
    "t_bot": to_px((R + fr_out + 1.2, 0, 0)),
    "section": to_px((R * 0.75, 0, T * 0.5)),
    "size": [args.width, args.height],
}
with open(args.anchors, "w", encoding="utf-8") as f:
    json.dump(anchors, f, indent=1)

bpy.ops.render.render(write_still=True)
print("RENDERED", args.out)
