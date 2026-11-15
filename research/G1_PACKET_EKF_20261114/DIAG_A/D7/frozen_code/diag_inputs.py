"""Load verified BLOCK_C RF, historical measurements, and frozen observers."""
import hashlib
import io
import json
import sys
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

WORK = Path(__file__).resolve().parents[1]
BASE = WORK.parent
ROOT = WORK / "rf"
PREP = WORK / "prepared"
STAGED = {
    BASE / "anchor_rf.zip": "9691d5b96141331734ac726b3b82c1b33f2d55e60721b64dd61080e399e8f36d",
    BASE / "anchor_prepared.zip": "613fce6e8aa67453c74d8e19171109c49c47c5f9fd94debe4096f1ec622d1895",
    BASE / "original_RF_R2.zip": "88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63",
    WORK / "bank.zip": "cad003e294edc59a4eecdbce39c02bec43d91524ecef37c93978a356ba519e8e",
}
MANIFEST_PATH = "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
CODE_PATH = "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
CASES = ("R2_aA_m0", "R2_aB_m0", "R4_aB_m0", "R5_aB_m0")
COHORTS = [("B0", 0), *((level, sign) for level in ("L0", "L1", "L2") for sign in (1, -1))]


def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def anchor_evidence(case):
    path, = [p for p in (BASE/"anchor_s0_hosted_43608230392").glob(
        f"g1-diag003-hosted-anchor-{case}-*") if p.is_dir()]
    return path


def verify_s0():
    import subprocess
    helper = BASE / "anchor_s0_correction/.github/diag003-s0/require_r2_receipt.py"
    r2 = BASE / "p_cause/actions_43606841242/r2_evidence/S0_REGRESSION.json"
    subprocess.run([sys.executable, str(helper), str(r2)], check=True)
    anchor = {}
    for case in ("R4_aB_m0", "R5_aB_m0"):
        src = anchor_evidence(case)
        row = json.loads((src/f"{case}_ANCHOR_S0.json").read_text(encoding="utf-8"))
        trace = src/f"{case}_full_B0_TRACE.npz"
        if row["status"] != "REPORT_LEVEL_PASS" or sha256(trace) != row["replay_frames_sha256"]:
            raise ValueError(f"Anchor B receipt or replay hash mismatch for {case}")
        anchor[case] = row
    return {"classification": "DIAGNOSTIC_ONLY", "s0_overall": "REPORT_LEVEL_PASS",
            "r2": json.loads(r2.read_text(encoding="utf-8")),
            "anchor_b": anchor, "r2_actions": 43606841242, "anchor_actions": 43608230392,
            "s2_prime": "STOP (FULL_6)", "step_3": "HOLD"}


def stage():
    for path, expected in STAGED.items():
        if sha256(path) != expected:
            raise ValueError(f"Frozen input hash mismatch for {path.name}")
    if not ROOT.exists():
        with zipfile.ZipFile(BASE / "anchor_rf.zip") as z:
            z.extractall(ROOT)
    PREP.mkdir(exist_ok=True)
    with zipfile.ZipFile(BASE / "anchor_prepared.zip") as z:
        for name in ("OBSERVATION_FEATURES_LABELS.csv.gz", "OOF_PARAMETERS.csv.gz"):
            z.extract(name, PREP)
    with zipfile.ZipFile(WORK / "bank.zip") as z:
        for name in ("LP_plus45_bank.npz", "LP_minus45_bank.npz"):
            member, = [m for m in z.namelist() if Path(m).name == name]
            if not (WORK/name).exists():
                with z.open(member) as src, (WORK/name).open("xb") as dst:
                    import shutil
                    shutil.copyfileobj(src, dst)
    (WORK/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256": {
        "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
        "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
    }}), encoding="utf-8")


def init_modules():
    for relative in (CODE_PATH, "research/FFD_P0P3_20261016"):
        sys.path.insert(0, str(ROOT/relative))
    # The R2 diagnostic replay uses the exact source revision validated in S0.
    sys.path.insert(0, str(BASE/"source/research/EKF4_RANGE_S_STAGED_20261014"))


def control_paths(data, level, sign, seeds):
    import r2_bias_replay as legacy
    t, pose = data["t"], data["pose"]
    result, initial = [], []
    for seed in seeds:
        odom, x0 = legacy.build_positive_bias_controls(t, pose, level, seed)
        if sign < 0:
            # Same Sensor-v2 noise streams, with the deterministic bias mirrored.
            odom["dtheta_gyro"] -= 2*np.radians(legacy.BIAS_LEVELS[level])*odom["dt_s"]
        result.append(odom)
        initial.append(x0)
    controls = {k: np.stack([v[k] for v in result]) for k in ("ds_odom", "dtheta_gyro")}
    return controls, np.stack(initial), sign*np.radians(legacy.BIAS_LEVELS[level])


def _r2_trace(case):
    with zipfile.ZipFile(BASE/"original_RF_R2.zip") as z:
        receipt = json.loads(z.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        row, = [r for r in receipt["per_case"] if r["case"] == case and r["channel"] == "full"]
        body = z.read("P2_OUT/"+row["trace_file"])
        if hashlib.sha256(body).hexdigest() != row["trace_sha256"]:
            raise ValueError("RF trace hash mismatch")
        with np.load(io.BytesIO(body), allow_pickle=False) as f:
            return {k: f[k] for k in ("pose_id", "t_s", "truth_for_offline_scoring_only", "z_r_m", "z_s")}


def load_case(case, ffd_model=None):
    from p3_rf_adapter4 import FrozenLut, R0
    from diag_lut import lut_batch

    manifest = json.loads((ROOT/MANIFEST_PATH).read_text(encoding="utf-8"))
    meta, = [c for c in manifest["cases"] if c["id"] == case]
    route, = [r for r in manifest["routes"] if r["id"] == meta["route"]]
    timeline = pd.read_csv(ROOT/route["path"])
    ids = timeline.pose_id.to_numpy(int)
    t = timeline.t_s.to_numpy(float)
    pose = timeline[["x", "y", "yaw_body_deg"]].to_numpy(float)
    pose[:, 2] = np.radians(pose[:, 2])
    ffd = case.startswith(("R4", "R5"))
    if ffd:
        if ffd_model is None:
            import p0_initial
            from source_model import SourceFFD
            p0_initial.OUT = PREP/case
            p0_initial.OUT.mkdir(exist_ok=True)
            ffd_model = SourceFFD()
        model = ffd_model.batch
        obs = pd.read_csv(PREP/"OBSERVATION_FEATURES_LABELS.csv.gz")
        obs = obs[(obs.case == case)&(obs.channel == "full")].set_index("pose_id").loc[ids]
        z = obs[["range_m", "s_fp"]].to_numpy()
        ref = anchor_evidence(case)/f"{case}_full_B0_TRACE.npz"
        with np.load(ref, allow_pickle=False) as data:
            j = data["arms"].tolist().index("JOINT4")
            if not np.array_equal(ids, data["pose_id"]) or not np.array_equal(t, data["t_s"]):
                raise ValueError(f"Anchor trace alignment failed for {case}")
            if not np.array_equal(pose, data["truth_scoring_only"]):
                raise ValueError(f"Anchor trace pose alignment failed for {case}")
            mu, R = data["mu"][:, j], data["R"][:, j]
            reference = {k: data[k][:, j] for k in ("state", "cov", "accepted", "nis")}
    else:
        src = _r2_trace(case)
        if not np.array_equal(ids, src["pose_id"]) or not np.allclose(t, src["t_s"], rtol=0, atol=1e-13):
            raise ValueError(f"R2 trace alignment failed for {case}")
        if not np.allclose(pose, src["truth_for_offline_scoring_only"], rtol=0, atol=1e-13):
            raise ValueError(f"R2 trace pose alignment failed for {case}")
        pose, t = src["truth_for_offline_scoring_only"], src["t_s"]
        z = np.column_stack([src["z_r_m"], src["z_s"]])
        lut = FrozenLut(BASE/"source")
        model = lambda x, case_meta: lut_batch(lut, x, case_meta)
        mu = np.zeros_like(z)
        R = np.broadcast_to(R0, (len(t), 2, 2))
        reference = None
    samples = pd.DataFrame(json.loads((ROOT/meta["samples_path"]).read_text(encoding="utf-8")))
    position = pd.Index(samples.pose_id).get_indexer(ids)
    if (position < 0).any() or not np.isfinite(z).all():
        raise ValueError(f"Missing or invalid BLOCK_C observations {case}")
    return {"case": meta, "model": model, "ffd": ffd, "pose": pose, "t": t,
            "z": z, "mu": mu, "R": R, "rotation": timeline.turn_phase.to_numpy(bool),
            "h_full": ROOT/meta["full_path"], "h_los": ROOT/meta["los_path"],
            "frequencies": (ROOT/route["path"]).parents[1]/"freqs_hz.npy",
            "position": position, "reference": reference}
