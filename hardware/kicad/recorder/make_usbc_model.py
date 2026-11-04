#!/usr/bin/env python
"""Build a STEP model of the HRO TYPE-C-31-M-13C mid-mount USB-C (LCSC C2848620).

Neither LCSC nor Octopart publishes a STEP for this part, and KiCad 10 ships
none, so this draws one from the HRO datasheet (drawing TYPE-C-31-M-13C,
2021-03-06):

- shell 8.94 wide x 3.16 tall x 6.50 deep, 0.30 mm stainless, stadium ends
- mouth 8.34 x 2.56, centred 1.60 - 3.16/2 = 0.02 mm above the board top
- tongue 0.70 thick carrying 12 gold contacts a side at 0.50 mm pitch
- four shell legs on the 11.24 mm line, 1.20 (front) and 0.80 (rear) long,
  through the slotted holes; 16 SMD tails behind the body

Coordinates are KiCad 3D: origin is the footprint origin, +Y is footprint
-Y, Z = 0 is the board top. The front face sits at footprint y = +4.70 (the
board edge), the body rear at y = -1.80, both from USB_C_Receptacle_HRO_
TYPE-C-31-M-13C.kicad_mod.

Run with any Python that has cadquery (the repo .venv):

    .venv/bin/python hardware/kicad/recorder/make_usbc_model.py
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent / "PSV.pretty" / "USB_C_Receptacle_HRO_TYPE-C-31-M-13C.step"

# Footprint frame (KiCad y down). Converted to model Y with y_m = -y_fp.
FRONT_FP = 4.70
REAR_FP = -1.80
DEPTH = FRONT_FP - REAR_FP  # 6.50, datasheet top view

SHELL_W, SHELL_H, SHELL_T = 8.94, 3.16, 0.30
Z_TOP = 1.60  # shell top above the board top (side view)
Z_MID = Z_TOP - SHELL_H / 2.0  # 0.02, mouth centre
TONGUE_W, TONGUE_T = 5.60, 0.70
TONGUE_FRONT_FP = FRONT_FP - 0.70  # tongue tip sits back from the face
REAR_PLUG = 1.40  # plastic fill at the back of the shell
LEG_X = 5.62
LEG_T = 0.40
LEG_BOTTOM = -1.45  # through 0.8 mm board, short tail below
LEGS = ((2.60, 1.20), (-1.40, 0.80))  # (fp y centre, length) front and rear
TAIL_X = (-3.2, -2.4, -1.75, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 1.75, 2.4, 3.2)
TAIL_END_FP = -3.05
TAIL_T = 0.12


def ym(y_fp: float) -> float:
    return -y_fp


def stadium(w: float, h: float, length: float, y0_fp: float) -> cq.Workplane:
    """Stadium prism with its front at footprint y0_fp, running back `length`."""
    prof = cq.Workplane("XZ").slot2D(w, h).extrude(length)  # XZ extrudes toward -Y
    # XZ normal is -Y in CadQuery, so the solid spans y in [-length, 0].
    return prof.translate((0, ym(y0_fp) + length, Z_MID))


def box(x0, x1, y0_fp, y1_fp, z0, z1) -> cq.Workplane:
    ya, yb = sorted((ym(y0_fp), ym(y1_fp)))
    return cq.Workplane("XY").box(x1 - x0, yb - ya, z1 - z0, centered=False).translate((x0, ya, z0))


def build() -> cq.Assembly:
    outer = stadium(SHELL_W, SHELL_H, DEPTH, FRONT_FP)
    inner = stadium(SHELL_W - 2 * SHELL_T, SHELL_H - 2 * SHELL_T, DEPTH - SHELL_T, FRONT_FP + 0.01)
    shell = outer.cut(inner)
    for (yc, ln) in LEGS:
        for s in (-1, 1):
            # Ear from the shell side out to the leg, at the board top, then the leg.
            x_in, x_out = SHELL_W / 2.0 - 0.1, LEG_X + LEG_T / 2.0
            ear = box(min(s * x_in, s * x_out), max(s * x_in, s * x_out), yc - ln / 2, yc + ln / 2, 0.0, 0.30)
            leg = box(s * LEG_X - LEG_T / 2, s * LEG_X + LEG_T / 2, yc - ln / 2, yc + ln / 2, LEG_BOTTOM, 0.30)
            shell = shell.union(ear).union(leg)

    plastic = stadium(SHELL_W - 2 * SHELL_T - 0.02, SHELL_H - 2 * SHELL_T - 0.02, REAR_PLUG, REAR_FP + SHELL_T + REAR_PLUG)
    tongue_len = TONGUE_FRONT_FP - (REAR_FP + SHELL_T + REAR_PLUG) + 0.05
    tongue = box(-TONGUE_W / 2, TONGUE_W / 2, TONGUE_FRONT_FP - tongue_len, TONGUE_FRONT_FP,
                 Z_MID - TONGUE_T / 2, Z_MID + TONGUE_T / 2).edges("|Z").fillet(0.15)
    plastic = plastic.union(tongue)

    gold = None
    pad_len = 3.2
    for i in range(12):
        x = -2.75 + 0.5 * i
        for z0 in (Z_MID + TONGUE_T / 2, Z_MID - TONGUE_T / 2 - 0.02):
            c = box(x - 0.125, x + 0.125, TONGUE_FRONT_FP - 0.25 - pad_len, TONGUE_FRONT_FP - 0.25, z0, z0 + 0.02)
            gold = c if gold is None else gold.union(c)
    for x in TAIL_X:
        w = 0.30 if abs(x) > 2.0 else 0.20
        t = box(x - w / 2, x + w / 2, TAIL_END_FP, REAR_FP + 0.3, 0.0, TAIL_T)
        gold = gold.union(t)

    asm = cq.Assembly(name="HRO_TYPE-C-31-M-13C")
    asm.add(shell, name="shell", color=cq.Color(0.78, 0.79, 0.80))
    asm.add(plastic, name="housing", color=cq.Color(0.08, 0.08, 0.08))
    asm.add(gold, name="contacts", color=cq.Color(0.86, 0.68, 0.25))
    return asm


def main() -> None:
    asm = build()
    asm.export(str(OUT))
    bb = asm.toCompound().BoundingBox()
    print(f"wrote {OUT}")
    print(f"bbox x {bb.xmin:.2f}..{bb.xmax:.2f}  y {bb.ymin:.2f}..{bb.ymax:.2f}  z {bb.zmin:.2f}..{bb.zmax:.2f}")


if __name__ == "__main__":
    main()
