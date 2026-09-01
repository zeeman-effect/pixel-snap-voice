#!/usr/bin/env python3
"""Prove the recorder schematic on the real KiCad artifact."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_SCH = HERE / "recorder.kicad_sch"
NETS_JSON = HERE / "nets_required.json"


def kicad_cli() -> Path:
    env = os.environ.get("KICAD_CLI")
    if env and Path(env).is_file():
        return Path(env)
    found = shutil.which("kicad-cli")
    if found:
        return Path(found)
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
    if local.is_file():
        return local
    pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
    if pf.is_file():
        return pf
    pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
    if pf86.is_file():
        return pf86
    return Path("kicad-cli")


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def check_fences() -> list[str]:
    errors: list[str] = []
    if HERE.name != "recorder":
        errors.append("verify must run from hardware/kicad/recorder")
    if "example_project" in HERE.parts:
        errors.append("refusing to operate on example_project")
    return errors


def check_mcu_value(sch_text: str) -> list[str]:
    if "ESP32-S3-MINI-1U-N8" not in sch_text:
        return ["U1 value ESP32-S3-MINI-1U-N8 missing from mcu_usb.kicad_sch"]
    return []


_NET_BLOCK = re.compile(
    r"\(net\s+\(code\s+\"[^\"]+\"\)\s+\(name\s+\"([^\"]+)\"\)([\s\S]*?)(?=\n\t\t\(net|\n\t\))",
)
_NODE = re.compile(r'\(ref\s+"([^"]+)"\)\s+\(pin\s+"([^"]+)"\)')
_WIRE = re.compile(r"\(wire\s+\(pts \(xy ([-\d.]+) ([-\d.]+)\) \(xy ([-\d.]+) ([-\d.]+)\)\)")
_LABEL = re.compile(r'\((?:global_label|label) "([^"]+)"[\s\S]*?\(at ([-\d.]+) ([-\d.]+) (\d+)\)')

MIN_STUB_MM = 5.08


def sheets() -> list[Path]:
    return sorted(p for p in HERE.glob("*.kicad_sch") if p != ROOT_SCH)


def labels(text: str) -> list[tuple[str, tuple[float, float], int]]:
    return [
        (name, (round(float(x), 2), round(float(y), 2)), int(rot))
        for name, x, y, rot in _LABEL.findall(text)
    ]


def wire_ends(text: str) -> dict[tuple[float, float], float]:
    longest: dict[tuple[float, float], float] = {}
    for a, b, c, d in _WIRE.findall(text):
        x1, y1, x2, y2 = float(a), float(b), float(c), float(d)
        span = max(abs(x2 - x1), abs(y2 - y1))
        for pt in ((round(x1, 2), round(y1, 2)), (round(x2, 2), round(y2, 2))):
            longest[pt] = max(longest.get(pt, 0.0), span)
    return longest


def clip(errors: list[str], keep: int = 6) -> list[str]:
    if len(errors) <= keep:
        return errors
    return errors[:keep] + [f"... and {len(errors) - keep} more"]


def check_label_stubs() -> list[str]:
    errors: list[str] = []
    for path in sheets():
        text = path.read_text(encoding="utf-8")
        ends = wire_ends(text)
        for name, pt, _rot in labels(text):
            span = ends.get(pt)
            if span is None:
                errors.append(f"{path.name}: label {name} at {pt} is not on a wire end")
            elif span < MIN_STUB_MM - 1e-6:
                errors.append(f"{path.name}: label {name} at {pt} sits on a {span:.2f} mm stub")
    return clip(errors)


def check_label_rotation() -> list[str]:
    errors: list[str] = []
    for path in sheets():
        text = path.read_text(encoding="utf-8")
        if not any(rot for _n, _pt, rot in labels(text)):
            errors.append(f"{path.name}: every label is at rotation 0")
    return errors


def check_labels_resolve(netlist: str) -> list[str]:
    nodes = net_nodes(netlist)
    missing: list[str] = []
    for path in sheets():
        for name, _pt, _rot in labels(path.read_text(encoding="utf-8")):
            if name not in nodes and f"{path.name}:{name}" not in missing:
                missing.append(f"{path.name}:{name}")
    return clip([f"label {m} names no net (shorted into a neighbour?)" for m in missing])


def net_nodes(netlist: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for m in _NET_BLOCK.finditer(netlist):
        name = m.group(1)
        nodes = {f"{ref}.{pin}" for ref, pin in _NODE.findall(m.group(2))}
        found[name] = nodes
        if "/" in name:
            found.setdefault(name.rsplit("/", 1)[-1], set()).update(nodes)
    return found


def check_netlist(netlist: str, required: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    nodes = net_nodes(netlist)
    for net, pins in required.items():
        have = nodes.get(net)
        if have is None:
            errors.append(f"net {net} missing from kicad-cli netlist")
            continue
        for pin in pins:
            if pin not in have:
                errors.append(f"net {net}: {pin} not a node")
    if "ESP32-S3-MINI-1U-N8" not in netlist:
        errors.append("MCU value ESP32-S3-MINI-1U-N8 not in netlist")
    return errors


def main() -> int:
    errors = check_fences()
    if not ROOT_SCH.is_file():
        errors.append(f"missing {ROOT_SCH}")
        print("VERIFY FAIL")
        for e in errors:
            print(" ", e)
        return 1

    mcu = (HERE / "mcu_usb.kicad_sch").read_text(encoding="utf-8")
    errors.extend(check_mcu_value(mcu))
    errors.extend(check_label_stubs())
    errors.extend(check_label_rotation())

    cli = str(kicad_cli())
    erc_rpt = HERE / "erc.rpt"
    erc = run(
        [
            cli,
            "sch",
            "erc",
            "--output",
            str(erc_rpt),
            "--format",
            "report",
            "--severity-error",
            "--exit-code-violations",
            str(ROOT_SCH),
        ]
    )
    if erc.returncode != 0:
        errors.append(f"kicad-cli sch erc failed ({erc.returncode})")
        if erc.stderr:
            errors.append(erc.stderr.strip()[:800])
        if erc_rpt.is_file():
            errors.append(erc_rpt.read_text(encoding="utf-8")[:2000])

    net_path = HERE / "recorder.net"
    nl = run(
        [
            cli,
            "sch",
            "export",
            "netlist",
            "--format",
            "kicadsexpr",
            "--output",
            str(net_path),
            str(ROOT_SCH),
        ]
    )
    if nl.returncode != 0:
        errors.append("kicad-cli netlist export failed")
        errors.append((nl.stderr or nl.stdout)[:800])
    else:
        netlist = net_path.read_text(encoding="utf-8")
        errors.extend(check_labels_resolve(netlist))
        if NETS_JSON.is_file():
            required = json.loads(NETS_JSON.read_text(encoding="utf-8"))
            errors.extend(check_netlist(netlist, required))

    if errors:
        print("VERIFY FAIL")
        for e in errors:
            print(" ", e)
        return 1
    print("verify_schematic: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
