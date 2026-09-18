#!/usr/bin/env python3
"""The three LCSC codes JLCPCB rejected at order time stay locked."""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from generate_jlc import BOM_CSV, lcsc_by_ref

ORDERED = {"F1": "C883095", "U7": "C7519", "Y1": "C49207908"}
DEAD = {"F1": "C37010", "U7": "C8678", "Y1": "C1857159"}


class OrderCodes(unittest.TestCase):
    def test_bom_md_matches_the_jlc_order(self):
        codes = lcsc_by_ref(set(ORDERED))
        self.assertEqual(codes, ORDERED)

    def test_generated_csv_matches_bom_md(self):
        found = {}
        with Path(BOM_CSV).open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                for ref in row["Designator"].split(","):
                    found[ref] = row["LCSC Part #"]
        for ref, code in ORDERED.items():
            self.assertEqual(found[ref], code)
        for ref, dead in DEAD.items():
            self.assertNotEqual(found[ref], dead)


if __name__ == "__main__":
    unittest.main()
