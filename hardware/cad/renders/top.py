"""Closed full stack from above, with screws."""

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
        need_board=True,
        need_magnets=True,
        need_pouch=True,
        need_screws=True,
        seat_magnets=True,
    )
    rm.pose_closed(scene.tray, scene.lid)
    rm.restore_board(scene.board)
    parts, mn, mx, center = rm.frame_scene(scene)
    rm.clear_lights()
    top = Vector((center.x, center.y, mx.z))
    rm.add_lights_raking(top)
    cam = rm.overhead_camera("top", center, mx, parts)
    rm.render_still("top", cam)


if __name__ == "__main__":
    main()
