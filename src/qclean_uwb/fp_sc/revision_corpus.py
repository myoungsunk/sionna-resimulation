"""Locked corpus enumeration; derived from original checker, production CIR transform."""
from pathlib import Path
import json
import numpy as np
from qclean_uwb.drivesim import observation

def production_cir(h):
    return observation.cir_batch(np.asarray(h)[None])[0]

def locked_corpus(repo: Path):
    """Read all declared spectra; evaluator labels are not generator inputs."""
    physical = repo / "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104"
    rf = repo / "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
    frequencies = np.load(rf / "freqs_hz.npy", allow_pickle=False)
    if not np.array_equal(frequencies, 6_250_400_000.0 + np.arange(257) * 1_950_000.0):
        raise ValueError("CHECKER_FREQUENCY_GRID")
    for route, n in (("R2", 979), ("R4", 742), ("R5", 1415)):
        p = physical / f"C1/C1A_001/FROZEN_PACKETS/algorithm_input/{route}_aB_m0_B0_Full.npz"
        with np.load(p, allow_pickle=False) as archive:
            ids, times = archive["pose_id"], archive["t"]
        if ids.shape != (n,) or times.shape != (n,) or ids.dtype != np.dtype("int64") or not np.all(np.diff(ids) > 0) or not np.all(np.diff(times) > 0):
            raise ValueError("CHECKER_LOCKED_POSE_TIME_SCHEMA")
        full = np.load(rf / f"FULL_RF/H_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
        native = np.load(rf / f"H_LoS_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
        for pose, timestamp in zip(ids, times):
            pair = {"Full": production_cir(full[int(pose), :, :, 0]),
                    "Native_LoS": production_cir(native[int(pose), :, :, 0])}
            for channel in ("Full", "Native_LoS"):
                meta = {"packet_uid": f"dynamic:{route}:{int(pose)}:{channel}", "corpus": "dynamic", "route": route,
                        "coordinate": None, "condition_id": None, "yaw_deg": None, "pose_id": int(pose),
                        "t_s": float(timestamp), "channel": channel}
                yield meta, pair[channel], pair["Native_LoS"]
    g4 = physical / "C3/G4_001/RUN_001"
    conditions = json.loads((g4 / "CONDITIONS.json").read_bytes())
    if len(conditions) != 24 or len({record["condition_id"] for record in conditions}) != 24 or len({record["coordinate"] for record in conditions}) != 6:
        raise ValueError("CHECKER_G4_SCOPE")
    for record in conditions:
        cid = record["condition_id"]
        if Path(cid).name != cid:
            raise ValueError("CHECKER_UNSAFE_G4_ID")
        with np.load(g4 / cid / "FIELDS_AND_WINDOWS.npz", allow_pickle=False) as archive:
            pair = {"Full": production_cir(archive["full_spectrum"]),
                    "Native_LoS": production_cir(archive["direct_spectrum"])}
        for channel in ("Full", "Native_LoS"):
            meta = {"packet_uid": f"static_g4:{cid}:{channel}", "corpus": "static_g4", "route": None,
                    "coordinate": record["coordinate"], "condition_id": cid, "yaw_deg": float(record["yaw_deg"]),
                    "pose_id": None, "t_s": None, "channel": channel}
            yield meta, pair[channel], pair["Native_LoS"]
