"""V5: *new-seed*, pre-registered confirmation of one selected DR-only estimator.

This never touches the original D6_SPEC or original cache/out. The confirmation
spec must be committed unchanged BEFORE running; original 8100:8399 D6 seeds
and development seeds are excluded. Original R2/R4/R5 routes are reused:
new-seed confirmation is NOT independent scene/geometry confirmation.

Typical workflow, after choosing a candidate on V2-V4 development data:
 python v5_independent.py init --spec specs/v5_second_order.json \
       --world gauss_level --candidate BOTH2 --seeds 9000:9300
 git add research/DR_EKF_DIAGNOSIS_20261013/followup_v2/specs/v5_second_order.json
 git commit -m "prereg: freeze V5 independent DR confirmation"
 python v5_independent.py run --spec specs/v5_second_order.json \
       --run-dir runs/v5_second_order --procs 4
 python v5_independent.py evaluate --spec specs/v5_second_order.json \
       --run-dir runs/v5_second_order

"evaluate" is ONLY a read-only scorer; incomplete runs fail without computing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import common as C
import dr_consistency as DC
import v3_second_order as V3

H = C.H
HERE = C.HERE
WORLD_BASE = {"b0": ("B0", "CKF_B0", "PF_B0"),
              "gauss_level": ("A2_3_GAUSS_LEVEL", "CKF_A2_3", "PF_A2_3"),
              "gauss_default": ("A2_3D_GAUSS_DEFAULT", "CKF_A2_3D", "PF_A2_3D")}
CANDIDATES = ("BASE", "MEAN2", "COV2", "BOTH2", "CKF", "PF")
SOURCE_FILES = ("common.py", "v3_second_order.py", "v5_independent.py")


def spec_path(s):
    p = Path(s)
    p = (HERE / p).resolve() if not p.is_absolute() else p.resolve()
    allowed = (HERE / "specs").resolve()
    if allowed not in p.parents or p.suffix != ".json":
        raise ValueError("V5 spec must be a JSON file inside followup_v2/specs/")
    return p


def run_dir_path(s):
    p = Path(s)
    p = (HERE / p).resolve() if not p.is_absolute() else p.resolve()
    allowed = (HERE / "runs").resolve()
    if allowed not in p.parents:
        raise ValueError("V5 result directory must be under followup_v2/runs/")
    return p


def expected_hashes():
    paths = {p: HERE / p for p in SOURCE_FILES}
    paths["dr_harness.py"] = C.DIAG / "dr_harness.py"
    paths["filter_v2.py"] = H.FROZEN_SRC / "qclean_uwb/drivesim/filter_v2.py"
    paths["sensor_v2.py"] = H.FROZEN_SRC / "qclean_uwb/drivesim/sensor_v2.py"
    return {k: C.sha256(v) for k, v in paths.items()}


def initialize(spec_name, world, candidate, seeds_text):
    seeds = C.parse_seed_range(seeds_text)
    if len(seeds) != 300 or set(seeds) & (set(C.D6_SEEDS) | set(C.DEV_SEEDS)
                                           | set(range(6000, 6300))):
        raise ValueError("V5 needs exactly 300 NEW seeds disjoint from D6/development")
    C.git_frozen_spec()
    p = spec_path(spec_name)
    p.parent.mkdir(exist_ok=True, parents=True)
    spec = dict(stage="V5", world=world, candidate=candidate,
                seeds=seeds_text, cells=[H.cell_name(*c) for c in H.CELLS],
                n_seeds=300, estimator_source_sha256=expected_hashes(),
                gates=dict(anees_min=2.4, anees_max=3.6, late_min=2.4,
                           late_max=3.6, coverage_min=.92, coverage_max=.98,
                           max_pos_rmse_ratio_vs_frozen_ekf=1.10),
                limitations=["one corridor scene and three existing routes",
                             "gauss_default repeats the same world across drift levels",
                             "PF particle convergence must be validated independently",
                             "no RF heading, range or real-world generalization"])
    C.write_json_new(p, spec)
    return p


def load_frozen_spec(spec_name):
    p = spec_path(spec_name)
    rel = p.relative_to(C.ROOT).as_posix()
    check = subprocess.run(["git", "-C", str(C.ROOT), "show", f"HEAD:{rel}"],
                           capture_output=True)
    if check.returncode != 0 or check.stdout != p.read_bytes():
        raise RuntimeError("V5 spec MUST be committed and unchanged before running")
    spec = json.loads(p.read_text())
    if spec.get("stage") != "V5" or spec.get("candidate") not in CANDIDATES \
            or spec.get("world") not in WORLD_BASE:
        raise ValueError("invalid frozen V5 specification")
    if spec.get("cells") != [H.cell_name(*c) for c in H.CELLS]:
        raise ValueError("V5 cells changed")
    seeds = C.parse_seed_range(spec["seeds"])
    if len(seeds) != 300 or set(seeds) & (set(C.D6_SEEDS) | set(C.DEV_SEEDS)
                                           | set(range(6000, 6300))):
        raise ValueError("V5 seeds overlap a previous experiment")
    if expected_hashes() != spec["estimator_source_sha256"]:
        raise RuntimeError("V5 source hash differs from pre-registered estimator")
    C.git_frozen_spec()
    return spec, p


def one(task):
    world, candidate, route, lv, seed = task
    base_arm, ckf_arm, pf_arm = WORLD_BASE[world]
    rbase = H.run_one(base_arm, route, lv, seed)
    if candidate == "BASE":
        r = rbase
        error, diag = r["E_post"], r["diag_post"]
    elif candidate in ("MEAN2", "COV2", "BOTH2"):
        r = V3.run_episode(world, candidate, route, lv, seed, steps=0)
        error, diag = r["errors"], r["diag"]
    else:
        r = H.run_one(ckf_arm if candidate == "CKF" else pf_arm,
                      route, lv, seed)
        error, diag = r["E_post"], r["diag_post"]
    return dict(seed=seed,
                nees=np.asarray(diag["nees_pose"], np.float32),
                nees_base=np.asarray(rbase["diag_post"]["nees_pose"], np.float32),
                head=np.asarray(diag["nees_heading"], np.float32),
                cond=np.asarray(diag["nees_cond_xy"], np.float32),
                pos=np.asarray(np.hypot(error[:, 0], error[:, 1]), np.float32),
                yaw=np.asarray(error[:, 2], np.float32),
                pos_base=np.asarray(np.hypot(rbase["E_post"][:, 0],
                                            rbase["E_post"][:, 1]), np.float32),
                yaw_base=np.asarray(rbase["E_post"][:, 2], np.float32))


def artifact_path(folder, route, lv):
    return folder / f"{H.cell_name(route, lv)}.npz"


def validated_artifact(path, seeds, steps):
    with np.load(path, allow_pickle=False) as z:
        arr = {k: z[k] for k in z.files}
    if not np.array_equal(arr.get("seeds"), seeds):
        raise ValueError(f"V5 seeds mismatch: {path}")
    for field in ("nees", "nees_base", "head", "cond", "pos", "yaw",
                  "pos_base", "yaw_base"):
        if field not in arr or arr[field].shape != (len(seeds), steps) or \
                not np.isfinite(arr[field]).all():
            raise ValueError(f"V5 invalid {field} in {path}")
    return arr


def run(spec, folder, procs):
    seeds = C.parse_seed_range(spec["seeds"])
    folder.mkdir(exist_ok=True, parents=True)
    marker = folder / "FROZEN_SPEC_SHA256.txt"
    spec_hash = C.sha256(spec_path_marker_to_spec(folder, spec)) if False else None
    # The caller stores the actual spec file SHA below; never mutate D6 outputs.
    lock = folder / "RUN_LOCK"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        for route, lv in H.CELLS:
            outfile = artifact_path(folder, route, lv)
            ntime = len(H.MOT[route]["t"])
            if outfile.exists():
                validated_artifact(outfile, seeds, ntime)
                print("REUSE", outfile)
                continue
            tasks = [(spec["world"], spec["candidate"], route, lv, seed)
                     for seed in seeds]
            if procs == 1:
                result = [one(t) for t in tasks]
            else:
                with ProcessPoolExecutor(max_workers=procs) as pool:
                    result = list(pool.map(one, tasks, chunksize=1))
            result.sort(key=lambda z: z["seed"])
            arr = {"seeds": np.array(seeds)}
            for field in ("nees", "nees_base", "head", "cond", "pos", "yaw",
                          "pos_base", "yaw_base"):
                arr[field] = np.stack([r[field] for r in result])
            tmp = outfile.with_name(outfile.name + ".tmp")
            with open(tmp, "wb") as fh:
                np.savez_compressed(fh, **arr)
            # Validate before publication; after this step, no overwrite.
            validated_artifact(tmp, seeds, ntime)
            os.replace(tmp, outfile)
            print("COMPLETED", outfile)
    finally:
        lock.unlink(missing_ok=True)


def spec_path_marker_to_spec(folder, spec):
    # Deliberately unused: no implicit discovery of mutable specs from caches.
    raise RuntimeError("Use the explicit --spec argument")


def assess(arr, route, gates):
    t = H.MOT[route]["t"]
    keep = t >= 30
    late_idx = np.flatnonzero(keep)[int(.75 * keep.sum()):]
    def metric(key):
        z = arr[key].astype(float)
        return float(z[:, keep].mean()), float(z[:, late_idx].mean())
    anees, late = metric("nees")
    a_base, late_base = metric("nees_base")
    coverage = float((arr["nees"][:, keep] <= 7.814727903251179).mean())
    base_cov = float((arr["nees_base"][:, keep] <= 7.814727903251179).mean())
    pose = float(np.sqrt(np.mean(arr["pos"][:, keep].astype(float)**2)))
    pose_base = float(np.sqrt(np.mean(arr["pos_base"][:, keep].astype(float)**2)))
    yaw = float(np.degrees(np.sqrt(np.mean(arr["yaw"][:, keep].astype(float)**2))))
    consistent = bool(gates["anees_min"] <= anees <= gates["anees_max"] and
                      gates["late_min"] <= late <= gates["late_max"] and
                      gates["coverage_min"] <= coverage <= gates["coverage_max"])
    return dict(anees=anees, anees_late25=late, coverage95=coverage,
                anees_baseline=a_base, baseline_late25=late_base,
                baseline_coverage95=base_cov, consistent=consistent,
                heading_contribution=float(arr["head"][:, keep].mean()),
                conditional_xy_contribution=float(arr["cond"][:, keep].mean()),
                position_rmse_m=pose, baseline_position_rmse_m=pose_base,
                position_rmse_ratio=pose / max(pose_base, 1e-12),
                heading_rmse_deg=yaw)


def evaluate(spec, folder):
    seeds = C.parse_seed_range(spec["seeds"])
    status, missing, cells = [], [], []
    for route, lv in H.CELLS:
        f = artifact_path(folder, route, lv)
        if not f.is_file():
            missing.append(H.cell_name(route, lv))
            continue
        arr = validated_artifact(f, seeds, len(H.MOT[route]["t"]))
        status.append(dict(cell=H.cell_name(route, lv), sha256=C.sha256(f)))
        cells.append(dict(cell=H.cell_name(route, lv),
                          **assess(arr, route, spec["gates"])))
    if missing:
        raise RuntimeError(f"V5 incomplete: missing cells {missing}; no verdict")
    all_consistent = all(c["consistent"] for c in cells)
    safe_accuracy = all(c["position_rmse_ratio"] <=
                        spec["gates"]["max_pos_rmse_ratio_vs_frozen_ekf"]
                        for c in cells)
    return dict(status="NEW_SEED_SAME_ROUTE_PASS" if all_consistent and safe_accuracy
                else "NEW_SEED_SAME_ROUTE_FAIL",
                cells=cells, files=status,
                consistency_all_cells=all_consistent,
                noninferiority_all_cells=safe_accuracy,
                independent_seed_count=len(seeds),
                physical_route_count=3,
                limitation="Only new sensor seeds; no new route/scene. NOT scientific_PASS.")


def main():
    p = argparse.ArgumentParser()
    commands = p.add_subparsers(dest="command", required=True)
    i = commands.add_parser("init")
    i.add_argument("--spec", required=True)
    i.add_argument("--candidate", choices=CANDIDATES, required=True)
    i.add_argument("--world", choices=list(WORLD_BASE), default="gauss_level")
    i.add_argument("--seeds", default="9000:9300")
    r = commands.add_parser("run")
    r.add_argument("--spec", required=True)
    r.add_argument("--run-dir", required=True)
    r.add_argument("--procs", type=int, default=1)
    e = commands.add_parser("evaluate")
    e.add_argument("--spec", required=True)
    e.add_argument("--run-dir", required=True)
    args = p.parse_args()

    if args.command == "init":
        print("CREATED (NOT RUN)", initialize(
            args.spec, args.world, args.candidate, args.seeds))
        return
    spec, src = load_frozen_spec(args.spec)
    folder = run_dir_path(args.run_dir)
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "FROZEN_SPEC_SHA256.txt"
    source_hash = C.sha256(src)
    if marker.is_file():
        if marker.read_text().strip() != source_hash:
            raise RuntimeError("V5 run directory belongs to another frozen spec")
    else:
        if list(folder.iterdir()):
            raise RuntimeError("V5 run directory is not empty and has no spec marker")
        marker.write_text(source_hash + "\n")
    if args.command == "run":
        if args.procs < 1:
            raise ValueError("--procs must be positive")
        run(spec, folder, args.procs)
        print("RUN COMPLETE; evaluation must be invoked explicitly")
    else:
        report = evaluate(spec, folder)
        out = folder / "V5_INDEPENDENT_CONSISTENCY.json"
        C.write_json_new(out, dict(**report, spec=spec,
                                   manifest=C.provenance(dict(spec_sha256=source_hash))))
        print(report["status"], "consistent", report["consistency_all_cells"],
              "accuracy", report["noninferiority_all_cells"])


if __name__ == "__main__":
    main()
