"""Empty exteriors, side by side, no internals."""

from pathlib import Path
import sys

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))
import render_metal as rm
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
    rm.pose_open_exteriors(scene.tray, scene.lid)
    parts, mn, mx, center = rm.frame_scene(scene)
    rm.clear_lights()
    top = Vector((center.x, center.y, mx.z))
    rm.add_lights_raking(top)
    cam = rm.overhead_camera("shells-outside", center, mx, parts)
    rm.render_still("shells-outside", cam)


if __name__ == "__main__":
    main()
