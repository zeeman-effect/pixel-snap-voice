#!/usr/bin/env python
"""Dump GLB object names and world bounds. Run under Blender."""

from __future__ import annotations

import json
import os
from pathlib import Path

import bpy
from mathutils import Vector

REPO = Path(os.environ.get("PSV_REPO", Path(__file__).resolve().parents[3]))
OUT = REPO / "build" / "product-renders"
GLB = OUT / "recorder.glb"


def bbox(objects):
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, world.x)
            mins.y = min(mins.y, world.y)
            mins.z = min(mins.z, world.z)
            maxs.x = max(maxs.x, world.x)
            maxs.y = max(maxs.y, world.y)
            maxs.z = max(maxs.z, world.z)
    return mins, maxs


bpy.ops.wm.read_factory_settings(use_empty=True)
print("import_scene ops", dir(bpy.ops.import_scene))
print("wm ops with gltf", [n for n in dir(bpy.ops.wm) if "gltf" in n.lower() or "import" in n.lower()])
bpy.ops.import_scene.gltf(filepath=str(GLB))

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
mins, maxs = bbox(meshes)
size = maxs - mins
rows = []
for obj in meshes:
    mn, mx = bbox([obj])
    rows.append(
        {
            "name": obj.name,
            "data": obj.data.name if obj.data else None,
            "dims": [round(obj.dimensions.x, 4), round(obj.dimensions.y, 4), round(obj.dimensions.z, 4)],
            "bbox": [[round(mn.x, 5), round(mn.y, 5), round(mn.z, 5)], [round(mx.x, 5), round(mx.y, 5), round(mx.z, 5)]],
            "mats": [s.material.name if s.material else None for s in obj.material_slots],
            "verts": len(obj.data.vertices),
        }
    )
payload = {
    "count": len(rows),
    "bbox": {
        "min": [mins.x, mins.y, mins.z],
        "max": [maxs.x, maxs.y, maxs.z],
        "size": [size.x, size.y, size.z],
    },
    "objects": rows,
}
path = OUT / "glb-inspect.json"
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print("wrote", path)
print("count", len(rows), "size", [round(size.x, 5), round(size.y, 5), round(size.z, 5)])
for row in rows[:40]:
    print(row["name"], row["dims"], row["mats"])
