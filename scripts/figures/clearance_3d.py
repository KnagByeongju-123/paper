"""[Blender] 블랭킹 금형(펀치·다이·판재) 3D 반단면 그림.

직접 실행하지 말고 아래처럼 실행합니다 (make_figures.py 가 대신 실행해 줌).
  blender -b -P scripts/figures/clearance_3d.py -- --out figures/clearance_3d_raw.png --anchors out.json

치수(mm) 는 아래 옵션으로 바꿀 수 있습니다. 간극은 눈에 보이도록 과장해서 그립니다.
  --punch-d 40   펀치 지름        --thick 3.0   판 두께
  --gap 4.0      편측 간극(그림용) --stroke 0.6  펀치 진입 깊이 (판 두께 대비 비율)
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
ap.add_argument("--punch-d", type=float, default=40.0)
ap.add_argument("--thick", type=float, default=3.0)
ap.add_argument("--gap", type=float, default=4.0)
ap.add_argument("--stroke", type=float, default=0.35)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--view", choices=["overall", "detail"], default="overall", help="overall=전체, detail=간극 확대")
ap.add_argument("--width", type=int, default=1800)
ap.add_argument("--height", type=int, default=1200)
args = ap.parse_args(argv)

Rp = args.punch_d / 2          # 펀치 반지름
Rd = Rp + args.gap               # 다이 구멍 반지름 = 펀치 + 간극
t = args.thick
pen = args.stroke * t          # 펀치가 판재로 들어간 깊이

# ---- 빈 장면 ----
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def material(name, rgb, metallic=0.6, rough=0.35):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    return m


def cylinder(name, r, depth, z_center, verts=128):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=(0, 0, z_center))
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


def boolean(target, cutter, op="DIFFERENCE"):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.object = cutter
    mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)


def smooth(o):
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    try:   # Blender 4.1 이상
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
    except (AttributeError, RuntimeError):   # Blender 4.0 이하
        bpy.ops.object.shade_smooth(use_auto_smooth=True, auto_smooth_angle=math.radians(35))
    o.select_set(False)


# ---- 다이: 블록에 구멍 ----
DIE_W, DIE_H = Rd * 2 + 30, 20
die = box("Die", DIE_W, DIE_W, DIE_H, (0, 0, -DIE_H / 2))
hole = cylinder("DieHole", Rd, DIE_H * 3, -DIE_H / 2)
boolean(die, hole)
bpy.data.objects.remove(hole)

# ---- 판재: 다이 위, 펀치 아래가 살짝 눌린 모양(전단 진행 중) ----
sheet = box("Sheet", DIE_W, DIE_W, t, (0, 0, t / 2))
slug = cylinder("Slug", Rp, t, t / 2 - pen)            # 펀치 아래로 밀려 내려간 부분
ring_cut = cylinder("RingCut", Rd, t * 3, t / 2)        # 판재에서 다이 구멍 영역 비우기
boolean(sheet, ring_cut)
bpy.data.objects.remove(ring_cut)
# 간극 영역의 판재(펀치~다이 사이) : 비스듬히 끊어지는 띠
neck_outer = cylinder("NeckO", Rd, t, t / 2 - pen / 2)
neck_inner = cylinder("NeckI", Rp, t * 3, t / 2)
boolean(neck_outer, neck_inner)
bpy.data.objects.remove(neck_inner)
for o in (slug, neck_outer):
    boolean(sheet, o, "UNION")
    bpy.data.objects.remove(o)

# ---- 펀치: 원기둥 + 위쪽 생크 ----
PUNCH_H = 40
punch = cylinder("Punch", Rp, PUNCH_H, t - pen + PUNCH_H / 2)
shank = cylinder("Shank", Rp * 0.6, 18, t - pen + PUNCH_H + 9)
boolean(punch, shank, "UNION")
bpy.data.objects.remove(shank)

# ---- 앞쪽 절반 잘라내기 → 반단면 ----
for o in (die, sheet, punch):
    cutter = box("Cutter", 400, 200, 400, (0, -100, 0))
    boolean(o, cutter)
    bpy.data.objects.remove(cutter)

die.data.materials.append(material("DieMat", (0.36, 0.45, 0.58), 0.7, 0.32))
punch.data.materials.append(material("PunchMat", (0.55, 0.57, 0.60), 0.85, 0.30))
sheet.data.materials.append(material("SheetMat", (0.92, 0.55, 0.22), 0.3, 0.45))
for o in (die, sheet, punch):
    smooth(o)


# ---- 조명 ----
bpy.ops.object.light_add(type="AREA", location=(60, -90, 120))
key = bpy.context.active_object
key.data.energy = 25000
key.data.size = 80
key.rotation_euler = (math.radians(40), 0, math.radians(30))
bpy.ops.object.light_add(type="SUN", location=(-50, -40, 80))
fill = bpy.context.active_object
fill.data.energy = 1.2
fill.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-40))

# ---- 카메라: 단면이 잘 보이게 앞·위·오른쪽에서 ----
if args.view == "overall":
    target = Vector((4, 0, 14))
    bpy.ops.object.camera_add(location=(70, -190, 85))
    cam = bpy.context.active_object
    cam.data.lens = 50
else:   # 오른쪽 간극 부분을 가까이에서
    target = Vector((Rp + args.gap / 2, 0, t / 2 - 1))
    bpy.ops.object.camera_add(location=(target.x + 16, -80, target.z + 22))
    cam = bpy.context.active_object
    cam.data.lens = 60
direction = target - cam.location
cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
scene.camera = cam

# ---- 배경: 흰색 ----
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0

# ---- 렌더 설정 ----
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = args.samples
# 노이즈 제거(OpenImageDenoise)는 설치판에 따라 없을 수 있어 끄고, 대신 샘플 수로 품질을 맞춘다
scene.cycles.use_denoising = False
scene.render.resolution_x = args.width
scene.render.resolution_y = args.height
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.render.filepath = args.out

# ---- 라벨 위치(화면 좌표) 계산 → PIL 로 한글 라벨을 붙이기 위함 ----
bpy.context.view_layer.update()   # 카메라 위치·방향을 확정한 뒤 좌표 계산


def to_px(p):
    v = world_to_camera_view(scene, cam, Vector(p))
    return [round(v.x * args.width), round((1 - v.y) * args.height)]


anchors = {
    "punch": to_px((Rp * 0.3, 0, t - pen + PUNCH_H * 0.6)),
    "die": to_px((Rd + 12, 0, -DIE_H * 0.55)),
    "sheet": to_px((Rd + 14, 0, t)),
    "gap_left": to_px((Rp, 0, -1.5)),
    "gap_right": to_px((Rd, 0, -1.5)),
    "gap_top": to_px((Rp + args.gap / 2, 0, t * 0.2)),
    "punch_d_l": to_px((-Rp, 0, t - pen + PUNCH_H + 2)),
    "punch_d_r": to_px((Rp, 0, t - pen + PUNCH_H + 2)),
    "size": [args.width, args.height],
    "params": {"punch_d": args.punch_d, "t": t, "c": args.gap},
}
with open(args.anchors, "w", encoding="utf-8") as f:
    json.dump(anchors, f, ensure_ascii=False, indent=1)

bpy.ops.render.render(write_still=True)
print("RENDERED", args.out)
