#!/usr/bin/env python3
"""Write hardware/kicad/jlcpcb_bom.csv, jlcpcb_cpl.csv, and jlcpcb_extra.csv from the board.

Both files used to be typed by hand. `docs/manufacturing.md` step 5 tells you
to upload them beside the Gerbers, so a stale row is not documentation drift,
it is a misassembled board. They had drifted: C11, C12, C17 and C18 still
carried their pre-route coordinates with no rotation, BT1's land had been
renamed under the BOM, and SW1 named a footprint the board has not used since
the switch became side-actuated. Nothing caught any of it, because nothing
compared the CSVs to `recorder.kicad_pcb`.

So they are generated now, in the same pass that plots the Gerbers.

Who owns which number:
  * Coordinates, rotation and side come from `hardware/kicad/fab/
    recorder-pos.csv`, which `kicad-cli pcb export pos` writes. Rotation and
    the Y sign flip are easy to get subtly wrong by hand, so they stay with
    the tool that already knows the convention. The one exception is
    JLC_ROTATION_OFFSET below: per-part turns for JLC's own footprints.
  * Which parts appear at all comes from the board's own KiCad attributes.
    A part is in the pick-and-place file unless it is flagged
    `exclude_from_pos_files`, and on the assembly BOM unless it is flagged
    `exclude_from_bom`. That is a board edit and shows up in a diff, instead
    of a list of references hidden in a script.
  * A part can still have an LCSC number in `docs/bom.md` after it is
    flagged `exclude_from_bom`. Those rows go to `jlcpcb_extra.csv` so the
    part can be added as extra components in the JLCPCB cart (shipped loose,
    not soldered). J1 is that case: order the header, do not wave-solder it.
  * LCSC order codes come from the LCSC column of `docs/bom.md`, which is
    where a human picks parts. A board part on the assembly BOM with no
    number there is a failed export: JLCPCB skips a blank LCSC cell, so a
    CSV that still writes is worse than none.
"""

import csv
import os
import re
import sys

import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    # KiCad 10's Windows build asserts in PCB_VIA::GetWidth() when no layer
    # is given. That pops a modal dialog and stops a headless script.
    wx.DisableAsserts()

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PCB = os.path.join(HERE, "recorder.kicad_pcb")
POS = os.path.join(REPO, "hardware", "kicad", "fab", "recorder-pos.csv")
BOM_DOC = os.path.join(REPO, "docs", "bom.md")
BOM_CSV = os.path.join(REPO, "hardware", "kicad", "jlcpcb_bom.csv")
CPL_CSV = os.path.join(REPO, "hardware", "kicad", "jlcpcb_cpl.csv")
EXTRA_CSV = os.path.join(REPO, "hardware", "kicad", "jlcpcb_extra.csv")

# JLCPCB places each part with its own library footprint, and that footprint's
# zero angle is not always KiCad's. These degrees (CCW) are added to the KiCad
# rotation in jlcpcb_cpl.csv so JLC's pin-1 lands on our pad 1. Each entry was
# read off JLC's assembly preview of the un-corrected CPL (pink pin-1 dot vs
# our pad 1 and pin-1 triangle), 1 Nov 2026. 270 is a quarter turn clockwise.
# Add a part here only from that preview, never by guessing a package rule.
# Not listed: U1 and U3 (correct at plain KiCad angles; earlier +180 tries
# did not show in the preview), J3 (flipped land; dot top-left matches).
# Y1 needs none: YXC C5203546 shows its dot on pad 1 at our 180. J2 (HRO
# TYPE-C-31-M-13C, C2848620, dev / USB-C variant) has no entry because the
# PSV land is the LCSC EasyEDA land copied 1:1, same origin and same zero
# angle (mouth toward +Y), so KiCad's 180 should be JLC's 180. That is not
# yet read off the preview: check the mouth lands on the board edge before
# paying, and add an offset here if it does not.
JLC_ROTATION_OFFSET = {
    "U2": 270,   # ES8311 C962342: dot top-left, pin 1 top-right
    "MK1": 90,   # IM73A135 C3171831: quarter turn counter-clockwise
    "U4": 270,   # AP2112K C51118: JLC body lies flat, our land stands up
    "U5": 270,   # AP22804 C3001659: same as U4
    "U7": 270,   # USBLC6-2SC6 C7519: same as U4
    "U8": 270,   # LP5907 C186700: same as U4
}

_LCSC = re.compile(r"^C\d{4,}$")
_REF = re.compile(r"^([^\d]+)(\d*)$")


def ref_key(ref):
    """Sort C2 before C10 and keep Rsd0..Rsd4 together."""
    prefix, number = _REF.match(ref).groups()
    return prefix, int(number) if number else -1


def lcsc_by_ref(refs):
    """Read the Ref and LCSC columns out of the tables in docs/bom.md.

    A Ref cell can name more than one part ("R2 / R3"), and it can name
    something that is not on this board ("MK1 alt", "MAG1"). Only tokens that
    match a reference actually placed on the PCB are used, so an alternate
    part listed for comparison never sneaks into the order.
    """
    found = {}
    with open(BOM_DOC, encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 4 or not _LCSC.match(cells[3]):
                continue
            for token in re.split(r"[/,]", cells[0]):
                token = token.strip()
                if token in refs:
                    found[token] = cells[3]
    return found


def read_pos():
    with open(POS, encoding="utf-8") as fh:
        return {row["Ref"]: row for row in csv.DictReader(fh)}


def write_cpl(board, placed):
    """Copy kicad-cli's position export into the column names JLC expects.

    The ref-set check is not enough. A stale recorder-pos.csv that still
    lists the same parts, just at last week's coordinates, would pass that
    and write a pick-and-place file the Gerbers no longer match. kicad-cli
    flips Y (physical +Y, opposite the editor) and may emit -90 where the
    board stores 270, so compare after those two transforms.
    """
    expected = {fp.GetReference(): fp for fp in board.GetFootprints()
                if not fp.IsExcludedFromPosFiles()}
    if set(expected) != set(placed):
        raise SystemExit(
            "hardware/kicad/fab/recorder-pos.csv does not describe this "
            "board. Only in the board: "
            f"{sorted(set(expected) - set(placed))}; only in the export: "
            f"{sorted(set(placed) - set(expected))}. Re-run "
            "'python3 scripts/check_gates.py' so kicad-cli rewrites it.")

    drifted = []
    for ref, fp in expected.items():
        row = placed[ref]
        x = round(pcbnew.ToMM(fp.GetPosition().x), 4)
        y = -round(pcbnew.ToMM(fp.GetPosition().y), 4)
        rot = round(fp.GetOrientationDegrees()) % 360
        side = "top" if fp.GetLayer() == pcbnew.F_Cu else "bottom"
        pos_x, pos_y = float(row["PosX"]), float(row["PosY"])
        pos_rot = round(float(row["Rot"])) % 360
        pos_side = row["Side"].strip().lower()
        if (abs(pos_x - x) > 0.01 or abs(pos_y - y) > 0.01
                or pos_rot != rot or pos_side != side):
            drifted.append(
                f"{ref}: pos ({pos_x},{pos_y},{pos_rot},{pos_side}) vs "
                f"board ({x},{y},{rot},{side})")
    if drifted:
        raise SystemExit(
            "hardware/kicad/fab/recorder-pos.csv is stale; its refs match "
            "the board but the coordinates do not:\n  "
            + "\n  ".join(drifted)
            + "\nRe-run 'python3 scripts/check_gates.py' so kicad-cli "
            "rewrites it.")

    with open(CPL_CSV, "w", encoding="utf-8", newline="\n") as fh:
        out = csv.writer(fh, lineterminator="\n")
        out.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for ref in sorted(placed, key=ref_key):
            row = placed[ref]
            # kicad-cli emits -90 for a quarter turn and the form wants 270.
            # Then turn JLC's footprint so its pin 1 meets ours.
            rot = (float(row["Rot"]) + JLC_ROTATION_OFFSET.get(ref, 0)) % 360.0
            out.writerow([ref, row["PosX"], row["PosY"], row["Side"],
                          f"{rot:.6f}"])
    return len(placed)


def write_bom(board):
    parts = [fp for fp in board.GetFootprints() if not fp.IsExcludedFromBOM()]
    codes = lcsc_by_ref({fp.GetReference() for fp in parts})
    unsourced = sorted((fp.GetReference() for fp in parts
                        if fp.GetReference() not in codes), key=ref_key)
    if unsourced:
        raise SystemExit(
            "docs/bom.md has no LCSC number for: " + ", ".join(unsourced)
            + ". JLCPCB will not place a blank LCSC cell. Put the C-number "
            "in the table and re-run.")
    _write_jlc_csv(BOM_CSV, _grouped_rows(parts, codes))
    return len(parts)


def _grouped_rows(parts, codes):
    groups = {}
    for fp in parts:
        ref = fp.GetReference()
        key = (fp.GetValue(), fp.GetFPIDAsString().split(":")[-1],
               codes.get(ref, ""))
        groups.setdefault(key, []).append(ref)
    return sorted(((key, sorted(refs, key=ref_key))
                   for key, refs in groups.items()),
                  key=lambda item: ref_key(item[1][0]))


def _write_jlc_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        out = csv.writer(fh, lineterminator="\n", quoting=csv.QUOTE_ALL)
        out.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, code), refs in rows:
            out.writerow([value, ",".join(refs), footprint, code])


def write_extra(board):
    """Parts flagged exclude_from_bom that still have an LCSC in docs/bom.md.

    JLCPCB will not solder these. Add them under Extra Parts in the SMT
    order so the bag still ships with the boards.
    """
    skipped = [fp for fp in board.GetFootprints() if fp.IsExcludedFromBOM()]
    codes = lcsc_by_ref({fp.GetReference() for fp in skipped})
    extra = [fp for fp in skipped if fp.GetReference() in codes]
    _write_jlc_csv(EXTRA_CSV, _grouped_rows(extra, codes))
    return len(extra)


def main():
    board = pcbnew.LoadBoard(PCB)
    if board is None:
        raise SystemExit(f"could not load {PCB}")
    placed = write_cpl(board, read_pos())
    lines = write_bom(board)
    extra = write_extra(board)
    print(f"jlcpcb_cpl.csv: {placed} placements, JLC rotation fixes: "
          + ", ".join(f"{r} +{d}" for r, d in sorted(JLC_ROTATION_OFFSET.items())))
    print(f"jlcpcb_bom.csv: {lines} parts")
    print(f"jlcpcb_extra.csv: {extra} parts (order, do not assemble)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
