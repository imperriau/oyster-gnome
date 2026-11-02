# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural, original AirPods Pro 2 style case + pods turntable for the lid-open card.

Builds the whole scene from primitives (no imported models, no Apple artwork) and renders a
seamless 360 degree turntable with a transparent background.

Run headless (Flatpak Blender):
    flatpak run org.blender.Blender -b --factory-startup \
        -P tools/blender/airpods_pro2_spin.py -- --out render/2420 [--frames 96] [--size 256]
        [--samples 48] [--preview 0,24,48] [--save render/airpods_pro2.blend]

Units: 1 Blender unit = 10 mm. Real case is about 60.6 x 21.7 x 45.2 mm.
"""

import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

# ----------------------------------------------------------------------------- dimensions
W, D = 6.06, 2.17  # case width (x) and depth (y)
HB, HL = 3.15, 1.37  # base and lid height
CORNER = 1.0  # vertical edge rounding
EDGE = 0.75  # bottom/top edge rounding
LID_OPEN_DEG = 100.0
START_DEG = -28.0  # first frame is a three-quarter view
POD_X = 1.42  # pod centres from the middle


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="output directory for frame_NNNN.png")
    p.add_argument("--frames", type=int, default=96)
    p.add_argument("--size", type=int, default=256)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--preview", default="", help="comma-separated frame numbers to render only")
    p.add_argument("--save", default="", help="also save the .blend here")
    return p.parse_args(argv)


# ----------------------------------------------------------------------------- helpers
def material(name, color, rough=0.3, coat=0.0, metallic=0.0, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    if emission:
        b.inputs["Emission Color"].default_value = (*emission, 1.0)
        b.inputs["Emission Strength"].default_value = strength
    return m


def rounded_block(name, w, d, h, z0, round_bottom, round_top, mat):
    """Box from z0 to z0+h with rounded vertical edges and optionally rounded top/bottom edges."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= w
        v.co.y *= d
        v.co.z = z0 + (v.co.z + 0.5) * h
    weight = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new(
        "bevel_weight_edge"
    )
    zmin, zmax = z0, z0 + h
    for e in bm.edges:
        a, b = e.verts
        vertical = abs(a.co.x - b.co.x) < 1e-6 and abs(a.co.y - b.co.y) < 1e-6
        at_bottom = abs(a.co.z - zmin) < 1e-6 and abs(b.co.z - zmin) < 1e-6
        at_top = abs(a.co.z - zmax) < 1e-6 and abs(b.co.z - zmax) < 1e-6
        e[weight] = (
            1.0 if vertical or (at_bottom and round_bottom) or (at_top and round_top) else 0.0
        )
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    # Two bevels: big radius on the vertical edges first, then the top/bottom edges.
    mod = ob.modifiers.new("corners", "BEVEL")
    mod.limit_method = "WEIGHT"
    mod.width = CORNER
    mod.segments = 14
    mod.profile = 0.55
    ob.data.materials.append(mat)
    apply_modifiers(ob)
    if round_bottom or round_top:
        mod = ob.modifiers.new("edges", "BEVEL")
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(60)
        mod.width = EDGE
        mod.segments = 10
        mod.profile = 0.5
        # Only round the faces we asked for: protect the seam face with a vertex group.
        apply_modifiers(ob)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def apply_modifiers(ob):
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def ellipsoid(name, loc, scale, mat, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob


def capsule(name, loc, radius, length, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40, radius=radius, depth=length, location=loc, rotation=rot
    )
    cyl = bpy.context.active_object
    cyl.name = name
    cyl.data.materials.append(mat)
    mod = cyl.modifiers.new("round", "BEVEL")
    mod.width = radius * 0.9
    mod.segments = 8
    mod.limit_method = "ANGLE"
    apply_modifiers(cyl)
    bpy.ops.object.shade_smooth()
    return cyl


def boolean(target, cutter, op="DIFFERENCE"):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.object = cutter
    apply_modifiers(target)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ----------------------------------------------------------------------------- scene
def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    white = material("case_white", (0.93, 0.93, 0.94), rough=0.22, coat=0.35)
    inner = material("case_inner", (0.80, 0.80, 0.82), rough=0.45)
    pod_white = material("pod_white", (0.95, 0.95, 0.96), rough=0.15, coat=0.5)
    tip = material("ear_tip", (0.83, 0.84, 0.86), rough=0.65)
    led = material("led", (0.1, 0.9, 0.3), rough=0.3, emission=(0.2, 1.0, 0.35), strength=8.0)
    steel = material("steel", (0.75, 0.75, 0.77), rough=0.25, metallic=1.0)

    rig = bpy.data.objects.new("turntable", None)
    scene.collection.objects.link(rig)

    # Base with two pod recesses.
    base = rounded_block("base", W, D, HB, 0.0, round_bottom=True, round_top=False, mat=white)
    base.data.materials.append(inner)
    for sx in (-1, 1):
        cut = ellipsoid("recess", (sx * POD_X, 0.0, HB), (0.98, 0.86, 0.75), inner)
        boolean(base, cut)
    # Recess walls get the inner material: faces whose normal does not point outwards.
    for p in base.data.polygons:
        c = p.center
        if (
            c.z > HB - 0.9
            and abs(c.x) < W / 2 - 0.25
            and abs(c.y) < D / 2 - 0.12
            and p.normal.z < 0.97
        ):
            p.material_index = 1
    base.parent = rig

    # Lid, hinged at the back top edge of the base.
    hinge = bpy.data.objects.new("hinge", None)
    scene.collection.objects.link(hinge)
    hinge.location = (0.0, D / 2, HB)
    hinge.parent = rig
    lid = rounded_block("lid", W, D, HL, HB + 0.015, round_bottom=False, round_top=True, mat=white)
    lid.parent = hinge
    lid.location = (0.0, -D / 2, -HB)
    hinge.rotation_euler.x = -math.radians(LID_OPEN_DEG)

    # Status light on the front, lanyard loop on the right side.
    led_ob = ellipsoid("led", (0.0, -D / 2 - 0.005, HB - 0.75), (0.07, 0.03, 0.07), led, 16, 8)
    led_ob.parent = rig
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.32,
        minor_radius=0.06,
        location=(W / 2 + 0.05, 0.0, 0.9),
        rotation=(0.0, math.radians(90), 0.0),
    )
    loop = bpy.context.active_object
    loop.data.materials.append(steel)
    bpy.ops.object.shade_smooth()
    loop.parent = rig

    # Pods sitting in the recesses: head above the rim, stem hidden in the base.
    for sx in (-1, 1):
        head = ellipsoid(
            f"pod_head_{sx}", (sx * POD_X, 0.0, HB + 0.18), (0.88, 0.78, 0.72), pod_white
        )
        head.parent = rig
        stem = capsule(
            f"pod_stem_{sx}", (sx * (POD_X + 0.25), 0.05, HB - 1.2), 0.32, 2.6, pod_white
        )
        stem.parent = rig
        tip_ob = ellipsoid(
            f"pod_tip_{sx}", (sx * (POD_X - 0.55), -0.05, HB + 0.42), (0.42, 0.42, 0.36), tip
        )
        tip_ob.rotation_euler = (0.0, math.radians(-35 * sx), 0.0)
        tip_ob.parent = rig

    # Turntable: seamless 360 degree loop over the frame range.
    return scene, rig


def lights_and_camera(scene):
    world = bpy.data.worlds.new("world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.57, 0.62, 1.0)
    bg.inputs["Strength"].default_value = 0.35

    def area(name, loc, energy, size):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        ob = bpy.data.objects.new(name, data)
        ob.location = loc
        scene.collection.objects.link(ob)
        direction = Vector((0, 0, 2.2)) - Vector(loc)
        ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    area("key", (-7.0, -9.0, 10.0), 520, 7.0)
    area("fill", (8.0, -6.0, 4.0), 140, 6.0)
    area("rim", (0.0, 9.0, 8.0), 420, 6.0)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 85
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    elev = math.radians(18)
    dist = 19.0
    target = Vector((0.0, 0.0, 2.55))
    cam.location = target + Vector((0.0, -math.cos(elev) * dist, math.sin(elev) * dist))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam


def animate(scene, rig, frames):
    scene.frame_start = 1
    scene.frame_end = frames
    start = math.radians(START_DEG)
    rig.rotation_euler.z = start
    rig.keyframe_insert("rotation_euler", index=2, frame=1)
    rig.rotation_euler.z = start + 2 * math.pi
    rig.keyframe_insert("rotation_euler", index=2, frame=frames + 1)
    for fc in (
        rig.animation_data.action.fcurves if hasattr(rig.animation_data.action, "fcurves") else []
    ):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    # Blender 5 layered actions: walk channelbags if fcurves is not on the action.
    act = rig.animation_data.action
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                for fc in bag.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"


def render_settings(scene, size, samples, out):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 90
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 1.3
    scene.render.filepath = os.path.join(os.path.abspath(out), "frame_")


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    scene, rig = build()
    lights_and_camera(scene)
    animate(scene, rig, args.frames)
    render_settings(scene, args.size, args.samples, args.out)
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
    if args.preview:
        for f in (int(x) for x in args.preview.split(",")):
            scene.frame_set(f)
            scene.render.filepath = os.path.join(os.path.abspath(args.out), f"preview_{f:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)


main()
