#!/usr/bin/env python
"""Build a Cycles product scene from the KiCad 10 GLB and render four views.

Run with Blender 5.2:

    blender --background --python build_product_scene.py

The GLB is metres with KiCad XY. This script scales it to millimetres.
Missing vendor STEPs get labeled fallbacks. J1's pin-header mesh is hidden;
its pads stay. Does not touch recorder.kicad_pcb.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(os.environ.get("PSV_REPO", Path(__file__).resolve().parents[3]))
OUT = REPO / "build" / "product-renders"
GLB = OUT / "recorder.glb"
BLEND = OUT / "recorder-product-renders.blend"
INSPECT = OUT / "scene-inspect.json"

BOARD_W = 64.0
BOARD_H = 86.0
SAMPLES = 160
RESOLUTION = (1920, 1280)

# KiCad XY, millimetres. z is height of the body.
FALLBACKS = [
    {
        "ref": "U1",
        "kind": "module",
        "x": 14.0,
        "y": -18.0,
        "rot": 0.0,
        "sx": 15.4,
        "sy": 15.4,
        "sz": 2.4,
        "note": "ESP32-S3-MINI-1U: KiCad 10 has no MINI-1U STEP",
    },
    {
        "ref": "U2",
        "kind": "qfn",
        "x": 26.0,
        "y": 22.0,
        "rot": 0.0,
        "sx": 3.0,
        "sy": 3.0,
        "sz": 0.75,
        "note": "ES8311: library QFN STEP name is missing",
    },
    {
        "ref": "Y1",
        "kind": "osc",
        "x": 16.0,
        "y": 24.0,
        "rot": 0.0,
        "sx": 3.2,
        "sy": 2.5,
        "sz": 0.9,
        "note": "12.288 MHz ASE 3.2x2.5: no matching STEP in this install",
    },
    {
        "ref": "MK1",
        "kind": "mic",
        "x": 30.0,
        "y": 10.0,
        "rot": 90.0,
        "sx": 4.0,
        "sy": 3.0,
        "sz": 1.2,
        "note": "IM73A135: no Infineon PG-LLGA STEP in this install",
    },
    {
        "ref": "J2",
        "kind": "usbc",
        "x": 8.0,
        "y": -37.6,
        "rot": 0.0,
        "sx": 9.0,
        "sy": 7.4,
        "sz": 3.2,
        "note": "USB-C HRO TYPE-C-31-M-12: no HRO STEP in this install",
    },
    {
        "ref": "J3",
        "kind": "sd",
        "x": -22.5,
        "y": -18.0,
        "rot": 90.0,
        "sx": 14.5,
        "sy": 14.0,
        "sz": 1.8,
        "note": "microSD Wuerth 693072010801: no Wuerth STEP; slot faces -X",
    },
    {
        "ref": "SP1",
        "kind": "speaker",
        "x": 0.0,
        "y": 36.0,
        "rot": 0.0,
        "sx": 13.0,
        "sy": 13.0,
        "sz": 4.0,
        "note": "KELIKING KLJ-01304T: footprint has no 3D model",
    },
    {
        "ref": "U3",
        "kind": "qfn",
        "x": 24.0,
        "y": -39.5,
        "rot": 180.0,
        "sx": 3.0,
        "sy": 3.0,
        "sz": 1.0,
        "note": "BQ24074RGTR: library VQFN STEP name is missing",
    },
    {
        "ref": "BT1",
        "kind": "jst",
        "x": -23.5,
        "y": 34.0,
        "rot": 0.0,
        "sx": 5.9,
        "sy": 7.6,
        "sz": 6.0,
        "note": "JST PH S2B-PH-K-S; KiCad STEP if the 3D plugin is installed",
    },
]


def data_name(obj) -> str:
    if obj.data is None:
        return obj.name
    return obj.data.name


def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def new_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (360, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat, bsdf, nodes, links


def mat_soldermask():
    mat, bsdf, nodes, links = new_mat("PSV_Soldermask")
    _set(bsdf, "Base Color", (0.02, 0.09, 0.04, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.32)
    _set(bsdf, "IOR", 1.5)
    _set(bsdf, "Coat Weight", 0.25)
    _set(bsdf, "Coat Roughness", 0.18)
    _set(bsdf, "Coat IOR", 1.5)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.012
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 80.0
    noise.inputs["Detail"].default_value = 5.0
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    if "Normal" in bsdf.inputs:
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mat_fr4():
    mat, bsdf, nodes, links = new_mat("PSV_FR4")
    _set(bsdf, "Base Color", (0.4, 0.3, 0.15, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.6)
    _set(bsdf, "Transmission Weight", 0.08)
    vol = nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (0.5, 0.34, 0.12, 1.0)
    vol.inputs["Density"].default_value = 22.0
    links.new(vol.outputs["Volume"], nodes["Material Output"].inputs["Volume"])
    return mat


def mat_enig():
    mat, bsdf, _, _ = new_mat("PSV_ENIG")
    _set(bsdf, "Base Color", (0.82, 0.67, 0.28, 1.0))
    _set(bsdf, "Metallic", 1.0)
    _set(bsdf, "Roughness", 0.2)
    return mat


def mat_copper():
    mat, bsdf, _, _ = new_mat("PSV_Copper")
    _set(bsdf, "Base Color", (0.68, 0.36, 0.16, 1.0))
    _set(bsdf, "Metallic", 1.0)
    _set(bsdf, "Roughness", 0.3)
    return mat


def mat_silk():
    mat, bsdf, _, _ = new_mat("PSV_Silk")
    _set(bsdf, "Base Color", (0.88, 0.88, 0.84, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.52)
    return mat


def mat_solder():
    mat, bsdf, _, _ = new_mat("PSV_Solder")
    _set(bsdf, "Base Color", (0.7, 0.71, 0.72, 1.0))
    _set(bsdf, "Metallic", 1.0)
    _set(bsdf, "Roughness", 0.3)
    return mat


def mat_nylon():
    mat, bsdf, nodes, links = new_mat("PSV_Nylon")
    _set(bsdf, "Base Color", (0.16, 0.15, 0.14, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.5)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.035
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 180.0
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    if "Normal" in bsdf.inputs:
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mat_sensor():
    mat, bsdf, _, _ = new_mat("PSV_Sensor")
    _set(bsdf, "Base Color", (0.06, 0.06, 0.065, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.55)
    return mat


def mat_metal_can():
    mat, bsdf, _, _ = new_mat("PSV_MetalCan")
    _set(bsdf, "Base Color", (0.55, 0.56, 0.58, 1.0))
    _set(bsdf, "Metallic", 1.0)
    _set(bsdf, "Roughness", 0.35)
    return mat


def mat_chip():
    mat, bsdf, _, _ = new_mat("PSV_Chip")
    _set(bsdf, "Base Color", (0.025, 0.025, 0.025, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.38)
    return mat


def mat_ceramic():
    mat, bsdf, _, _ = new_mat("PSV_Ceramic")
    _set(bsdf, "Base Color", (0.72, 0.62, 0.42, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.45)
    return mat


def mat_speaker():
    mat, bsdf, _, _ = new_mat("PSV_Speaker")
    _set(bsdf, "Base Color", (0.035, 0.035, 0.04, 1.0))
    _set(bsdf, "Metallic", 0.2)
    _set(bsdf, "Roughness", 0.4)
    return mat


def mat_terminal():
    mat, bsdf, nodes, links = new_mat("PSV_Terminal")
    _set(bsdf, "Base Color", (0.05, 0.22, 0.08, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.52)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 140.0
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    if "Normal" in bsdf.inputs:
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def mat_stage():
    mat, bsdf, _, _ = new_mat("PSV_Stage")
    _set(bsdf, "Base Color", (0.016, 0.016, 0.018, 1.0))
    _set(bsdf, "Metallic", 0.0)
    _set(bsdf, "Roughness", 0.74)
    return mat


def world_setup():
    world = bpy.data.worlds.new("PSV_World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.018, 0.019, 0.022, 1.0)
    bg.inputs["Strength"].default_value = 0.15
    links.new(bg.outputs["Background"], out.inputs["Surface"])


def meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def world_bbox(objects):
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    found = False
    for obj in objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, world.x)
            mins.y = min(mins.y, world.y)
            mins.z = min(mins.z, world.z)
            maxs.x = max(maxs.x, world.x)
            maxs.y = max(maxs.y, world.y)
            maxs.z = max(maxs.z, world.z)
            found = True
    if not found:
        return Vector((0, 0, 0)), Vector((0, 0, 0))
    return mins, maxs


def assign_all(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
        return
    for i in range(len(obj.data.materials)):
        obj.data.materials[i] = mat


def apply_imported_materials(mats):
    counts = {
        "mask": 0,
        "fr4": 0,
        "copper": 0,
        "enig": 0,
        "silk": 0,
        "header_hidden": 0,
        "chip": 0,
        "passive": 0,
        "switch": 0,
        "other": 0,
    }
    for obj in meshes():
        name = data_name(obj).lower()
        if "pinheader" in name:
            obj.hide_render = True
            obj.hide_viewport = True
            counts["header_hidden"] += 1
            continue
        if "soldermask" in name:
            assign_all(obj, mats["mask"])
            counts["mask"] += 1
        elif name.endswith("_pcb") or "recorder_pcb" in name:
            assign_all(obj, mats["fr4"])
            counts["fr4"] += 1
        elif "silkscreen" in name:
            assign_all(obj, mats["silk"])
            counts["silk"] += 1
        elif "pad" in name:
            assign_all(obj, mats["enig"])
            counts["enig"] += 1
        elif "copper" in name or "via" in name:
            assign_all(obj, mats["copper"])
            counts["copper"] += 1
        elif "sw_spst" in name:
            assign_all(obj, mats["nylon"])
            counts["switch"] += 1
        elif "jst" in name or "s2b_ph" in name:
            if obj.data.materials:
                obj.data.materials[0] = mats["nylon"]
                for i in range(1, len(obj.data.materials)):
                    obj.data.materials[i] = mats["metal"]
            counts["other"] += 1
        elif "d_sma" in name:
            if obj.data.materials:
                obj.data.materials[0] = mats["chip"]
                for i in range(1, len(obj.data.materials)):
                    obj.data.materials[i] = mats["enig"]
            counts["other"] += 1
        elif any(k in name for k in ("sot-23", "msop", "qfn")):
            assign_all(obj, mats["chip"])
            counts["chip"] += 1
        elif name.startswith("c_") or "capacitor" in name:
            if obj.data.materials:
                obj.data.materials[0] = mats["ceramic"]
                for i in range(1, len(obj.data.materials)):
                    obj.data.materials[i] = mats["solder"]
            counts["passive"] += 1
        elif name.startswith("r_") or name.startswith("fuse") or name.startswith("led"):
            if obj.data.materials:
                obj.data.materials[0] = mats["chip"]
                for i in range(1, len(obj.data.materials)):
                    obj.data.materials[i] = mats["solder"]
            counts["passive"] += 1
        else:
            counts["other"] += 1
    return counts


def mm(value):
    return value * 0.001


def kicad_xy(x_mm, y_mm):
    """KiCad 10 GLB flips Y relative to the board file."""
    return mm(x_mm), -mm(y_mm)


def add_box(name, loc, size, rot_z, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    obj.location = loc
    obj.rotation_euler = (0.0, 0.0, math.radians(rot_z))
    assign_all(obj, mat)
    return obj


def add_cyl(name, loc, radius, depth, mat, axis="z"):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth)
    obj = bpy.context.active_object
    obj.name = name
    obj.location = loc
    if axis == "x":
        obj.rotation_euler = (0.0, math.pi / 2.0, 0.0)
    elif axis == "y":
        obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    assign_all(obj, mat)
    return obj


def add_fallbacks(fcu_z, mats):
    created = []

    def place(x_mm, y_mm, z):
        x, y = kicad_xy(x_mm, y_mm)
        return Vector((x, y, z))

    for spec in FALLBACKS:
        zc = fcu_z + mm(spec["sz"] / 2.0)
        loc = place(spec["x"], spec["y"], zc)
        kind = spec["kind"]
        ref = spec["ref"]
        if kind == "speaker":
            can = add_cyl(
                f"{ref}_fallback",
                loc,
                mm(spec["sx"] / 2.0),
                mm(spec["sz"]),
                mats["speaker"],
            )
            cap = add_cyl(
                f"{ref}_dustcap",
                place(spec["x"], spec["y"], fcu_z + mm(spec["sz"] + 0.05)),
                mm(4.2),
                mm(0.12),
                mats["nylon"],
            )
            created.extend([can.name, cap.name])
        elif kind == "usbc":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["metal"],
            )
            mouth = add_box(
                f"{ref}_mouth",
                place(spec["x"], -42.4, fcu_z + mm(1.55)),
                (mm(8.4), mm(1.6), mm(2.6)),
                0.0,
                mats["nylon"],
            )
            created.extend([body.name, mouth.name])
        elif kind == "sd":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["metal"],
            )
            slot = add_box(
                f"{ref}_slot",
                place(spec["x"] - 6.8, spec["y"], fcu_z + mm(0.85)),
                (mm(1.2), mm(12.0), mm(1.1)),
                0.0,
                mats["nylon"],
            )
            created.extend([body.name, slot.name])
        elif kind == "mic":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["sensor"],
            )
            created.append(body.name)
        elif kind == "module":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["metal"],
            )
            shield = add_box(
                f"{ref}_shield",
                place(spec["x"], spec["y"], fcu_z + mm(spec["sz"] + 0.05)),
                (mm(14.6), mm(14.6), mm(0.12)),
                spec["rot"],
                mats["metal"],
            )
            created.extend([body.name, shield.name])
        elif kind == "screw":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["terminal"],
            )
            created.append(body.name)
            ang = math.radians(spec["rot"])
            pitch = 3.5

            def board_from_local(lx, ly):
                bx = spec["x"] + lx * math.cos(ang) - ly * math.sin(ang)
                by = spec["y"] + lx * math.sin(ang) + ly * math.cos(ang)
                return bx, by

            for i, sign in enumerate((-1.0, 1.0)):
                sx, sy = board_from_local(sign * (pitch / 2.0), 0.0)
                screw = add_cyl(
                    f"{ref}_screw{i}",
                    place(sx, sy, fcu_z + mm(spec["sz"] + 0.2)),
                    mm(1.15),
                    mm(0.55),
                    mats["metal"],
                )
                mx, my = board_from_local(sign * (pitch / 2.0), spec["sy"] / 2.0 - 0.35)
                mouth = add_box(
                    f"{ref}_mouth{i}",
                    place(mx, my, fcu_z + mm(3.4)),
                    (mm(2.4), mm(1.1), mm(3.0)),
                    spec["rot"],
                    mats["nylon"],
                )
                created.extend([screw.name, mouth.name])
        elif kind == "jst":
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["nylon"],
            )
            created.append(body.name)
            for i, dx in enumerate((-3.9, 3.9)):
                pin = add_cyl(
                    f"{ref}_pin{i}",
                    place(spec["x"] + dx, spec["y"], fcu_z + mm(2.2)),
                    mm(0.55),
                    mm(4.4),
                    mats["enig"],
                )
                created.append(pin.name)
        else:
            body = add_box(
                f"{ref}_fallback",
                loc,
                (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"])),
                spec["rot"],
                mats["chip"] if kind in {"qfn", "osc"} else mats["sensor"],
            )
            created.append(body.name)
    return created


def add_solder_fillets(mats):
    added = 0
    for obj in list(meshes()):
        name = data_name(obj).lower()
        if obj.hide_render or not (
            name.startswith("r_") or name.startswith("c_") or name.startswith("fuse")
        ):
            continue
        mn, mx = world_bbox([obj])
        size = mx - mn
        footprint = sorted((abs(size.x), abs(size.y)))
        if not (mm(0.55) < footprint[0] < mm(1.1) and mm(1.2) < footprint[1] < mm(2.1)):
            continue
        long_x = abs(size.x) > abs(size.y)
        center = (mn + mx) / 2.0
        span = size.x if long_x else size.y
        for sign in (-1.0, 1.0):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=7, radius=mm(0.2))
            blob = bpy.context.active_object
            blob.name = f"Solder_{obj.name}_{sign:+.0f}"
            loc = center.copy()
            if long_x:
                loc.x += sign * (span / 2.0 - mm(0.12))
            else:
                loc.y += sign * (span / 2.0 - mm(0.12))
            loc.z = mn.z + mm(0.08)
            blob.location = loc
            blob.scale = (1.1, 0.65, 0.4)
            assign_all(blob, mats["solder"])
            added += 1
    return added


def add_stage(center):
    bpy.ops.mesh.primitive_plane_add(size=0.42)
    plane = bpy.context.active_object
    plane.name = "Stage"
    plane.location = (center.x, center.y, mm(-8.0))
    assign_all(plane, mat_stage())
    return plane


def add_lights(center):
    def area(name, energy, size, loc, rot, color=(1.0, 1.0, 1.0)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = size
        light.color = color
        obj = bpy.data.objects.new(name, light)
        obj.location = loc
        obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)
        return obj

    area(
        "Key",
        4.5,
        0.16,
        center + Vector((0.09, -0.11, 0.14)),
        (math.radians(48), 0.0, math.radians(28)),
    )
    area(
        "Fill",
        1.4,
        0.22,
        center + Vector((-0.12, 0.05, 0.1)),
        (math.radians(58), 0.0, math.radians(-40)),
        (0.78, 0.84, 1.0),
    )
    area(
        "Rim",
        2.0,
        0.12,
        center + Vector((0.01, 0.14, 0.06)),
        (math.radians(72), 0.0, math.radians(180)),
        (1.0, 0.96, 0.9),
    )
    area(
        "Bounce",
        0.7,
        0.25,
        center + Vector((0.0, 0.0, -0.08)),
        (math.radians(180), 0.0, 0.0),
        (0.85, 0.8, 0.7),
    )


def look_at(camera, target):
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def add_cameras(center):
    cams = {}

    def cam(name, loc, target, lens):
        data = bpy.data.cameras.new(name)
        data.lens = lens
        data.clip_start = 0.001
        data.clip_end = 2.0
        obj = bpy.data.objects.new(name, data)
        obj.location = loc
        bpy.context.scene.collection.objects.link(obj)
        look_at(obj, target)
        cams[name] = obj

    cam("hero", center + Vector((0.09, -0.13, 0.1)), center + Vector((0.0, 0.0, 0.002)), 45.0)
    cam("top", center + Vector((0.012, -0.02, 0.22)), center + Vector((0.0, 0.0, 0.001)), 50.0)
    mic_x, mic_y = kicad_xy(30.0, 10.0)
    cam(
        "sensor-detail",
        Vector((mic_x + 0.016, mic_y - 0.018, 0.022)),
        Vector((mic_x, mic_y, 0.0015)),
        50.0,
    )
    cam("back", center + Vector((0.06, 0.11, -0.09)), center + Vector((0.0, 0.0, 0.0)), 45.0)
    return cams


def enable_gpu():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.get_devices()
    chosen = None
    for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == kind
                chosen = kind
                break
        except Exception:
            continue
    scene.cycles.device = "GPU" if chosen else "CPU"
    return chosen or "CPU"


def render_views(cams):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium Contrast"
    scene.view_settings.exposure = -0.6
    written = []
    stage = bpy.data.objects.get("Stage")
    for name, cam in cams.items():
        if stage is not None:
            stage.hide_render = name == "back"
        scene.camera = cam
        path = OUT / f"recorder-{name}.png"
        scene.render.filepath = str(path)
        print("render", name, "->", path, flush=True)
        bpy.ops.render.render(write_still=True)
        written.append(path)
    if stage is not None:
        stage.hide_render = False
    return written


def write_gallery(pngs):
    cards = []
    for path in pngs:
        cards.append(
            f'<figure><img src="{path.name}" alt="{path.stem}">'
            f"<figcaption>{path.stem}</figcaption></figure>"
        )
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Recorder board product renders</title>
<style>
body {{ margin: 24px; background: #111; color: #ddd; font: 16px/1.4 sans-serif; }}
h1 {{ font-weight: 500; }}
.grid {{ display: grid; gap: 20px; grid-template-columns: 1fr; }}
@media (min-width: 900px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
img {{ width: 100%; height: auto; background: #000; }}
figcaption {{ margin-top: 6px; color: #aaa; }}
</style>
<h1>Recorder board</h1>
<p>KiCad 10 GLB, Blender 5.2 Cycles. Hero parts without vendor STEPs are labeled fallbacks.</p>
<div class="grid">
{''.join(cards)}
</div>
"""
    dest = OUT / "recorder-render-gallery.html"
    dest.write_text(html, encoding="utf-8")
    return dest


def main():
    if not GLB.is_file():
        raise SystemExit(f"missing {GLB}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(GLB))
    bpy.context.view_layer.update()

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    mats = {
        "mask": mat_soldermask(),
        "fr4": mat_fr4(),
        "enig": mat_enig(),
        "copper": mat_copper(),
        "silk": mat_silk(),
        "solder": mat_solder(),
        "nylon": mat_nylon(),
        "sensor": mat_sensor(),
        "metal": mat_metal_can(),
        "chip": mat_chip(),
        "ceramic": mat_ceramic(),
        "speaker": mat_speaker(),
        "terminal": mat_terminal(),
    }
    counts = apply_imported_materials(mats)

    pcb_objs = [o for o in meshes() if data_name(o).lower().endswith("_pcb")]
    if pcb_objs:
        pcb_min, pcb_max = world_bbox(pcb_objs)
        fcu_z = pcb_max.z
        holes_ok = abs((pcb_max.x - pcb_min.x) - mm(BOARD_W)) < mm(1.0)
    else:
        pcb_min, pcb_max = world_bbox(meshes())
        fcu_z = mm(0.4)
        holes_ok = False

    fallbacks = add_fallbacks(fcu_z, mats)
    fillets = add_solder_fillets(mats)
    bpy.context.view_layer.update()

    vis_min, vis_max = world_bbox(meshes())
    center = (vis_min + vis_max) / 2.0
    size = vis_max - vis_min
    add_stage(center)
    add_lights(center)
    world_setup()
    cams = add_cameras(center)
    device = enable_gpu()

    inspect = {
        "glb": str(GLB),
        "glb_bytes": GLB.stat().st_size,
        "object_count": len(meshes()),
        "objects": [
            {
                "name": o.name,
                "data": data_name(o),
                "hidden": bool(o.hide_render),
            }
            for o in meshes()
        ],
        "board_bbox_mm": {
            "min": [round(vis_min.x * 1000, 3), round(vis_min.y * 1000, 3), round(vis_min.z * 1000, 3)],
            "max": [round(vis_max.x * 1000, 3), round(vis_max.y * 1000, 3), round(vis_max.z * 1000, 3)],
            "size": [round(size.x * 1000, 3), round(size.y * 1000, 3), round(size.z * 1000, 3)],
        },
        "pcb_bbox_mm": {
            "min": [round(pcb_min.x * 1000, 3), round(pcb_min.y * 1000, 3), round(pcb_min.z * 1000, 3)],
            "max": [round(pcb_max.x * 1000, 3), round(pcb_max.y * 1000, 3), round(pcb_max.z * 1000, 3)],
        },
        "expected_outline_mm": [BOARD_W, BOARD_H],
        "outline_matches": holes_ok,
        "outline": "rectangular 64 x 86 mm, no corner radius",
        "fcu_z_mm": round(fcu_z * 1000, 3),
        "material_counts": counts,
        "fallbacks": FALLBACKS,
        "fallback_objects": fallbacks,
        "solder_fillets": fillets,
        "cycles_device": device,
        "mounting_holes_expected": 4,
        "mk1_port_expected": True,
    }
    INSPECT.write_text(json.dumps(inspect, indent=2), encoding="utf-8")
    print("inspect", INSPECT, flush=True)
    print(
        "size_mm",
        inspect["board_bbox_mm"]["size"],
        "fcu_z",
        fcu_z,
        "device",
        device,
        "fillets",
        fillets,
        flush=True,
    )

    pngs = render_views(cams)
    gallery = write_gallery(pngs)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    print("blend", BLEND, flush=True)
    print("gallery", gallery, flush=True)
    for path in pngs:
        print("png", path, "bytes", path.stat().st_size, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
