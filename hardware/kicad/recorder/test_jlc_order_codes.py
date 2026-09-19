#!/usr/bin/env python3
"""The three LCSC codes JLCPCB rejected at order time stay locked.

Reads docs/bom.md and hardware/kicad/jlcpcb_bom.csv directly. Do not import
generate_jlc: that module loads pcbnew, and this lock has to run in the
plain-Python half of check_gates.
"""

from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BOM_DOC = REPO / "docs" / "bom.md"
BOM_CSV = REPO / "hardware" / "kicad" / "jlcpcb_bom.csv"

_LCSC = re.compile(r"^C\d{4,}$")
ORDERED = {"F1": "C883095", "U7": "C7519", "Y1": "C49207908"}
DEAD = {"F1": "C37010", "U7": "C8678", "Y1": "C1857159"}
BANNED_BACKUP = "C5917271"


def lcsc_by_ref(refs: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in BOM_DOC.read_text(encoding="utf-8").splitlines():
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


class OrderCodes(unittest.TestCase):
    def test_bom_md_matches_the_jlc_order(self):
        self.assertEqual(lcsc_by_ref(set(ORDERED)), ORDERED)

    def test_generated_csv_matches_bom_md(self):
        found: dict[str, str] = {}
        with BOM_CSV.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                for ref in row["Designator"].split(","):
                    found[ref] = row["LCSC Part #"]
        for ref, code in ORDERED.items():
            self.assertEqual(found[ref], code)
        for ref, dead in DEAD.items():
            self.assertNotEqual(found[ref], dead)

    def test_y1_notes_do_not_offer_the_3v3_only_lucki(self):
        y1_row = next(
            line for line in BOM_DOC.read_text(encoding="utf-8").splitlines()
            if line.startswith("| Y1 ")
        )
        self.assertIn("C49207908", y1_row)
        self.assertNotIn("Backup", y1_row)
        self.assertIn(BANNED_BACKUP, y1_row)
        self.assertIn("not", y1_row.lower())


if __name__ == "__main__":
    unittest.main()
