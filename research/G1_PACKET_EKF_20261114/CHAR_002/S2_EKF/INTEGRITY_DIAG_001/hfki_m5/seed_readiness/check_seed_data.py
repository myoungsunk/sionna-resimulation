"""Check M5 Stage 0 B0 seed-input feasibility against the frozen seed-10 files."""

from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT.parent
WORK = ARTIFACTS.parent
DIAG = ARTIFACTS / "G1_INT_DIAG_001_20261115"
STRUCTURE = DIAG / "structure_sc_ki/RUN_CONTRACT.json"
BASE = DIAG / "RUN_CONTRACT.json"
RF_REGISTRY = ARTIFACTS / "G1_CHAR002_S2_MOUNT45_20261116/RUN_CONTRACT.json"
REPO = WORK / "g1_mount45_b0_publication_20261116"
PLAN_REVISION = "033abcc7f2940bd8437ccbebd145d2f9f229730b"
PLAN_PATH = "research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/PLAN_M5_HFKI_STAGED_KO.md"
TOL = 1e-10
B0_ONLY_FIELDS = ("t", "pose_id", "P0", "z", "muMB", "muBASE", "R", "D")
SENSOR_FIELDS = ("ds", "gy", "dt", "x0")
TRACE_FIELDS = ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff", "nu", "S")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def checked(record):
    path = Path(record["path"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"SHA-256 differs: {path}")
    return path


def array_sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def compare(actual, expected):
    np.testing.assert_allclose(actual, expected, rtol=0., atol=TOL)
    return dict(max_abs=float(np.max(np.abs(actual - expected))), array_equal=bool(np.array_equal(actual, expected)))


def main():
    receipt = ROOT / "SEED_DATA_READINESS.json"
    if receipt.exists():
        raise FileExistsError(receipt)
    plan = subprocess.check_output(["git", "-C", str(REPO), "show", f"{PLAN_REVISION}:{PLAN_PATH}"])
    base, structure = read(BASE), read(STRUCTURE)
    for record in structure["governance"]:
        checked(record)
    rf_registry = read(RF_REGISTRY)["inputs_sha256"]
    if structure["scope"] != dict(anchor="B", bias="B0", routes=["R2", "R4", "R5"], seed=10, mount_deg=0., rf="Full"):
        raise ValueError("The parent structure contract has a different scope")

    native, s2 = Path(base["native"]), Path(base["s2"])
    sys.path[:0] = [str(native / "src"), str(s2), str(DIAG)]
    from d0_d5 import replay_sigma
    from prepare_s2_extensions import native_measurements
    from qclean_uwb.drivesim import observation
    from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng
    from qclean_uwb.fp_sc.e0_baseline import SPEC, load_original_model, read_npz
    from replay_s2 import b0_reference, validate_trace

    for name in ("src/qclean_uwb/drivesim/sensor_v2.py", "src/qclean_uwb/drivesim/sensors.py",
                 "src/qclean_uwb/drivesim/observation.py"):
        checked(structure["model_assets"][name])
    for name in ("d0_d5.py", "replay_s2.py"):
        matching = [record for record in structure["sources"] + structure["s2_sources"] if Path(record["path"]).name == name]
        if len(matching) != 1:
            raise ValueError(f"Missing or ambiguous parent source record for {name}")
        checked(matching[0])
    core, original, model, model_hashes = load_original_model(native)
    if SPEC != {"anchor": (10., 0., 2.65), "robot_z_m": .45, "mount_deg": 0.}:
        raise ValueError("Unexpected E0 observation geometry")
    b0_config = SensorV2Config(level=1, condition="noise_pair", common_scale=0., bias_rw_rad_s_sqrt_s=0.)
    results = {}
    for cell in structure["cells"]:
        route = cell["route"]
        old, ref, loro, evaluator = (read_npz(checked(cell[name])) for name in
                                     ("online", "fixed_gate_trace", "loro_trace", "evaluator"))
        t, pose, ids = evaluator["t"], evaluator["truth"], evaluator["pose_id"]
        for reference in (old, ref, loro):
            np.testing.assert_array_equal(reference["t"], t)
            np.testing.assert_array_equal(reference["pose_id"], ids)
        rf_matches = [{ "path": name, "sha256": digest } for name, digest in rf_registry.items()
                      if Path(name).name == f"H_{route}_aB_m0.npy"]
        if len(rf_matches) != 1:
            raise ValueError(f"{route}: missing or ambiguous frozen RF payload")
        rf_path = checked(rf_matches[0])
        raw = np.load(rf_path, mmap_mode="r", allow_pickle=False)[ids, :, :, 0]
        np.testing.assert_array_equal(raw, old["Hrf"])
        np.testing.assert_array_equal(raw, old["clean_Hrf"])
        z = native_measurements(observation, raw)
        z_parity = compare(z, old["z"])
        ds, yaw = motion_increments(t, pose, convention="legacy-euler")
        trials = {}
        for seed in (10, 11, 12, 13, 14):
            data, latent = generate(t, ds, yaw, b0_config, seed)
            x0 = pose[0] + rng(seed, "initial").standard_normal(3) * [0.1, 0.1, math.radians(5.)]
            x0[2] = (x0[2] + math.pi) % (2. * math.pi) - math.pi
            controls = dict(ds=data["ds_odom"], gy=data["dtheta_gyro"], dt=data["dt_s"], x0=np.r_[x0, 0.])
            for name, array in controls.items():
                if array.shape != old[name].shape or not np.isfinite(array).all():
                    raise ValueError(f"{route}/{seed}: invalid {name} shape or values")
            np.testing.assert_array_equal(latent["true_bias_rad_s"], 0.)
            np.testing.assert_array_equal(controls["dt"], old["dt"])
            # Build an input-only packet in memory, with no seed-10 state traces or evaluator data.
            packet = {**{key: old[key] for key in B0_ONLY_FIELDS}, **controls}
            if seed == 10:
                control_parity = {key: compare(controls[key], old[key]) for key in SENSOR_FIELDS}
                e0 = original.replay(packet, controls | {"x0": controls["x0"][:3]}, "W0", core, model, SPEC)
                np.testing.assert_array_equal(e0["mask"], ref["mask"])
                validate_trace(e0)
                historical = b0_reference(old)
                e0_parity = {key: compare(e0[key], historical[key]) for key in ("x", "P", "prior", "Pprior", "h", "H", "K", "Reff")}
                e0_loro = replay_sigma(packet, controls, e0["mask"], core, original, model, SPEC, cell["sigma_b"])
                np.testing.assert_array_equal(e0_loro["mask"], loro["mask"])
                validate_trace(e0_loro)
                loro_parity = {key: compare(e0_loro[key], loro[key]) for key in TRACE_FIELDS}
            else:
                trials[str(seed)] = dict(
                    fields_sha256={key: array_sha(packet[key]) for key in (*SENSOR_FIELDS, "z", "t", "pose_id")},
                    max_abs_vs_archived_seed10={key: float(np.max(np.abs(controls[key] - old[key]))) for key in SENSOR_FIELDS})
        for alternative in combinations(trials.values(), 2):
            for name in ("ds", "gy", "x0"):
                if alternative[0]["fields_sha256"][name] == alternative[1]["fields_sha256"][name]:
                    raise ValueError(f"{route}: different seeds have equal {name}")
        results[route] = dict(
            rows=len(t), rf=rf_matches[0], archived_inputs={name: cell[name] for name in
                     ("online", "evaluator", "fixed_gate_trace", "loro_trace")},
            seed10_z_parity=z_parity, seed10_controls_parity=control_parity, seed10_E0_parity=e0_parity,
            seed10_E0_LORO_parity=loro_parity, seed10_gate_count=int(e0["mask"].sum()), in_memory_seed_probes=trials)
        print(route, "z parity", z_parity["max_abs"], "E0 parity", max(x["max_abs"] for x in e0_parity.values()),
              "LORO parity", max(x["max_abs"] for x in loro_parity.values()), "gate", int(e0["mask"].sum()), "/", len(t),
              "seed 11–14 inputs ready", flush=True)

    result = dict(status="SEED_DATA_FEASIBLE", role="IMPLEMENTER", question="G1-INT-001/M5 Stage 0 seed data readiness",
                  utc=datetime.now(timezone.utc).isoformat(), scope=structure["scope"] | {"probe_seeds": [11, 12, 13, 14]},
                  plan=dict(commit=PLAN_REVISION, path=PLAN_PATH, sha256=hashlib.sha256(plan).hexdigest()),
                  prerequisites={str(path): sha(path) for path in (BASE, STRUCTURE, RF_REGISTRY, s2 / "prepare_s2_extensions.py")},
                  governance=structure["governance"], native_hashes=model_hashes, script_sha256=sha(__file__),
                  python=sys.version, numpy=np.__version__, command=sys.argv,
                  routes=results, n_input_probes=12,
                  seed_protocol="Historical B0 wheel/gyro noise and independent stream for noisy x0; archived P0 and RF-derived z fixed",
                  native_truth_use="Offline synthetic motion generation and replay identity only. Candidate packet excludes evaluator fields.",
                  scope_boundary="Feasibility and seed-10 reference parity. No HF-KI implementation parity, Stage 2/3 arm scoring, or online NPZ publication.")
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
