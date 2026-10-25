"""Tray cavity-up with the N52 ring and clocking magnet seated."""

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
        need_lid=False,
        need_pill=False,
        need_board=False,
        need_magnets=True,
        need_pouch=False,
        need_screws=False,
        seat_magnets=True,
    )
    rm.pose_closed(scene.tray, None)
    parts, mn, mx, center = rm.frame_scene(scene)
    rm.clear_lights()
    top = Vector((center.x, center.y, mx.z))
    rm.add_lights_pocket(center, top)
    # Magnet backs sit flush with the 2.35 mm floor. Default pocket fill
    # clips that floor to a white disc, so the ring reads as a decal.
    # Keep the side rake, drop the on-axis fill, leave a little well
    # energy so nickel has shape, and pull exposure off Filmic's shoulder.
    bpy.data.lights["Key"].energy = 10.0
    bpy.data.lights["Fill"].energy = 0.5
    bpy.data.lights["Well"].energy = 1.8
    bpy.context.scene.view_settings.exposure = -1.35
    cam = rm.overhead_camera("tray-magnets", center, mx, parts, y_pull=-0.07)
    rm.render_still("tray-magnets", cam)


if __name__ == "__main__":
    main()
