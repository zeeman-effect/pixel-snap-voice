#!/usr/bin/env python3

from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECORDER = REPO / "hardware" / "kicad" / "recorder"
PCB = RECORDER / "recorder.kicad_pcb"
FAB = REPO / "hardware" / "kicad" / "fab"


def find_kicad_cli() -> Path | None:
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).is_file():
        return Path(env)
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def run(args: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.check_call(args, cwd=str(cwd or REPO))


def has_pcbnew() -> bool:
    probe = subprocess.run([sys.executable, "-c", "import pcbnew"],
                           capture_output=True)
    return probe.returncode == 0


def drc_counts(kicad: Path, extra: list[str]) -> dict:
    """Run kicad-cli DRC and hand back the parsed JSON."""
    out = Path(tempfile.gettempdir()) / "psv-drc.json"
    run([str(kicad), "pcb", "drc", "--severity-all", "--schematic-parity",
         "--format", "json", "-o", str(out), str(PCB)] + extra)
    return json.loads(out.read_text(encoding="utf-8"))


# kicad-cli pcb drc --schematic-parity reports these 26 notes and every one is
# expected. Counting them is not a check: a new extra footprint, or a pad that
# quietly lost its net, lands in the same list and the old gate still plotted.
# Each key is (violation type, reference, pad or field name). Add a key only
# together with the reason it is allowed to be there.
EXPECTED_PARITY: dict[tuple[str, str, str], str] = {}
EXPECTED_PARITY.update({
    # NPTH mounting holes. Mechanical, so no symbol, so nothing in the
    # schematic to match. Giving them symbols would put four fake parts in the
    # BOM to silence a note that is telling the truth.
    ("extra_footprint", ref, ""): "NPTH mounting hole, mechanical only"
    for ref in ("H1", "H2", "H3", "H4")
})
EXPECTED_PARITY.update({
    # The module breaks out far more GPIO than v1 uses. The schematic only
    # draws the castellations that go somewhere; the rest are left floating on
    # purpose so a v2 can pick them up.
    ("net_conflict", "U1", pad): "spare ESP32-S3-MINI-1U castellation"
    for pad in ("7", "25", "26", "27", "28", "29", "30", "31", "32", "33",
                "34", "35", "36", "37", "38", "41", "44")
})
EXPECTED_PARITY.update({
    ("net_conflict", "J2", "A8"): "USB-C SBU1: v1 is a 5 V sink, no alt mode",
    ("net_conflict", "J2", "B8"): "USB-C SBU2: v1 is a 5 V sink, no alt mode",
    ("net_conflict", "U4", "4"): "AP2112K-3.3 pin 4 is NC",
    ("net_conflict", "U5", "3"): "AP22804AW5 fault flag, not read by firmware",
    ("net_conflict", "U8", "4"): "LP5907MFX-3.3 pin 4 is NC",
})

_PAD = re.compile(r"^Pad (\S+) \[.*\] of (\w+) on ")
_FOOTPRINT = re.compile(r"^Footprint (\w+)$")
_FIELD = re.compile(r"^Field '([^']+)' differs")


def parity_key(note: dict) -> tuple[str, str, str]:
    """Boil a parity note down to what it is about, dropping coordinates."""
    kind = note["type"]
    ref = subject = ""
    for item in note.get("items", []):
        text = item.get("description", "")
        pad = _PAD.match(text)
        if pad:
            subject, ref = pad.group(1), pad.group(2)
            break
        fp = _FOOTPRINT.match(text)
        if fp:
            ref = fp.group(1)
            break
    field = _FIELD.match(note.get("description", ""))
    if field:
        subject = field.group(1)
    return kind, ref, subject


def drc_gate(kicad: Path) -> None:
    """Refuse to plot unless the board is clean, poured, and matches the sheets.

    Three things used to slip past. The old call passed --severity-error, so
    every warning-level rule (silk over copper, dangling vias, missing
    footprint libraries, and the JLC pad hole-spacing rule in
    recorder.kicad_dru) was invisible. Nothing noticed when the zone fills
    stored in the board were out of date, and kicad-cli plots the stored fill,
    so a stale one ships. And the schematic-parity notes were printed, then
    ignored, so a new one changed a number nobody was checking.

    Warnings fail here too. A DRC rule this project has decided not to care
    about belongs in rule_severities in recorder.kicad_pro, set to 'ignore',
    where the decision shows up in a diff and someone reviews it. It does not
    belong in an allowlist that quietly grows.
    """
    report = drc_counts(kicad, [])
    violations = report["violations"]
    unconnected = report["unconnected_items"]
    parity = report["schematic_parity"]

    refilled = drc_counts(kicad, ["--refill-zones"])
    if (len(refilled["violations"]), len(refilled["unconnected_items"])) != \
            (len(violations), len(unconnected)):
        raise SystemExit(
            "zone fills in recorder.kicad_pcb are stale: DRC disagrees with "
            "itself once the pours are refilled, and the Gerbers would be "
            "plotted from the stale copper. Run "
            "'python3 hardware/kicad/recorder/route_pcb.py --planes-only'."
        )

    run([str(kicad), "pcb", "drc", "--severity-all", "--schematic-parity",
         "-o", str(RECORDER / "drc.rpt"), str(PCB)])
    counts = collections.Counter(
        f"{v['type']} ({v['severity']})" for v in violations)
    print(f"drc: {len(violations)} violations, {len(unconnected)} unconnected, "
          f"{len(parity)} schematic-parity notes")

    problems = []
    for name, count in sorted(counts.items()):
        problems.append(f"  {count} x {name}")
    if unconnected:
        problems.append(f"  {len(unconnected)} unconnected items")

    seen = collections.Counter(parity_key(note) for note in parity)
    for key, count in sorted(seen.items()):
        if key not in EXPECTED_PARITY:
            kind, ref, subject = key
            problems.append(
                f"  unexpected schematic-parity note: {kind} on "
                f"{ref or '?'}{' ' + subject if subject else ''}")
        elif count > 1:
            problems.append(f"  schematic-parity note {key} seen {count} times")
    for key, reason in sorted(EXPECTED_PARITY.items()):
        if key not in seen:
            problems.append(
                f"  schematic-parity note {key} is gone ({reason}). If that "
                f"is the fix, drop it from EXPECTED_PARITY.")

    if problems:
        raise SystemExit("DRC is not clean; not writing fab output:\n"
                         + "\n".join(problems))


def export_fab(kicad: Path) -> None:
    """Write the whole upload package, not just the copper.

    Gerbers alone used to be re-exported here while the drill file, the
    pick-and-place CSV, and recorder-jlc.zip kept whatever date they were
    committed with. That is worse than exporting nothing: the drill file on
    disk predated the routed board and had no 0.3 mm tool in it, so the
    package described a board with none of its vias drilled. Everything the
    fab reads is now written in one pass from one board file.

    That now includes the two assembly CSVs. docs/manufacturing.md tells you
    to upload them beside the Gerbers and they were hand-typed, so four
    decoupling capacitors still sat at their pre-route coordinates and SW1
    named a land the board had stopped using. Half a fresh package is worse
    than none, so a missing pcbnew stops the export instead of writing
    Gerbers that no longer agree with the CSVs next to them.
    """
    drc_gate(kicad)
    if not has_pcbnew():
        raise SystemExit(
            "no pcbnew in this interpreter, so hardware/kicad/jlcpcb_bom.csv "
            "and jlcpcb_cpl.csv cannot be rewritten from the board and would "
            "not match the Gerbers. On Windows, run this with KiCad 10's "
            "python.exe.")
    run([str(kicad), "pcb", "export", "gerbers", "-o", str(FAB), str(PCB)])
    run([str(kicad), "pcb", "export", "drill", "--generate-map",
         "--excellon-separate-th", "-o", str(FAB) + os.sep, str(PCB)])
    run([str(kicad), "pcb", "export", "pos", "--format", "csv", "--units", "mm",
         "-o", str(FAB / "recorder-pos.csv"), str(PCB)])
    run([sys.executable, str(RECORDER / "generate_jlc.py")])

    # JLCPCB wants the layers and the drills in one archive. Fab/courtyard and
    # the user layers are internal documentation, so they stay out of it.
    archive = FAB / "recorder-jlc.zip"
    skip = ("Fab", "Courtyard", "Adhesive", "User_", "Margin")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(FAB.iterdir()):
            if path.suffix.lower() not in (".gbl", ".gbo", ".gbp", ".gbs",
                                           ".gbrjob", ".gm1", ".gtl", ".gto",
                                           ".gtp", ".gts", ".g1", ".g2", ".drl"):
                continue
            if any(tag in path.name for tag in skip):
                continue
            zf.write(path, path.name)
    print("kicad-cli gerbers, drills, pos and", archive.name, "written to", FAB)


def main() -> int:
    test = REPO / "build" / "host" / "Debug" / "recorder_test.exe"
    if not test.is_file():
        test = REPO / "build" / "host" / "recorder_test"
    if not test.is_file():
        run(["cmake", "-S", "sim/host", "-B", "build/host"])
        run(["cmake", "--build", "build/host"])
        test = REPO / "build" / "host" / "Debug" / "recorder_test.exe"
        if not test.is_file():
            test = REPO / "build" / "host" / "recorder_test"
    run([str(test)], cwd=test.parent)

    run([sys.executable, str(REPO / "hardware" / "cad" / "check_envelope.py")])
    run([sys.executable, str(RECORDER / "verify_schematic.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_kicad_format.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_drc.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_mcu.py")])
    run([sys.executable, str(REPO / "hardware" / "kicad" / "check_pins.py")])

    # Placement needs pcbnew, which on Windows only lives inside KiCad's own
    # python.exe. Every other gate here is plain Python on purpose, so this one
    # runs when the module happens to be importable and says so when it is not.
    if has_pcbnew():
        run([sys.executable, str(RECORDER / "check_placement.py")])
    else:
        print("check_placement skipped (no pcbnew in this interpreter)")

    kicad = find_kicad_cli()
    if PCB.is_file() and kicad:
        FAB.mkdir(parents=True, exist_ok=True)
        export_fab(kicad)
        print("check_gates: ok")
        return 0

    reasons = []
    if not PCB.is_file():
        reasons.append("recorder.kicad_pcb not on disk yet")
    if not kicad:
        reasons.append("kicad-cli not found")
    print("kicad-cli gerber export skipped (" + "; ".join(reasons) + ").")
    print("hardware/kicad/fab/ is a stand-in outline, not a JLCPCB upload.")
    print("check_gates: ok (do not send fab/ to a board house)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print("check_gates: FAIL", exc, file=sys.stderr)
        raise SystemExit(1)
