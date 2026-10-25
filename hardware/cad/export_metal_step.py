#!/usr/bin/env python3
"""Build hardware/cad/export/metal/tray.step from the live metal tray CSG.

OpenSCAD 2021.01 only writes mesh. JLCCNC quotes STEP. FreeCAD is not
installed here; CadQuery rebuilds the same CSG tree as B-rep (cylinders,
rounded hulls, cubes) and writes AP214 STEP. The 6061 tray stays on HOLD
until a Pixel 10 and a stuffed board are calipered.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq
import numpy as np

ROOT = Path(__file__).resolve().parent
CASE_SCAD = ROOT / "case.scad"
EXPORT = ROOT / "export" / "metal"
CSG_PATH = EXPORT / "tray.csg"
STEP_PATH = EXPORT / "tray.step"

OPENSCAD_CANDIDATES = (
    Path(r"C:\Program Files\OpenSCAD\openscad.exe"),
    Path("/usr/bin/openscad"),
    Path("/usr/local/bin/openscad"),
)


@dataclass
class Call:
    name: str
    args: dict[str, object] = field(default_factory=dict)
    children: list[Call] = field(default_factory=list)


class CsgParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0
        self.n = len(text)

    def peek(self) -> str:
        self._skip()
        return self.text[self.i] if self.i < self.n else ""

    def _skip(self) -> None:
        while self.i < self.n:
            ch = self.text[self.i]
            if ch.isspace():
                self.i += 1
                continue
            if self.text.startswith("//", self.i):
                self.i = self.text.find("\n", self.i)
                if self.i < 0:
                    self.i = self.n
                continue
            if self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                self.i = self.n if end < 0 else end + 2
                continue
            break

    def _take(self, count: int = 1) -> str:
        out = self.text[self.i : self.i + count]
        self.i += count
        return out

    def parse_file(self) -> Call:
        node = self.parse_call()
        self._skip()
        if self.i < self.n:
            raise ValueError(f"trailing CSG at {self.i}")
        return node

    def parse_call(self) -> Call:
        name = self._ident()
        if self.peek() != "(":
            raise ValueError(f"expected ( after {name}")
        self._take()
        args = self._args()
        if self.peek() != ")":
            raise ValueError(f"expected ) after {name} args")
        self._take()
        children: list[Call] = []
        if self.peek() == "{":
            self._take()
            while self.peek() not in ("", "}"):
                children.append(self.parse_call())
            if self.peek() != "}":
                raise ValueError(f"unclosed block in {name}")
            self._take()
        elif self.peek() == ";":
            self._take()
        return Call(name, args, children)

    def _ident(self) -> str:
        self._skip()
        start = self.i
        if self.i < self.n and self.text[self.i] == "$":
            self.i += 1
        while self.i < self.n and (self.text[self.i].isalnum() or self.text[self.i] == "_"):
            self.i += 1
        if self.i == start:
            raise ValueError(f"expected name at {self.i}")
        return self.text[start : self.i]

    def _args(self) -> dict[str, object]:
        args: dict[str, object] = {}
        idx = 0
        while self.peek() not in ("", ")"):
            if self.peek() == ",":
                self._take()
                continue
            if self._looks_named():
                key = self._ident()
                if self.peek() != "=":
                    raise ValueError(f"expected = after {key}")
                self._take()
                args[key] = self._value()
            else:
                args[str(idx)] = self._value()
                idx += 1
        return args

    def _looks_named(self) -> bool:
        mark = self.i
        try:
            self._ident()
            named = self.peek() == "="
        except ValueError:
            named = False
        self.i = mark
        return named

    def _value(self) -> object:
        self._skip()
        ch = self.peek()
        if ch == "[":
            return self._list()
        if ch in ".-0123456789":
            return self._number()
        ident = self._ident()
        if ident == "true":
            return True
        if ident == "false":
            return False
        raise ValueError(f"bad value {ident!r}")

    def _list(self) -> list[object]:
        self._take()
        out: list[object] = []
        while self.peek() not in ("", "]"):
            if self.peek() == ",":
                self._take()
                continue
            out.append(self._value())
        if self.peek() != "]":
            raise ValueError("unclosed list")
        self._take()
        return out

    def _number(self) -> float:
        self._skip()
        start = self.i
        if self.peek() in "+-":
            self._take()
        while self.i < self.n and (self.text[self.i].isdigit() or self.text[self.i] in ".eE+-"):
            if self.text[self.i] in "+-" and self.text[self.i - 1] not in "eE":
                break
            self.i += 1
        return float(self.text[start : self.i])


def find_openscad() -> Path:
    found = shutil.which("openscad")
    if found:
        return Path(found)
    for path in OPENSCAD_CANDIDATES:
        if path.is_file():
            return path
    raise FileNotFoundError("openscad is not installed")


def export_csg(openscad: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / "_tray_export.csg"
    cmd = [
        str(openscad),
        "--export-format",
        "csg",
        "-D",
        'variant="metal"',
        "-D",
        'part="tray"',
        "-o",
        str(tmp),
        str(CASE_SCAD),
    ]
    subprocess.run(cmd, check=True)
    tmp.replace(dest)


def mat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return a @ b


def call_matrix(node: Call) -> np.ndarray:
    raw = node.args.get("0", node.args.get("m"))
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError("multmatrix needs a 4x4")
    return np.array(raw, dtype=float)


def arg_float(node: Call, *names: str, default: float | None = None) -> float:
    for name in names:
        if name in node.args:
            return float(node.args[name])  # type: ignore[arg-type]
    if default is None:
        raise KeyError(names)
    return default


def make_cylinder(cq, node: Call, matrix: np.ndarray):
    h = arg_float(node, "h")
    r1 = arg_float(node, "r1", "r", default=0.0)
    r2 = arg_float(node, "r2", default=r1)
    center = bool(node.args.get("center", False))
    if abs(r1 - r2) > 1e-9:
        solid = cq.Solid.makeCone(r1, r2, h)
    else:
        solid = cq.Solid.makeCylinder(r1, h)
    if center:
        solid = solid.translate((0, 0, -h / 2))
    return apply_matrix(cq, solid, matrix)


def make_cube(cq, node: Call, matrix: np.ndarray):
    size = node.args.get("size", node.args.get("0"))
    if not isinstance(size, list) or len(size) != 3:
        raise ValueError("cube needs size [x,y,z]")
    sx, sy, sz = (float(v) for v in size)
    center = bool(node.args.get("center", False))
    solid = cq.Solid.makeBox(sx, sy, sz)
    if center:
        solid = solid.translate((-sx / 2, -sy / 2, -sz / 2))
    return apply_matrix(cq, solid, matrix)


def apply_matrix(cq, shape, matrix: np.ndarray):
    rows = [list(map(float, row)) for row in matrix]
    return shape.transformGeometry(cq.Matrix(rows))


def combine(cq, op: str, shapes: list[object]):
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        return None
    if len(shapes) == 1:
        return shapes[0]
    if op in ("group", "union", "render"):
        out = shapes[0]
        for shape in shapes[1:]:
            out = out.fuse(shape)
        return out.clean()
    if op == "difference":
        out = shapes[0]
        cut = shapes[1]
        for shape in shapes[2:]:
            cut = cut.fuse(shape)
        return out.cut(cut).clean()
    if op == "intersection":
        out = shapes[0]
        for shape in shapes[1:]:
            out = out.intersect(shape)
        return out.clean()
    raise ValueError(f"unsupported CSG op {op}")


def collect_prims(node: Call, matrix: np.ndarray) -> list[tuple[Call, np.ndarray]]:
    if node.name == "multmatrix":
        child_m = mat_mul(matrix, call_matrix(node))
        out: list[tuple[Call, np.ndarray]] = []
        for child in node.children:
            out.extend(collect_prims(child, child_m))
        return out
    if node.name in ("group", "union", "render", "hull"):
        out = []
        for child in node.children:
            out.extend(collect_prims(child, matrix))
        return out
    if node.name in ("cylinder", "cube"):
        return [(node, matrix)]
    raise ValueError(f"cannot hull {node.name}")


def _axis_from_matrix(matrix: np.ndarray) -> np.ndarray:
    axis = matrix[:3, :3] @ np.array([0.0, 0.0, 1.0])
    norm = np.linalg.norm(axis)
    if norm < 1e-12:
        raise ValueError("degenerate cylinder axis")
    return axis / norm


def _origin(matrix: np.ndarray) -> np.ndarray:
    return matrix[:3, 3]


def convex_hull_2d(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    uniq = sorted(set(points))
    if len(uniq) <= 2:
        return uniq

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in uniq:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(uniq):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def hull_cylinders(cq, prims: list[tuple[Call, np.ndarray]]):
    if any(node.name != "cylinder" for node, _ in prims):
        raise ValueError("metal tray hull is cylinders only")
    specs = []
    for node, matrix in prims:
        h = arg_float(node, "h")
        r = arg_float(node, "r1", "r")
        r2 = arg_float(node, "r2", default=r)
        if abs(r - r2) > 1e-6:
            raise ValueError("cannot hull a cone")
        if node.args.get("center"):
            raise ValueError("centered hull cylinder is not used")
        specs.append((h, r, matrix))
    h0, r0, _ = specs[0]
    axis0 = _axis_from_matrix(specs[0][2])
    for h, r, matrix in specs[1:]:
        if abs(h - h0) > 1e-6 or abs(r - r0) > 1e-6:
            raise ValueError("hull cylinders must match")
        axis = _axis_from_matrix(matrix)
        if abs(abs(float(axis @ axis0)) - 1.0) > 1e-6:
            raise ValueError("hull cylinders must be parallel")
    origins = [_origin(matrix) for _, _, matrix in specs]
    helper = np.array([0.0, 0.0, 1.0]) if abs(axis0[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    xdir = np.cross(helper, axis0)
    xdir /= np.linalg.norm(xdir)
    ydir = np.cross(axis0, xdir)
    origin = origins[0]
    pts = []
    for point in origins:
        rel = point - origin
        pts.append((float(rel @ xdir), float(rel @ ydir)))
    hull = convex_hull_2d(pts)
    plane = cq.Plane(origin=tuple(origin), xDir=tuple(xdir), normal=tuple(axis0))
    wp = cq.Workplane(plane)
    if len(hull) == 1:
        return apply_matrix(cq, cq.Solid.makeCylinder(r0, h0), specs[0][2])
    if len(hull) == 2:
        p0, p1 = hull
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        angle = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        return (
            wp.workplane()
            .center(mid[0], mid[1])
            .transformed(rotate=(0, 0, angle))
            .slot2D(length + 2 * r0, 2 * r0)
            .extrude(h0)
            .val()
        )
    return wp.polyline(hull).close().wires().toPending().offset2D(r0).extrude(h0).val()


def eval_csg(cq, node: Call, matrix: np.ndarray):
    if node.name == "multmatrix":
        child_m = mat_mul(matrix, call_matrix(node))
        return combine(cq, "group", [eval_csg(cq, child, child_m) for child in node.children])
    if node.name in ("group", "union", "difference", "intersection", "render"):
        return combine(cq, node.name, [eval_csg(cq, child, matrix) for child in node.children])
    if node.name == "hull":
        return hull_cylinders(cq, collect_prims(node, matrix))
    if node.name == "cylinder":
        return make_cylinder(cq, node, matrix)
    if node.name == "cube":
        return make_cube(cq, node, matrix)
    raise ValueError(f"unsupported CSG node {node.name}")


def shape_report(shape) -> str:
    box = shape.BoundingBox()
    vol = float(shape.Volume())
    return (
        f"{box.xlen:.3f} x {box.ylen:.3f} x {box.zlen:.3f} mm, "
        f"volume {vol:.1f} mm3"
    )


def build_step(csg_path: Path, step_path: Path) -> None:
    tree = CsgParser(csg_path.read_text(encoding="ascii")).parse_file()
    solid = eval_csg(cq, tree, np.eye(4))
    if solid is None:
        raise SystemExit("CSG tree produced no solid")
    step_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solid, str(step_path), exportType="STEP")
    print(f"wrote {step_path} ({step_path.stat().st_size} bytes)")
    print(f"  solid: {shape_report(solid)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reuse-csg",
        action="store_true",
        help="use an existing tray.csg instead of running OpenSCAD",
    )
    args = parser.parse_args()
    if args.reuse_csg and CSG_PATH.is_file():
        print(f"reusing {CSG_PATH}")
    else:
        openscad = find_openscad()
        print(f"exporting CSG with {openscad}")
        export_csg(openscad, CSG_PATH)
        print(f"wrote {CSG_PATH} ({CSG_PATH.stat().st_size} bytes)")
    build_step(CSG_PATH, STEP_PATH)
    print("HOLD: quote file only. Caliper a Pixel 10 and a stuffed board before 6061.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
