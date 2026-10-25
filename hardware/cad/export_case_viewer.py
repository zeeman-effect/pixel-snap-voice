#!/usr/bin/env python
"""Orbitable GLB of the closed case, same materials as the stills.

    blender --background --python hardware/cad/export_case_viewer.py

Writes build/case-renders/case-6061.glb and copies case-viewer.html beside
it. Open the HTML through a local server (a file:// page cannot load the
model). The wave engraving and grip ridges are mesh, not a picture.

Does not render the PNGs and does not touch hardware/cad/export/.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import bpy

CAD = Path(__file__).resolve().parent
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))

import render_metal as rm


def viewer_metal(mat):
    """Soft web lighting, so the same 6061 reads closer to the studio stills."""
    principled = mat.node_tree.nodes["Principled BSDF"]
    principled.inputs["Base Color"].default_value = (0.70, 0.72, 0.74, 1.0)
    rm.set_input(principled, "Roughness", 0.36)
    rm.set_input(principled, "Metallic", 1.0)


def viewer_petg(mat):
    """Same natural PETG, with a wall thickness the web viewer can shade."""
    principled = mat.node_tree.nodes["Principled BSDF"]
    rm.set_input(principled, "Thin Wall", False)
    rm.set_input(principled, "Thickness", 0.0012)
    mat.use_backface_culling = False


def select_tree(roots):
    for obj in bpy.data.objects:
        obj.select_set(False)
    chosen = []
    for root in roots:
        root.select_set(True)
        chosen.append(root)
        for child in root.children_recursive:
            child.select_set(True)
            chosen.append(child)
    meshes = [obj for obj in chosen if obj.type == "MESH"]
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    return meshes


def main():
    if not rm.TRAY.is_file() or not rm.LID.is_file() or not rm.PILL.is_file():
        raise SystemExit(f"missing STLs: {rm.TRAY} {rm.LID} {rm.PILL}")
    board_path = rm.BOARD_GLB
    if not board_path.is_file():
        board_path = rm.REPO / "build" / "product-renders" / "recorder.glb"
    if not board_path.is_file():
        raise SystemExit(f"missing board GLB: {rm.BOARD_GLB}")

    rm.reset_scene()
    tray = rm.import_stl(rm.TRAY, "Tray")
    lid = rm.import_stl(rm.LID, "Lid")
    metal = rm.mat_6061("Al6061_tray", 0.52, 0.22)
    viewer_metal(metal)
    rm.assign(tray, metal)
    petg = rm.mat_petg_purple()
    viewer_petg(petg)
    rm.assign(lid, petg)
    pill = rm.import_stl(rm.PILL, "Pill")
    rm.assign(pill, rm.mat_tpu())
    rm.parent_keep(pill, lid)
    board = rm.import_board(board_path)
    rm.parent_keep(board, tray)
    magnets, pouch = rm.add_pack(tray, board)
    screws = rm.add_screws(lid)
    rm.pose_closed(tray, lid)
    # model-viewer keeps Lid, Tray, and one mesh child of the clear lid
    # (the TPU pill). A third scene root, or extra lid children, never
    # reach Three.js. MagnetRing survives as a Tray child; hang the
    # fasteners there too.
    rm.parent_keep(screws, tray)

    meshes = select_tree([tray, lid, board, pill, magnets, pouch, screws])
    tris = sum(len(obj.data.polygons) for obj in meshes)
    print(f"export meshes {len(meshes)} tris {tris}", flush=True)

    rm.OUT.mkdir(parents=True, exist_ok=True)
    glb = rm.OUT / "case-6061.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
    )
    html_src = CAD / "case-viewer.html"
    html_dst = rm.OUT / "case-6061.html"
    shutil.copyfile(html_src, html_dst)
    print(f"wrote {glb} ({glb.stat().st_size} bytes)", flush=True)
    print(f"wrote {html_dst}", flush=True)


if __name__ == "__main__":
    main()
