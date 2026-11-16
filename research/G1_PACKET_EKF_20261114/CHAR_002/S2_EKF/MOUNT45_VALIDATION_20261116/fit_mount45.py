"""Fit the CHAR-002 S2 mount +45 models from guarded G-T1 TEACH/REPEAT data.

This is an offline, single-purpose runner. It reuses the frozen CHAR-001
O30/sensitivity functions, CHAR-002 model classes, and S2 E4 sweep fitter as
imported modules. It never reads G-T2/G-V, PATHS_NEAR, or evaluation routes.

Example (run only after the mount45 input gate is accepted):
  python fit_mount45.py --gt1 artifacts/G1_CHAR002_S2_MOUNT45_VALIDATION_20261116/guarded_gt1 \
    --src <pinned qclean_uwb src> --banks <pinned banks> \
    --char-root <repo>/research/G1_PACKET_EKF_20261114 \
    --s2-dir <repo>/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF \
    --out artifacts/G1_CHAR002_S2_MOUNT45_VALIDATION_20261116/fit

Outputs FIT.json (run_s2.models-compatible; R1/R2 range and S1/S2/S3
polarization),
FIT_S2.json (direct replay_s2.fit_sweep output), extracted training-only
ERRORS_G-T1_{A,B,C}.npz, TEACH sweep CSV inputs, and RUN_CONTRACT.json.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


QUESTION_ID = "G1-CHAR-002-S2-MOUNT45"
PINNED_SPEC_COMMIT = "6c175a53fbbbb19f990881f7dfcf82a3760dab70"
CASES = ("G-T1_A", "G-T1_B", "G-T1_C")
TRAIN_SETS = ("P-A_TEACH", "P-A_REPEAT")
YAW_SET = "P-A_TEACH"
YAW_PROTOCOL = "dense49"
EXPECTED_MOUNT_DEG = 45.0
EXPECTED_ANCHORS = {
    "G-T1_A": np.array([7.0, 0.0, 2.65]),
    "G-T1_B": np.array([9.8, 0.0, 2.65]),
    "G-T1_C": np.array([3.0, 0.0, 2.65]),
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def put_json(path: Path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def import_modules(char_root: Path, s2_dir: Path, src: Path, banks_dir: Path):
    char1_scripts = char_root / "CHAR_001" / "scripts"
    char2_scripts = char_root / "CHAR_002" / "scripts"
    for required in (char1_scripts / "char_extract.py", char1_scripts / "char_mount.py",
                     char2_scripts / "char2_fit_eval.py", s2_dir / "replay_s2.py"):
        if not required.is_file():
            raise FileNotFoundError(required)
    sys.path[:0] = [str(char1_scripts), str(char2_scripts), str(s2_dir), str(src)]
    import char_extract
    import char_mount
    import char2_fit_eval
    import replay_s2

    char2_fit_eval.FOLD = 180.0
    char2_fit_eval.NB = 12
    # The imported code is pinned and unmodified. Verify the source and bank
    # identities using the original CHAR-001 declarations.
    for rel, prefix in char_extract.SRC_SHA.items():
        actual = sha(src / "qclean_uwb" / rel)
        if not actual.startswith(prefix):
            raise ValueError(f"pinned source mismatch: {rel} ({actual})")
    for filename, expected in char_extract.BANK_SHA.items():
        actual = sha(banks_dir / filename)
        if actual != expected:
            raise ValueError(f"pinned bank mismatch: {filename} ({actual})")

    from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
    banks = [pat.Bank(dict(np.load(banks_dir / name, allow_pickle=False)))
             for name in char_extract.BANK_SHA]
    if not np.array_equal(banks[0].freqs_hz, banks[1].freqs_hz):
        raise ValueError("polarization bank frequency grids differ")
    freq = banks[0].freqs_hz
    if freq.shape != (257,) or not np.all(np.isfinite(freq)) or np.any(np.diff(freq) <= 0):
        raise ValueError("unexpected/nonfinite RF frequency grid")
    df = float(freq[1] - freq[0])
    return char_extract, char_mount, char2_fit_eval, replay_s2, model, obs, banks, df


def verify_retrieval(gt1: Path):
    receipt_path = gt1 / "RETRIEVAL.json"
    receipt = load_json(receipt_path)
    if receipt.get("published_commit") != "1b5888cb7464b494bf9f3095855fe00d4e811558":
        raise ValueError("guarded G-T1 published commit mismatch")
    expected_files = receipt.get("files", {})
    for case in CASES:
        records = expected_files.get(case)
        if not records:
            raise ValueError(f"retrieval receipt missing {case}")
        for rel, expected in records.items():
            path = gt1 / rel
            if not path.is_file() or sha(path) != expected:
                raise ValueError(f"guarded input checksum mismatch: {rel}")
    return receipt_path, receipt


def extract_case(gt1: Path, case: str, out: Path, ce, model, obs, banks, df):
    hdir, pdir = gt1 / "H" / case, gt1 / "poses" / case
    manifest = load_json(hdir / "MANIFEST.json")
    if manifest.get("mount_deg") != EXPECTED_MOUNT_DEG:
        raise ValueError(f"{case} mount is not +45 degrees")
    if manifest.get("status") != "PASS":
        raise ValueError(f"{case} H manifest is not PASS")
    full_path, los_path = hdir / "H_full.npy", hdir / "H_LoS.npy"
    if sha(full_path) != manifest.get("full_H_sha256"):
        raise ValueError(f"{case} H_full hash differs from manifest")
    if sha(los_path) != manifest.get("los_H_sha256"):
        raise ValueError(f"{case} H_LoS hash differs from manifest")

    scene = load_json(pdir / "SCENE_ENTRY.json")
    poses = load_json(pdir / "rf_poses.json")
    samples_path = pdir / "SAMPLES.json"
    samples = load_json(samples_path)
    anchor_name = case.rsplit("_", 1)[1]
    anchor = np.asarray(scene["anchors_xyz_m"][anchor_name], dtype=float)
    if not np.allclose(anchor, EXPECTED_ANCHORS[case], atol=1e-12, rtol=0):
        raise ValueError(f"{case} anchor does not match frozen G-T1 mapping")
    if len(poses) != int(manifest["poses"]):
        raise ValueError(f"{case} pose count differs from H manifest")
    full = np.load(full_path, mmap_mode="r")
    los = np.load(los_path, mmap_mode="r")
    expected_shape = (len(poses), 257, 2, 2)
    if full.shape != expected_shape or los.shape != expected_shape:
        raise ValueError(f"{case} H array shape is not {expected_shape}")

    xy = np.asarray([[row["x"], row["y"]] for row in poses], dtype=float)
    yaw_body = np.asarray([row["yaw_body_deg"] for row in poses], dtype=float)
    robot_z = float(scene["rx_z_m"])
    delta = np.column_stack((xy, np.full(len(xy), robot_z))) - anchor
    distance = np.linalg.norm(delta, axis=1)
    if np.any(distance <= 0) or not np.all(np.isfinite(distance)):
        raise ValueError(f"{case} has invalid RF geometry")
    e = ce.errors(full, los, distance, obs, df)
    # The physical RF orientation is antenna yaw = body yaw + mount offset.
    # Relative bearing remains the frozen CHAR-001 body-yaw convention.
    yaw_ant = yaw_body + EXPECTED_MOUNT_DEG
    g_psi, s_los_syn = ce.sensitivity(model, obs, banks, delta / distance[:, None], yaw_ant, distance, df)

    by_pose = {}
    for row in samples:
        by_pose.setdefault(int(row["pose_id"]), row)
    if set(by_pose) != set(range(len(poses))):
        raise ValueError(f"{case} samples do not map one-to-one onto pose indices")
    if len(by_pose) != len(poses):
        raise ValueError(f"{case} has duplicate or missing pose sample identity")
    sample_row = [by_pose[i] for i in range(len(poses))]
    set_names = np.asarray([r.get("set", "") for r in sample_row], dtype=str)
    allowed = np.isin(set_names, TRAIN_SETS)
    if not allowed.any() or np.any(~np.isin(set_names[allowed], TRAIN_SETS)):
        raise ValueError(f"{case} contains no TEACH/REPEAT training rows")

    npz_path = out / f"ERRORS_{case}.npz"
    np.savez_compressed(
        npz_path, **e, g_psi=g_psi, s_los_syn=s_los_syn, d=distance,
        x=xy[:, 0], y=xy[:, 1], yaw=yaw_body,
        mount=np.full(len(distance), EXPECTED_MOUNT_DEG),
        elev=ce.elevation(delta), rel_bearing=ce.rel_bearing(xy, anchor, yaw_body),
        set=set_names, motion=np.asarray([r.get("motion", "") for r in sample_row], dtype=str),
        along=np.asarray([np.nan if r.get("along") is None else r.get("along", np.nan)
                          for r in sample_row], dtype=float),
        station=np.asarray([r.get("station_id", "") for r in sample_row], dtype=str),
        planned_rel=np.asarray([np.nan if r.get("planned_rel_deg") is None else r.get("planned_rel_deg", np.nan)
                                for r in sample_row], dtype=float),
    )

    # replay_s2.fit_sweep consumes the original CHAR-001 CSV.gz shape. Write a
    # minimal derived CSV with only fields that fitter joins/uses.
    csv_path = out / f"ERRORS_{case}.csv.gz"
    with gzip.open(csv_path, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("pose_id", "x", "y", "yaw", "d", "rel_bearing", "e_s"))
        writer.writeheader()
        for i in np.flatnonzero(allowed):
            writer.writerow({"pose_id": i, "x": xy[i, 0], "y": xy[i, 1], "yaw": yaw_body[i],
                             "d": distance[i], "rel_bearing": ce.rel_bearing(xy[i:i+1], anchor, yaw_body[i:i+1])[0],
                             "e_s": e["e_s"][i]})

    parity = float(np.quantile(np.abs(s_los_syn - e["s_los"]), .9))
    return {
        "case": case, "mount_deg": EXPECTED_MOUNT_DEG, "poses": len(poses),
        "train_rows": int(allowed.sum()),
        "teach_rows": int(np.sum(set_names == "P-A_TEACH")),
        "repeat_rows": int(np.sum(set_names == "P-A_REPEAT")),
        "anchor_xyz_m": anchor.tolist(), "H_full_sha256": sha(full_path), "H_LoS_sha256": sha(los_path),
        "samples_sha256": sha(samples_path), "rf_poses_sha256": sha(pdir / "rf_poses.json"),
        "scene_sha256": sha(pdir / "SCENE_ENTRY.json"), "derived_errors_npz_sha256": sha(npz_path),
        "derived_sweep_csv_sha256": sha(csv_path), "los_sensitivity_parity_p90_abs": parity,
    }


def fit_folding_diagnostic(data, cm, ce, model, obs, banks):
    """Original 180-degree-fold diagnostic with +45 antenna yaw handled explicitly."""
    rows = {}
    for case in CASES:
        z = data[case]
        idx = np.flatnonzero(np.isin(z["set"], TRAIN_SETS))[::4]
        anchor = EXPECTED_ANCHORS[case]
        delta = np.column_stack((z["x"][idx], z["y"][idx], np.full(len(idx), .45))) - anchor
        distance = np.linalg.norm(delta, axis=1)
        u = delta / distance[:, None]
        yaw_ant = z["yaw"][idx] + z["mount"][idx]
        g0 = cm.sens(model, obs, banks, u, yaw_ant, distance)
        g180 = cm.sens(model, obs, banks, u, yaw_ant + 180., distance)
        h0 = obs.cir_batch(cm.synth_los(model, banks, u, yaw_ant, distance)[..., 0])
        h1 = obs.cir_batch(cm.synth_los(model, banks, u, yaw_ant + 180., distance)[..., 0])
        s0, s1 = ce.s_at(h0, ce.o30(h0)), ce.s_at(h1, ce.o30(h1))
        rows[case] = {
            "n": int(len(idx)),
            "s_abs_diff_p90": float(np.quantile(np.abs(s0 - s1), .9)),
            "g_abs_diff_p90": float(np.quantile(np.abs(g0 - g180), .9)),
            "g_abs_median": float(np.median(np.abs(g0))),
            "angle_convention": "antenna_yaw = body_yaw + 45 degrees; compare against +180 degrees",
        }
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gt1", "src", "banks", "char-root", "s2-dir", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError(f"output directory must be empty: {out}")

    retrieval_path, retrieval = verify_retrieval(args.gt1.resolve())
    ce, cm, char2, replay, model, obs, banks, df = import_modules(
        args.char_root.resolve(), args.s2_dir.resolve(), args.src.resolve(), args.banks.resolve())

    started = datetime.now(timezone.utc).isoformat()
    source_paths = {
        "char_extract.py": args.char_root / "CHAR_001" / "scripts" / "char_extract.py",
        "char_mount.py": args.char_root / "CHAR_001" / "scripts" / "char_mount.py",
        "char2_fit_eval.py": args.char_root / "CHAR_002" / "scripts" / "char2_fit_eval.py",
        "replay_s2.py": args.s2_dir / "replay_s2.py",
        "model.py": args.src / "qclean_uwb" / "drivesim" / "hs_lut.py",
        "observation.py": args.src / "qclean_uwb" / "drivesim" / "observation.py",
        "pattern_apply.py": args.src / "qclean_uwb" / "drivesim" / "pattern_apply.py",
    }
    frozen_inputs = {
        "retrieval_receipt": {"path": str(retrieval_path.resolve()), "sha256": sha(retrieval_path),
                              "published_commit": retrieval["published_commit"]},
        "guarded_files": {rel: digest for case in CASES
                          for rel, digest in retrieval["files"][case].items()},
        "sources": {name: sha(path) for name, path in source_paths.items()},
        "banks": {name: sha(args.banks / name) for name in ce.BANK_SHA},
        "model_rules": {"char2_fit_eval.py": "R1/R2 on e_r_abs; S1/S2/S3 on e_s; original model definitions and optimizer"},
        "train_sets": list(TRAIN_SETS),
        "train_cases": list(CASES),
        "e4_filter": {"set": YAW_SET, "protocol": YAW_PROTOCOL},
    }
    contract = {
        "question_id": QUESTION_ID, "role": "IMPLEMENTER", "status": "FROZEN_BEFORE_FIT",
        "frozen_utc": started, "spec_commit": PINNED_SPEC_COMMIT,
        "published_rt_commit": retrieval["published_commit"],
        "scope": {"mount_deg": EXPECTED_MOUNT_DEG, "cases": list(CASES)},
        "training_only": {"model_sets": list(TRAIN_SETS), "model_cases": list(CASES),
                          "e4_set": YAW_SET, "e4_protocol": YAW_PROTOCOL},
        "models": ["R1", "R2", "S1", "S2", "S3"],
        "exclusions": ["G-T2", "G-V", "PATHS_NEAR", "evaluation routes", "sealed inputs"],
        "angle_conventions": {
            "bearing_predictor": "CHAR-001 rel_bearing from body yaw; folded to [0,180)",
            "O30_sensitivity": "antenna yaw = body yaw + mount_deg (+45)",
            "E4_yaw_delta": "body yaw as stored by SAMPLES; constant mount offset cancels from pairwise yaw difference",
        },
        "inputs": frozen_inputs,
        "expected_outputs": ["FIT.json", "FIT_S2.json", "FIT_RECEIPT.json",
                             *(f"ERRORS_{c}.npz" for c in CASES),
                             *(f"ERRORS_{c}.csv.gz" for c in CASES)],
        "runner_sha256": sha(Path(__file__).resolve()), "command": sys.argv,
    }
    contract_path = out / "RUN_CONTRACT.json"
    put_json(contract_path, contract)

    receipts = [extract_case(args.gt1.resolve(), case, out, ce, model, obs, banks, df) for case in CASES]
    data = {}
    for case in CASES:
        with np.load(out / f"ERRORS_{case}.npz", allow_pickle=False) as archive:
            data[case] = {key: archive[key] for key in archive.files}
    # These are the only fitting rows: all anchors, P-A_TEACH + P-A_REPEAT.
    fit_rows = {}
    for case, z in data.items():
        if not np.all(z["mount"] == EXPECTED_MOUNT_DEG):
            raise ValueError(f"{case} extracted mount identity changed")
        mask = np.isin(z["set"], TRAIN_SETS)
        bearing = char2.psi_f(z)[mask]
        bins = char2.bins(bearing)
        d = z["d"][mask]
        e_r = z["e_r_abs"][mask]
        e_s = z["e_s"][mask]
        if not (np.all(np.isfinite(bins)) and np.all(np.isfinite(d))
                and np.all(np.isfinite(e_r)) and np.all(np.isfinite(e_s))):
            raise ValueError(f"{case} training rows contain nonfinite model inputs")
        fit_rows[case] = (bins, d, e_r, e_s)
    cat = lambda j: np.concatenate([fit_rows[c][j] for c in CASES])
    b_train, d_train, e_r_train, e_s_train = (cat(j) for j in range(4))
    support = {
        "d_max": float(np.max(d_train)), "d_min": float(np.min(d_train)),
        "bin_counts": [int(np.sum(b_train == j)) for j in range(12)],
        "bin_ok": [bool(np.sum(b_train == j) >= char2.MIN_BIN) for j in range(12)],
    }
    r1, r2 = (m.fit(e_r_train, b_train, d_train) for m in char2.r_models()[1:3])
    s1, s2, s3 = (m.fit(e_s_train, b_train, d_train) for m in char2.s_models()[1:4])
    if not all(m.success for m in (r1, r2, s1, s2, s3)):
        raise RuntimeError("one or more frozen CHAR-002 R1/R2/S1/S2/S3 optimizers did not converge")
    fits = {
        "e_r_abs": {m.name: m.describe() for m in (r1, r2)},
        "e_s": {m.name: m.describe() for m in (s1, s2, s3)},
    }
    fit_doc = {
        "question_id": QUESTION_ID, "mount_deg": EXPECTED_MOUNT_DEG,
        "fold_deg": 180.0, "n_bins": 12, "train_sets": list(TRAIN_SETS),
        "train_cases": list(CASES), "support": support,
        "fit_rows": {case: {"total": int(len(data[case]["set"])),
                             "teach": int(np.sum(data[case]["set"] == "P-A_TEACH")),
                             "repeat": int(np.sum(data[case]["set"] == "P-A_REPEAT"))}
                     for case in CASES},
        "fits": fits,
        "s_fold_symmetry": fit_folding_diagnostic(data, cm, ce, model, obs, banks),
        "angle_conventions": {
            "bearing_predictor": "CHAR-001 rel_bearing from body yaw; folded to [0,180)",
            "O30_sensitivity": "antenna yaw = body yaw + mount_deg (+45)",
            "E4_yaw_delta": "body yaw as stored by SAMPLES; constant mount offset cancels from pairwise yaw difference",
        },
        "inputs": {
            "guarded_retrieval": {"path": str(retrieval_path.resolve()), "sha256": sha(retrieval_path),
                                  "published_commit": retrieval["published_commit"]},
            "training_errors_npz": {case: sha(out / f"ERRORS_{case}.npz") for case in CASES},
            "training_sweep_csv": {case: sha(out / f"ERRORS_{case}.csv.gz") for case in CASES},
        },
        "script_sha256": sha(Path(__file__).resolve()),
    }
    fit_path = out / "FIT.json"
    put_json(fit_path, fit_doc)

    s_fit = replay.Learned.load(s3.describe())
    sweep_files = [out / f"ERRORS_{case}.csv.gz" for case in CASES]
    samples = [args.gt1 / "poses" / case / "SAMPLES.json" for case in CASES]
    yaw_fit = replay.fit_sweep(sweep_files, samples, s_fit)
    yaw_fit.update({"question_id": QUESTION_ID, "mount_deg": EXPECTED_MOUNT_DEG,
                    "train_sets": [YAW_SET], "train_protocol": YAW_PROTOCOL,
                    "angle_convention": "body yaw; constant +45 degree mount cancels in pairwise delta yaw",
                    "published_commit": retrieval["published_commit"]})
    yaw_path = out / "FIT_S2.json"
    put_json(yaw_path, yaw_fit)

    receipt = {
        "question_id": QUESTION_ID,
        "status": "PASS",
        "outcome": "DIAGNOSTIC_ONLY",
        "gate": "PASS means frozen input identity and fit artifact integrity only; it does not mean EKF integrity or adoption",
        "contract_sha256": sha(contract_path),
        "outputs_sha256": {"FIT.json": sha(fit_path), "FIT_S2.json": sha(yaw_path)},
        "fit_rows": fit_doc["fit_rows"],
        "mount_deg": EXPECTED_MOUNT_DEG,
        "published_rt_commit": retrieval["published_commit"],
        "case_inputs": {case: row for case, row in zip(CASES, receipts, strict=True)},
    }
    put_json(out / "FIT_RECEIPT.json", receipt)


if __name__ == "__main__":
    main()
