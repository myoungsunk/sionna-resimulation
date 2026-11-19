"""Generate the fixed G1 corridor meshes and material bindings, without Sionna."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

LENGTH_M = 20.0
HEIGHT_M = 2.70
RX_Z_M = 0.45
ANCHORS = {"A": (7.0, 0.0, 2.65), "B": (9.8, 0.0, 2.65), "C": (3.0, 0.0, 2.65)}
HALF_WIDTHS = {"G-T1": 0.97, "G-T2": 0.97, "G-V": 1.20}
RECESSES = ((6.0, 6.7), (12.65, 13.65))
RECESS_DEPTH_M = 0.19
RECESS_TOP_M = 2.10
PROTRUSION = (8.6, 10.0)
PROTRUSION_DEPTH_M = 0.39
CONCRETE = ("concrete", 0.20)
PLASTERBOARD = ("plasterboard", 0.0125)
WOOD = ("wood", 0.04)


def lane_y(geometry: str) -> float:
    return HALF_WIDTHS[geometry] - 0.50


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def horizontal(x0, x1, y0, y1, z, *, down=False):
    quad = ((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z))
    return quad[::-1] if down else quad


def side(x0, x1, y, z0, z1, *, positive):
    quad = ((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1))
    return quad if positive else quad[::-1]


def end(x, y0, y1, z0, z1, *, start):
    quad = ((x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1))
    return quad if start else quad[::-1]


def wall_profile(geometry: str, *, positive: bool):
    """Return the footprint boundary (including the recesses or protrusion)."""
    half = HALF_WIDTHS[geometry]
    base = half if positive else -half
    if geometry != "G-T2":
        return [(0.0, base), (LENGTH_M, base)]
    spans = RECESSES if positive else (PROTRUSION,)
    offset = RECESS_DEPTH_M if positive else PROTRUSION_DEPTH_M
    profile = [(0.0, base)]
    for lo, hi in spans:
        profile.extend(((lo, base), (lo, base + offset), (hi, base + offset), (hi, base)))
    return [*profile, (LENGTH_M, base)]


def surfaces(geometry: str) -> dict:
    half, length, height = HALF_WIDTHS[geometry], LENGTH_M, HEIGHT_M
    wall = CONCRETE if geometry == "G-V" else PLASTERBOARD
    result = {
        "floor": (CONCRETE, [horizontal(0, length, -half, half, 0)]),
        "ceiling": (CONCRETE, [horizontal(0, length, -half, half, height, down=True)]),
        "end_x_min": (CONCRETE, [end(0, -half, half, 0, height, start=True)]),
        "end_x_max": (CONCRETE, [end(length, -half, half, 0, height, start=False)]),
    }
    if geometry != "G-T2":
        result["wall_y_neg"] = (wall, [side(0, length, -half, 0, height, positive=False)])
        result["wall_y_pos"] = (wall, [side(0, length, half, 0, height, positive=True)])
        return result

    # Positive-y openings remove the original wall below the lintel.
    panels, previous = [], 0.0
    for index, (lo, hi) in enumerate(RECESSES, 1):
        back = half + RECESS_DEPTH_M
        panels.extend((side(previous, lo, half, 0, height, positive=True),
                       side(lo, hi, half, RECESS_TOP_M, height, positive=True)))
        result[f"recess_{index}_wood"] = (WOOD, [
            side(lo, hi, back, 0, RECESS_TOP_M, positive=True),
            end(lo, half, back, 0, RECESS_TOP_M, start=True),
            end(hi, half, back, 0, RECESS_TOP_M, start=False),
        ])
        result[f"recess_{index}_floor"] = (CONCRETE, [horizontal(lo, hi, half, back, 0)])
        result[f"recess_{index}_soffit"] = (
            WOOD, [horizontal(lo, hi, half, back, RECESS_TOP_M, down=True)])
        previous = hi
    panels.append(side(previous, length, half, 0, height, positive=True))
    result["wall_y_pos"] = (wall, panels)

    lo, hi = PROTRUSION
    face = -half + PROTRUSION_DEPTH_M
    result["wall_y_neg"] = (wall, [
        side(0, lo, -half, 0, height, positive=False),
        side(hi, length, -half, 0, height, positive=False),
    ])
    result["protrusion"] = (CONCRETE, [
        side(lo, hi, face, 0, height, positive=False),
        end(lo, -half, face, 0, height, start=False),
        end(hi, -half, face, 0, height, start=True),
    ])
    for name, z, down in (("floor", 0, False), ("ceiling", height, True)):
        result[name] = (CONCRETE, [
            horizontal(0, lo, -half, half, z, down=down),
            horizontal(lo, hi, face, half, z, down=down),
            horizontal(hi, length, -half, half, z, down=down),
        ])
    return result


def write_ply(path: Path, quads: list) -> None:
    """Write BLOCK_C's ASCII PLY triangle convention for one or more quads."""
    vertices = [point for quad in quads for point in quad]
    triangles = [(i, i + 1, i + 2) for i in range(0, len(vertices), 4)]
    triangles += [(i, i + 2, i + 3) for i in range(0, len(vertices), 4)]
    header = [
        "ply", "format ascii 1.0", f"element vertex {len(vertices)}",
        "property float x", "property float y", "property float z",
        f"element face {len(triangles)}", "property list uchar int vertex_indices", "end_header",
    ]
    rows = [" ".join(format(v, ".17g") for v in point) for point in vertices]
    rows += [f"3 {a} {b} {c}" for a, b, c in triangles]
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write("\n".join(header + rows) + "\n")


def build_scenes(out: Path) -> dict:
    manifest = {"environment": "ENV_ASSUMED", "units": "m", "geometries": {}}
    out.mkdir(parents=True, exist_ok=False)
    for geometry, half in HALF_WIDTHS.items():
        directory = out / geometry
        directory.mkdir()
        bindings = []
        for name, ((material, thickness), quads) in surfaces(geometry).items():
            path = directory / f"{name}.ply"
            write_ply(path, quads)
            bindings.append(dict(object=name, ply=path.relative_to(out).as_posix(),
                                 itu_type=material, thickness_m=thickness, ply_sha256=sha256(path)))
        manifest["geometries"][geometry] = dict(
            dimensions_m=[LENGTH_M, 2 * half, HEIGHT_M], lane_y_m=lane_y(geometry),
            anchors_xyz_m=ANCHORS, rx_z_m=RX_Z_M, material_bindings=bindings)
    write_json(out / "SCENE_MANIFEST.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    build_scenes(parser.parse_args().out)
