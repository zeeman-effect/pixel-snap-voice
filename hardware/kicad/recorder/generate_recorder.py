#!/usr/bin/env python3
"""Emit a full KiCad 10 schematic for the v1 recorder.

Product schematic and PCB live in hardware/kicad/recorder/. Writes only
that directory. The old generated pixel_snap_voice tree is gone. Still
refuses example_project and leftover pixel_snap_voice* paths.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from fp_lib_table import write_fp_lib_table

HERE = Path(__file__).resolve().parent


def _system_symbol_dir() -> Path:
    """Where KiCad 10 keeps its shipped .kicad_sym files on this machine.

    This used to assume the Windows install path, so the script only ran on
    one laptop and died with a FileNotFoundError anywhere else.
    """
    env = os.environ.get("KICAD_SYMBOL_DIR")
    candidates = [Path(env)] if env else []
    candidates += [
        Path("/usr/share/kicad/symbols"),
        Path("/usr/local/share/kicad/symbols"),
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs" / "KiCad" / "10.0" / "share" / "kicad" / "symbols",
        Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols"),
    ]
    for path in candidates:
        if path.is_dir():
            return path
    raise SystemExit(
        "cannot find the KiCad 10 symbol libraries. Set KICAD_SYMBOL_DIR."
    )


KICAD_SYM = _system_symbol_dir()
SCH_VER = 20260306
ROOT_UUID = "a1b0c3d4-e5f6-4789-a012-3456789abcde"
STUB_MM = 7.62

NETS_REQUIRED = {
    "USB_DP": ["U1.24", "U7.1", "J2.A6"],
    "USB_DM": ["U1.23", "U7.3", "J2.A7"],
    "I2C_SDA": ["U1.8", "U2.19"],
    "I2C_SCL": ["U1.9", "U2.1"],
    "I2S_MCLK": ["U1.18", "U2.2", "Y1.3"],
    "I2S_BCLK": ["U1.17", "U2.6"],
    "I2S_WS": ["U1.16", "U2.8"],
    "I2S_DIN": ["U1.14", "U2.7"],
    "I2S_DOUT": ["U1.15", "U2.9"],
    "PA_EN": ["U1.12", "U6.1"],
    "VBUS": ["J2.A4", "F1.1"],
    "VBUS_CHG": ["F1.2", "U3.13", "U3.6", "U3.7"],
    "VBAT": ["U3.2", "BT1.1", "C21.1"],
    "VSYS": ["U3.10", "U4.1", "U8.1", "U6.6"],
    "VDD33": ["U5.1", "U1.3"],
    "3V3A": ["U8.5", "U2.11"],
    "GND": ["U1.1", "J2.A1", "BT1.2", "SW_BOOT.2", "SW_RST.2"],
    "BTN": ["U1.5", "SW1.1"],
    "BOOT": ["U1.4", "Rboot.2", "SW_BOOT.1"],
    "EN": ["U1.45", "R1.2", "C2.1", "SW_RST.1"],
    "LED": ["U1.6", "D1.1"],
    "CHG_STAT": ["U1.13", "U3.9"],
    "SD_CLK": ["U1.19", "J3.5"],
    "SD_CMD": ["U1.11", "J3.3"],
    "SD_D0": ["U1.10", "J3.7"],
    "SD_D1": ["U1.20", "J3.8"],
    "SD_D2": ["U1.21", "J3.1"],
    "SD_D3": ["U1.22", "J3.2"],
}


def uid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "psv-recorder:" + name))


def write_out(path: Path, text: str) -> None:
    resolved = path.resolve()
    if "example_project" in resolved.parts:
        raise RuntimeError(f"refusing to write {path}")
    if resolved.name.startswith("pixel_snap_voice"):
        raise RuntimeError(f"refusing to write {path}")
    if HERE.resolve() not in resolved.parents and resolved.parent != HERE.resolve():
        raise RuntimeError(f"refusing to write outside recorder/: {path}")
    path.write_text(text, encoding="utf-8", newline="\n")


_EMBEDDED_FONTS = re.compile(r"\s*\(embedded_fonts[\s\S]*?\)")


def split_top_symbols(block: str) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(block)
    while i < n:
        while i < n and block[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        if block[i] != "(":
            i += 1
            continue
        start = i
        depth = 0
        while i < n:
            if block[i] == "(":
                depth += 1
            elif block[i] == ")":
                depth -= 1
                if depth == 0:
                    out.append(block[start : i + 1])
                    i += 1
                    break
            i += 1
        else:
            raise RuntimeError("unclosed s-expr in symbol extract")
    return out


def top_symbol_name(block: str) -> str:
    m = re.search(r'\(symbol "([^"]+)"', block)
    if not m:
        raise ValueError("symbol block missing name")
    return m.group(1)


def prefix_lib_ids(block: str, lib_prefix: str) -> str:
    m = re.match(r'^(\s*\(symbol ")([^"]+)(")', block)
    if not m:
        raise ValueError("symbol header missing")
    name = m.group(2)
    if ":" not in name:
        block = f"{m.group(1)}{lib_prefix}:{name}{m.group(3)}{block[m.end() :]}"

    def _extends(mm: re.Match[str]) -> str:
        parent = mm.group(1)
        if ":" in parent:
            return mm.group(0)
        return f'(extends "{lib_prefix}:{parent}")'

    return re.sub(r'\(extends "([^"]+)"\)', _extends, block, count=1)


def extract_symbol(lib_file: Path, name: str) -> str:
    text = lib_file.read_text(encoding="utf-8")
    start = text.find(f'\t(symbol "{name}"')
    if start < 0:
        start = text.find(f'(symbol "{name}"')
    if start < 0:
        raise KeyError(f"{name} not in {lib_file}")
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                block = _EMBEDDED_FONTS.sub("", text[start : i + 1])
                parts = split_top_symbols(block)
                if len(parts) != 1:
                    raise RuntimeError(f"extract_symbol({name}) returned {len(parts)} symbols")
                return parts[0]
        i += 1
    raise RuntimeError(f"unclosed symbol {name}")


def parse_pins(block: str) -> dict[str, tuple[float, float, float]]:
    pins: dict[str, tuple[float, float, float]] = {}
    for m in re.finditer(
        r"\(pin \w+ line\s+\(at ([-\d.]+) ([-\d.]+) (\d+)\)[\s\S]*?\(number \"([^\"]+)\"",
        block,
    ):
        pins[m.group(4)] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return pins


def load_lib(lib_file: Path, name: str) -> tuple[str, dict[str, tuple[float, float, float]], str]:
    prefix = lib_file.stem
    block = prefix_lib_ids(extract_symbol(lib_file, name), prefix)
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:
        parent_name = ext.group(1).split(":")[-1]
        block = prefix_lib_ids(extract_symbol(lib_file, parent_name), prefix)
    return block, parse_pins(block), top_symbol_name(block)


class Sch:
    def __init__(self, title: str, paper: str = "A3") -> None:
        self.title = title
        self.paper = paper
        self.libs: list[str] = []
        self.body: list[str] = []
        self._seen: set[str] = set()

    def add_lib(self, block: str) -> None:
        for sym in split_top_symbols(block):
            key = top_symbol_name(sym)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.libs.append(sym)

    def add(self, chunk: str) -> None:
        self.body.append(chunk)

    def emit(self, path: Path, page: str, sch_uuid: str) -> None:
        libs = "\n".join(self.libs)
        body = "\n".join(self.body)
        write_out(
            path,
            f"""(kicad_sch
	(version {SCH_VER})
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{sch_uuid}")
	(paper "{self.paper}")
	(title_block
		(title "{self.title}")
		(date "2026-08-30")
		(rev "0")
	)
	(lib_symbols
{libs}
	)
{body}
	(sheet_instances
		(path "/"
			(page "{page}")
		)
	)
	(embedded_fonts no)
)
""",
        )


def inst(
    lib_id: str,
    ref: str,
    value: str,
    x: float,
    y: float,
    pins: dict[str, tuple[float, float, float]],
    footprint: str = "",
    rot: float = 0,
    mirror: str = "",
) -> str:
    pin_xml = "\n".join(
        f'\t\t(pin "{n}" (uuid "{uid(ref + "-p-" + n)}"))' for n in pins
    )
    mir = f"\t\t(mirror {mirror})\n" if mirror else ""
    return f"""	(symbol
		(lib_id "{lib_id}")
		(at {x:.2f} {y:.2f} {rot:.0f})
{mir}		(unit 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{uid("sym-" + ref)}")
		(property "Reference" "{ref}" (at {x:.2f} {y - 8:.2f} 0)
			(effects (font (size 1.27 1.27))))
		(property "Value" "{value}" (at {x:.2f} {y - 5.5:.2f} 0)
			(effects (font (size 1.27 1.27))))
		(property "Footprint" "{footprint}" (at {x:.2f} {y:.2f} 0)
			(effects (font (size 1.27 1.27)) hide))
		(property "Datasheet" "~" (at {x:.2f} {y:.2f} 0)
			(effects (font (size 1.27 1.27)) hide))
{pin_xml}
	)"""


def wire(x1: float, y1: float, x2: float, y2: float, name: str) -> str:
    return f"""	(wire
		(pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f}))
		(stroke (width 0) (type default))
		(uuid "{uid("w-" + name)}")
	)"""


def run(sch: Sch, ident: str, *points: tuple[float, float]) -> None:
    for i, (a, b) in enumerate(zip(points, points[1:])):
        sch.add(wire(a[0], a[1], b[0], b[1], f"{ident}-{i}"))


def label_rot(ldx: float, ldy: float) -> int:
    if ldx:
        return 0 if ldx > 0 else 180
    return 90 if ldy < 0 else 270


def _justify(rot: int) -> str:
    return "right" if rot in (180, 270) else "left"


def glabel(net: str, x: float, y: float, ident: str, rot: int = 0) -> str:
    return f"""	(global_label "{net}"
		(shape input)
		(at {x:.2f} {y:.2f} {rot})
		(effects (font (size 1.27 1.27)) (justify {_justify(rot)}))
		(uuid "{uid("g-" + ident + "-" + net)}")
	)"""


def label(net: str, x: float, y: float, ident: str, rot: int = 0) -> str:
    return f"""	(label "{net}"
		(at {x:.2f} {y:.2f} {rot})
		(effects (font (size 1.27 1.27)) (justify {_justify(rot)} bottom))
		(uuid "{uid("l-" + ident)}")
	)"""


def noconnect(x: float, y: float, ident: str) -> str:
    return f"""	(no_connect
		(at {x:.2f} {y:.2f})
		(uuid "{uid("nc-" + ident)}")
	)"""


def junction(x: float, y: float, ident: str) -> str:
    return f"""	(junction
		(at {x:.2f} {y:.2f})
		(diameter 0)
		(uuid "{uid("j-" + ident)}")
	)"""


def text(msg: str, x: float, y: float, ident: str) -> str:
    return f"""	(text "{msg}"
		(exclude_from_sim no)
		(at {x:.2f} {y:.2f} 0)
		(effects (font (size 2.0 2.0)) (justify left bottom))
		(uuid "{uid("t-" + ident)}")
	)"""


def _rot_vec(sx: float, sy: float, rot: float, mirror: str) -> tuple[float, float]:
    if mirror == "y":
        sx = -sx
    elif mirror == "x":
        sy = -sy
    r = int(rot) % 360
    if r == 90:
        sx, sy = -sy, sx
    elif r == 180:
        sx, sy = -sx, -sy
    elif r == 270:
        sx, sy = sy, -sx
    return sx, sy


def pin_xy(
    inst_x: float,
    inst_y: float,
    pins: dict[str, tuple[float, float, float]],
    number: str,
    rot: float = 0,
    mirror: str = "",
) -> tuple[float, float]:
    px, py, _prot = pins[number]
    px, py = _rot_vec(px, py, rot, mirror)
    return inst_x + px, inst_y - py


def pin_lead(
    pins: dict[str, tuple[float, float, float]],
    number: str,
    length: float = 2.54,
    rot: float = 0,
    mirror: str = "",
) -> tuple[float, float]:
    _px, _py, prot = pins[number]
    sx, sy = {0: (-1.0, 0.0), 90: (0.0, -1.0), 180: (1.0, 0.0), 270: (0.0, 1.0)}[int(prot) % 360]
    sx, sy = _rot_vec(sx, sy, rot, mirror)
    return sx * length, -sy * length


def stub(
    sch: Sch,
    inst_x: float,
    inst_y: float,
    pins: dict[str, tuple[float, float, float]],
    number: str,
    net: str,
    ident: str,
    global_net: bool = True,
    rot: float = 0,
    mirror: str = "",
    length: float = STUB_MM,
) -> tuple[float, float]:
    x, y = pin_xy(inst_x, inst_y, pins, number, rot=rot, mirror=mirror)
    ldx, ldy = pin_lead(pins, number, length, rot, mirror)
    end = (x + ldx, y + ldy)
    sch.add(wire(x, y, end[0], end[1], ident))
    lab = glabel if global_net else label
    sch.add(lab(net, end[0], end[1], ident, label_rot(ldx, ldy)))
    return end


def nc_pin(
    sch: Sch,
    inst_x: float,
    inst_y: float,
    pins: dict[str, tuple[float, float, float]],
    number: str,
    ident: str,
    rot: float = 0,
    mirror: str = "",
) -> None:
    x, y = pin_xy(inst_x, inst_y, pins, number, rot=rot, mirror=mirror)
    sch.add(noconnect(x, y, ident))


def nc_unused(
    sch: Sch,
    inst_x: float,
    inst_y: float,
    pins: dict[str, tuple[float, float, float]],
    used: set[str],
    prefix: str,
    rot: float = 0,
    mirror: str = "",
) -> None:
    stacked = {pin_xy(inst_x, inst_y, pins, n, rot=rot, mirror=mirror) for n in used if n in pins}
    for number in pins:
        if number in used:
            continue
        if pin_xy(inst_x, inst_y, pins, number, rot=rot, mirror=mirror) in stacked:
            continue
        nc_pin(sch, inst_x, inst_y, pins, number, f"{prefix}{number}", rot=rot, mirror=mirror)


def place_rail(
    sch: Sch,
    lib_id: str,
    ref: str,
    net: str,
    x: float,
    y: float,
    pins: dict[str, tuple[float, float, float]],
) -> tuple[float, float]:
    sch.add(inst(lib_id, ref, net, x, y, pins))
    return stub(sch, x, y, pins, "1", net, ref)


def pwr_flag(
    sch: Sch,
    ref: str,
    x: float,
    y: float,
    pins: dict[str, tuple[float, float, float]],
) -> None:
    # Value must stay PWR_FLAG, matching the library. The pin name is empty, so
    # KiCad does not turn that value into a net; the wired label (AGND, VBUS,
    # …) still owns the connection. A dummy value like "pwr" plus the library's
    # (power global) flag would merge every flag onto one net.
    sch.add(inst("power:PWR_FLAG", ref, "PWR_FLAG", x, y, pins))


def build() -> None:
    device_r, r_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "R")
    device_c, c_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "C")
    device_led, led_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "LED")
    device_fuse, fuse_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "Fuse")
    device_bat, bat_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "Battery")
    device_spk, spk_pins, _ = load_lib(KICAD_SYM / "Device.kicad_sym", "Speaker")
    sw_blk, sw_pins, _ = load_lib(KICAD_SYM / "Switch.kicad_sym", "SW_Push")
    conn4, conn4_pins, _ = load_lib(KICAD_SYM / "Connector_Generic.kicad_sym", "Conn_01x04")
    usb_blk, usb_pins, _ = load_lib(KICAD_SYM / "Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P")
    sd_blk, sd_pins, _ = load_lib(KICAD_SYM / "Connector.kicad_sym", "Micro_SD_Card")
    mcu_blk, mcu_pins, mcu_id = load_lib(KICAD_SYM / "RF_Module.kicad_sym", "ESP32-S3-MINI-1")
    chg_blk, chg_pins, chg_id = load_lib(HERE / "PSV.kicad_sym", "BQ24074RGT")
    ldo_blk, ldo_pins, ldo_id = load_lib(KICAD_SYM / "Regulator_Linear.kicad_sym", "AP2112K-3.3")
    ana_blk, ana_pins, ana_id = load_lib(KICAD_SYM / "Regulator_Linear.kicad_sym", "LP5907MFX-3.3")
    swi_blk, swi_pins, swi_id = load_lib(KICAD_SYM / "Power_Management.kicad_sym", "AP22804AW5")
    esd_blk, esd_pins, esd_id = load_lib(KICAD_SYM / "Power_Protection.kicad_sym", "USBLC6-2SC6")
    osc_blk, osc_pins, osc_id = load_lib(KICAD_SYM / "Oscillator.kicad_sym", "ASE-xxxMHz")
    gnd_blk, gnd_pins, _ = load_lib(KICAD_SYM / "power.kicad_sym", "GND")
    pflag_blk, pflag_pins, _ = load_lib(KICAD_SYM / "power.kicad_sym", "PWR_FLAG")
    vbus_blk, vbus_pins, _ = load_lib(KICAD_SYM / "power.kicad_sym", "VBUS")
    es_blk, es_pins, es_id = load_lib(HERE / "PSV.kicad_sym", "ES8311")
    pa_blk, pa_pins, pa_id = load_lib(HERE / "PSV.kicad_sym", "NS4150B")
    mic_blk, mic_pins, mic_id = load_lib(HERE / "PSV.kicad_sym", "IM73A135")
    vdd33_blk, vdd33_pins, _ = load_lib(HERE / "PSV.kicad_sym", "VDD33")
    vbat_blk, vbat_pins, _ = load_lib(HERE / "PSV.kicad_sym", "VBAT")
    a3v3_blk, a3v3_pins, _ = load_lib(HERE / "PSV.kicad_sym", "3V3A")
    vsys_blk, vsys_pins, _ = load_lib(HERE / "PSV.kicad_sym", "VSYS")

    mcu = Sch("Recorder — MCU / USB")
    for b in (mcu_blk, usb_blk, esd_blk, device_r, device_c, conn4, sw_blk, gnd_blk, vdd33_blk, vbus_blk):
        mcu.add_lib(b)
    ux, uy = 95.25, 114.30
    mcu.add(inst(mcu_id, "U1", "ESP32-S3-MINI-1U-N8", ux, uy, mcu_pins, "PSV:ESP32-S3-MINI-1U"))
    mcu.add(text("ESP32-S3-MINI-1U-N8. IPEX unused. S3 is I2S slave.", 25, 20, "mcu-h"))

    stub(mcu, ux, uy, mcu_pins, "3", "VDD33", "mcu-3v3")
    stub(mcu, ux, uy, mcu_pins, "1", "GND", "mcu-gnd")
    stub(mcu, ux, uy, mcu_pins, "45", "EN", "mcu-en", False)
    stub(mcu, ux, uy, mcu_pins, "4", "BOOT", "mcu-boot", False)
    stub(mcu, ux, uy, mcu_pins, "5", "BTN", "mcu-btn")
    stub(mcu, ux, uy, mcu_pins, "6", "LED", "mcu-led")
    stub(mcu, ux, uy, mcu_pins, "8", "I2C_SDA", "mcu-sda")
    stub(mcu, ux, uy, mcu_pins, "9", "I2C_SCL", "mcu-scl")
    stub(mcu, ux, uy, mcu_pins, "10", "SD_D0", "mcu-d0")
    stub(mcu, ux, uy, mcu_pins, "11", "SD_CMD", "mcu-cmd")
    stub(mcu, ux, uy, mcu_pins, "12", "PA_EN", "mcu-pa")
    stub(mcu, ux, uy, mcu_pins, "13", "CHG_STAT", "mcu-stat")
    stub(mcu, ux, uy, mcu_pins, "14", "I2S_DIN", "mcu-din")
    stub(mcu, ux, uy, mcu_pins, "15", "I2S_DOUT", "mcu-dout")
    stub(mcu, ux, uy, mcu_pins, "16", "I2S_WS", "mcu-ws")
    stub(mcu, ux, uy, mcu_pins, "17", "I2S_BCLK", "mcu-bclk")
    stub(mcu, ux, uy, mcu_pins, "18", "I2S_MCLK", "mcu-mclk")
    stub(mcu, ux, uy, mcu_pins, "19", "SD_CLK", "mcu-clk")
    stub(mcu, ux, uy, mcu_pins, "20", "SD_D1", "mcu-d1")
    stub(mcu, ux, uy, mcu_pins, "21", "SD_D2", "mcu-d2")
    stub(mcu, ux, uy, mcu_pins, "22", "SD_D3", "mcu-d3")
    dm_end = stub(mcu, ux, uy, mcu_pins, "23", "USB_DM", "mcu-dm")
    dp_end = stub(mcu, ux, uy, mcu_pins, "24", "USB_DP", "mcu-dp")
    stub(mcu, ux, uy, mcu_pins, "39", "UART_TX", "mcu-tx", False)
    stub(mcu, ux, uy, mcu_pins, "40", "UART_RX", "mcu-rx", False)
    nc_unused(
        mcu,
        ux,
        uy,
        mcu_pins,
        {
            "1",
            "3",
            "4",
            "5",
            "6",
            "8",
            "9",
            "10",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "17",
            "18",
            "19",
            "20",
            "21",
            "22",
            "23",
            "24",
            "39",
            "40",
            "45",
        },
        "mcu-nc-",
    )

    mcu.add(inst("Device:R", "R1", "10k", 45, 135.4, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
    mcu.add(inst("Device:C", "C2", "1uF", 45, 152.4, c_pins, "Capacitor_SMD:C_0603_1608Metric", rot=90))
    mcu.add(inst("Device:R", "Rboot", "10k", 45, 119.38, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
    mcu.add(inst("Device:C", "C1", "22uF", 95.25, 55, c_pins, "Capacitor_SMD:C_0805_2012Metric"))
    mcu.add(inst("Device:C", "C3", "100nF", 110, 55, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(mcu, 45, 135.4, r_pins, "1", "VDD33", "ren-v", rot=90)
    stub(mcu, 45, 135.4, r_pins, "2", "EN", "ren-en", False, rot=90)
    stub(mcu, 45, 152.4, c_pins, "1", "EN", "cen-en", False, rot=90)
    stub(mcu, 45, 152.4, c_pins, "2", "GND", "cen-gnd", rot=90)
    stub(mcu, 45, 119.38, r_pins, "1", "VDD33", "rboot-v", rot=90)
    stub(mcu, 45, 119.38, r_pins, "2", "BOOT", "rboot-b", False, rot=90)
    # Prototype download buttons. Same local BOOT / EN nets as the pull-ups.
    # Hold Boot, tap Reset, release Boot. Not firmware GPIOs.
    mcu.add(inst("Switch:SW_Push", "SW_BOOT", "boot", 70, 119.38, sw_pins, "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"))
    stub(mcu, 70, 119.38, sw_pins, "1", "BOOT", "swboot-b", False)
    stub(mcu, 70, 119.38, sw_pins, "2", "GND", "swboot-g")
    mcu.add(inst("Switch:SW_Push", "SW_RST", "reset", 70, 135.4, sw_pins, "Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A"))
    stub(mcu, 70, 135.4, sw_pins, "1", "EN", "swrst-en", False)
    stub(mcu, 70, 135.4, sw_pins, "2", "GND", "swrst-g")
    mcu.add(text("Hold Boot, tap Reset, release Boot to enter download mode.", 52, 108, "boot-note"))
    stub(mcu, 95.25, 55, c_pins, "1", "VDD33", "c1-v")
    stub(mcu, 95.25, 55, c_pins, "2", "GND", "c1-g")
    stub(mcu, 110, 55, c_pins, "1", "VDD33", "c3-v")
    stub(mcu, 110, 55, c_pins, "2", "GND", "c3-g")

    jx, jy = 250, 90
    mcu.add(inst("Connector:USB_C_Receptacle_USB2.0_16P", "J2", "USB_C_16P", jx, jy, usb_pins, "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", mirror="y"))
    j2_used = set()
    j2_end: dict[str, tuple[float, float]] = {}
    for num, net, ident in (
        ("A4", "VBUS", "j2-a4"),
        ("A9", "VBUS", "j2-a9"),
        ("B4", "VBUS", "j2-b4"),
        ("B9", "VBUS", "j2-b9"),
        ("A5", "CC1", "j2-cc1"),
        ("B5", "CC2", "j2-cc2"),
        ("A6", "USB_DP", "j2-a6"),
        ("B6", "USB_DP", "j2-b6"),
        ("A7", "USB_DM", "j2-a7"),
        ("B7", "USB_DM", "j2-b7"),
        ("A1", "GND", "j2-a1"),
        ("A12", "GND", "j2-a12"),
        ("B1", "GND", "j2-b1"),
        ("B12", "GND", "j2-b12"),
        # The shell was a no-connect, which left the four retention tabs on a
        # placeholder net that DRC then wanted joined to each other. Grounding
        # it is what the shell wants anyway: it is the return path for the
        # cable braid, and the tabs are the connector's mechanical anchors.
        ("SH", "GND", "j2-sh"),
    ):
        if num in usb_pins:
            j2_end[num] = stub(mcu, jx, jy, usb_pins, num, net, ident, mirror="y")
            j2_used.add(num)
    nc_unused(mcu, jx, jy, usb_pins, j2_used, "j2-nc-", mirror="y")

    ex, ey = 190, 70
    mcu.add(inst(esd_id, "U7", "USBLC6-2SC6", ex, ey, esd_pins, "Package_TO_SOT_SMD:SOT-23-6"))
    stub(mcu, ex, ey, esd_pins, "5", "VBUS", "esd-v")
    stub(mcu, ex, ey, esd_pins, "2", "GND", "esd-g")

    dp_line, dm_line = ey, ey + 2.54
    run(mcu, "dp-j2", j2_end["A6"], (214.44, j2_end["A6"][1]), (214.44, dp_line), pin_xy(ex, ey, esd_pins, "6"))
    run(mcu, "dp-u1", pin_xy(ex, ey, esd_pins, "1"), (137.16, dp_line), (137.16, dp_end[1]), dp_end)
    run(mcu, "dm-j2", j2_end["A7"], (219.52, j2_end["A7"][1]), (219.52, dm_line), pin_xy(ex, ey, esd_pins, "4"))
    run(mcu, "dm-u1", pin_xy(ex, ey, esd_pins, "3"), (127.00, dm_line), (127.00, dm_end[1]), dm_end)

    mcu.add(inst("Device:R", "R2", "5.11k", 250, 140, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    mcu.add(inst("Device:R", "R3", "5.11k", 270, 140, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(mcu, 250, 140, r_pins, "1", "CC1", "r2-cc")
    stub(mcu, 250, 140, r_pins, "2", "GND", "r2-g")
    stub(mcu, 270, 140, r_pins, "1", "CC2", "r3-cc")
    stub(mcu, 270, 140, r_pins, "2", "GND", "r3-g")

    mcu.add(inst("Connector_Generic:Conn_01x04", "J1", "UART0", 160, 175, conn4_pins, "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"))
    stub(mcu, 160, 175, conn4_pins, "1", "VDD33", "uart-v")
    stub(mcu, 160, 175, conn4_pins, "2", "UART_RX", "uart-rx", False)
    stub(mcu, 160, 175, conn4_pins, "3", "UART_TX", "uart-tx", False)
    stub(mcu, 160, 175, conn4_pins, "4", "GND", "uart-g")
    mcu.add(text("J1: 3V3, U0RXD (adapter TX), U0TXD (adapter RX), GND", 25, 200, "uart-note"))

    place_rail(mcu, "power:GND", "#PWR01", "GND", 40, 180, gnd_pins)
    place_rail(mcu, "PSV:VDD33", "#PWR02", "VDD33", 40, 40, vdd33_pins)
    place_rail(mcu, "power:VBUS", "#PWR03", "VBUS", 220, 40, vbus_pins)
    mcu.emit(HERE / "mcu_usb.kicad_sch", "2", uid("sch-mcu"))

    aud = Sch("Recorder — Audio")
    for b in (es_blk, pa_blk, mic_blk, osc_blk, device_r, device_c, device_spk, gnd_blk, pflag_blk, a3v3_blk, vbat_blk, vsys_blk):
        aud.add_lib(b)
    aud.add(text("ES8311 is I2S master. 12.288 MHz oscillator drives MCLK. No XI/XO on this codec.", 20, 18, "aud-h"))
    ax, ay = 90, 90
    aud.add(inst(es_id, "U2", "ES8311", ax, ay, es_pins, "Package_DFN_QFN:QFN-20-1EP_3x3mm_P0.4mm_EP1.65x1.65mm"))
    stub(aud, ax, ay, es_pins, "1", "I2C_SCL", "es-scl")
    stub(aud, ax, ay, es_pins, "19", "I2C_SDA", "es-sda")
    stub(aud, ax, ay, es_pins, "20", "VDD33", "es-ce")
    stub(aud, ax, ay, es_pins, "2", "I2S_MCLK", "es-mclk")
    stub(aud, ax, ay, es_pins, "6", "I2S_BCLK", "es-bclk")
    stub(aud, ax, ay, es_pins, "8", "I2S_WS", "es-ws")
    stub(aud, ax, ay, es_pins, "7", "I2S_DIN", "es-asd")
    stub(aud, ax, ay, es_pins, "9", "I2S_DOUT", "es-dsd")
    stub(aud, ax, ay, es_pins, "3", "VDD33", "es-pv")
    stub(aud, ax, ay, es_pins, "4", "VDD33", "es-dv")
    stub(aud, ax, ay, es_pins, "11", "3V3A", "es-av")
    stub(aud, ax, ay, es_pins, "5", "GND", "es-dg")
    stub(aud, ax, ay, es_pins, "10", "AGND", "es-ag", False)
    # Pad 21 is the QFN exposed pad. It is the codec's analog return, so it
    # belongs on AGND in the netlist, not only on the board.
    stub(aud, ax, ay, es_pins, "21", "AGND", "es-ep", False)
    stub(aud, ax, ay, es_pins, "12", "AOUTP", "es-op", False)
    stub(aud, ax, ay, es_pins, "13", "AOUTN", "es-on", False)
    stub(aud, ax, ay, es_pins, "18", "MIC_P", "es-mp")
    stub(aud, ax, ay, es_pins, "17", "MIC_N", "es-mn", False)

    aud.add(inst("Device:C", "C10", "1uF", 130, 140, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    aud.add(inst("Device:C", "C11", "1uF", 145, 140, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    aud.add(inst("Device:C", "C12", "1uF", 160, 140, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(aud, 130, 140, c_pins, "1", "VMID", "c10", False)
    stub(aud, 130, 140, c_pins, "2", "AGND", "c10g", False)
    stub(aud, 145, 140, c_pins, "1", "ADCVREF", "c11", False)
    stub(aud, 145, 140, c_pins, "2", "AGND", "c11g", False)
    stub(aud, 160, 140, c_pins, "1", "DACVREF", "c12", False)
    stub(aud, 160, 140, c_pins, "2", "AGND", "c12g", False)
    stub(aud, ax, ay, es_pins, "16", "VMID", "es-vmid", False)
    stub(aud, ax, ay, es_pins, "15", "ADCVREF", "es-aref", False)
    stub(aud, ax, ay, es_pins, "14", "DACVREF", "es-dref", False)

    aud.add(inst("Device:C", "C13", "1uF", 55, 50, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    aud.add(inst("Device:C", "C14", "100nF", 70, 50, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(aud, 55, 50, c_pins, "1", "3V3A", "c13a")
    stub(aud, 55, 50, c_pins, "2", "AGND", "c13g", False)
    stub(aud, 70, 50, c_pins, "1", "VDD33", "c14v")
    stub(aud, 70, 50, c_pins, "2", "GND", "c14g")

    aud.add(inst("Device:R", "R5", "4.7k", 40, 80, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
    aud.add(inst("Device:R", "R6", "4.7k", 40, 95, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
    stub(aud, 40, 80, r_pins, "1", "VDD33", "r5v", rot=90)
    stub(aud, 40, 80, r_pins, "2", "I2C_SDA", "r5d", rot=90)
    stub(aud, 40, 95, r_pins, "1", "VDD33", "r6v", rot=90)
    stub(aud, 40, 95, r_pins, "2", "I2C_SCL", "r6c", rot=90)

    aud.add(inst(osc_id, "Y1", "12.288MHz", 90, 160, osc_pins, "Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm"))
    stub(aud, 90, 160, osc_pins, "1", "3V3A", "y1en")
    stub(aud, 90, 160, osc_pins, "2", "GND", "y1g")
    stub(aud, 90, 160, osc_pins, "3", "I2S_MCLK", "y1out")
    stub(aud, 90, 160, osc_pins, "4", "3V3A", "y1v")

    aud.add(inst(mic_id, "MK1", "IM73A135", 40, 175, mic_pins, "PSV:IM73A135_PG-LLGA-5-3"))
    stub(aud, 40, 175, mic_pins, "1", "MIC_OUT", "mk-out", False)
    stub(aud, 40, 175, mic_pins, "2", "3V3A", "mk-v")
    stub(aud, 40, 175, mic_pins, "3", "AGND", "mk-g", False)
    stub(aud, 40, 175, mic_pins, "5", "AGND", "mk-g5", False)
    stub(aud, 40, 175, mic_pins, "4", "AGND", "mk-sel", False)
    aud.add(inst("Device:C", "C15", "1uF", 70, 175, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(aud, 70, 175, c_pins, "1", "MIC_OUT", "c15p", False)
    stub(aud, 70, 175, c_pins, "2", "MIC_P", "c15s")
    aud.add(inst("Device:C", "C16", "1uF", 55, 195, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(aud, 55, 195, c_pins, "1", "MIC_N", "c16n", False)
    stub(aud, 55, 195, c_pins, "2", "AGND", "c16g", False)

    aud.add(inst("Device:R", "Ragnd", "0R", 90, 200, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(aud, 90, 200, r_pins, "1", "AGND", "ag1", False)
    stub(aud, 90, 200, r_pins, "2", "GND", "ag2")

    px, py = 200, 90
    aud.add(inst(pa_id, "U6", "NS4150B", px, py, pa_pins, "Package_SO:MSOP-8_3x3mm_P0.65mm"))
    stub(aud, px, py, pa_pins, "1", "PA_EN", "pa-en")
    stub(aud, px, py, pa_pins, "2", "PA_BYP", "pa-byp", False)
    stub(aud, px, py, pa_pins, "3", "PA_INP", "pa-inp", False)
    stub(aud, px, py, pa_pins, "4", "PA_INN", "pa-inn", False)
    stub(aud, px, py, pa_pins, "6", "VSYS", "pa-v")
    stub(aud, px, py, pa_pins, "7", "GND", "pa-g")
    stub(aud, px, py, pa_pins, "8", "SPK_P", "pa-p", False)
    stub(aud, px, py, pa_pins, "5", "SPK_N", "pa-n", False)
    aud.add(inst("Device:C", "C17", "1uF", 165, 70, c_pins, "Capacitor_SMD:C_0603_1608Metric", rot=90))
    aud.add(inst("Device:R", "R7", "10k", 165, 85, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
    aud.add(inst("Device:C", "C18", "1uF", 165, 100, c_pins, "Capacitor_SMD:C_0603_1608Metric", rot=90))
    aud.add(inst("Device:C", "C19", "1uF", 165, 115, c_pins, "Capacitor_SMD:C_0603_1608Metric", rot=270))
    stub(aud, 165, 70, c_pins, "1", "AOUTP", "c17a", False, rot=90)
    stub(aud, 165, 70, c_pins, "2", "PA_INP", "c17b", False, rot=90)
    stub(aud, 165, 85, r_pins, "1", "PA_INP", "r7a", False, rot=90)
    stub(aud, 165, 85, r_pins, "2", "GND", "r7b", rot=90)
    stub(aud, 165, 100, c_pins, "1", "AOUTN", "c18a", False, rot=90)
    stub(aud, 165, 100, c_pins, "2", "PA_INN", "c18b", False, rot=90)
    stub(aud, 165, 115, c_pins, "1", "PA_BYP", "c19a", False, rot=270)
    stub(aud, 165, 115, c_pins, "2", "GND", "c19b", rot=270)

    aud.add(inst("Device:Speaker", "SP1", "KLJ-01304T-08R07W", 250, 90, spk_pins, "PSV:Speaker_KLJ-01304T"))
    stub(aud, 250, 90, spk_pins, "1", "SPK_P", "sp1p", False)
    stub(aud, 250, 90, spk_pins, "2", "SPK_N", "sp1n", False)
    aud.add(inst("Device:C", "C20", "10uF", 220, 55, c_pins, "Capacitor_SMD:C_0805_2012Metric"))
    stub(aud, 220, 55, c_pins, "1", "VBAT", "c20v")
    stub(aud, 220, 55, c_pins, "2", "GND", "c20g")
    place_rail(aud, "power:GND", "#PWR10", "GND", 30, 210, gnd_pins)
    place_rail(aud, "PSV:3V3A", "#PWR11", "3V3A", 30, 35, a3v3_pins)
    place_rail(aud, "PSV:VBAT", "#PWR12", "VBAT", 220, 35, vbat_pins)
    place_rail(aud, "PSV:VSYS", "#PWR13", "VSYS", 250, 35, vsys_pins)
    pwr_flag(aud, "#FLG10", 105, 200, pflag_pins)
    stub(aud, 105, 200, pflag_pins, "1", "AGND", "flg-ag", False)
    aud.emit(HERE / "audio.kicad_sch", "3", uid("sch-aud"))

    pwr_s = Sch("Recorder — Power")
    for b in (
        chg_blk,
        ldo_blk,
        ana_blk,
        swi_blk,
        device_r,
        device_c,
        device_fuse,
        device_bat,
        device_led,
        gnd_blk,
        pflag_blk,
        vbus_blk,
        vdd33_blk,
        vbat_blk,
        vsys_blk,
        a3v3_blk,
    ):
        pwr_s.add_lib(b)
    pwr_s.add(text("USB-C 5V -> PTC -> BQ24074 IN. OUT is VSYS (loads). BAT is the pouch only.", 20, 12, "pwr-h"))
    pwr_s.add(text("USB runs the board with BT1 open. Do not strap VSYS to VBAT.", 20, 18, "pwr-h2"))
    fx, fy = 50, 50
    cx, cy = 80, 70
    u3x, u3y = 145, 95
    c5x, c5y = 195, 80
    btx, bty = 230, 92.54
    # Same 3x3 VQFN land as the ThermalVias variant, but without the 0.2 mm
    # EP drills. This board's hole floor is 0.3 mm (JLC preferred). A 0.6/0.3
    # barrel on the exposed pad is added in route_pcb.py.
    u3_fp = "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm"
    pwr_s.add(inst("Device:Fuse", "F1", "500mA PTC", fx, fy, fuse_pins, "Fuse:Fuse_0603_1608Metric"))
    pwr_s.add(inst("Device:C", "C4", "4.7uF", cx, cy, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    pwr_s.add(inst(chg_id, "U3", "BQ24074RGTR", u3x, u3y, chg_pins, u3_fp))
    pwr_s.add(inst("Device:C", "C5", "4.7uF", c5x, c5y, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    pwr_s.add(inst("Device:Battery", "BT1", "JST-PH 1S", btx, bty, bat_pins, "Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal"))

    vbus_rail = place_rail(pwr_s, "power:VBUS", "#PWR21", "VBUS", fx, 33.02, vbus_pins)
    pwr_flag(pwr_s, "#FLG02", fx, 33.02, pflag_pins)
    run(pwr_s, "vbus-f1", vbus_rail, pin_xy(fx, fy, fuse_pins, "1"))

    pwr_flag(pwr_s, "#FLG07", 70, 53.34, pflag_pins)
    stub(pwr_s, u3x, u3y, chg_pins, "13", "VBUS_CHG", "u3in")
    stub(pwr_s, u3x, u3y, chg_pins, "7", "VBUS_CHG", "u3en1")
    flg_chg = stub(pwr_s, 70, 53.34, pflag_pins, "1", "VBUS_CHG", "flg-vchg")
    chg_bus = 60.96
    run(pwr_s, "vchg-f1", pin_xy(fx, fy, fuse_pins, "2"), (fx, chg_bus), flg_chg)
    run(pwr_s, "vchg-c4", flg_chg, (cx, chg_bus), pin_xy(cx, cy, c_pins, "1"))
    pwr_s.add(junction(flg_chg[0], flg_chg[1], "vchg-flg"))
    pwr_s.add(junction(cx, chg_bus, "vchg-c4tap"))
    stub(pwr_s, cx, cy, c_pins, "2", "GND", "c4g")

    stub(pwr_s, u3x, u3y, chg_pins, "10", "VSYS", "u3out")
    stub(pwr_s, u3x, u3y, chg_pins, "2", "VBAT", "u3bat")
    nc_pin(pwr_s, u3x, u3y, chg_pins, "8", "u3pgood")
    stub(pwr_s, u3x, u3y, chg_pins, "17", "GND", "u3ep")
    stub(pwr_s, u3x, u3y, chg_pins, "9", "CHG_STAT", "u3s")
    stub(pwr_s, u3x, u3y, chg_pins, "4", "GND", "u3ce")
    stub(pwr_s, u3x, u3y, chg_pins, "5", "GND", "u3en2")
    stub(pwr_s, u3x, u3y, chg_pins, "16", "ISET", "u3iset", False)
    stub(pwr_s, u3x, u3y, chg_pins, "12", "ILIM", "u3ilim", False)
    stub(pwr_s, u3x, u3y, chg_pins, "14", "TMR", "u3tmr", False)
    stub(pwr_s, u3x, u3y, chg_pins, "1", "TS", "u3ts", False)
    stub(pwr_s, u3x, u3y, chg_pins, "15", "ITERM", "u3iterm", False)
    stub(pwr_s, c5x, c5y, c_pins, "1", "VSYS", "c5v")
    stub(pwr_s, c5x, c5y, c_pins, "2", "GND", "c5g")
    # Local BAT ceramic. C20 is 10 µF at the pouch, ~70 mm of edge copper from
    # U3 pins 2/3. USB-with-BT1-open has no cell to act as bulk, so this 10 µF
    # sits next to the QFN. TI wants 4.7–47 µF from BAT to VSS.
    c21x, c21y = 195, 110
    pwr_s.add(inst("Device:C", "C21", "10uF", c21x, c21y, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(pwr_s, c21x, c21y, c_pins, "1", "VBAT", "c21v")
    stub(pwr_s, c21x, c21y, c_pins, "2", "GND", "c21g")
    stub(pwr_s, btx, bty, bat_pins, "1", "VBAT", "bt1p")
    stub(pwr_s, btx, bty, bat_pins, "2", "GND", "bt1n")

    # USB500: EN1 high (tied to IN), EN2 low. ISET 1.8k ~ 494 mA (KISET/R).
    # ILIM 3.01k is the datasheet backup (~500 mA) if EN1/EN2 later select
    # ILIM mode. TS is 10k to GND: no pack NTC. ITERM 3.01k ~ 10 percent.
    pwr_s.add(inst("Device:R", "R4", "1.8k", 85, 115, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 85, 115, r_pins, "1", "ISET", "r4p", False)
    stub(pwr_s, 85, 115, r_pins, "2", "GND", "r4g")
    pwr_s.add(inst("Device:R", "R8", "3.01k", 85, 100, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 85, 100, r_pins, "1", "ILIM", "r8p", False)
    stub(pwr_s, 85, 100, r_pins, "2", "GND", "r8g")
    pwr_s.add(inst("Device:R", "R9", "49.9k", 85, 85, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 85, 85, r_pins, "1", "TMR", "r9p", False)
    stub(pwr_s, 85, 85, r_pins, "2", "GND", "r9g")
    pwr_s.add(inst("Device:R", "R10", "10k", 85, 70, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 85, 70, r_pins, "1", "TS", "r10p", False)
    stub(pwr_s, 85, 70, r_pins, "2", "GND", "r10g")
    pwr_s.add(inst("Device:R", "R11", "3.01k", 85, 55, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 85, 55, r_pins, "1", "ITERM", "r11p", False)
    stub(pwr_s, 85, 55, r_pins, "2", "GND", "r11g")

    pwr_s.add(inst("Device:LED", "D2", "chg", 195, 30, led_pins, "LED_SMD:LED_0603_1608Metric"))
    pwr_s.add(inst("Device:R", "Rchg", "1k", 215, 30, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 215, 30, r_pins, "1", "VBUS_CHG", "rchgv")
    stub(pwr_s, 215, 30, r_pins, "2", "CHG_LED", "rchgd", False)
    stub(pwr_s, 195, 30, led_pins, "1", "CHG_LED", "d2a", False)
    stub(pwr_s, 195, 30, led_pins, "2", "CHG_STAT", "d2k")
    pwr_s.add(inst("Device:R", "Rstat", "10k", 240, 30, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(pwr_s, 240, 30, r_pins, "1", "VDD33", "rstv")
    stub(pwr_s, 240, 30, r_pins, "2", "CHG_STAT", "rsts")

    pwr_s.add(inst(ldo_id, "U4", "AP2112K-3.3", 80, 150, ldo_pins, "Package_TO_SOT_SMD:SOT-23-5"))
    stub(pwr_s, 80, 150, ldo_pins, "1", "VSYS", "u4in")
    stub(pwr_s, 80, 150, ldo_pins, "2", "GND", "u4g")
    stub(pwr_s, 80, 150, ldo_pins, "3", "VSYS", "u4en")
    stub(pwr_s, 80, 150, ldo_pins, "5", "3V3_RAW", "u4out", False)
    nc_pin(pwr_s, 80, 150, ldo_pins, "4", "u4nc")
    pwr_s.add(inst("Device:C", "C6", "1uF", 50, 170, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    pwr_s.add(inst("Device:C", "C7", "2.2uF", 110, 170, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(pwr_s, 50, 170, c_pins, "1", "VSYS", "c6v")
    stub(pwr_s, 50, 170, c_pins, "2", "GND", "c6g")
    stub(pwr_s, 110, 170, c_pins, "1", "3V3_RAW", "c7v", False)
    stub(pwr_s, 110, 170, c_pins, "2", "GND", "c7g")

    pwr_s.add(inst(swi_id, "U5", "AP22804AW5", 150, 150, swi_pins, "Package_TO_SOT_SMD:SOT-23-5"))
    stub(pwr_s, 150, 150, swi_pins, "5", "3V3_RAW", "u5in", False)
    stub(pwr_s, 150, 150, swi_pins, "1", "VDD33", "u5out")
    stub(pwr_s, 150, 150, swi_pins, "2", "GND", "u5g")
    stub(pwr_s, 150, 150, swi_pins, "4", "3V3_RAW", "u5en", False)
    nc_pin(pwr_s, 150, 150, swi_pins, "3", "u5flg")
    pwr_s.add(inst("Device:C", "C8", "10uF", 185, 170, c_pins, "Capacitor_SMD:C_0805_2012Metric"))
    stub(pwr_s, 185, 170, c_pins, "1", "VDD33", "c8v")
    stub(pwr_s, 185, 170, c_pins, "2", "GND", "c8g")

    pwr_s.add(inst(ana_id, "U8", "LP5907MFX-3.3", 80, 205, ana_pins, "Package_TO_SOT_SMD:SOT-23-5"))
    stub(pwr_s, 80, 205, ana_pins, "1", "VSYS", "u8in")
    stub(pwr_s, 80, 205, ana_pins, "2", "GND", "u8g")
    stub(pwr_s, 80, 205, ana_pins, "3", "VDD33", "u8en")
    stub(pwr_s, 80, 205, ana_pins, "5", "3V3A", "u8out")
    nc_pin(pwr_s, 80, 205, ana_pins, "4", "u8nc")
    pwr_s.add(inst("Device:C", "C9", "1uF", 120, 205, c_pins, "Capacitor_SMD:C_0603_1608Metric"))
    stub(pwr_s, 120, 205, c_pins, "1", "3V3A", "c9v")
    stub(pwr_s, 120, 205, c_pins, "2", "GND", "c9g")

    place_rail(pwr_s, "power:GND", "#PWR20", "GND", 30, 230, gnd_pins)
    place_rail(pwr_s, "PSV:VBAT", "#PWR22", "VBAT", 230, 35, vbat_pins)
    place_rail(pwr_s, "PSV:VSYS", "#PWR25", "VSYS", 200, 35, vsys_pins)
    place_rail(pwr_s, "PSV:VDD33", "#PWR23", "VDD33", 250, 130, vdd33_pins)
    place_rail(pwr_s, "PSV:3V3A", "#PWR24", "3V3A", 150, 205, a3v3_pins)
    pwr_flag(pwr_s, "#FLG06", 30, 230, pflag_pins)
    pwr_s.emit(HERE / "power.kicad_sch", "4", uid("sch-pwr"))

    io = Sch("Recorder — IO")
    for b in (sd_blk, sw_blk, device_r, device_led, gnd_blk, vdd33_blk):
        io.add_lib(b)
    io.add(text("microSD 4-bit SDMMC, side-fire button, status LED. Pull-ups on CMD/DAT.", 20, 18, "io-h"))
    io.add(inst("Connector:Micro_SD_Card", "J3", "microSD", 80, 80, sd_pins, "Connector_Card:microSD_HC_Wuerth_693072010801"))
    stub(io, 80, 80, sd_pins, "1", "SD_D2", "sd-d2")
    stub(io, 80, 80, sd_pins, "2", "SD_D3", "sd-d3")
    stub(io, 80, 80, sd_pins, "3", "SD_CMD", "sd-cmd")
    stub(io, 80, 80, sd_pins, "4", "VDD33", "sd-v")
    stub(io, 80, 80, sd_pins, "5", "SD_CLK", "sd-clk")
    stub(io, 80, 80, sd_pins, "6", "GND", "sd-g")
    stub(io, 80, 80, sd_pins, "7", "SD_D0", "sd-d0")
    stub(io, 80, 80, sd_pins, "8", "SD_D1", "sd-d1")
    if "SH" in sd_pins:
        stub(io, 80, 80, sd_pins, "SH", "GND", "sd-sh")
    for i, net in enumerate(("SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3")):
        ref = f"Rsd{i}"
        io.add(inst("Device:R", ref, "10k", 150, 50 + i * 12.7, r_pins, "Resistor_SMD:R_0603_1608Metric", rot=90))
        stub(io, 150, 50 + i * 12.7, r_pins, "1", "VDD33", f"{ref}v", rot=90)
        stub(io, 150, 50 + i * 12.7, r_pins, "2", net, f"{ref}n", rot=90)

    # Side-actuated, not the top-actuated PTS645 this used to be. The record
    # button is on the left wall, so a top plunger needed a case lever to bend
    # a sideways press into a downward one. The EVQP7C01P presses straight
    # through the wall instead. Panasonic EVQP7 series, JLCPCB C388883.
    io.add(inst("Switch:SW_Push", "SW1", "record", 80, 160, sw_pins, "Button_Switch_SMD:SW_SPST_EVQP7C"))
    # Pin 1 carries BTN and pin 2 carries GND, which is the other way round
    # from the top-actuated part this replaced. A push button's two terminals
    # are interchangeable, and on the rotated side-actuated land pin 2 is the
    # row nearest the board edge with only 1.46 mm of copper to the cut.
    # Putting the plane net there lets the F.Cu GND pour reach it directly and
    # leaves BTN on the inner row, where it has room to leave the part.
    stub(io, 80, 160, sw_pins, "1", "BTN", "swb")
    stub(io, 80, 160, sw_pins, "2", "GND", "swg")
    io.add(inst("Device:LED", "D1", "status", 80, 190, led_pins, "LED_SMD:LED_0603_1608Metric"))
    io.add(inst("Device:R", "Rled", "1k", 110, 190, r_pins, "Resistor_SMD:R_0603_1608Metric"))
    stub(io, 80, 190, led_pins, "1", "LED", "d1a")
    stub(io, 80, 190, led_pins, "2", "LED_K", "d1k", False)
    stub(io, 110, 190, r_pins, "1", "LED_K", "rleda", False)
    stub(io, 110, 190, r_pins, "2", "GND", "rledg")
    place_rail(io, "power:GND", "#PWR30", "GND", 30, 210, gnd_pins)
    place_rail(io, "PSV:VDD33", "#PWR31", "VDD33", 30, 35, vdd33_pins)
    io.emit(HERE / "io.kicad_sch", "5", uid("sch-io"))

    root = Sch("Pixel Snap Voice — recorder", "A4")
    root.add(
        f"""	(sheet
		(at 25.40 30.48)
		(size 71.12 30.48)
		(stroke (width 0.1524) (type solid))
		(fill (color 0 0 0 0.0000))
		(uuid "{uid("sheet-mcu")}")
		(property "Sheetname" "MCU_USB" (at 26.40 29.00 0)
			(effects (font (size 1.27 1.27)) (justify left bottom)))
		(property "Sheetfile" "mcu_usb.kicad_sch" (at 26.40 62.00 0)
			(effects (font (size 1.27 1.27)) (justify left)))
		(instances
			(project "recorder"
				(path "/{ROOT_UUID}" (page "2"))
			)
		)
	)
	(sheet
		(at 110.00 30.48)
		(size 71.12 30.48)
		(stroke (width 0.1524) (type solid))
		(fill (color 0 0 0 0.0000))
		(uuid "{uid("sheet-aud")}")
		(property "Sheetname" "Audio" (at 111.00 29.00 0)
			(effects (font (size 1.27 1.27)) (justify left bottom)))
		(property "Sheetfile" "audio.kicad_sch" (at 111.00 62.00 0)
			(effects (font (size 1.27 1.27)) (justify left)))
		(instances
			(project "recorder"
				(path "/{ROOT_UUID}" (page "3"))
			)
		)
	)
	(sheet
		(at 25.40 80.00)
		(size 71.12 30.48)
		(stroke (width 0.1524) (type solid))
		(fill (color 0 0 0 0.0000))
		(uuid "{uid("sheet-pwr")}")
		(property "Sheetname" "Power" (at 26.40 78.50 0)
			(effects (font (size 1.27 1.27)) (justify left bottom)))
		(property "Sheetfile" "power.kicad_sch" (at 26.40 111.50 0)
			(effects (font (size 1.27 1.27)) (justify left)))
		(instances
			(project "recorder"
				(path "/{ROOT_UUID}" (page "4"))
			)
		)
	)
	(sheet
		(at 110.00 80.00)
		(size 71.12 30.48)
		(stroke (width 0.1524) (type solid))
		(fill (color 0 0 0 0.0000))
		(uuid "{uid("sheet-io")}")
		(property "Sheetname" "IO" (at 111.00 78.50 0)
			(effects (font (size 1.27 1.27)) (justify left bottom)))
		(property "Sheetfile" "io.kicad_sch" (at 111.00 111.50 0)
			(effects (font (size 1.27 1.27)) (justify left)))
		(instances
			(project "recorder"
				(path "/{ROOT_UUID}" (page "5"))
			)
		)
	)
	(text "Full product schematic. Global labels join sheets. Not the generated pixel_snap_voice board."
		(exclude_from_sim no)
		(at 25.40 20.00 0)
		(effects (font (size 2.0 2.0)) (justify left bottom))
		(uuid "{uid("t-root")}")
	)"""
    )
    write_out(
        HERE / "recorder.kicad_sch",
        f"""(kicad_sch
	(version {SCH_VER})
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{ROOT_UUID}")
	(paper "A4")
	(title_block
		(title "Pixel Snap Voice recorder")
		(date "2026-08-30")
		(rev "0")
	)
	(lib_symbols
	)
{chr(10).join(root.body)}
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(embedded_fonts no)
)
""",
    )

    write_out(HERE / "sym-lib-table", """(sym_lib_table
	(version 7)
	(lib (name "PSV")(type "KiCad")(uri "${KIPRJMOD}/PSV.kicad_sym")(options "")(descr "Recorder custom parts"))
)
""")
    # Not written inline. This used to be a hardcoded PSV-only table, which
    # deleted the thirteen stock-library rows generate_pcb.py had put there and
    # left every non-PSV land unresolvable. fp_lib_table rebuilds the whole set
    # from the sheets just written plus the board on disk, so running either
    # generator gives the same table.
    write_fp_lib_table()
    write_out(HERE / "nets_required.json", json.dumps(NETS_REQUIRED, indent=2) + "\n")

    # Only the schematic half of the project file belongs to this script. The
    # board half (design_settings, net_settings) is the PCB's DRC policy and
    # is what route_pcb.py and kicad-cli pcb drc read. Overwriting the whole
    # file here used to silently reset the board to KiCad defaults, which is
    # how the board ended up with a 0.2 mm minimum track width under a 0.15 mm
    # Default net class. Merge instead.
    pro_path = HERE / "recorder.kicad_pro"
    pro = json.loads(pro_path.read_text(encoding="utf-8")) if pro_path.is_file() else {}
    pro.setdefault("board", {"design_settings": {"defaults": {"board_outline_line_width": 0.05}}})
    pro.setdefault("boards", [])
    pro.setdefault("cvpcb", {"equivalence_files": []})
    pro.setdefault("libraries", {"pinned_footprint_libs": [], "pinned_symbol_libs": []})
    pro.setdefault(
        "net_settings",
        {
            "classes": [
                {"name": "Default", "clearance": 0.15, "track_width": 0.15, "via_diameter": 0.6, "via_drill": 0.3, "priority": -1}
            ],
            "meta": {"version": 5},
        },
    )
    pro["meta"] = {"filename": "recorder.kicad_pro", "version": 3}
    # Merge, for the same reason the board half is merged above: replacing the
    # block wholesale dropped bus_aliases and the legacy_lib_* keys that
    # Eeschema adds on save, so re-running this script dirtied the tree even
    # when the schematic had not changed.
    pro.setdefault("schematic", {}).update({
        "meta": {"version": 1},
        "top_level_sheets": [{"filename": "recorder.kicad_sch", "name": "Root", "uuid": ROOT_UUID}],
    })
    pro["sheets"] = [
        [ROOT_UUID, "Root"],
        [uid("sch-mcu"), "MCU_USB"],
        [uid("sch-aud"), "Audio"],
        [uid("sch-pwr"), "Power"],
        [uid("sch-io"), "IO"],
    ]
    pro.setdefault("text_variables", {})
    write_out(pro_path, json.dumps(pro, indent=2) + "\n")


if __name__ == "__main__":
    build()
    print("wrote hardware/kicad/recorder/")
