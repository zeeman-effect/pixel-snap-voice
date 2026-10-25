"""Microphone grille, full closed stack."""

from pathlib import Path
import sys

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))
import render_metal as rm


def main():
    scene = rm.build_scene(
        need_lid=True, need_pill=True,
        need_board=True, need_magnets=True, need_pouch=True, need_screws=True,
        seat_magnets=True,
    )
    rm.pose_closed(scene.tray, scene.lid)
    rm.restore_board(scene.board)
    parts, mn, mx, center = rm.frame_scene(scene)
    rm.clear_lights()
    rm.add_lights_studio(center)
    cam = rm.camera_grille(mn, mx)
    rm.render_still("grille", cam)


if __name__ == "__main__":
    main()
