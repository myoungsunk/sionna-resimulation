"""Compare all F1 path signatures on the nine locations identified in the G3 diagnostics."""
import argparse
from pathlib import Path
from time import monotonic

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write


ROOT = Path("/g3")
INPUT = ROOT / "input"
SOURCE = Path("/ref")
TARGET_SURFACES = ("ceiling", "wall_y_neg", "recess_1_wood")
CONTROL_BINS = (0, 52, 121, 128, 138, 139, 140, 141, 142, 143, 144, 162, 173, 174, 205, 256)
CASES = (
    ("G-T2_A", "x6.0000_y-0.3100"),
    ("G-T2_A", "x6.0000_y-0.3300"),
    ("G-T2_A", "x6.0000_y0.4700"),
    ("G-T2_A", "x6.0003_y0.4698"),
    ("G-T2_A", "x6.3521_y0.4684"),
    ("G-T2_A", "x7.0252_y0.0549"),
    ("G-T2_B", "x13.6482_y0.4903"),
    ("G-T2_B", "x13.6500_y0.4902"),
    ("G-T2_C", "x17.0000_y0.4700"),
)


def extract(trace, path, depth, none):
    tau = np.asarray(path.tau).ravel()
    angles = [np.asarray(getattr(path, name)).ravel()
              for name in ("theta_t", "phi_t", "theta_r", "phi_r")]
    directions = trace.P.path_directions(*angles)
    events = np.asarray(path.interactions).reshape(depth, len(tau)).T
    surfaces = np.asarray(path.objects).reshape(depth, len(tau)).T
    jones = (np.asarray(path.a[0]) + 1j * np.asarray(path.a[1])).reshape(2, 2, len(tau))
    if not len(tau) or not all(np.isfinite(a).all() for a in (tau, directions, jones)):
        raise ValueError("Empty or nonfinite solver output")
    signatures = [tuple((int(e), int(s)) for e, s in zip(event, surface) if e != none)
                  for event, surface in zip(events, surfaces)]
    return tau, directions, signatures, jones


def compare(left, right, angle_tol):
    lt, ld, ls, _ = left
    rt, rd, rs, _ = right
    dt = np.abs(lt[:, None] - rt[None, :])
    dd = np.linalg.norm(ld[:, None] - rd[None, :], axis=-1)
    same_chain = np.array([[a == b for b in rs] for a in ls])
    matched = (dt <= 2e-13) & (dd <= angle_tol) & same_chain
    if np.any(matched.sum(axis=0) > 1) or np.any(matched.sum(axis=1) > 1):
        raise ValueError("Ambiguous geometric signature")
    li, ri = np.nonzero(matched)
    return li, ri, float(dt[li, ri].max(initial=0)), float(dd[li, ri].max(initial=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=int, choices=range(len(CASES)))
    args = parser.parse_args()
    from sionna.rt.constants import InteractionType

    start = monotonic()
    case, tag = CASES[args.index]
    geom, anchor = case.split("_")
    ref_path = INPUT / "REFERENCE.json"
    reference = read(ref_path)
    for name, expected in reference["method_b_sha256"].items():
        if sha(SOURCE / name) != expected:
            raise ValueError(f"Method B input changed: {name}")
    manifest_path = INPUT / "scene/SCENE_MANIFEST.json"
    scene_entry = read(manifest_path)["geometries"][geom]
    for item in scene_entry["material_bindings"]:
        if sha(INPUT / "scene" / item["ply"]) != item["ply_sha256"]:
            raise ValueError(f"G0 mesh changed: {item['ply']}")
    frozen = ROOT / "output" / case / "bin_by_bin" / f"{tag}_trace.npz"
    receipt_path = frozen.with_name(f"{frozen.stem}_receipt.json")
    receipt = read(receipt_path)
    with np.load(frozen, allow_pickle=False) as raw:
        freqs = raw["node_freq_hz"]
        if not np.array_equal(raw["node_bins"], np.arange(257)) or not np.all(np.diff(freqs) > 0):
            raise ValueError("Frozen bin grid is incomplete")
    trace, _, versions = load_runtime(SOURCE)
    anchor_xyz = scene_entry["anchors_xyz_m"][anchor]
    entry = dict(scene_entry, anchors_xyz_m={"A": anchor_xyz})
    factory, loader = geometry_adapter(trace, entry, INPUT / "scene")
    setup = factory(anchor_x_m=anchor_xyz[0])
    scene, _ = loader(setup, None)
    rt, mi = trace.rt, trace.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(receipt["x"], receipt["y"]).tolist(),
                          orientation=[0.0]*3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(trace.Ports([trace.IsoPort(0), trace.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    cfg = reference["block_c_solver"]
    if (cfg["refraction"], cfg["samples_per_src"], cfg["max_depth"]) != (True, 100_000, 3):
        raise ValueError("Unexpected frozen solver settings")
    off_cfg = cfg | {"refraction": False}
    depth = cfg["max_depth"]
    solver = rt.PathSolver()
    target = tuple((InteractionType.SPECULAR, scene.objects[name].object_id)
                   for name in TARGET_SURFACES)
    control_rows = []
    rows = []
    for bin_id, frequency in enumerate(freqs):
        scene.frequency = float(frequency)
        p = extract(trace, solver(scene, **off_cfg), depth, InteractionType.NONE)
        if bin_id == 0:
            baseline = p
        li, ri, dt, dd = compare(baseline, p, trace.ANGLE_TOL_RAD)
        trans_p = [i for i, s in enumerate(p[2])
                   if any(e == InteractionType.REFRACTION for e, _ in s)]
        if trans_p:
            raise ValueError("F1 returned a refraction path")
        rows.append(dict(bin=bin_id, freq_hz=float(frequency), paths=len(p[0]),
                         baseline_only=len(baseline[0])-len(li), bin_only=len(p[0])-len(ri),
                         matched_max_delay_delta_s=dt, matched_max_direction_delta=dd,
                         target_paths=p[2].count(target)))
        if bin_id in CONTROL_BINS:
            q = extract(trace, solver(scene, **cfg), depth, InteractionType.NONE)
            pi, qi, _, _ = compare(p, q, trace.ANGLE_TOL_RAD)
            trans_q = [i for i, s in enumerate(q[2])
                       if any(e == InteractionType.REFRACTION for e, _ in s)]
            power = np.sum(np.abs(q[3].astype(np.complex128))**2, axis=(0, 1))
            control_rows.append(dict(bin=bin_id, paths_on=len(q[0]), matched=len(pi),
                                     refraction_paths_on=len(trans_q),
                                     refraction_iso_energy_share=float(sum(power[trans_q])/sum(power)),
                                     max_matched_jones_abs_delta=float(np.abs(
                                         p[3][:, :, pi]-q[3][:, :, qi]).max(initial=0)),
                                     target_paths_on=q[2].count(target)))
    failed_bins = [r["bin"] for r in rows if r["baseline_only"] or r["bin_only"]]
    write(Path("/diag") / f"{args.index}_{case}_{tag}.json",
          dict(question_id="G1-RT-TB3-001", kind="F1_PILOT", case=case, tag=tag,
               status="PASS" if not failed_bins else "FAIL", failed_bins=failed_bins,
               xy_m=[receipt["x"], receipt["y"]], runtime=versions,
               input_sha256=dict(frozen_trace=sha(frozen), receipt=sha(receipt_path),
                                 reference=sha(ref_path), scene_manifest=sha(manifest_path),
                                 prior_g3=sha(ROOT / "analysis/G3.json"),
                                 revalidation=sha(Path("/revalidation/EVALUATION/analysis/G3.json")),
                                 script=sha(Path(__file__))),
               baseline_paths=dict(tau_s=baseline[0].tolist(), directions=baseline[1].tolist(),
                                   signatures=baseline[2],
                                   shape_ids={name: obj.object_id for name, obj in scene.objects.items()}),
               solver=off_cfg, control_solver=cfg, rows=rows, control_rows=control_rows,
               wall_s=monotonic()-start))
    print(case, tag, f"F1 path count {len(baseline[0])}", f"signature mismatches {len(failed_bins)}",
          f"controls with refraction {sum(bool(r['refraction_paths_on']) for r in control_rows)}",
          flush=True)


if __name__ == "__main__":
    main()
