"""Empty interiors, side by side, no internals."""

from pathlib import Path
import sys

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))
import render_metal as rm
import bpy
from mathutils import Vector


def main():
    scene = rm.build_scene(
        need_lid=True,
        need_pill=True,
        need_board=False,
        need_magnets=False,
        need_pouch=False,
        need_screws=False,
    )
    rm.pose_open_interiors(scene.tray, scene.lid)
    parts, mn, mx, center = rm.frame_scene(scene)
    rm.clear_lights()
    top = Vector((center.x, center.y, mx.z))
    rm.add_lights_pocket(center, top)
    # Default pocket fill clips empty 6061 floors into a white disc. Keep the
    # rake, drop the on-axis fill, and pull exposure off Filmic's shoulder.
    bpy.data.lights["Key"].energy = 10.0
    bpy.data.lights["Fill"].energy = 0.6
    bpy.data.lights["Well"].energy = 0.6
    bpy.context.scene.view_settings.exposure = -1.3
    cam = rm.down_camera(
        "shells-inside", center, mx, parts, height=0.21, margin=1.14
    )
    rm.render_still("shells-inside", cam)


if __name__ == "__main__":
    main()
