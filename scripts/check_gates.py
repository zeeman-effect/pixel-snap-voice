#!/usr/bin/env python3

from __future__ import annotations

import json
import os
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


def drc_gate(kicad: Path) -> None:
    """Gate on copper errors, and refuse to plot a board with stale pours.

    Two things used to slip past here. The old call passed --severity-error,
    so every warning-level rule the board is checked against (silk over
    copper, dangling vias, footprint/library parity) was invisible to the
    gate. And nothing noticed when the zone fills stored in the board were out
    of date: kicad-cli plots the stored fill, so a stale one ships to the fab
    even though DRC refills before checking and reports a clean board.
    """
    report = drc_counts(kicad, [])
    errors = [v for v in report["violations"] if v["severity"] == "error"]
    warnings = [v for v in report["violations"] if v["severity"] == "warning"]
    unconnected = report["unconnected_items"]
    parity = report["schematic_parity"]

    refilled = drc_counts(kicad, ["--refill-zones"])
    if (len(refilled["violations"]), len(refilled["unconnected_items"])) != \
            (len(report["violations"]), len(unconnected)):
        raise SystemExit(
            "zone fills in recorder.kicad_pcb are stale: DRC disagrees with "
            "itself once the pours are refilled, and the Gerbers would be "
            "plotted from the stale copper. Run "
            "'python3 hardware/kicad/recorder/route_pcb.py --planes-only'."
        )

    run([str(kicad), "pcb", "drc", "--severity-all", "--schematic-parity",
         "-o", str(RECORDER / "drc.rpt"), str(PCB)])
    print(f"drc: {len(errors)} errors, {len(warnings)} warnings, "
          f"{len(unconnected)} unconnected, {len(parity)} schematic-parity notes")
    if errors or unconnected:
        raise SystemExit("DRC is not clean; not writing fab output")


def export_fab(kicad: Path) -> None:
    """Write the whole upload package, not just the copper.

    Gerbers alone used to be re-exported here while the drill file, the
    pick-and-place CSV, and recorder-jlc.zip kept whatever date they were
    committed with. That is worse than exporting nothing: the drill file on
    disk predated the routed board and had no 0.3 mm tool in it, so the
    package described a board with none of its vias drilled. Everything the
    fab reads is now written in one pass from one board file.
    """
    drc_gate(kicad)
    run([str(kicad), "pcb", "export", "gerbers", "-o", str(FAB), str(PCB)])
    run([str(kicad), "pcb", "export", "drill", "--generate-map",
         "--excellon-separate-th", "-o", str(FAB) + os.sep, str(PCB)])
    run([str(kicad), "pcb", "export", "pos", "--format", "csv", "--units", "mm",
         "-o", str(FAB / "recorder-pos.csv"), str(PCB)])

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
