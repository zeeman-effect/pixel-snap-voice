#!/usr/bin/env python3
"""Guard the JLC assembly CSVs: every machine-placed part needs an LCSC code."""

from __future__ import annotations

import unittest

from generate_jlc import HAND_PLACE, lcsc_by_ref, sourced_or_die


class LcscTable(unittest.TestCase):
    def test_assembled_refs_have_codes(self):
        refs = {
            "C1", "C21", "F1", "R4", "R8", "Ragnd", "U5", "U7", "U8", "Y1",
            "BT1", "J1", "MK1", "MAG1",
        }
        codes = lcsc_by_ref(refs)
        self.assertEqual(codes["C1"], "C45783")
        self.assertEqual(codes["F1"], "C883095")
        self.assertEqual(codes["U7"], "C7519")
        self.assertEqual(codes["C21"], "C19702")
        self.assertEqual(codes["R4"], "C4177")
        self.assertEqual(codes["R8"], "C22991")
        self.assertEqual(codes["Ragnd"], "C21189")
        self.assertEqual(codes["U5"], "C3001659")
        self.assertEqual(codes["U8"], "C80670")
        self.assertEqual(codes["Y1"], "C1857159")
        self.assertEqual(codes["BT1"], "C173752")
        self.assertNotIn("MAG1", codes)
        # J1 stays off the JLC files. MK1 has a buy-it-yourself code in
        # bom.md, but require_hand_place keeps it off the CSVs.
        self.assertNotIn("J1", codes)
        self.assertEqual(codes["MK1"], "C3171831")

    def test_blank_lcsc_fails_the_gate(self):
        with self.assertRaises(SystemExit) as caught:
            sourced_or_die("jlcpcb_bom.csv", ["C1", "Y1"], {"C1": "C45783"})
        self.assertIn("Y1", str(caught.exception))

    def test_hand_place_list(self):
        self.assertEqual(set(HAND_PLACE), {"J1", "MK1"})


if __name__ == "__main__":
    unittest.main()
