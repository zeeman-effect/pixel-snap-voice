#!/usr/bin/env python
"""Generate hardware/kicad/recorder/recorder.kicad_pcb from the recorder netlist.

Run with the KiCad 10 interpreter, which is the only one that has pcbnew:

    /c/Users/zachr/AppData/Local/Programs/KiCad/10.0/bin/python.exe generate_pcb.py

Electrical truth is recorder.net, exported from the recorder schematic. This
script never reads or writes a .kicad_sch. It creates the board outline, the
4-layer 0.8 mm stackup, the mounting holes, the magnet-ring keepout markings,
and places every schematic part at the coordinates in PLACEMENT below. It does
not route. It also writes placement.json, the XY record for the CAD side.
Edit that file and the board together when a part moves. Re-running this
script wipes existing copper.

Coordinates are board coordinates in millimetres with the origin at the
magnet-ring (Pixelsnap) centre, matching hardware/cad/params.json: +X is phone
right and +Y is toward the camera bar. These are written straight into the
.kicad_pcb, so the USB edge is the y = -42.8 edge of the file.
"""

import json
import math
import os
import re

import pcbnew

try:
    import wx
except ImportError:
    wx = None
else:
    # KiCad 10's Windows build asserts in PCB_VIA::GetWidth() when no layer
    # is given. That pops a modal dialog and stops a headless script.
    wx.DisableAsserts()

from fp_lib_table import write_fp_lib_table

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PARAMS = os.path.join(REPO, "hardware", "cad", "params.json")
NETLIST = os.path.join(HERE, "recorder.net")
PCB_OUT = os.path.join(HERE, "recorder.kicad_pcb")
PROJECT = os.path.join(HERE, "recorder.kicad_pro")
PLACEMENT_OUT = os.path.join(HERE, "placement.json")

# Keys in the .kicad_pro that belong to the schematic, not the board. pcbnew
# rewrites the whole project file on save and blanks these, which would leave
# KiCad unable to find the hierarchical sheets, so they are put back verbatim.
SCHEMATIC_OWNED_KEYS = ("sheets", "schematic", "text_variables", "meta")

def _system_footprint_dir():
    """Where KiCad 10 keeps its shipped .pretty folders on this machine."""
    env = os.environ.get("KICAD_FOOTPRINT_DIR")
    candidates = [env] if env else []
    candidates += [
        "/usr/share/kicad/footprints",
        "/usr/local/share/kicad/footprints",
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs", "KiCad", "10.0", "share", "kicad", "footprints",
        ),
        r"C:\Program Files\KiCad\10.0\share\kicad\footprints",
    ]
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    raise SystemExit(
        "cannot find the KiCad 10 footprint libraries. Set KICAD_FOOTPRINT_DIR."
    )


SYS_FP = _system_footprint_dir()
LOCAL_FP = os.path.join(HERE, "PSV.pretty")

# No footprint substitutions any more. The schematic used to name six
# footprints that do not exist under that name in KiCad 10, and this script
# quietly swapped each for a look-alike. Board and schematic now agree:
# four names were corrected in generate_recorder.py, and the two land
# patterns KiCad 10 does not ship at all (ESP32-S3-MINI-1U and the
# IM73A135 PG-LLGA-5-3 with a hole-clearance-legal ring pad) live in
# PSV.pretty. Keep this table empty; fix the name instead.
SUBSTITUTIONS = {}

# ---------------------------------------------------------------------------
# Fab policy. pcbnew writes recorder.kicad_pro from BOARD defaults on save and
# generate_recorder.py rewrites the schematic half of the same file, so the
# DRC numbers have to be re-applied from one place afterwards.
#
# Every number below is JLCPCB's published standard 4-layer FR-4 capability or
# tighter, and the comment says which. The rules KiCad cannot express as a
# single global minimum (pad hole spacing, NPTH size) live in
# recorder.kicad_dru so that DRC checks the fab, not just the board.
# ---------------------------------------------------------------------------
DESIGN_RULES = {
    # JLC allows 0.1016 mm (4 mil) trace and space on 1 oz outer copper. Held
    # at 5 mil so a re-route cannot quietly drift onto their fine-line pricing.
    "min_clearance": 0.127,
    "min_track_width": 0.127,
    # JLC wants 0.2 mm copper to a routed edge. 0.3 absorbs their +/-0.2 mm
    # routing tolerance.
    "min_copper_edge_clearance": 0.3,
    # JLC wants 0.2 mm from any hole wall to copper. Non-plated holes carry a
    # +/-0.2 mm diameter tolerance, so a 1.7 mm mounting hole can come back
    # 0.1 mm larger in radius. 0.2 + 0.1 = 0.3 keeps the spec at worst case.
    "min_hole_clearance": 0.3,
    # Via hole-to-hole floor is 0.2 mm at JLC. Pads need 0.45 mm, which is a
    # separate rule in recorder.kicad_dru because it depends on item type.
    "min_hole_to_hole": 0.25,
    # JLC drills down to 0.15 mm on multilayer; 0.3 is their preferred size and
    # what every via on this board uses.
    "min_through_hole_diameter": 0.3,
    "min_via_diameter": 0.45,
    # Multilayer 1 oz PTH annular ring: 0.20 mm recommended, 0.15 mm absolute.
    # Every via here is 0.6/0.3, so 0.15 mm per side is what the board holds.
    "min_via_annular_width": 0.15,
    # Standard-font legend. JLC's capability table says characters under
    # 1.0 mm tall or 0.15 mm wide "will be unidentifiable".
    "min_text_height": 1.0,
    "min_text_thickness": 0.15,
}

# USB_DP / USB_DM are a coupled pair, not an impedance-matched one. See
# usb_diff_note in hardware/cad/params.json: the ESP32-S3's USB is full speed
# only, so 90 ohm control buys nothing on a 0.1 mm prepreg. The 0.2 mm gap is
# what route_pcb.py actually lays, chosen over the 0.15 mm minimum so the
# corners where one lane turns and the other runs past keep some margin.
NET_CLASSES = {
    "Default": {"clearance": 0.15, "track_width": 0.15, "via_diameter": 0.6, "via_drill": 0.3, "priority": -1},
    "USB": {"clearance": 0.15, "track_width": 0.2, "diff_pair_width": 0.2, "diff_pair_gap": 0.2, "via_diameter": 0.6, "via_drill": 0.3, "priority": 0},
    # Charge and rail currents, up to the 500 mA the BQ24073 ISET resistor
    # sets. 0.3 mm of 1 oz outer copper carries that with room to spare.
    "POWER": {"clearance": 0.15, "track_width": 0.3, "via_diameter": 0.6, "via_drill": 0.3, "priority": 0},
}

NETCLASS_PATTERNS = [
    ("USB_DP", "USB"),
    ("USB_DM", "USB"),
    ("VBUS", "POWER"),
    ("VBUS_CHG", "POWER"),
    ("VBAT", "POWER"),
    ("VSYS", "POWER"),
    ("/Power/3V3_RAW", "POWER"),
    ("3V3A", "POWER"),
]


def apply_project_policy(project_path=PROJECT):
    """Write DESIGN_RULES and NET_CLASSES into the .kicad_pro."""
    data = json.load(open(project_path, encoding="utf-8"))
    settings = data.setdefault("board", {}).setdefault("design_settings", {})
    settings.setdefault("rules", {}).update(DESIGN_RULES)
    # Solid pad-to-zone connections. Thermal spokes on a 0.8 mm board with a
    # 2-spoke minimum produced starved_thermal errors on every pad the pour
    # could only reach from one side, and this board is reflowed, not
    # hand-soldered, so the relief buys nothing.
    settings.setdefault("defaults", {}).setdefault("zones", {})["pad_connection"] = 3

    net_settings = data.setdefault("net_settings", {})
    classes = net_settings.setdefault("classes", [])
    by_name = {c.get("name"): c for c in classes}
    for name, values in NET_CLASSES.items():
        target = by_name.get(name)
        if target is None:
            target = {"name": name}
            classes.append(target)
        target.update(values)
    net_settings["netclass_patterns"] = [
        {"pattern": pattern, "netclass": name} for pattern, name in NETCLASS_PATTERNS
    ]
    with open(project_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")

# ---------------------------------------------------------------------------
# Placement: ref -> (x_mm, y_mm, rotation_deg, note)
#
# Floorplan, in board coordinates (59.6 x 85.6 mm: edges x = +/-29.8,
# y = +/-42.8). The 6 o'clock end is -Y, with the camera at +Y. The board
# and lid were spun 180° around the magnet origin; the tray clocking magnet
# stays at 6 o'clock. Dev / USB-C variant: J2 is a mid-mount USB-C on the
# phone-bottom edge, in a slot its footprint cuts (add_outline leaves the gap).
#   y +14 .. +42.8  Analog: mic, codec, analog LDO, oscillator. No speaker
#                   or class-D amp.
#   y -33 .. +33    Ring interior and the 51.5 x 66 mm Jauch pouch taped
#                   to B.Cu at (0, 0). Nothing taller than ~0.5 mm sits
#                   under that tape outline. SW1 and the status LED stay
#                   west (phone-left); I2C pull-ups and MK1 stay east.
#   y -42.8 .. -26  Charger, both regulators and USB-C J2 (+ U7, R2, R3) on
#                   the phone-bottom end.
# The magnet ring is an annulus from r = 22 to r = 28 about the origin. Every
# analog part is placed outside r = 28.
# ---------------------------------------------------------------------------
PLACEMENT = {
    # --- USB-C (dev variant) + ESD + CC Rd, phone-bottom edge ---
    "J2": (7.0, -38.1, 180, "C2848620 mid-mount USB-C, mouth on y = -42.8, params usbc_x/y"),
    "U7": (7.0, -29.3, 0, "USBLC6-2SC6 ESD, north of the J2 contact row"),
    "R2": (10.9, -32.9, 270, "CC1 Rd 5.1k"),
    "R3": (3.1, -32.9, 270, "CC2 Rd 5.1k"),
    # --- Battery charger (BQ24073 VQFN-16, phone-bottom island) ---
    # Same relative layout as the routed 64 x 86 board, shifted (-2.4, +0.2)
    # so U3 clears H2 at (26.3, -39.3) and the edge runs keep their margin.
    "F1": (15.1, -39.8, 90, "VBUS PTC"),
    "C4": (18.1, -39.8, 90, "VBUS_CHG bulk"),
    "U3": (21.6, -39.3, 180, "BQ24073, rotated so OUT/programming face C5 and the resistors"),
    "C5": (18.6, -35.3, 90, "VSYS bulk at charger OUT"),
    # West of Rstat/Rchg, over the VBAT B.Cu trunk that climbs the left edge
    # to the pouch. The aisle between U3 and H2 is inside the hole keepout.
    "C21": (28.6, -34.0, 90, "VBAT ceramic at U3 BAT, TI 4.7-47uF"),
    "R4": (16.6, -32.6, 0, "ISET ~500 mA, west of the VBUS climb to F1"),
    "R8": (15.1, -30.8, 0, "ILIM USB current backup"),
    "R9": (15.1, -28.3, 0, "TMR safety timer"),
    "R10": (18.6, -30.8, 0, "TS 10k, no pack NTC"),
    "R11": (18.6, -28.3, 0, "ITERM ~10 percent"),
    "Rstat": (25.6, -35.8, 0, "CHG_STAT pull-up"),
    "Rchg": (25.6, -32.8, 0, "charge LED series resistor"),
    "D2": (21.6, -32.8, 0, "charge status LED"),
    # --- Regulators (right of the charger, still on the camera end) ---
    "U4": (-6.0, -39.5, 0, "AP2112K-3.3, VSYS -> 3V3_RAW"),
    "C7": (-2.5, -40.0, 90, "3V3_RAW output cap"),
    "U5": (-16.0, -39.5, 0, "AP22804 load switch, 3V3_RAW -> VDD33"),
    "C8": (-20.5, -40.0, 90, "VDD33 bulk"),
    "C6": (-10.5, -36.0, 90, "VSYS decoupling at U4"),
    # --- MCU ---
    "U1": (14.0, -18.0, 0, "ESP32-S3-MINI-1U-N8, IPEX to lid FPC, no PCB antenna"),
    "C1": (24.5, -25.0, 90, "VDD33 22uF bulk at the module"),
    "C3": (24.5, -21.5, 90, "VDD33 100nF at the module"),
    "C2": (24.5, -18.0, 90, "EN delay cap"),
    "R1": (24.5, -14.5, 90, "EN pull-up"),
    "Rboot": (24.5, -11.0, 90, "IO0 boot pull-up"),
    # Bring-up pads for download mode once MSC owns the magnetic USB: short TP_BOOT to
    # TP_GND, pulse TP_EN to TP_GND, release. A column just south of Rboot,
    # west of the fence and north of the analog island, with room beside each
    # pad for a legible designator. The column west of C1-Rboot has none.
    "TP_BOOT": (27.6, -7.4, 0, "GPIO0 test pad, south of Rboot"),
    "TP_EN": (27.6, -3.6, 0, "EN test pad"),
    "TP_GND": (27.6, 0.2, 0, "GND test pad"),
    "TP_3V3": (27.6, 4.0, 0, "VDD33 test pad"),
    # --- Soldered SD NAND (old socket seat, no wall slot) ---
    "J3": (-22.0, -18.0, 0, "MKDV4GCL-ABB 512 MB SD NAND, LGA-8"),
    "Rsd0": (-11.0, -25.0, 0, "SD_CMD pull-up"),
    "Rsd1": (-11.0, -22.5, 0, "SD_D0 pull-up"),
    "Rsd2": (-11.0, -20.0, 0, "SD_D1 pull-up"),
    "Rsd3": (-11.0, -17.5, 0, "SD_D2 pull-up"),
    "Rsd4": (-11.0, -15.0, 0, "SD_D3 pull-up"),
    "C14": (-11.0, -12.0, 0, "VDD33 decoupling for the SD rail"),
    # --- Left edge user IO ---
    # Rotated 270 so the side actuator points at -X, the phone-left wall
    # when the accessory is snapped on the phone. Its tip is local (0, 2.1),
    # so x = -27.1 puts it 0.6 mm inside the board edge, where
    # params.json button_tip_inset_mm and the case key nub expect it.
    "SW1": (-27.1, 12.0, 270, "record button, side actuator faces the left "
                              "wall; TPU pill in the lid is the finger target"),
    # Rot 90 puts D1's pad 1 north, toward the trace from U1, and pad 2
    # south beside Rled pad 1.
    "D1": (-28.6, 18.0, 270, "status LED under the translucent PETG lid"),
    "Rled": (-28.6, 21.4, 270, "status LED series resistor"),
    # --- Analog island: microphone ---
    # Rot 90 puts the bottom-port NPTH (local 0.68, 0) at (27.5, 16.32),
    # the CAD mic_npth the tray seal collects.
    "MK1": (27.5, 17.0, 90, "IM73A135 analog MEMS mic, params mic_y_mm = 17"),
    # --- Analog island: codec ---
    # Rot 90 turns the codec so each pin row faces what it drives: AOUT and
    # the references south into the open band, the mic inputs west toward
    # MK1, MCLK/SCL north toward Y1 and U1, I2S east toward the module. The
    # 0.4 mm rows fan out about 1.9 mm before anything else may sit there,
    # so every cap is parked past that ring.
    "U2": (24.5, 29.0, 270, "ES8311 codec, I2S master"),
    "C15": (28.8, 28.2, 270, "MIC_OUT DC block, pad 1 toward MK1"),
    "C16": (28.8, 31.3, 270, "MIC_N reference"),
    "C10": (28.8, 34.4, 270, "VMID"),
    "C13": (21.6, 33.9, 180, "3V3A decoupling at the codec"),
    "C12": (25.1, 34.2, 270, "DACVREF"),
    "C11": (26.7, 34.2, 270, "ADCVREF"),
    "Ragnd": (-14.0, 29.5, 0, "AGND to GND stitch, under the pouch outline on F.Cu, east of the analog island"),
    # West of the 51.5 mm pouch (x <= -25.75). A 1.0 mm-tall can will not fit
    # under the tape outline.
    "Y1": (27.2, 23.0, 180, "12.288 MHz oscillator into ES8311 MCLK"),
    # --- Analog island: analog supply ---
    "U8": (17.5, 30.8, 0, "LP5907-2.8 low-noise LDO, VSYS -> 2.8 V analog (net 3V3A)"),
    "C9": (12.4, 29.8, 180, "3V3A output cap, east of U8, north of the 7.7 mm pogo body"),
    # West of the pouch tape outline (x < -26 with the 1 mm keepout).
    "R5": (27.5, 7.1, 90, "I2C SDA pull-up"),
    "R6": (27.5, 10.5, 90, "I2C SCL pull-up"),
    # --- Battery ---
    # BT1 is two SMT solder pads for the pouch pigtail on B.Cu, west of J2
    # and just north of the 66 mm cell. Flip to the back after placing; rot
    # 0 keeps pad 1 west. USB-C J2 is the only 5 V inlet; VSYS
    # stays up with BT1 open.
    "BT1": (-17.0, 35.0, 0, "B.Cu pouch pigtail pads, pad 1 VBAT (west), pad 2 GND"),
    "C20": (-25.5, 29.4, 90, "VBAT bulk at the pouch pads"),
}

# JLCPCB's SMT line places surface-mount parts only. BT1 is two bare pads
# the pigtail is hand-soldered to and the TP_* parts are bare test pads:
# nothing to place, nothing to buy, nothing in the extra-parts bag.
_BARE_PADS = {
    "BT1": "pouch pigtail solder pads, hand-soldered at assembly",
    "TP_3V3": "bare test pad",
    "TP_GND": "bare test pad",
    "TP_EN": "bare test pad",
    "TP_BOOT": "bare test pad",
}
NO_PICK_AND_PLACE = dict(_BARE_PADS)
NO_BOM = dict(_BARE_PADS)
# Flipped after place so pad 1 (VBAT) stays west. See apply_hollow_tray.py.
BOTTOM = {"BT1"}

# 3.5 mm in from both edges, where params.json hole_inset_mm and the lid
# standoffs put them.
MOUNTING_HOLES = [
    ("H1", 26.3, 39.3),
    ("H2", -26.3, 39.3),
    ("H3", 26.3, -39.3),
    ("H4", -26.3, -39.3),
]

# 4-layer 0.8 mm build. Copper and dielectric numbers are baked into STACKUP
# in this file: 0.035 outer, 0.1 prepreg, 0.017 inner, 0.53 mm core.
# 0.035 + 0.1 + 0.017 + 0.53 + 0.017 + 0.1 + 0.035 = 0.834 mm, which lands on
# the 0.8 mm nominal every quick-turn fab quotes.
STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.017))
\t\t\t(layer "dielectric 2" (type "core") (thickness 0.53) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.017))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(copper_finish "OSP")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def load_netlist():
    text = open(NETLIST, encoding="utf-8").read()

    comp_re = re.compile(
        r'\(comp\s*\(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*\(footprint "([^"]*)"\)',
        re.S,
    )
    sheet_re = re.compile(r'\(name "Sheetname"\)\s*\(value "([^"]*)"\)', re.S)
    comps = []
    for m in comp_re.finditer(text):
        tail = text[m.end() : m.end() + 2000]
        sm = sheet_re.search(tail)
        comps.append(
            {
                "ref": m.group(1),
                "value": m.group(2),
                "footprint": m.group(3),
                "sheet": sm.group(1) if sm else "",
            }
        )

    body = text[text.find("(nets") :]
    net_re = re.compile(r'\(net\s*\(code "(\d+)"\)\s*\(name "([^"]*)"\)', re.S)
    node_re = re.compile(r'\(node\s*\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', re.S)
    hits = list(net_re.finditer(body))
    nets = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
        nets[m.group(2)] = [
            (n.group(1), n.group(2))
            for n in node_re.finditer(body[m.end() : end])
        ]
    return comps, nets


def vec(x_mm, y_mm):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))


# J2's footprint carries the three inner sides of its board slot on Edge.Cuts;
# the outline leaves the mouth open between these x values on y = -half_h.
USBC_SLOT_X = (7.0 - 4.62, 7.0 + 4.62)


def add_outline(board, half_w, half_h):
    for a, b in [
        ((-half_w, -half_h), (USBC_SLOT_X[0], -half_h)),
        ((USBC_SLOT_X[1], -half_h), (half_w, -half_h)),
        ((half_w, -half_h), (half_w, half_h)),
        ((half_w, half_h), (-half_w, half_h)),
        ((-half_w, half_h), (-half_w, -half_h)),
    ]:
        seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(vec(*a))
        seg.SetEnd(vec(*b))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(pcbnew.FromMM(0.05))
        board.Add(seg)


def add_circle(board, radius, layer, width):
    """Add a circle centred on the origin.

    The stroke is left solid here and switched to dashed in
    patch_saved_board; the LINE_STYLE enum is not exported by SWIG.
    """
    c = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE)
    c.SetStart(vec(0, 0))
    c.SetEnd(vec(radius, 0))
    c.SetLayer(layer)
    c.SetWidth(pcbnew.FromMM(width))
    c.SetFilled(False)
    board.Add(c)


def add_text(board, message, x_mm, y_mm, layer, size=1.2):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(message)
    t.SetPosition(vec(x_mm, y_mm))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(size / 8.0))
    board.Add(t)


def resolve_footprint(fpid):
    """Return (loaded FOOTPRINT, placed fpid, substitution note or None)."""
    placed, note = SUBSTITUTIONS.get(fpid, (fpid, None))
    lib, name = placed.split(":", 1)
    libdir = LOCAL_FP if lib == "PSV" else os.path.join(SYS_FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(libdir, name)
    if fp is None:
        raise SystemExit(f"could not load footprint {placed} from {libdir}")
    # FootprintLoad takes a directory, so what comes back is stamped with the
    # bare name. Leaving it that way makes every footprint on the board look
    # like a different part from the one the schematic asked for, which is 57
    # footprint_symbol_mismatch hits under kicad-cli pcb drc --schematic-parity.
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp, placed, note


def main():
    params = json.load(open(PARAMS, encoding="utf-8"))
    pcb = params["pcb"]
    half_w = pcb["width_mm"] / 2.0
    half_h = pcb["height_mm"] / 2.0
    ring_od = params["magnet"]["od_mm"]
    ring_id = params["magnet"]["id_mm"]

    comps, nets = load_netlist()
    by_ref = {c["ref"]: c for c in comps}

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(pcb["layers"])
    board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
    board.SetLayerName(pcbnew.In2_Cu, "In2.Cu")
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER)
    board.SetUserDefinedLayerCount(0)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(pcb["thickness_mm"]))

    add_outline(board, half_w, half_h)

    # Magnet ring: annulus that sits under the board on the phone side.
    add_circle(board, ring_od / 2.0, pcbnew.Cmts_User, 0.15)
    add_circle(board, ring_id / 2.0, pcbnew.Cmts_User, 0.15)
    add_circle(board, ring_od / 2.0, pcbnew.Eco1_User, 0.15)
    add_text(
        board,
        f"Pixelsnap ring OD {ring_od:g} / ID {ring_id:g} sits under B.Cu."
        " No tall parts on B.Cu inside this circle.",
        0,
        0,
        pcbnew.Cmts_User,
        size=1.4,
    )
    add_text(
        board,
        "B.Cu faces the phone. The pouch and BT1 sit on B.Cu; tall parts stay on F.Cu.",
        0,
        4,
        pcbnew.Cmts_User,
        size=1.4,
    )
    add_text(
        board,
        "In1.Cu = GND plane   In2.Cu = VDD33 plane",
        0,
        -4,
        pcbnew.Cmts_User,
        size=1.4,
    )

    # Nets.
    netmap = {}
    for name in sorted(nets):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netmap[name] = ni

    pad_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pad_net[(ref, pin)] = name

    placed_rows = []
    missing = []

    for ref, (x, y, rot, note) in PLACEMENT.items():
        comp = by_ref.get(ref)
        if comp is None:
            missing.append((ref, "not in netlist"))
            continue
        fp, placed_fpid, sub_note = resolve_footprint(comp["footprint"])
        fp.SetReference(ref)
        fp.SetValue(comp["value"])
        # generate_recorder.py writes Datasheet "~" on every symbol.
        # Library lands ship a URL or an empty field, and schematic-parity
        # flags the difference on every part.
        fp.SetField("Datasheet", "~")
        fp.SetPosition(vec(x, y))
        if rot:
            fp.SetOrientationDegrees(rot)
        if ref in BOTTOM:
            fp.Flip(fp.GetPosition(), False)
        fp.SetPath(pcbnew.KIID_PATH())
        fp.SetExcludedFromBOM(ref in NO_BOM)
        if ref in NO_PICK_AND_PLACE:
            fp.SetExcludedFromPosFiles(True)
        for pad in fp.Pads():
            name = pad_net.get((ref, pad.GetNumber()))
            if name and name in netmap:
                pad.SetNet(netmap[name])
        board.Add(fp)
        placed_rows.append(
            {
                "ref": ref,
                "value": comp["value"],
                "sheet": comp["sheet"],
                "x_mm": x,
                "y_mm": y,
                "rot_deg": round(fp.GetOrientationDegrees()) % 360,
                "layer": "B.Cu" if ref in BOTTOM else "F.Cu",
                "footprint": placed_fpid,
                "footprint_in_schematic": comp["footprint"],
                "substitution_reason": sub_note,
                "note": note,
            }
        )

    for ref in sorted(by_ref):
        if ref not in PLACEMENT:
            missing.append((ref, "no coordinate in PLACEMENT"))

    for ref, x, y in MOUNTING_HOLES:
        fp = pcbnew.FootprintLoad(LOCAL_FP, "MountingHole_1.7mm_M1.6")
        if fp is None:
            raise SystemExit("could not load PSV:MountingHole_1.7mm_M1.6")
        fp.SetFPID(pcbnew.LIB_ID("PSV", "MountingHole_1.7mm_M1.6"))
        fp.SetReference(ref)
        fp.SetValue("M1.6 NPTH")
        fp.SetPosition(vec(x, y))
        # The holes sit 3.5 mm in from two edges, so silk designators would be
        # clipped by the outline. The positions are in placement.json instead.
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)
        placed_rows.append(
            {
                "ref": ref,
                "value": "M1.6 NPTH",
                "sheet": "mechanical",
                "x_mm": x,
                "y_mm": y,
                "rot_deg": 0,
                "layer": "F.Cu",
                "footprint": "PSV:MountingHole_1.7mm_M1.6",
                "footprint_in_schematic": None,
                "substitution_reason": None,
                "note": "mechanical only, not in the schematic",
            }
        )

    tuck_reference_text(board, half_w, half_h)
    # The board is still in memory here, so hand its libraries over as extras;
    # fp_lib_table picks the schematic's up off disk by itself.
    write_fp_lib_table({fp.GetFPIDAsString().split(":")[0]
                        for fp in board.GetFootprints()})

    project_before = json.load(open(PROJECT, encoding="utf-8"))

    board.BuildListOfNets()
    pcbnew.SaveBoard(PCB_OUT, board)
    patch_saved_board(pcb)
    restore_project(project_before)

    payload = {
        "_comment": (
            "Generated by hardware/kicad/recorder/generate_pcb.py. Footprint "
            "XY for the recorder PCB; keep this file in sync with "
            "recorder.kicad_pcb. Origin is the magnet-ring (Pixelsnap) "
            "centre; +X phone right, +Y toward the camera bar. Coordinates "
            "are written verbatim into recorder.kicad_pcb, so the USB edge "
            "is y = -42.8. Re-running this script wipes copper. Edit both "
            "files when a part moves."
        ),
        "board": {
            "width_mm": pcb["width_mm"],
            "height_mm": pcb["height_mm"],
            "thickness_mm": pcb["thickness_mm"],
            "layers": ["F.Cu", "In1.Cu (GND)", "In2.Cu (VDD33)", "B.Cu"],
            "finish": pcb["finish"],
            "usb_diff_ohm": pcb["usb_diff_ohm"],
            "usb_signalling": pcb["usb_signalling"],
            "usb_diff_note": pcb["usb_diff_note"],
            "outline_rect_mm": [[-half_w, -half_h], [half_w, half_h]],
            "b_cu_faces_phone": True,
        },
        "magnet_keepout": {
            "od_mm": ring_od,
            "id_mm": ring_id,
            "layers": ["User.Comments", "User.Eco1"],
            "kind": "graphic annotation, not a DRC rule area",
            "note": (
                "Ring is an annulus from r=22 to r=28 about the origin, below "
                "B.Cu. Every analog part (MK1, U2, U8, Y1) is placed "
                "outside r=28."
            ),
        },
        "mounting_holes": {
            "drill_mm": params["mounting"]["hole_d_mm"],
            "screw": params["mounting"]["screw"],
            "plating": "NPTH",
            "plating_rationale": (
                "Non-plated. The shell is aluminium in the CNC version and a "
                "steel shunt sits directly under the board, so an unplated "
                "hole removes any path for the shell to touch board copper. "
                "Switch to PTH with a GND pad only if the shell is chosen as "
                "the chassis ground return."
            ),
            "positions_mm": [[x, y] for _, x, y in MOUNTING_HOLES],
        },
        "footprint_substitutions": {
            k: {"placed": v[0], "reason": v[1]} for k, v in SUBSTITUTIONS.items()
        },
        # This script only ever produces a bare placement, so the first two
        # items are always true right after it runs. route_pcb.py replaces
        # this whole list once it has poured and routed the board.
        "open_items": [
            "Not routed. This script writes placement only, so every net is "
            "still a ratsnest line. Run route_pcb.py next.",
            "No copper pours. In1.Cu (GND) and In2.Cu (VDD33) are named and in "
            "the stackup but carry no zones until route_pcb.py runs.",
            "MK1 sound port. The mic is on F.Cu and its port is an NPTH "
            "through the board at (27.5, 16.32), so the acoustic path opens "
            "on the B.Cu side, which faces the phone. The PETG tray ducts it "
            "out to the right wall; keep params.json mic_npth and case.scad "
            "in step if the mic ever moves.",
            "SW1 is a side-actuated Panasonic EVQP7C01P aimed at the "
            "phone-left wall, so the case aperture presses it directly and needs no "
            "lever. Its two 0.7 mm NPTH board guides take the sideways load "
            "instead of the solder joints.",
        ],
        "parts": sorted(placed_rows, key=lambda r: r["ref"]),
    }
    with open(PLACEMENT_OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")

    print(f"schematic parts: {len(comps)}")
    print(f"placed parts:    {len(placed_rows) - len(MOUNTING_HOLES)}")
    print(f"mounting holes:  {len(MOUNTING_HOLES)}")
    print(f"nets:            {len(nets)}")
    if missing:
        print("UNPLACED:")
        for ref, why in missing:
            print(f"  {ref}: {why}")
    else:
        print("every schematic part placed")
    print(f"wrote {PCB_OUT}")
    print(f"wrote {PLACEMENT_OUT}")


def restore_project(before):
    """Undo pcbnew's damage to the schematic half of the project file.

    pcbnew rewrites the whole .kicad_pro on save from BOARD defaults, which
    blanks the hierarchical sheet list and resets every DRC number. Put the
    schematic keys back verbatim and re-apply the fab policy.
    """
    after = json.load(open(PROJECT, encoding="utf-8"))
    for key in SCHEMATIC_OWNED_KEYS:
        if key in before:
            after[key] = before[key]
    with open(PROJECT, "w", encoding="utf-8") as fh:
        json.dump(after, fh, indent=2)
        fh.write("\n")
    apply_project_policy()


# JLCPCB prints two silkscreen classes. The standard font needs 1.0 mm
# characters on a 0.15 mm stroke; 0.8 mm is only legal on their high-precision
# line, and their capability table warns that anything under 1.0 mm "will be
# unidentifiable". This board is dense, so an earlier pass shrank every
# designator to 0.8 mm to win seats. That bought placement with illegible
# silk. Print at the standard 1.0 mm instead and let the seat search work
# harder; a designator nobody can read is not worth the space it saves.
SILK_HEIGHT = 1.0
SILK_STROKE = 0.15
SILK_GAP = 0.12

SILK_STEP = 0.25
SILK_REACH = 6.0


def _box_mm(box):
    return (pcbnew.ToMM(box.GetLeft()), pcbnew.ToMM(box.GetTop()),
            pcbnew.ToMM(box.GetRight()), pcbnew.ToMM(box.GetBottom()))


def _rects_overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _silk_obstacles(board):
    """Everything a front designator has to miss: pads and other silk.

    Tracks are deliberately absent. KiCad only reports silk over *exposed*
    copper, and everything but a pad is under solder mask.
    """
    rects = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if pad.IsOnLayer(pcbnew.F_Cu):
                rects.append(_box_mm(pad.GetBoundingBox()))
        for item in fp.GraphicalItems():
            if isinstance(item, pcbnew.PCB_SHAPE) and item.GetLayer() == pcbnew.F_SilkS:
                rects.append(_box_mm(item.GetBoundingBox()))
    return rects


def _silk_seats(cx, cy, half_fw, half_fh, half_tw, half_th):
    """Candidate label centres, nearest gap first.

    Radiating along eight compass lines leaves a part boxed in by its own
    neighbours with nowhere to go, so sweep a full ring instead and let the
    angular resolution grow with the radius.
    """
    seats = []
    reach = SILK_STEP
    while reach <= SILK_REACH:
        rx = half_fw + half_tw + SILK_GAP + reach
        ry = half_fh + half_th + SILK_GAP + reach
        steps = max(8, int(2 * math.pi * reach / SILK_STEP))
        for i in range(steps):
            theta = 2 * math.pi * i / steps
            seats.append((cx + rx * math.cos(theta), cy + ry * math.sin(theta)))
        reach += SILK_STEP
    return seats


def tuck_reference_text(board, half_w, half_h):
    """Shrink every front designator and park it somewhere legible.

    Library footprints put the reference above the part at 1.0 mm, which on
    this board put 29 of them over a neighbour's pad, over a neighbour's
    outline, or off the board edge. Each one is shrunk to the fab's minimum
    and then walked out from its footprint until it clears the pads, the
    other silk, and the designators already placed. Only the ones with
    nowhere to go are left overlapping.
    """
    obstacles = _silk_obstacles(board)
    homeless = []
    for fp in sorted(board.GetFootprints(),
                     key=lambda f: f.GetReference()):
        ref = fp.Reference()
        if not ref.IsVisible() or ref.GetLayer() != pcbnew.F_SilkS:
            continue
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(SILK_HEIGHT),
                                        pcbnew.FromMM(SILK_HEIGHT)))
        ref.SetTextThickness(pcbnew.FromMM(SILK_STROKE))
        x0, y0, x1, y1 = _box_mm(ref.GetBoundingBox())
        half_tw, half_th = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        fx0, fy0, fx1, fy1 = _box_mm(fp.GetBoundingBox(False, False))
        cx, cy = (fx0 + fx1) / 2.0, (fy0 + fy1) / 2.0

        seats = [(pcbnew.ToMM(ref.GetPosition().x),
                  pcbnew.ToMM(ref.GetPosition().y))]
        seats += _silk_seats(cx, cy, (fx1 - fx0) / 2.0, (fy1 - fy0) / 2.0,
                             half_tw, half_th)

        for sx, sy in seats:
            rect = (sx - half_tw, sy - half_th, sx + half_tw, sy + half_th)
            if (abs(rect[0]) > half_w - 0.4 or abs(rect[2]) > half_w - 0.4
                    or abs(rect[1]) > half_h - 0.4 or abs(rect[3]) > half_h - 0.4):
                continue
            if any(_rects_overlap(rect, other, SILK_GAP) for other in obstacles):
                continue
            ref.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(sx), pcbnew.FromMM(sy)))
            obstacles.append(rect)
            break
        else:
            homeless.append(fp.GetReference())
    if homeless:
        print(f"silk: no clear seat for {', '.join(homeless)}")
    return homeless


def dash_keepout_circles(text):
    """Draw the magnet-ring circles dashed so they never read as copper."""
    out = []
    cursor = 0
    for m in re.finditer(r"\(gr_circle\b", text):
        if m.start() < cursor:
            continue
        depth = 0
        for i in range(m.start(), len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        block = text[m.start() : end]
        if '"Cmts.User"' in block or '"Eco1.User"' in block:
            block = block.replace("(type default)", "(type dash)")
        out.append(text[cursor : m.start()])
        out.append(block)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def patch_saved_board(pcb):
    """Add what the SWIG API cannot: the stackup and the title block.

    pcbnew's Python bindings expose no writable stackup descriptor, so the
    physical layer numbers are injected into the saved file instead. The
    numbers are baked into STACKUP in this file (0.035/0.1/0.017/0.53).
    """
    text = open(PCB_OUT, encoding="utf-8").read()
    text = dash_keepout_circles(text)

    if "(stackup" not in text:
        m = re.search(r"^\t\(setup\n", text, re.M)
        text = text[: m.end()] + STACKUP + text[m.end() :]

    header = (
        '\t(title_block\n'
        '\t\t(title "pixel-snap-voice recorder")\n'
        '\t\t(comment 1 "4-layer 0.8 mm OSP. Origin = Pixelsnap magnet centre.")\n'
        f'\t\t(comment 2 "USB D+/D- is a tight pair, not impedance controlled: {pcb["usb_signalling"]}.")\n'
        '\t\t(comment 3 "First-pass placement from generate_pcb.py. Not routed.")\n'
        '\t)\n'
    )
    if "(title_block" not in text:
        m = re.search(r'^\t\(paper "A4"\)\n', text, re.M)
        text = text[: m.end()] + header + text[m.end() :]

    with open(PCB_OUT, "w", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
