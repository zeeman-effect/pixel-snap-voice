#!/usr/bin/env python3
"""Write hardware/kicad/jlcpcb_bom.csv and jlcpcb_cpl.csv from the board.

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
    the tool that already knows the convention.
  * Which parts appear at all comes from the board's own KiCad attributes.
    A part is in the pick-and-place file unless it is flagged
    `exclude_from_pos_files`, and on the BOM unless it is flagged
    `exclude_from_bom`. That is a board edit and shows up in a diff, instead
    of a list of references hidden in a script.
  * LCSC order codes come from the LCSC column of `docs/bom.md`, which is
    where a human picks parts. A BOM or pick-and-place row with no number
    is a feeder JLC cannot fill, so this script refuses to write the CSVs
    until every assembled part has a code. Hand-placed parts (J1, MK1)
    stay off those files via the board's exclude flags, not via a blank
    cell.
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
            # Same angle, written the way JLC's uploader expects to read it:
            # kicad-cli emits -90 for a quarter turn and the form wants 270.
            rot = float(row["Rot"]) % 360.0
            out.writerow([ref, row["PosX"], row["PosY"], row["Side"],
                          f"{rot:.6f}"])
    return len(placed)


def write_bom(board, codes):
    parts = [fp for fp in board.GetFootprints() if not fp.IsExcludedFromBOM()]
    groups = {}
    for fp in parts:
        ref = fp.GetReference()
        key = (fp.GetValue(), fp.GetFPIDAsString().split(":")[-1],
               codes.get(ref, ""))
        groups.setdefault(key, []).append(ref)

    rows = sorted(((key, sorted(refs, key=ref_key))
                   for key, refs in groups.items()),
                  key=lambda item: ref_key(item[1][0]))
    with open(BOM_CSV, "w", encoding="utf-8", newline="\n") as fh:
        out = csv.writer(fh, lineterminator="\n", quoting=csv.QUOTE_ALL)
        out.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (value, footprint, code), refs in rows:
            out.writerow([value, ",".join(refs), footprint, code])
    return [fp.GetReference() for fp in parts]


def sourced_or_die(kind, refs, codes):
    """Refuse a JLC upload whose machine file still has blank LCSC cells."""
    missing = sorted((ref for ref in refs if ref not in codes), key=ref_key)
    if missing:
        raise SystemExit(
            f"{kind} still has no LCSC number in docs/bom.md: "
            + ", ".join(missing)
            + ". Put the order code in the Electrical table, or flag the "
            "footprint exclude_from_bom / exclude_from_pos_files if JLC "
            "must not place it."
        )


HAND_PLACE = {
    "J1": "UART header, soldered at bring-up",
    "MK1": "analog MEMS, placed after SMT",
}


def require_hand_place(board):
    """J1 and MK1 stay off the JLC order even if someone types an LCSC code."""
    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    problems = []
    for ref, reason in HAND_PLACE.items():
        fp = by_ref.get(ref)
        if fp is None:
            problems.append(f"{ref} is missing ({reason})")
            continue
        if not fp.IsExcludedFromBOM() or not fp.IsExcludedFromPosFiles():
            problems.append(
                f"{ref} must be exclude_from_bom and exclude_from_pos_files "
                f"({reason})"
            )
    if problems:
        raise SystemExit("hand-placed parts leaked into the JLC order:\n  "
                         + "\n  ".join(problems))


def main():
    board = pcbnew.LoadBoard(PCB)
    if board is None:
        raise SystemExit(f"could not load {PCB}")
    require_hand_place(board)
    bom_refs = [fp.GetReference() for fp in board.GetFootprints()
                if not fp.IsExcludedFromBOM()]
    pos_refs = [fp.GetReference() for fp in board.GetFootprints()
                if not fp.IsExcludedFromPosFiles()]
    codes = lcsc_by_ref(set(bom_refs) | set(pos_refs))
    sourced_or_die("jlcpcb_bom.csv", bom_refs, codes)
    sourced_or_die("jlcpcb_cpl.csv", pos_refs, codes)
    placed = write_cpl(board, read_pos())
    lines = len(write_bom(board, codes))
    print(f"jlcpcb_cpl.csv: {placed} placements")
    print(f"jlcpcb_bom.csv: {lines} parts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
