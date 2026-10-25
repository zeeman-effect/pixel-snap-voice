#!/usr/bin/env python
"""Scene library for the 6061 tray / PETG lid product stills.

Per-image scripts live in hardware/cad/renders/. Each one imports this
module, builds only the parts it needs, and writes one PNG:

    blender --background --python hardware/cad/renders/exploded.py

The lid is natural translucent PETG so D1 and D2, the tray, and the
cavity read through it. The tray stays bead-blasted 6061. The board is
the KiCad GLB, seated on the four posts. J2 is the C6276862 stadium
(black PA46, four gold faces). Other parts with no vendor STEP get a sized box.

OpenSCAD millimetres become Blender metres. Does not touch the print STLs
in hardware/cad/export/.
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

REPO = Path(os.environ.get("PSV_REPO", Path(__file__).resolve().parents[2]))
_CAD = str(REPO / "hardware" / "cad")
if _CAD not in sys.path:
    sys.path.insert(0, _CAD)
import pogo_model
from check_envelope import stacks
SRC = REPO / "build" / "case-renders"
OUT = SRC
BLEND = OUT / "case-6061.blend"
TRAY = SRC / "tray_worn.stl"
LID = SRC / "lid_worn.stl"
PILL = SRC / "button_worn.stl"
BOARD_GLB = Path(
    os.environ.get(
        "PSV_BOARD_GLB",
        SRC / "board.glb",
    )
)
PARAMS = REPO / "hardware" / "cad" / "params.json"

# KiCad 10 has no STEP for these. Boxes use board-file XY so they sit
# with the Y-flipped GLB. Heights are the datasheet / params.json bodies.
# Live after the lid/board 180° spin: J2 at phone-top, MK1 phone-right.
BOARD_FALLBACKS = (
    {"ref": "U1", "x": 14.0, "y": -18.0, "sx": 15.4, "sy": 15.4, "sz": 2.4, "rot": 0.0, "kind": "module"},
    {"ref": "J2", "x": 0.0, "y": 36.0, "sx": 22.3, "sy": 7.7, "sz": 2.0, "rot": 0.0, "kind": "pogo"},
    {"ref": "J3", "x": -22.0, "y": -18.0, "sx": 6.2, "sy": 8.0, "sz": 0.8, "rot": 0.0, "kind": "sd"},
    {"ref": "MK1", "x": 27.5, "y": 17.0, "sx": 4.0, "sy": 3.0, "sz": 1.2, "rot": 90.0, "kind": "mic"},
    {"ref": "Y1", "x": 27.2, "y": 23.0, "sx": 3.2, "sy": 2.5, "sz": 0.9, "rot": 180.0, "kind": "osc"},
)

SAMPLES = int(os.environ.get("PSV_SAMPLES", "128"))
RESOLUTION = (1920, 1280)
EXPLODE_GAP_MM = 18.0
CSK_H_MM = 0.9
CSK_HEAD_D_MM = 3.0
SCREW_SHAFT_D_MM = 1.6
SCREW_SHAFT_L_MM = 6.0
# Sit the CSK face a hair above the lid skin so a camera ray (and the
# web viewer) hits metal before it skips through the PETG sheet.
SCREW_PROUD_MM = 0.2


@dataclass
class BuiltScene:
    tray: object
    lid: object | None
    pill: object | None
    board: object | None
    magnets: object | None
    pouch: object | None
    screws: object | None
    stage: object


def mm(value):
    return value * 0.001


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 12
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_x = RESOLUTION[0]
    scene.render.resolution_y = RESOLUTION[1]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.8
    prefs = bpy.context.preferences.addons.get("cycles")
    if prefs is not None:
        cycles = prefs.preferences
        if getattr(cycles, "compute_device_type", "") != "NONE":
            scene.cycles.device = "GPU"
        devices = getattr(cycles, "devices", None)
        if devices:
            for device in devices:
                device.use = True
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.05, 0.052, 0.055, 1.0)
    bg.inputs["Strength"].default_value = 0.4


def set_input(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def new_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    principled = mat.node_tree.nodes["Principled BSDF"]
    return mat, principled, mat.node_tree


def mat_6061(name, roughness, anisotropic):
    """Bead-blasted 6061, clear-anodised. Not a chrome brick."""
    mat, principled, tree = new_mat(name)
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", roughness)
    set_input(principled, "Specular IOR Level", 0.35)
    set_input(principled, "Specular", 0.35)
    set_input(principled, "Coat Weight", 0.08)
    set_input(principled, "Coat", 0.08)
    set_input(principled, "Coat Roughness", 0.45)
    set_input(principled, "Anisotropic", anisotropic)
    set_input(principled, "Anisotropic Rotation", 0.22)
    principled.inputs["Base Color"].default_value = (0.42, 0.44, 0.46, 1.0)
    tex = tree.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 140.0
    tex.inputs["Detail"].default_value = 10.0
    tex.inputs["Roughness"].default_value = 0.6
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0002
    tree.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return mat


def mat_petg_natural():
    """Natural translucent PETG. D1 and D2 read through it."""
    mat, principled, tree = new_mat("PETG_natural")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.08)
    set_input(principled, "IOR", 1.53)
    set_input(principled, "Specular IOR Level", 0.5)
    set_input(principled, "Transmission Weight", 1.0)
    set_input(principled, "Coat Weight", 0.18)
    set_input(principled, "Coat Roughness", 0.08)
    set_input(principled, "Thin Wall", True)
    principled.inputs["Base Color"].default_value = (0.90, 0.91, 0.86, 1.0)
    tex = tree.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 90.0
    tex.inputs["Detail"].default_value = 6.0
    tex.inputs["Roughness"].default_value = 0.45
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.02
    bump.inputs["Distance"].default_value = 0.00010
    tree.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    vol = tree.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = (0.82, 0.86, 0.78, 1.0)
    vol.inputs["Density"].default_value = 18.0
    out = tree.nodes["Material Output"]
    tree.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat


def mat_petg_purple():
    """Kept for the case-viewer script. Same natural PETG as the stills."""
    return mat_petg_natural()


def mat_stage():
    mat, principled, _tree = new_mat("Stage")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.82)
    principled.inputs["Base Color"].default_value = (0.04, 0.04, 0.045, 1.0)
    return mat


def import_stl(path, name):
    bpy.ops.wm.stl_import(filepath=str(path), up_axis="Z", forward_axis="Y")
    obj = bpy.context.selected_objects[0]
    obj.name = name
    obj.scale = (0.001, 0.001, 0.001)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def assign_all(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
        return
    for i in range(len(obj.data.materials)):
        obj.data.materials[i] = mat


def data_name(obj):
    if obj.data is None:
        return obj.name
    return obj.data.name


def stack_z():
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    pcb_t = params["pcb"]["thickness_mm"]
    pcb_z = stacks(params)["tray"] - pcb_t
    return pcb_z, pcb_t


def parent_keep(obj, parent):
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_parent_inverse = parent.matrix_world.inverted()
    obj.matrix_world = world


def walk_meshes(root):
    found = []

    def visit(obj):
        if obj.type == "MESH" and not obj.hide_render:
            found.append(obj)
        for child in obj.children:
            visit(child)

    visit(root)
    return found


def mat_soldermask():
    mat, principled, _tree = new_mat("PSV_Soldermask")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.32)
    set_input(principled, "Coat Weight", 0.22)
    set_input(principled, "Coat Roughness", 0.18)
    principled.inputs["Base Color"].default_value = (0.02, 0.09, 0.04, 1.0)
    return mat


def mat_fr4():
    mat, principled, _tree = new_mat("PSV_FR4")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.6)
    principled.inputs["Base Color"].default_value = (0.4, 0.3, 0.15, 1.0)
    return mat


def mat_enig():
    mat, principled, _tree = new_mat("PSV_ENIG")
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", 0.22)
    principled.inputs["Base Color"].default_value = (0.82, 0.67, 0.28, 1.0)
    return mat


def mat_silk():
    mat, principled, _tree = new_mat("PSV_Silk")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.52)
    principled.inputs["Base Color"].default_value = (0.88, 0.88, 0.84, 1.0)
    mat.use_backface_culling = True
    return mat


def mat_tpu():
    """Matte black TPU 95A. The record pill, not shiny ABS."""
    mat, principled, _tree = new_mat("TPU_95A")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.62)
    set_input(principled, "Specular IOR Level", 0.28)
    set_input(principled, "IOR", 1.50)
    principled.inputs["Base Color"].default_value = (0.018, 0.018, 0.02, 1.0)
    return mat


def mat_chip():
    mat, principled, _tree = new_mat("PSV_Chip")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.4)
    principled.inputs["Base Color"].default_value = (0.03, 0.03, 0.035, 1.0)
    return mat


def mat_module():
    mat, principled, _tree = new_mat("PSV_Module")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.45)
    principled.inputs["Base Color"].default_value = (0.08, 0.09, 0.1, 1.0)
    return mat


def mat_pogo():
    """Black PA46 housing. Matches the LCSC C6276862 photo."""
    mat, principled, _tree = new_mat("PSV_Pogo")
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.22)
    set_input(principled, "Specular IOR Level", 0.45)
    set_input(principled, "Specular", 0.45)
    principled.inputs["Base Color"].default_value = (0.025, 0.025, 0.028, 1.0)
    return mat


def mat_pogo_gold():
    mat, principled, _tree = new_mat("PSV_PogoGold")
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", 0.18)
    principled.inputs["Base Color"].default_value = (0.86, 0.68, 0.28, 1.0)
    return mat


def mat_nickel():
    """Plated NdFeB ring. The phone-face connector."""
    mat, principled, _tree = new_mat("PSV_Nickel")
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", 0.16)
    principled.inputs["Base Color"].default_value = (0.78, 0.79, 0.76, 1.0)
    return mat


def mat_shunt():
    """Steel keeper behind the ring, away from the phone."""
    mat, principled, _tree = new_mat("PSV_Shunt")
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", 0.42)
    principled.inputs["Base Color"].default_value = (0.42, 0.43, 0.45, 1.0)
    return mat


def mat_stainless():
    """M1.6 CSK heads. Bead-blasted 304, not chrome."""
    mat, principled, _tree = new_mat("PSV_M16")
    set_input(principled, "Metallic", 1.0)
    set_input(principled, "Roughness", 0.28)
    principled.inputs["Base Color"].default_value = (0.72, 0.73, 0.75, 1.0)
    return mat


def mat_pouch():
    """Kapton-wrapped LiPo foil. Amber, not bare silver."""
    mat, principled, tree = new_mat("PSV_Pouch")
    set_input(principled, "Metallic", 0.72)
    set_input(principled, "Roughness", 0.34)
    principled.inputs["Base Color"].default_value = (0.62, 0.38, 0.12, 1.0)
    tex = tree.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 40.0
    tex.inputs["Detail"].default_value = 4.0
    bump = tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.00015
    tree.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return mat


def mat_wire(name, color):
    mat, principled, _tree = new_mat(name)
    set_input(principled, "Metallic", 0.0)
    set_input(principled, "Roughness", 0.45)
    principled.inputs["Base Color"].default_value = (*color, 1.0)
    return mat


def mesh_from_pydata(name, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def extrude_loop_mm(name, loop_mm, z0_mm, z1_mm):
    loop = [(mm(x), mm(y)) for x, y in loop_mm]
    n = len(loop)
    verts = [(x, y, mm(z0_mm)) for x, y in loop] + [(x, y, mm(z1_mm)) for x, y in loop]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    return mesh_from_pydata(name, verts, faces)


def rounded_rect_loop(length_mm, width_mm, radius_mm, segs=8):
    """CCW outline in millimetres, centered on the origin."""
    radius_mm = min(radius_mm, length_mm / 2.0, width_mm / 2.0)
    hx = length_mm / 2.0 - radius_mm
    hy = width_mm / 2.0 - radius_mm
    corners = (
        (hx, -hy, -math.pi / 2.0),
        (hx, hy, 0.0),
        (-hx, hy, math.pi / 2.0),
        (-hx, -hy, math.pi),
    )
    pts = []
    for cx, cy, a0 in corners:
        for i in range(segs):
            ang = a0 + (math.pi / 2.0) * i / segs
            pts.append((cx + radius_mm * math.cos(ang), cy + radius_mm * math.sin(ang)))
    return pts


def annulus_mesh(name, od_mm, id_mm, z0_mm, z1_mm, segs=80):
    ro = mm(od_mm / 2.0)
    ri = mm(id_mm / 2.0)
    z0 = mm(z0_mm)
    z1 = mm(z1_mm)

    def ring(radius, z):
        return [
            (
                radius * math.cos(2.0 * math.pi * i / segs),
                radius * math.sin(2.0 * math.pi * i / segs),
                z,
            )
            for i in range(segs)
        ]

    verts = ring(ro, z0) + ring(ri, z0) + ring(ro, z1) + ring(ri, z1)
    faces = []
    n = segs
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, 2 * n + j, 2 * n + i))
        faces.append((n + j, n + i, 3 * n + i, 3 * n + j))
        faces.append((j, i, n + i, n + j))
        faces.append((2 * n + i, 2 * n + j, 3 * n + j, 3 * n + i))
    return mesh_from_pydata(name, verts, faces)


def add_lead(parent, name, p0_mm, p1_mm, diameter_mm, mat):
    start = Vector((mm(p0_mm[0]), mm(p0_mm[1]), mm(p0_mm[2])))
    end = Vector((mm(p1_mm[0]), mm(p1_mm[1]), mm(p1_mm[2])))
    delta = end - start
    bpy.ops.mesh.primitive_cylinder_add(
        radius=mm(diameter_mm / 2.0),
        depth=delta.length,
        vertices=12,
    )
    lead = bpy.context.active_object
    lead.name = name
    assign(lead, mat)
    lead.parent = parent
    lead.location = (start + end) / 2.0
    lead.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
    return lead


def load_params():
    return json.loads(PARAMS.read_text(encoding="utf-8"))


def hole_xy_mm(params=None):
    """Four M1.6 centres, same as case.scad hole_xy()."""
    if params is None:
        params = load_params()
    inset = params["mounting"]["hole_inset_mm"]
    hx = params["pcb"]["width_mm"] / 2.0 - inset
    hy = params["pcb"]["height_mm"] / 2.0 - inset
    return ((-hx, -hy), (hx, -hy), (-hx, hy), (hx, hy))


def add_magnets():
    """Nickel ring and clocking block in tray-local millimetres.

    Own empty at the origin. Call parent_keep(magnets, tray) to seat them
    in the wells. Do not parent here: the exploded shot needs them free.
    """
    params = load_params()
    mag = params["magnet"]
    nickel = mat_nickel()
    empty = bpy.data.objects.new("Magnets", None)
    bpy.context.scene.collection.objects.link(empty)
    skin = mag["skin_mm"]
    ring = annulus_mesh(
        "MagnetRing",
        mag["od_mm"],
        mag["id_mm"],
        skin,
        skin + mag["thickness_mm"],
    )
    assign(ring, nickel)
    ring.parent = empty
    if mag["shunt_thickness_mm"] > 0.05:
        shunt = extrude_loop_mm(
            "Shunt",
            [
                (
                    mag["shunt_od_mm"] / 2.0 * math.cos(2.0 * math.pi * i / 64),
                    mag["shunt_od_mm"] / 2.0 * math.sin(2.0 * math.pi * i / 64),
                )
                for i in range(64)
            ],
            skin + mag["thickness_mm"],
            skin + mag["thickness_mm"] + mag["shunt_thickness_mm"],
        )
        assign(shunt, mat_shunt())
        shunt.parent = empty
    ring_r = (mag["od_mm"] + 0.3) / 2.0
    well_h = mag["clock_length_mm"] + 0.8
    cy = -(ring_r + 1.2 + well_h / 2.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    clock = bpy.context.active_object
    clock.name = "ClockMagnet"
    clock.scale = (
        mm(mag["clock_width_mm"]),
        mm(mag["clock_length_mm"]),
        mm(mag["thickness_mm"]),
    )
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    clock.parent = empty
    clock.location = (0.0, mm(cy), mm(skin + mag["thickness_mm"] / 2.0))
    assign(clock, nickel)
    print(
        f"  magnets: ring OD {mag['od_mm']:.0f} / ID {mag['id_mm']:.0f} x "
        f"{mag['thickness_mm']:.1f} mm, clock at y={cy:.1f}",
        flush=True,
    )
    return empty


def add_pouch(board):
    """Kapton pouch taped to B.Cu. Parents to the board empty."""
    params = load_params()
    batt = params["battery"]
    tape = batt["tape_mm"]
    thick = batt["max_thickness_mm"]
    length = batt["pocket_width_mm"]
    width = batt["pocket_height_mm"]
    empty = bpy.data.objects.new("Pouch", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.parent = board
    empty.location = (
        mm(batt["offset_x_mm"]),
        mm(batt["offset_y_mm"]),
        mm(-(tape + thick / 2.0)),
    )
    pouch_mat = mat_pouch()
    body = extrude_loop_mm(
        "PouchBody",
        rounded_rect_loop(length - 5.0, width - 5.0, 3.0),
        -thick / 2.0,
        thick / 2.0,
    )
    assign(body, pouch_mat)
    body.parent = empty
    flange = extrude_loop_mm(
        "PouchSeal",
        rounded_rect_loop(length, width, 4.0),
        -0.22,
        0.22,
    )
    assign(flange, pouch_mat)
    flange.parent = empty
    pad_x = params["connectors"]["batt_pad_x_mm"]
    pad_y = params["connectors"]["batt_pad_y_mm"]
    toward = 1.0 if pad_y >= batt["offset_y_mm"] else -1.0
    pcm_w = 20.0
    pcm_h = 8.0
    pcm_t = 1.0
    pcm_y = toward * (width / 2.0 - pcm_h / 2.0 - 1.0)
    pcm = extrude_loop_mm(
        "PouchPCM",
        rounded_rect_loop(pcm_w, pcm_h, 0.6),
        thick / 2.0 - pcm_t,
        thick / 2.0 + 0.05,
    )
    assign(pcm, mat_chip())
    pcm.parent = empty
    pcm.location = (0.0, mm(pcm_y), 0.0)
    red = mat_wire("PSV_WireRed", (0.45, 0.02, 0.015))
    black = mat_wire("PSV_WireBlack", (0.015, 0.015, 0.016))
    exit_y = toward * (width / 2.0 - 0.8)
    z_pad = tape + thick / 2.0 - 0.08
    for name, x_mm, mat in (("LeadPlus", 2.0, red), ("LeadMinus", -2.0, black)):
        add_lead(
            empty,
            name,
            (x_mm, exit_y, thick / 2.0 - 0.2),
            (
                pad_x + x_mm - batt["offset_x_mm"],
                pad_y - batt["offset_y_mm"],
                z_pad,
            ),
            0.7,
            mat,
        )
    print(
        f"  pouch: {batt.get('mpn', 'pouch')} {length:.1f}x{width:.1f}x{thick:.1f} mm at "
        f"({batt['offset_x_mm']:.0f}, {batt['offset_y_mm']:.0f})",
        flush=True,
    )
    return empty


def add_pack(tray, board):
    """Closed-case helper: magnets in the wells, pouch on B.Cu."""
    magnets = add_magnets()
    parent_keep(magnets, tray)
    pouch = add_pouch(board)
    return magnets, pouch


def join_objects(name, objects):
    """Bake selected meshes into one named object. Origins stay at the world origin."""
    if not objects:
        raise ValueError("join_objects: nothing to join")
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for obj in bpy.data.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    if joined.data is not None:
        joined.data.name = name
    return joined


def add_screws(lid):
    """Four M1.6 CSK fasteners in the lid outer countersinks.

    One mesh named Screws, parented to the lid for stills. The orbit
    exporter reparents it onto the tray: model-viewer drops extra lid
    children and extra scene roots, but it keeps Tray mesh children.
    """
    params = load_params()
    acc_t = params["accessory"]["thickness_mm"]
    face_z = acc_t + SCREW_PROUD_MM
    steel = mat_stainless()
    parts = []
    for i, (x_mm, y_mm) in enumerate(hole_xy_mm(params), 1):
        bpy.ops.mesh.primitive_cone_add(
            vertices=24,
            radius1=mm(CSK_HEAD_D_MM / 2.0),
            radius2=mm(SCREW_SHAFT_D_MM / 2.0),
            depth=mm(CSK_H_MM),
            location=(mm(x_mm), mm(y_mm), mm(face_z - CSK_H_MM / 2.0)),
            rotation=(math.pi, 0.0, 0.0),
        )
        head = bpy.context.active_object
        head.name = f"Screw{i}Head"
        assign(head, steel)
        parts.append(head)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=16,
            radius=mm(SCREW_SHAFT_D_MM / 2.0),
            depth=mm(SCREW_SHAFT_L_MM),
            location=(
                mm(x_mm),
                mm(y_mm),
                mm(face_z - CSK_H_MM - SCREW_SHAFT_L_MM / 2.0),
            ),
        )
        shaft = bpy.context.active_object
        shaft.name = f"Screw{i}Shaft"
        assign(shaft, steel)
        parts.append(shaft)
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(mm(x_mm), mm(y_mm), mm(face_z - 0.04)),
        )
        slot = bpy.context.active_object
        slot.name = f"Screw{i}Slot"
        slot.scale = (mm(1.5), mm(0.22), mm(0.18))
        assign(slot, steel)
        parts.append(slot)
    joined = join_objects("Screws", parts)
    parent_keep(joined, lid)
    print(
        f"  screws: 4x M1.6 CSK at z={face_z:.2f} mm "
        f"(+{SCREW_PROUD_MM:.2f} mm proud)",
        flush=True,
    )
    return joined


def add_pogo_body(root, spec, housing_mat, gold_mat):
    """Stadium housing + four gold faces. Not a cube."""
    length = spec["sx"]
    width = spec["sy"]
    height = spec["sz"]
    body = extrude_loop_mm(
        f"FB_{spec['ref']}",
        pogo_model.stadium_loop_mm(length, width),
        -height / 2.0,
        height / 2.0,
    )
    assign_all(body, housing_mat)
    body.parent = root
    body.location = (
        mm(spec["x"]),
        mm(spec["y"]),
        0.0008 + mm(height / 2.0),
    )
    body.rotation_euler.z = math.radians(spec.get("rot", 0.0))
    contact_r = pogo_model.POGO_CONTACT_D / 2.0
    proud = pogo_model.POGO_CONTACT_PROUD
    for i, px in enumerate(pogo_model.POGO_PINS_X, 1):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=mm(contact_r),
            depth=mm(0.12),
            vertices=24,
        )
        pin = bpy.context.active_object
        pin.name = f"FB_{spec['ref']}_P{i}"
        assign_all(pin, gold_mat)
        pin.parent = body
        pin.location = (mm(px), 0.0, mm(height / 2.0 + proud))
    print(
        f"  fallback {spec['ref']}: {length}x{width}x{height} mm stadium "
        f"at ({spec['x']}, {spec['y']})",
        flush=True,
    )
    return body


def apply_board_materials():
    mats = {
        "mask": mat_soldermask(),
        "fr4": mat_fr4(),
        "enig": mat_enig(),
        "silk": mat_silk(),
        "chip": mat_chip(),
    }
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        name = data_name(obj).lower()
        if "soldermask" in name:
            assign_all(obj, mats["mask"])
        elif name.endswith("_pcb") or "recorder_pcb" in name:
            assign_all(obj, mats["fr4"])
        elif "silkscreen" in name:
            assign_all(obj, mats["silk"])
        elif "pad" in name:
            assign_all(obj, mats["enig"])
        elif "copper" in name or "via" in name:
            assign_all(obj, mats["enig"])
        elif name.startswith("r_") or name.startswith("c_") or name.startswith("fuse") or "sot-23" in name:
            assign_all(obj, mats["chip"])
        elif "sw_spst" in name:
            assign_all(obj, mats["chip"])
    return mats


def pogo_glb_meshes(root):
    return [
        obj
        for obj in walk_meshes(root)
        if "yz103915020t" in data_name(obj).lower()
        or "yz103915020t" in obj.name.lower()
    ]


def mesh_span_mm(objs):
    if not objs:
        return 0.0
    mn, mx = world_bbox(objs)
    return max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z) * 1000.0


def add_board_fallbacks(root, mats):
    """Boxes for footprints KiCad exported without a body.

    Live in the baked board frame (KiCad XY, millimetres already metres).
    Do not parent_keep onto the empty: setting matrix_world there can
    drop a scale and leave a 1 m cube.
    """
    kinds = {
        "module": mat_module(),
        "pogo": mat_pogo(),
        "sd": mats["chip"],
        "mic": mats["chip"],
        "osc": mats["chip"],
        "qfn": mats["chip"],
    }
    pogo_gold = mat_pogo_gold()
    fcu = 0.0008
    for spec in BOARD_FALLBACKS:
        if spec.get("kind") == "pogo":
            found = pogo_glb_meshes(root)
            span = mesh_span_mm(found)
            if found and span >= 15.0:
                print(
                    f"  skip fallback {spec['ref']}: GLB stadium is {span:.1f} mm",
                    flush=True,
                )
                continue
            if found:
                print(
                    f"  drop GLB {spec['ref']}: span {span:.2f} mm, want "
                    f"{spec['sx']:.1f} x {spec['sy']:.1f}",
                    flush=True,
                )
                for obj in found:
                    mesh = obj.data
                    bpy.data.objects.remove(obj, do_unlink=True)
                    if mesh is not None and mesh.users == 0:
                        bpy.data.meshes.remove(mesh)
            add_pogo_body(root, spec, kinds["pogo"], pogo_gold)
            continue
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.active_object
        obj.name = f"FB_{spec['ref']}"
        obj.scale = (mm(spec["sx"]), mm(spec["sy"]), mm(spec["sz"]))
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.parent = root
        obj.location = (
            mm(spec["x"]),
            mm(spec["y"]),
            fcu + mm(spec["sz"] / 2.0),
        )
        obj.rotation_euler.z = math.radians(spec.get("rot", 0.0))
        assign_all(obj, kinds.get(spec["kind"], mats["chip"]))
        print(
            f"  fallback {spec['ref']}: {spec['sx']}x{spec['sy']}x{spec['sz']} mm "
            f"at ({spec['x']}, {spec['y']})",
            flush=True,
        )


def import_board(path):
    """KiCad 10 GLB is metres, Y flipped vs the board file. Seat B.Cu on the rebate."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    new = [obj for obj in bpy.data.objects if obj not in before]
    roots = [obj for obj in new if obj.parent is None]
    if len(roots) == 1:
        root = roots[0]
    else:
        root = bpy.data.objects.new("Board", None)
        bpy.context.scene.collection.objects.link(root)
        for obj in roots:
            parent_keep(obj, root)
    root.name = "Board"
    # KiCad 10 GLB is Y-flipped vs the board file. Bake that back to KiCad
    # XY and make F.Silk face +Z; a live scale.y = -1 shows the back of
    # each glyph (a mirror).
    bake_board_y_flip(root)
    hide_back_silk(root)
    mats = apply_board_materials()
    pcb_z, pcb_t = stack_z()
    pcb_objs = [
        obj
        for obj in walk_meshes(root)
        if data_name(obj).lower().endswith("_pcb")
    ]
    if pcb_objs:
        mn, mx = world_bbox(pcb_objs)
        root.location.z += mm(pcb_z) - mn.z
        bpy.context.view_layer.update()
        mn, mx = world_bbox(pcb_objs)
        print(
            f"  board rebate {mn.z * 1000:.2f}..{mx.z * 1000:.2f} mm "
            f"(want {pcb_z:.2f}..{pcb_z + pcb_t:.2f})",
            flush=True,
        )
    add_board_fallbacks(root, mats)
    return root


def bake_board_y_flip(root):
    """Apply the GLB Y-flip into mesh data so silk is not a live reflection."""
    root.scale.y = -1.0
    bpy.context.view_layer.update()
    meshes = list(walk_meshes(root))
    worlds = [(obj, obj.matrix_world.copy()) for obj in meshes]
    for obj, mw in worlds:
        obj.parent = None
        obj.matrix_world = mw
    root.scale = (1.0, 1.0, 1.0)
    root.location = (0.0, 0.0, 0.0)
    root.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    identity = Matrix.Identity(4)
    for obj, _mw in worlds:
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.transform(obj.matrix_world)
        obj.matrix_world = identity.copy()
        silk = "silkscreen" in data_name(obj).lower()
        if silk:
            face_silk_up(obj.data)
            print(f"  silk baked +Z: {obj.name} / {data_name(obj)}", flush=True)
        else:
            obj.data.flip_normals()
        obj.data.update()
        obj.parent = root
        obj.matrix_parent_inverse = identity.copy()


def face_silk_up(mesh):
    """Every silk face that points at the table gets flipped to +Z."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        if face.normal.z < 0.0:
            face.normal_flip()
    bm.to_mesh(mesh)
    bm.free()


def hide_back_silk(root):
    """B.Silk is authored mirrored. Hide it so only F.Silk reads from above."""
    ranked = []
    for obj in walk_meshes(root):
        if "silkscreen" not in data_name(obj).lower():
            continue
        mn, mx = world_bbox([obj])
        ranked.append((obj, (mn.z + mx.z) / 2.0))
    if len(ranked) < 2:
        return
    ranked.sort(key=lambda item: item[1])
    back, z_mid = ranked[0]
    back.hide_render = True
    back.hide_viewport = True
    print(f"  hide back silk {back.name} z={z_mid * 1000:.2f} mm", flush=True)


def world_bbox(objects):
    pts = []
    for obj in objects:
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def add_stage():
    bpy.ops.mesh.primitive_plane_add(size=0.55)
    plane = bpy.context.active_object
    plane.name = "Stage"
    assign(plane, mat_stage())
    return plane


def place_stage(stage, center, z_bottom):
    stage.location = (center.x, center.y, z_bottom - mm(0.3))
    stage.hide_render = False


def clear_lights():
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)
    for light in list(bpy.data.lights):
        bpy.data.lights.remove(light)


def add_area(name, energy, size, loc, target, color=(1.0, 1.0, 1.0)):
    light = bpy.data.lights.new(name, "AREA")
    light.energy = energy
    light.size = size
    light.color = color
    obj = bpy.data.objects.new(name, light)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, target)
    return obj


def add_lights_studio(center):
    """Hero / button: key-fill-rim, no under-light (the case sits on the stage)."""

    def area(name, energy, size, loc, rot, color=(1.0, 1.0, 1.0)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = energy
        light.size = size
        light.color = color
        obj = bpy.data.objects.new(name, light)
        obj.location = loc
        obj.rotation_euler = rot
        bpy.context.scene.collection.objects.link(obj)

    area(
        "Key",
        8.0,
        0.18,
        center + Vector((0.07, -0.10, 0.12)),
        (math.radians(50), 0.0, math.radians(32)),
        (1.0, 0.98, 0.95),
    )
    area(
        "Fill",
        2.2,
        0.24,
        center + Vector((-0.11, 0.04, 0.09)),
        (math.radians(60), 0.0, math.radians(-38)),
        (0.82, 0.88, 1.0),
    )
    area(
        "Rim",
        4.0,
        0.10,
        center + Vector((0.02, 0.13, 0.05)),
        (math.radians(75), 0.0, math.radians(180)),
        (1.0, 0.97, 0.92),
    )


def add_lights_pocket(center, top):
    """Side rake into the tray wells so the floor, posts, and magnet bore read."""
    add_area(
        "Key",
        16.0,
        0.08,
        top + Vector((0.12, -0.09, 0.015)),
        center,
        (1.0, 0.98, 0.94),
    )
    add_area(
        "Fill",
        1.5,
        0.22,
        top + Vector((-0.13, 0.05, 0.07)),
        top,
        (0.84, 0.90, 1.0),
    )
    add_area(
        "Well",
        6.0,
        0.06,
        center + Vector((-0.02, -0.04, 0.04)),
        center + Vector((0.0, 0.01, -0.01)),
        (1.0, 0.97, 0.92),
    )


def add_lights_raking(top):
    """Low side key so 0.35 mm lid grooves and tray pockets read as shadows."""
    add_area(
        "Key",
        22.0,
        0.07,
        top + Vector((0.13, -0.03, 0.028)),
        top,
        (1.0, 0.98, 0.94),
    )
    add_area(
        "Fill",
        2.8,
        0.20,
        top + Vector((-0.15, 0.04, 0.07)),
        top,
        (0.84, 0.90, 1.0),
    )
    add_area(
        "Bounce",
        1.4,
        0.16,
        top + Vector((0.01, 0.11, 0.045)),
        top,
        (1.0, 0.99, 0.97),
    )


def look_at(camera, target):
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def bbox_corners(mn, mx):
    return [
        Vector((x, y, z))
        for x in (mn.x, mx.x)
        for y in (mn.y, mx.y)
        for z in (mn.z, mx.z)
    ]


def mesh_world_corners(objects):
    """Every mesh AABB corner, not the union box.

    The exploded stack is tall. Fitting only the eight corners of the
    combined box leaves the near tray rim and the ring outside the
    picture, because those sit on a face of the box, not a corner.
    """
    pts = []
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    return pts


def frame_extent(camera, points):
    """Largest |NDC| of the points (1.0 = touching the frame edge)."""
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    extent = 0.0
    behind = False
    for point in points:
        co = world_to_camera_view(scene, camera, point)
        if co.z <= 0.0:
            behind = True
        extent = max(extent, abs(co.x - 0.5) * 2.0, abs(co.y - 0.5) * 2.0)
    return extent, behind


def fit_in_frame(camera, target, points, margin=1.15):
    """Push the camera back along its view axis until every point sits in frame.

    `margin` 1.15 means the case uses the inner ~87% of the image, so nothing
    kisses the edge.
    """
    offset = camera.location - target
    if offset.length < 1e-9:
        return
    direction = offset.normalized()
    dist = offset.length
    for _ in range(12):
        camera.location = target + direction * dist
        look_at(camera, target)
        extent, behind = frame_extent(camera, points)
        if not behind and extent * margin <= 1.0:
            break
        scale = 1.25 if behind else max(1.04, extent * margin)
        dist *= scale
    print(f"  {camera.name}: dist {dist * 1000.0:.0f} mm, extent {extent:.2f}", flush=True)


def make_camera(name, loc, target, lens=50.0):
    if name in bpy.data.objects:
        obj = bpy.data.objects[name]
        obj.location = loc
        look_at(obj, target)
        return obj
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.clip_start = 0.001
    data.clip_end = 5.0
    obj = bpy.data.objects.new(name, data)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, target)
    return obj


def clear_parent_keep(obj):
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world


def reset_pose(tray, lid):
    for obj in (tray, lid):
        if obj is None:
            continue
        if obj.parent is not None:
            clear_parent_keep(obj)
        obj.location = Vector((0.0, 0.0, 0.0))
        obj.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def restore_board(board):
    if board is None:
        return
    if "seat_z" not in board:
        board["seat_z"] = board.location.z
    board.location.z = board["seat_z"]


def sit_on_z(objects, z_plane):
    bpy.context.view_layer.update()
    mn, _mx = world_bbox(objects)
    lift = z_plane - mn.z
    for obj in objects:
        obj.location.z += lift
    bpy.context.view_layer.update()


def pose_closed(tray, lid):
    reset_pose(tray, lid)
    objs = [tray] if lid is None else [tray, lid]
    sit_on_z(objs, 0.0)


def pose_phone_up(tray, lid):
    """Phone face up, lid skin on the table. Same tabletop as the lid shot."""
    reset_pose(tray, lid)
    tray.rotation_euler.x = math.pi
    lid.rotation_euler.x = math.pi
    sit_on_z([tray, lid], 0.0)


def set_tree_visible(obj, visible):
    obj.hide_render = not visible
    obj.hide_viewport = not visible
    for child in obj.children:
        set_tree_visible(child, visible)


def place_side_by_side(left, right, gap_mm=14.0):
    bpy.context.view_layer.update()
    left_mn, left_mx = world_bbox([left])
    right_mn, right_mx = world_bbox([right])
    gap = mm(gap_mm)
    left_cx = (left_mn.x + left_mx.x) / 2.0
    right_cx = (right_mn.x + right_mx.x) / 2.0
    left_cy = (left_mn.y + left_mx.y) / 2.0
    right_cy = (right_mn.y + right_mx.y) / 2.0
    left_w = left_mx.x - left_mn.x
    right_w = right_mx.x - right_mn.x
    left_x = -(gap / 2.0 + left_w / 2.0)
    right_x = gap / 2.0 + right_w / 2.0
    left.location.x += left_x - left_cx
    right.location.x += right_x - right_cx
    left.location.y += -left_cy
    right.location.y += -right_cy
    sit_on_z([left, right], 0.0)


def pose_open_interiors(tray, lid):
    """Both halves cavity-up, flat on the table, side by side.

    Worn tray already has the phone face down. Worn lid has the outer skin
    up, so it flips. Tray sits left, lid right, about 14 mm between them.
    """
    reset_pose(tray, lid)
    lid.rotation_euler.x = math.pi
    place_side_by_side(tray, lid)


def pose_open_exteriors(tray, lid):
    """Lid outer-skin up on the left, tray phone-face up on the right."""
    reset_pose(tray, lid)
    tray.rotation_euler.x = math.pi
    place_side_by_side(lid, tray)


def pose_exploded(scene, gap_mm=EXPLODE_GAP_MM):
    """XY-aligned Z explode: lid, board, pouch, magnets, tray."""
    pose_closed(scene.tray, scene.lid)
    restore_board(scene.board)
    if scene.board is not None:
        clear_parent_keep(scene.board)
    if scene.pouch is not None:
        clear_parent_keep(scene.pouch)
    if scene.magnets is not None:
        clear_parent_keep(scene.magnets)
    gap = mm(gap_mm)
    if scene.magnets is not None:
        scene.magnets.location.z += gap
    if scene.pouch is not None:
        scene.pouch.location.z += 2.0 * gap
    if scene.board is not None:
        scene.board.location.z += 3.0 * gap
    if scene.lid is not None:
        scene.lid.location.z += 4.0 * gap
    bpy.context.view_layer.update()
    print(f"  exploded gap {gap_mm:.0f} mm", flush=True)


def overhead_camera(name, center, mx, parts, y_pull=-0.045):
    top = Vector((center.x, center.y, mx.z))
    cam = make_camera(name, top + Vector((0.02, y_pull, 0.19)), top, 50.0)
    fit_in_frame(cam, top, bbox_corners(*world_bbox(parts)), margin=1.16)
    return cam


def down_camera(name, center, mx, parts, height=0.28, margin=1.12):
    top = Vector((center.x, center.y, mx.z))
    cam = make_camera(name, top + Vector((0.0, 0.0, height)), top, 50.0)
    fit_in_frame(cam, top, bbox_corners(*world_bbox(parts)), margin=margin)
    return cam


def camera_button(mn, mx):
    """Locked side camera on the TPU pill (phone-left wall)."""
    mid_z = mn.z + (mx.z - mn.z) * 0.48
    btn_t = Vector((mn.x, mm(12.0), mid_z))
    cam = make_camera("button", btn_t + Vector((-0.095, 0.006, 0.008)), btn_t, 80.0)
    print(
        f"  button: locked side cam at x={cam.location.x * 1000:.0f} mm",
        flush=True,
    )
    return cam


def camera_grille(mn, mx):
    """Locked side camera on the three mic holes (phone-right wall)."""
    mid_z = mn.z + (mx.z - mn.z) * 0.48
    mic_t = Vector((mx.x, mm(16.32), mid_z))
    cam = make_camera("grille", mic_t + Vector((0.052, -0.010, 0.007)), mic_t, 80.0)
    add_area(
        "Graze",
        6.0,
        0.04,
        mic_t + Vector((0.025, -0.035, 0.018)),
        mic_t,
        (1.0, 0.98, 0.94),
    )
    print(
        f"  grille: locked side cam at x={cam.location.x * 1000:.0f} mm",
        flush=True,
    )
    return cam


def camera_exploded(parts, elev_deg=42.0, az_deg=322.0, dist=0.32):
    """3/4 from phone-left / phone-bottom so the tray and ring are in
    the foreground and J2 sits at the top of the frame.

    322° (−38°) stands on (−X, −Y). The older 218° seat was on the pad
    corner, which put the tray at the far edge and cropped the base.
    """
    mn, mx = world_bbox(parts)
    center = (mn + mx) / 2.0
    # Look below the stack midpoint so the lid does not own the frame.
    target = Vector((center.x, center.y, mn.z + (mx.z - mn.z) * 0.36))
    elev = math.radians(elev_deg)
    az = math.radians(az_deg)
    loc = target + Vector(
        (
            dist * math.cos(elev) * math.sin(az),
            -dist * math.cos(elev) * math.cos(az),
            dist * math.sin(elev),
        )
    )
    cam = make_camera("exploded", loc, target, 35.0)
    fit_in_frame(cam, target, mesh_world_corners(parts), margin=1.38)
    print(
        f"  exploded: az={az_deg:.0f} deg, "
        f"cam xy=({cam.location.x * 1000:.0f}, {cam.location.y * 1000:.0f}) mm",
        flush=True,
    )
    return cam


def flip_png_vertical(path):
    """KiCad's 3D top view has +Y at the bottom. Flip the still to match."""
    img = bpy.data.images.load(str(path))
    width, height = img.size
    pixels = list(img.pixels)
    row = width * 4
    flipped = []
    for y in range(height - 1, -1, -1):
        flipped.extend(pixels[y * row : (y + 1) * row])
    img.pixels = flipped
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    print(f"  flipped {path.name} so J2 sits at the bottom", flush=True)


def resolve_board_glb():
    if BOARD_GLB.is_file():
        return BOARD_GLB
    alt = REPO / "build" / "product-renders" / "recorder.glb"
    if alt.is_file():
        return alt
    raise SystemExit(
        f"missing board GLB: {BOARD_GLB} "
        "(run hardware/kicad/recorder/product_renders/export_board_3d.py)"
    )


def require_shell_stls(*, need_lid=True, need_pill=True):
    missing = []
    if not TRAY.is_file():
        missing.append(TRAY)
    if need_lid and not LID.is_file():
        missing.append(LID)
    if need_pill and not PILL.is_file():
        missing.append(PILL)
    if missing:
        raise SystemExit("missing STLs: " + " ".join(str(path) for path in missing))


def build_scene(
    *,
    need_lid=True,
    need_pill=True,
    need_board=False,
    need_magnets=False,
    need_pouch=False,
    need_screws=False,
    seat_magnets=True,
):
    if need_pouch and not need_board:
        raise ValueError("need_pouch requires need_board")
    if need_screws and not need_lid:
        raise ValueError("need_screws requires need_lid")
    if need_pill and not need_lid:
        raise ValueError("need_pill requires need_lid")
    require_shell_stls(need_lid=need_lid, need_pill=need_pill)
    reset_scene()
    tray = import_stl(TRAY, "Tray")
    assign(tray, mat_6061("Al6061_tray", 0.52, 0.22))
    lid = None
    pill = None
    if need_lid:
        lid = import_stl(LID, "Lid")
        assign(lid, mat_petg_natural())
        if need_pill:
            pill = import_stl(PILL, "Pill")
            assign(pill, mat_tpu())
            parent_keep(pill, lid)
    board = None
    if need_board:
        board = import_board(resolve_board_glb())
        parent_keep(board, tray)
    magnets = None
    if need_magnets:
        magnets = add_magnets()
        if seat_magnets:
            parent_keep(magnets, tray)
    pouch = None
    if need_pouch:
        pouch = add_pouch(board)
    screws = None
    if need_screws:
        screws = add_screws(lid)
    return BuiltScene(
        tray=tray,
        lid=lid,
        pill=pill,
        board=board,
        magnets=magnets,
        pouch=pouch,
        screws=screws,
        stage=add_stage(),
    )


def visible_parts(scene):
    found = []
    for root in (
        scene.tray,
        scene.lid,
        scene.pill,
        scene.board,
        scene.magnets,
        scene.pouch,
        scene.screws,
    ):
        if root is None:
            continue
        found.extend(walk_meshes(root))
    return found


def frame_scene(scene):
    parts = visible_parts(scene)
    mn, mx = world_bbox(parts)
    center = (mn + mx) / 2.0
    place_stage(scene.stage, center, mn.z)
    return parts, mn, mx, center


def render_still(name, camera, save_blend=True, flip=False):
    scene = bpy.context.scene
    scene.camera = camera
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"case-6061-{name}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if flip:
        flip_png_vertical(path)
    print(f"wrote {path}", flush=True)
    if save_blend:
        blend = OUT / f"case-6061-{name}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        print(f"wrote {blend}", flush=True)
    return path


def main():
    raise SystemExit(
        "render_metal.py is the scene library. Run one still:\n"
        "  blender --background --python hardware/cad/renders/shells_inside.py\n"
        "  blender --background --python hardware/cad/renders/shells_outside.py\n"
        "  blender --background --python hardware/cad/renders/exploded.py\n"
        "  blender --background --python hardware/cad/renders/top.py\n"
        "  blender --background --python hardware/cad/renders/button.py\n"
        "  blender --background --python hardware/cad/renders/grille.py\n"
        "  blender --background --python hardware/cad/renders/tray_magnets.py"
    )


if __name__ == "__main__":
    main()
