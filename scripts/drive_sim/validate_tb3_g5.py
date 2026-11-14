"""G5 lateral wall distance parity from the frozen G-T2 scene meshes."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


THRESHOLD_M = 0.01
RX_HEIGHT_M = 0.45
EPS = 1e-12
CASES = tuple(f"G-T2_{anchor}" for anchor in "ABC")
SETS = ("P-A_TEACH", "P-A_REPEAT")
STATIONS = tuple(f"P{i:03d}" for i in range(1, 19))
INPUT_SHA256 = {
    "g0/RUN_MANIFEST.json": "48ebdcdde68f3d62ec1b00c3061440f9363313ef35577f409eb5b5c0b75c13b6",
    "g7/RUN_MANIFEST.json": "a1542122461b919f55ad2ce43314ba0a3732e0611a574fd51fa692e6b03e9830",
    "config/SPEC_KO.md": "013763c09cd6014d45c9030efe6769a4ecee375a91d9ae7cafde3bd38f190299",
    "results/GENERATION_RESULT.json": "b05cae3dc9c26a62714e93931c1621c5c195844830b942b6bc738834b72e7c28",
    "results/gates/G4.json": "eebc54523655cc7eeacbd3e8a48c2a0700fb12a67653b6c801da35737d43cdb0",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(root, relative, expected, checked):
    path = verify_file(root, relative, expected, checked)
    return json.loads(path.read_bytes())


def verify_file(root, relative, expected, checked):
    path = root / relative
    if path.is_symlink() or not path.is_file() or sha(path) != expected:
        raise ValueError(f"Missing or changed frozen input: {path}")
    checked[relative] = expected
    return path


def mesh_triangles(path):
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:2] != ["ply", "format ascii 1.0"]:
        raise ValueError(f"Expected ASCII PLY: {path}")
    header_end = lines.index("end_header")
    vertices_n = int(lines[2].removeprefix("element vertex "))
    faces_n = int(lines[6].removeprefix("element face "))
    start = header_end + 1
    vertices = [tuple(map(float, r.split())) for r in lines[start:start + vertices_n]]
    faces = [list(map(int, r.split())) for r in lines[start + vertices_n:]]
    if (not vertices or not faces or len(vertices) != vertices_n or len(faces) != faces_n
            or any(len(v) != 3 or not all(map(math.isfinite, v)) for v in vertices)
            or any(len(f) != 4 or f[0] != 3 or min(f[1:]) < 0 or max(f[1:]) >= vertices_n for f in faces)):
        raise ValueError(f"Invalid mesh geometry: {path}")
    return [(vertices[a], vertices[b], vertices[c]) for _, a, b, c in faces]


def y_hit(triangle, x, z):
    """Intersect a world-y line with a triangle using xz barycentric weights."""
    a, b, c = triangle
    bx, bz = b[0] - a[0], b[2] - a[2]
    cx, cz = c[0] - a[0], c[2] - a[2]
    den = bx * cz - bz * cx
    if abs(den) < EPS:
        # End walls and jambs are parallel to the ray. Their side-wall
        # junctions are included by the closed edges of facing triangles.
        return None
    dx, dz = x - a[0], z - a[2]
    u = (dx * cz - dz * cx) / den
    v = (bx * dz - bz * dx) / den
    if u < -EPS or v < -EPS or u + v > 1 + EPS:
        return None
    return a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])


def spec_distances(x, y):
    """Independent lateral cross section of SPEC_KO §1.2 at RX height."""
    # The recess is open between jambs. At a jamb the first contact is
    # the nominal wall edge. The solid protrusion includes its end faces.
    left_wall = 1.16 if 6.0 < x < 6.7 or 12.65 < x < 13.65 else 0.97
    right_wall = -0.58 if 8.6 <= x <= 10.0 else -0.97
    if not 0.0 < x < 20.0 or not right_wall < y < left_wall:
        raise ValueError(f"Station base outside the specified corridor: {(x, y)}")
    return {"left": left_wall - y, "right": y - right_wall}


def station_bases(samples):
    base = {(r["set"], r["station_id"]): r for r in samples if r["protocol"] == "base"}
    expected = {(kind, station) for kind in SETS for station in STATIONS}
    if set(base) != expected or sum(r["protocol"] == "base" for r in samples) != len(expected):
        raise ValueError("Expected exactly one base per TEACH/REPEAT station")
    return base


def run(root):
    checked = {}
    inputs = {name: read_json(root, name, checksum, checked)
              for name, checksum in INPUT_SHA256.items() if name.endswith(".json")}
    spec_name = "config/SPEC_KO.md"
    verify_file(root, spec_name, INPUT_SHA256[spec_name], checked)
    if any(inputs[f"results/{name}.json"]["status"] != "PASS"
           for name in ("GENERATION_RESULT", "gates/G4")):
        raise ValueError("Production and G4 must be complete")
    g0 = inputs["g0/RUN_MANIFEST.json"]
    g7 = inputs["g7/RUN_MANIFEST.json"]
    g0_hashes, g7_hashes = g0["output_sha256"], g7["output_sha256"]
    scene_name = "scene/SCENE_MANIFEST.json"
    scene = read_json(root, f"results/{scene_name}", g0_hashes[scene_name], checked)["geometries"]["G-T2"]
    if scene["rx_z_m"] != RX_HEIGHT_M:
        raise ValueError("G-T2 receiver height differs from the specification")
    triangles = {}
    for binding in scene["material_bindings"]:
        name = binding["object"]
        relative = f"scene/{binding['ply']}"
        if name in triangles or binding["ply"] != f"G-T2/{name}.ply":
            raise ValueError("Unexpected G-T2 mesh binding")
        if binding["ply_sha256"] != g0_hashes[relative]:
            raise ValueError("Inconsistent G-T2 mesh provenance")
        path = verify_file(root, f"results/{relative}", g0_hashes[relative], checked)
        triangles[name] = mesh_triangles(path)

    rows = []
    for case in CASES:
        folder = f"poses/{case}"
        pose_name, scene_entry_name, samples_name = (
            f"{folder}/{name}" for name in ("rf_poses.json", "SCENE_ENTRY.json", "SAMPLES.json")
        )
        poses = read_json(root, f"results/{pose_name}", g7_hashes[pose_name], checked)
        entry = read_json(root, f"results/{scene_entry_name}", g7_hashes[scene_entry_name], checked)
        if entry != scene:
            raise ValueError(f"Production scene differs between anchors: {case}")
        base = read_json(root, f"g0/{samples_name}", g0_hashes[samples_name], checked)
        samples = root / f"results/{samples_name}"
        baselines = station_bases(base)
        actual = station_bases(json.loads(samples.read_bytes()))
        checked[f"results/{samples_name}"] = sha(samples)
        if actual != baselines:
            raise ValueError(f"Production base observations differ from frozen G0: {case}")
        if [p["pose_id"] for p in poses] != list(range(len(poses))):
            raise ValueError(f"Unexpected production pose IDs: {case}")
        for (kind, station), row in actual.items():
            pid = row["pose_id"]
            if not 0 <= pid < len(poses):
                raise ValueError(f"Missing production base pose: {case}/{kind}/{station}")
            x, y = (poses[pid][name] for name in ("x", "y"))
            if not all(map(math.isfinite, (x, y))) or (x, y) != (row["x"], row["y"]):
                raise ValueError(f"Invalid production base coordinates: {case}/{kind}/{station}")
            reference = spec_distances(x, y)
            contacts = {"left": [], "right": []}
            for name, mesh in triangles.items():
                for triangle in mesh:
                    hit = y_hit(triangle, x, RX_HEIGHT_M)
                    if hit is not None:
                        contacts["left" if hit >= y else "right"].append((abs(hit - y), name))
            for side, expected in reference.items():
                if not contacts[side]:
                    raise ValueError(f"Mesh wall ray missed: {case}/{kind}/{station}/{side}")
                measured, surface = min(contacts[side])
                rows.append(dict(case=case, set=kind, station_id=station, pose_id=pid,
                                 x_m=x, y_m=y, side=side, mesh_wall=surface,
                                 expected_m=expected, measured_m=measured,
                                 abs_delta_m=abs(measured - expected)))
    expected_checks = len(CASES) * len(SETS) * len(STATIONS) * 2
    if len(rows) != expected_checks:
        raise ValueError("Incomplete G5 coverage")
    worst = max(rows, key=lambda row: row["abs_delta_m"])
    return dict(status="PASS" if worst["abs_delta_m"] <= THRESHOLD_M else "FAIL",
                question_id="G1-RT-TB3-001", gate="G5", role="IMPLEMENTER",
                definition="Nearest +/- world-y mesh-triangle contact from station-base RF center at z=0.45 m",
                tolerance_m=THRESHOLD_M, cases=list(CASES), station_base_observations=len(rows) // 2,
                compared_wall_distances=len(rows), max_abs_delta_m=worst["abs_delta_m"],
                worst=worst, rows=rows, input_sha256=checked, governance=g0["governance"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    started, tick = datetime.now(timezone.utc), time.monotonic()
    result = run(args.production_root)
    result.update(started_utc=started.isoformat(), finished_utc=datetime.now(timezone.utc).isoformat(),
                  wall_s=time.monotonic() - tick, command=[sys.executable, *sys.argv],
                  code_commit=args.code_commit, validator_sha256=sha(Path(__file__)))
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"G5 {result['status']}: {result['compared_wall_distances']} wall distances, "
          f"max error {result['max_abs_delta_m']:.9g} m, {result['wall_s']:.3f} s", flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
