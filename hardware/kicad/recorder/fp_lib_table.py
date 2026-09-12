#!/usr/bin/env python3
"""One owner for hardware/kicad/recorder/fp-lib-table.

Two generators used to write this file. generate_pcb.py listed every library
the board cites, and generate_recorder.py overwrote the same file with a
PSV-only table. Whichever ran last won, so editing the schematic - the
documented, ordinary thing to do - silently deleted thirteen rows. KiCad then
could not resolve names like Capacitor_SMD:C_0805_2012Metric, and DRC reported
that as lib_footprint_issues, which is a warning.

The fix is not to pick a winner. Both scripts now call write_fp_lib_table()
here, and the set of libraries is read back off disk from the placed symbols in
every .kicad_sch plus the footprints in recorder.kicad_pcb. Run order stops
mattering, because both answers are the same answer.

This module deliberately has no pcbnew import: generate_recorder.py is plain
python3 and generate_pcb.py is KiCad's bundled interpreter, and both need it.
"""

from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "fp-lib-table")

# Libraries that live in the project rather than the KiCad install. Everything
# else is resolved through KICAD10_FOOTPRINT_DIR, which KiCad defines itself,
# so the table works on whichever machine has KiCad rather than on one laptop.
LOCAL_LIBS = {
    "PSV": ("${KIPRJMOD}/PSV.pretty",
            "Recorder land patterns KiCad 10 does not ship"),
}
STOCK_DESCR = "KiCad 10 stock library"

_LIB_NICK = r"([A-Za-z0-9_.+\-]+)"
_SCH_FOOTPRINT = re.compile(r'\(property\s+"Footprint"\s+"' + _LIB_NICK + ':')
_PCB_FOOTPRINT = re.compile(r'^\s*\(footprint\s+"' + _LIB_NICK + ':', re.M)


def _strip_quoted(text: str) -> str:
    """Blank out quoted strings so paren counting cannot be fooled by them."""
    out = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            out.append(" ")
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                out[-1] = '"'
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
    return "".join(out)


def strip_lib_symbols(text: str) -> str:
    """Drop the cached (lib_symbols ...) block from a .kicad_sch.

    That block is a verbatim copy of each stock symbol, including its default
    Footprint field, and those defaults name libraries this project never
    places. KiCad's own ESP32-S3-MINI-1 symbol, for one, defaults to
    RF_Module:ESP32-S2-MINI-1. Only the placed symbols below the cache say
    what the board actually uses.
    """
    start = text.find("(lib_symbols")
    if start < 0:
        return text
    masked = _strip_quoted(text)
    depth = 0
    for i in range(start, len(masked)):
        if masked[i] == "(":
            depth += 1
        elif masked[i] == ")":
            depth -= 1
            if depth == 0:
                return text[:start] + text[i + 1:]
    raise ValueError("unterminated (lib_symbols ...) block")


def libs_in_use(project_dir: str = HERE) -> set[str]:
    """Every library nickname cited by the schematic sheets and the board."""
    libs = set(LOCAL_LIBS)
    for name in sorted(os.listdir(project_dir)):
        path = os.path.join(project_dir, name)
        if name.endswith(".kicad_sch"):
            with open(path, encoding="utf-8") as fh:
                text = strip_lib_symbols(fh.read())
            libs |= set(_SCH_FOOTPRINT.findall(text))
        elif name.endswith(".kicad_pcb"):
            with open(path, encoding="utf-8") as fh:
                libs |= set(_PCB_FOOTPRINT.findall(fh.read()))
    return libs


def render(libs) -> str:
    rows = ["(fp_lib_table", "\t(version 7)"]
    for lib in sorted(libs):
        uri, descr = LOCAL_LIBS.get(
            lib, ("${KICAD10_FOOTPRINT_DIR}/" + lib + ".pretty", STOCK_DESCR))
        rows.append(f'\t(lib (name "{lib}")(type "KiCad")(uri "{uri}")'
                    f'(options "")(descr "{descr}"))')
    rows.append(")")
    return "\n".join(rows) + "\n"


def write_fp_lib_table(extra=(), path: str = TABLE,
                       project_dir: str = HERE) -> set[str]:
    """Write the table and return what went into it.

    `extra` is for a caller holding a board in memory that is not on disk yet,
    such as generate_pcb.py mid-build. Everything else is rediscovered, so a
    library that stops being used drops out instead of lingering.
    """
    libs = libs_in_use(project_dir) | set(extra)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render(libs))
    return libs


if __name__ == "__main__":
    print("\n".join(sorted(write_fp_lib_table())))
