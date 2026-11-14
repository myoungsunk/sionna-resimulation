"""Trace and validate the bin-invariant F1 path set on the frozen G3 sample."""
import argparse
import hashlib
import re
from pathlib import Path
from time import monotonic

import numpy as np


RUN = Path("/run_g3a")
INPUT = Path("/g3/input")
SOURCE = Path("/ref")
N_BINS = 257
N_POSITIONS = 195
TAU_TOL_S = 2e-13
DIRECTION_TOL = 1e-4
BUNDLES_PER_CASE = 4


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def match(ref_tau, ref_dirs, ref_chain, tau, dirs, chain):
    delay = np.abs(ref_tau[:, None] - tau[None, :])
    direction = np.linalg.norm(ref_dirs[:, None, :] - dirs[None, :, :], axis=-1)
    seq = (ref_chain[:, None, :] == chain[None, :, :]).all(axis=-1)
    pairs = (delay <= TAU_TOL_S) & (direction <= DIRECTION_TOL) & seq
    ambiguous = bool(np.any(pairs.sum(axis=0) > 1) or np.any(pairs.sum(axis=1) > 1))
    return int((~pairs.any(axis=1)).sum()), int((~pairs.any(axis=0)).sum()), ambiguous


def self_check():
    t = np.array([1e-8, 1.3e-8])
    d = np.eye(2, 6)
    s = np.array([[1, 5], [1, 7]])
    assert match(t, d, s, t[::-1], d[::-1], s[::-1]) == (0, 0, False)
    assert match(t, d, s, t[:1], d[:1], s[:1]) == (1, 0, False)
    assert match(t, d, s, t, d, s[::-1]) == (2, 2, False)
    assert match(t, d, s, t+3e-13, d, s) == (2, 2, False)
    assert match(t, d, s, t, d+1e-4, s) == (2, 2, False)
    assert match(t, d, s, t[[0, 0]], d[[0, 0]], s[[0, 0]]) == (1, 0, True)


def manifest():
    from run_tb3_g1_pilot import read

    return read(RUN / "MANIFEST.json")


def task_table():
    from run_tb3_g1_pilot import read

    cases = read(INPUT / "G3_CONTRACT.json")["cases"]
    tasks = {case: read(INPUT / "cases" / f"{case}.json") for case in cases}
    for case, entries in tasks.items():
        keys = {(t["x"], t["y"]) for t in entries}
        tags = {t["tag"] for t in entries}
        if len(keys) != len(tags) or len(tags) != len(entries) or len(entries) != cases[case]["trace_positions"]:
            raise ValueError(f"Invalid frozen position list: {case}")
        if len({t["task_id"] for t in entries}) != len(entries):
            raise ValueError(f"Duplicate task ID: {case}")
        if sum(len(t["sampled_yaws"]) for t in entries) != cases[case]["poses"]:
            raise ValueError(f"Frozen pose count mismatch: {case}")
        if not all(re.fullmatch(r"x-?\d+\.\d+_y-?\d+\.\d+", t["tag"]) and
                   np.isfinite([t["x"], t["y"]]).all() for t in entries):
            raise ValueError(f"Invalid task entry: {case}")
    if len(tasks) != 9 or sum(map(len, tasks.values())) != N_POSITIONS:
        raise ValueError("Unexpected G3 sample")
    return tasks


def preflight():
    from run_tb3_g1_pilot import load_runtime, read, write

    self_check()
    manifest_data = manifest()
    for rel, expected in manifest_data["input_sha256"].items():
        if sha(INPUT / rel) != expected:
            raise ValueError(f"Frozen input changed: {rel}")
    for rel, expected in manifest_data["run_input_sha256"].items():
        if sha(RUN / rel) != expected:
            raise ValueError(f"Run bundle changed: {rel}")
    reference = read(INPUT / "REFERENCE.json")
    for rel, expected in reference["method_b_sha256"].items():
        if sha(SOURCE / rel) != expected:
            raise ValueError(f"Method B input changed: {rel}")
    geometries = read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"]
    for entry in geometries.values():
        for item in entry["material_bindings"]:
            if sha(INPUT / "scene" / item["ply"]) != item["ply_sha256"]:
                raise ValueError(f"G0 mesh changed: {item['ply']}")
    trace, _, versions = load_runtime(SOURCE)
    bank_freq = np.asarray(trace.C.load_banks()[0]["freqs_hz"])
    if bank_freq.shape != (N_BINS,) or not np.isfinite(bank_freq).all() or not (np.diff(bank_freq) > 0).all():
        raise ValueError("Invalid frozen RF frequency grid")
    cfg = reference["block_c_solver"]
    if (cfg["refraction"], cfg["samples_per_src"], cfg["max_depth"], cfg["seed"]) != (True, 100000, 3, 20260924):
        raise ValueError("Unexpected reference solver")
    tasks = task_table()
    write(RUN / "PREFLIGHT.json", dict(status="PASS", versions=versions,
          refraction_event_id=trace.rt.constants.InteractionType.REFRACTION, method_b_commit=reference["method_b_commit"],
          manifest_sha256=sha(RUN / "MANIFEST.json"), solver=cfg | {"refraction": False},
          counts={case: len(rows) for case, rows in tasks.items()}, freqs_hz=bank_freq.tolist()))
    for case in tasks:
        for shard in range(BUNDLES_PER_CASE):
            print(case, shard)


def trace_case(case, shard):
    from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, write

    trace, _, _ = load_runtime(SOURCE)
    run_input = read(RUN / "PREFLIGHT.json")
    cfg = run_input["solver"]
    freq = np.array(run_input["freqs_hz"])
    tasks = task_table()[case][shard::BUNDLES_PER_CASE]
    geom, anchor = case.split("_")
    entry = read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"][geom]
    anchor_xyz = entry["anchors_xyz_m"][anchor]
    factory, loader = geometry_adapter(trace, dict(entry, anchors_xyz_m={"A": anchor_xyz}), INPUT / "scene")
    setup = factory(anchor_x_m=anchor_xyz[0])
    rt, mi = trace.rt, trace.mi
    if not all(c["passed"] for c in setup.validate()):
        raise ValueError(f"Invalid corridor setup: {case}")
    scene, _ = loader(setup, None)
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(), orientation=[0.0]*3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(trace.Ports([trace.IsoPort(0), trace.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    solver = rt.PathSolver()
    depth = cfg["max_depth"]
    out = RUN / "raw" / case
    out.mkdir(parents=True, exist_ok=True)
    for row in tasks:
        started = monotonic()
        tag, x, y = row["tag"], row["x"], row["y"]
        scene.receivers["rx"].position = mi.Point3f(*setup.robot_position(x, y).tolist())
        offsets = [0]
        all_tau, all_angles, all_events, all_objects, all_iso = [], [], [], [], []
        for frequency in freq:
            scene.frequency = float(frequency)
            result = solver(scene, **cfg)
            tau = np.asarray(result.tau).ravel()
            count = tau.size
            angles = np.stack([np.asarray(getattr(result, name)).ravel()
                               for name in ("theta_t", "phi_t", "theta_r", "phi_r")])
            a = (np.asarray(result.a[0]) + 1j * np.asarray(result.a[1])).reshape(2, 2, count)
            all_tau.append(tau)
            all_angles.append(angles)
            all_events.append(np.asarray(result.interactions).reshape(depth, count).T.copy())
            all_objects.append(np.asarray(result.objects).reshape(depth, count).T.copy())
            all_iso.append(a)
            offsets.append(offsets[-1]+count)
        tmp = out / f"{tag}.tmp.npz"
        data = out / f"{tag}.npz"
        np.savez_compressed(tmp, bin_offsets=offsets, node_bins=np.arange(N_BINS), node_freq_hz=freq,
                            tau=np.concatenate(all_tau), ang=np.concatenate(all_angles, axis=1),
                            interactions=np.concatenate(all_events), objects=np.concatenate(all_objects),
                            jones_iso=np.concatenate(all_iso, axis=2), x=x, y=y, task_id=row["task_id"])
        tmp.replace(data)
        write(out / f"{tag}.json", dict(case=case, tag=tag, task_id=row["task_id"], xy=[x, y],
              anchor_xyz=anchor_xyz, sampled_yaws=row["sampled_yaws"], solver=cfg, bin_count=N_BINS,
              shape_ids={name: obj.object_id for name, obj in scene.objects.items()},
              raw_sha256=sha(data), elapsed_s=monotonic()-started))
        print(f"{case} {tag} {N_BINS} bins {monotonic()-started:.1f}s", flush=True)


def evaluate():
    from run_tb3_g1_pilot import load_runtime, read, write

    started = monotonic()
    trace, _, _ = load_runtime(SOURCE)
    info = read(RUN / "PREFLIGHT.json")
    none = trace.rt.constants.InteractionType.NONE
    cases = {}
    all_rows = []
    for case, tasks in task_table().items():
        case_rows = []
        for task in tasks:
            tag = task["tag"]
            out = RUN / "raw" / case
            data, receipt = out / f"{tag}.npz", out / f"{tag}.json"
            if not data.is_file() or not receipt.is_file():
                case_rows.append(dict(case=case, tag=tag, error="missing trace or receipt",
                                      compared_bins=0, trace_calls=0, mismatched_bins=[], invalid_bins=[]))
                continue
            meta = read(receipt)
            if (meta["case"], meta["tag"], meta["task_id"], meta["xy"], meta["solver"], meta["bin_count"]) != (
                case, tag, task["task_id"], [task["x"], task["y"]], info["solver"], N_BINS
            ) or sha(data) != meta["raw_sha256"]:
                raise ValueError(f"Trace receipt mismatch: {case}/{tag}")
            with np.load(data, allow_pickle=False) as raw:
                edges, tau, angles = raw["bin_offsets"], raw["tau"], raw["ang"]
                events, objects, iso = raw["interactions"], raw["objects"], raw["jones_iso"]
                if not (edges.shape == (N_BINS+1,) and edges[0] == 0 and edges[-1] == tau.size
                        and (np.diff(edges) >= 0).all() and np.array_equal(raw["node_bins"], np.arange(N_BINS))
                        and np.array_equal(raw["node_freq_hz"], info["freqs_hz"])
                        and (float(raw["x"]), float(raw["y"]), int(raw["task_id"])) ==
                            (task["x"], task["y"], task["task_id"])
                        and angles.shape == (4, len(tau)) and events.shape == objects.shape ==
                            (len(tau), info["solver"]["max_depth"]) and iso.shape == (2, 2, len(tau))):
                    raise ValueError(f"Invalid raw trace: {case}/{tag}")
            dirs = trace.P.path_directions(*angles)
            chain = np.concatenate((events, np.where(events == none, 0, objects)), axis=1)
            valid = (np.isfinite(tau) & (tau >= 0) & np.isfinite(dirs).all(axis=1)
                     & np.isfinite(iso).all(axis=(0, 1)) & (events != info["refraction_event_id"]).all(axis=1))
            records = []
            invalid = []
            compared = 0
            baseline = slice(0, edges[1])
            baseline_valid = edges[1] > 0 and valid[baseline].all()
            for fi, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
                section = slice(lo, hi)
                if not baseline_valid or lo == hi or not valid[section].all():
                    invalid.append(dict(bin=fi, reason="empty or invalid path data"))
                    continue
                missing, extra, ambiguous = match(tau[baseline], dirs[baseline], chain[baseline],
                                                  tau[section], dirs[section], chain[section])
                if ambiguous:
                    invalid.append(dict(bin=fi, reason="ambiguous match within tolerances"))
                    continue
                compared += 1
                if missing or extra:
                    records.append(dict(bin=fi, baseline_only=missing, bin_only=extra))
            case_rows.append(dict(case=case, tag=tag, xy=meta["xy"], baseline_paths=int(edges[1]),
                                  compared_bins=compared, trace_calls=N_BINS, mismatched_bins=records,
                                  invalid_bins=invalid, trace_sha256=meta["raw_sha256"],
                                  min_paths=int(np.diff(edges).min()), max_paths=int(np.diff(edges).max())))
        cases[case] = dict(positions=len(case_rows), compared_bins=sum(r["compared_bins"] for r in case_rows),
                           mismatched_bins=sum(len(r["mismatched_bins"]) for r in case_rows),
                           invalid_bins=sum(len(r["invalid_bins"]) for r in case_rows))
        all_rows.extend(case_rows)
    trace_files = list((RUN / "raw").glob("*/*.npz"))
    if len(trace_files) != sum(r["trace_calls"] > 0 for r in all_rows):
        raise ValueError("Unexpected extra raw traces")
    calls = sum(r["trace_calls"] for r in all_rows)
    compared = sum(r["compared_bins"] for r in all_rows)
    num_mismatch = sum(len(r["mismatched_bins"]) for r in all_rows)
    invalid = sum(len(r["invalid_bins"]) for r in all_rows)
    status = "INCOMPLETE" if compared != N_POSITIONS*N_BINS else "FAIL" if num_mismatch else "PASS"
    write(RUN / "POSITION_CHECKS.json", all_rows)
    write(RUN / "G3A.json", dict(question_id="G1-RT-TB3-001", stage="G3a", status=status,
          expected_positions=N_POSITIONS, expected_calls=N_POSITIONS*N_BINS, completed_positions=len(trace_files),
          trace_calls=calls, compared_bins=compared, invalid_bins=invalid, mismatched_bins=num_mismatch,
          affected_positions=sum(bool(r["mismatched_bins"]) for r in all_rows),
          baseline_only_paths=sum(b["baseline_only"] for r in all_rows for b in r["mismatched_bins"]),
          bin_only_paths=sum(b["bin_only"] for r in all_rows for b in r["mismatched_bins"]),
          raw_npz_bytes=sum(p.stat().st_size for p in trace_files), evaluation_wall_s=monotonic()-started,
          solve_start_utc=(RUN / "TRACE_START_UTC.txt").read_text().strip(),
          solve_finish_utc=(RUN / "TRACE_FINISH_UTC.txt").read_text().strip(),
          solve_wall_s=float((RUN / "TRACE_WALL_S.txt").read_text().strip()),
          cases=cases, position_checks_sha256=sha(RUN / "POSITION_CHECKS.json"),
          manifest_sha256=sha(RUN / "MANIFEST.json")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "trace", "evaluate"))
    parser.add_argument("case", nargs="?")
    parser.add_argument("shard", type=int, nargs="?")
    args = parser.parse_args()
    if args.mode == "preflight":
        preflight()
    elif args.mode == "trace":
        trace_case(args.case, args.shard)
    else:
        evaluate()


if __name__ == "__main__":
    main()
