"""C6276862 / YZ103915020T-04025-02 body for Blender and the KiCad WRL.

Vendor drawing and LCSC photo: 22.30 x 7.70 x 2.00 mm black PA46 stadium,
full-radius ends, four gold contact faces on a 2.54 mm pitch. Magnets sit
inside the plastic; they are not on the mating face.
"""

from __future__ import annotations

import math
from pathlib import Path

# Millimetres. Twin of params.json connectors.pogo_body_* and the land.
POGO_LENGTH = 22.30
POGO_WIDTH = 7.70
POGO_HEIGHT = 2.00
POGO_PINS_X = (-3.81, -1.27, 1.27, 3.81)
# Visible gold face. Land is 2.30 mm; the tube on the drawing is ~1.5–1.6.
POGO_CONTACT_D = 1.60
POGO_CONTACT_PROUD = 0.05
POGO_SEGS = 20


def stadium_loop_mm(length: float = POGO_LENGTH, width: float = POGO_WIDTH, segs: int = POGO_SEGS):
    """Closed XY outline, millimetres, CCW, origin at the part centre."""
    radius = width / 2.0
    cx = (length - width) / 2.0
    pts = []
    for i in range(segs + 1):
        ang = -math.pi / 2 + math.pi * i / segs
        pts.append((cx + radius * math.cos(ang), radius * math.sin(ang)))
    for i in range(segs + 1):
        ang = math.pi / 2 + math.pi * i / segs
        pts.append((-cx + radius * math.cos(ang), radius * math.sin(ang)))
    return pts


def _circle_loop_mm(diameter: float, segs: int = 20):
    r = diameter / 2.0
    return [
        (r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs))
        for i in range(segs)
    ]


def _extrude(loop, z0: float, z1: float):
    n = len(loop)
    verts = [(x, y, z0) for x, y in loop] + [(x, y, z1) for x, y in loop]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    return verts, faces


def _wrl_color(r: float, g: float, b: float, shininess: float) -> str:
    return (
        "appearance Appearance {\n"
        "  material Material {\n"
        f"    diffuseColor {r:.3f} {g:.3f} {b:.3f}\n"
        f"    specularColor {r:.3f} {g:.3f} {b:.3f}\n"
        f"    shininess {shininess:.2f}\n"
        "  }\n"
        "}\n"
    )


def _wrl_shape(verts, faces, color, shininess, scale=1 / 2.54) -> str:
    # KiCad reads VRML as 0.1 inch per unit (2.54 mm), not full inches.
    coord = ",\n          ".join(
        f"{x * scale:.6f} {y * scale:.6f} {z * scale:.6f}" for x, y, z in verts
    )
    idx = ",\n          ".join(
        " ".join(str(i) for i in face) + " -1" for face in faces
    )
    return (
        "    Shape {\n"
        f"{_wrl_color(*color, shininess)}"
        "      geometry IndexedFaceSet {\n"
        "        solid TRUE\n"
        "        coord Coordinate {\n"
        f"          point [ {coord} ]\n"
        "        }\n"
        f"        coordIndex [ {idx} ]\n"
        "      }\n"
        "    }\n"
    )


def write_wrl(path: Path) -> None:
    """Write a KiCad-usable VRML of the housing plus four gold faces."""
    body_v, body_f = _extrude(stadium_loop_mm(), 0.0, POGO_HEIGHT)
    parts = [_wrl_shape(body_v, body_f, (0.04, 0.04, 0.045), 0.25)]
    z0 = POGO_HEIGHT - 0.02
    z1 = POGO_HEIGHT + POGO_CONTACT_PROUD
    for px in POGO_PINS_X:
        loop = [(x + px, y) for x, y in _circle_loop_mm(POGO_CONTACT_D)]
        verts, faces = _extrude(loop, z0, z1)
        parts.append(_wrl_shape(verts, faces, (0.85, 0.70, 0.28), 0.55))
    text = (
        "#VRML V2.0 utf8\n"
        "# Xinyangze YZ103915020T-04025-02 / LCSC C6276862\n"
        "# 22.30 x 7.70 x 2.00 mm stadium, four gold contacts. Units: 0.1 inch.\n"
        "Group {\n"
        "  children [\n"
        + "".join(parts)
        + "  ]\n"
        "}\n"
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    here = Path(__file__).resolve().parent
    out = here.parent / "kicad" / "recorder" / "PSV.pretty" / "YZ103915020T_4P.wrl"
    write_wrl(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
