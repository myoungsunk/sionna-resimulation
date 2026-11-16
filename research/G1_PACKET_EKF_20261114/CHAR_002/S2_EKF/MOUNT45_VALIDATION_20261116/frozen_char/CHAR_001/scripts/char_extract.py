"""G1-CHAR-001 step 1: noise-free per-pose multipath errors with the frozen MODEL-003 O30 chain.

Usage: python -I char_extract.py --src <qclean_uwb src> --banks <dir> --gt1 <G-T1 root> --blockc <BLOCK_C root> --out <dir>
G-T2/G-V are never opened.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

C = 299792458.0
OFFSET_O30_M = -0.5315983906250129  # MODEL-003 S1 PARITY.json
SRC_SHA = {"drivesim/observation.py": "95079dc0", "drivesim/hs_lut.py": "24f1007e",
           "drivesim/pattern_apply.py": "ab991a70", "scenarios/corridor.py": "38c42cb1"}
BANK_SHA = {"LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
            "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
OBJECTS = {1: "floor", 2: "ceiling", 3: "end_x_min", 4: "end_x_max", 5: "wall_y_neg", 6: "wall_y_pos"}
BATCH = 256


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def o30(cir):
    """Integer O30 index on the strongest branch (identical to range_candidates rule O30)."""
    mag = np.abs(cir)
    branch = mag.max(axis=1).argmax(axis=1)
    strongest = np.take_along_axis(mag, branch[:, None, None], axis=2)[:, :, 0]
    peak = strongest.max(axis=1)
    if np.any(peak <= 0):
        raise ValueError("Zero CIR in noise-free characterization")
    return (strongest >= 0.3 * peak[:, None]).argmax(axis=1)


def s_at(cir, idx):
    p = np.abs(cir[np.arange(len(cir)), idx, :]) ** 2
    return (p[:, 0] - p[:, 1]) / p.sum(axis=1)


def errors(full, los, d, obs, df):
    out = {k: [] for k in ("s_los", "s_full", "s_same", "idx_los", "idx_full")}
    for a in range(0, len(d), BATCH):
        cf = obs.cir_batch(np.asarray(full[a:a + BATCH])[..., 0])
        cl = obs.cir_batch(np.asarray(los[a:a + BATCH])[..., 0])
        il, iff = o30(cl), o30(cf)
        out["s_los"].append(s_at(cl, il))
        out["s_full"].append(s_at(cf, iff))
        out["s_same"].append(s_at(cf, il))
        out["idx_los"].append(il)
        out["idx_full"].append(iff)
    out = {k: np.concatenate(v) for k, v in out.items()}
    n_taps = 4 * full.shape[1]
    r_full = out["idx_full"] / (n_taps * df) * C
    r_los = out["idx_los"] / (n_taps * df) * C
    return dict(e_s=out["s_full"] - out["s_los"], e_s_same=out["s_same"] - out["s_los"],
                dtap=out["idx_full"] - out["idx_los"], e_r=r_full - r_los,
                e_r_abs=r_full - OFFSET_O30_M - d, s_los=out["s_los"], s_full=out["s_full"],
                idx_los=out["idx_los"], idx_full=out["idx_full"])


def sensitivity(model, obs, banks, direction, yaw_ant, dist, df, step=0.5):
    """g_psi = d s_LoS / d psi [1/deg] at the LoS O30 tap, and synthetic LoS s for parity."""
    g, s0 = np.empty(len(dist)), np.empty(len(dist))
    for a in range(0, len(dist), BATCH):
        ii = range(a, min(a + BATCH, len(dist)))
        hs = [np.stack([model.los_h(banks, direction[i], float(yaw_ant[i] + dy), float(dist[i])) for i in ii])
              for dy in (-step, 0.0, step)]
        cirs = [obs.cir_batch(h[..., 0]) for h in hs]
        idx = o30(cirs[1])
        sm, sc, sp = (s_at(c, idx) for c in cirs)
        g[a:a + len(ii)] = (sp - sm) / (2 * step)
        s0[a:a + len(ii)] = sc
    return g, s0


def near_features(path, n_pose, tap_s):
    """Per pose: near non-LoS / LoS energy ratio (dB), dominant object of non-LoS near energy, its excess delay."""
    z = np.load(path, allow_pickle=False)
    pid, los = z["pose_id"], z["is_los"]
    energy = np.mean(np.abs(z["coefficients"][:, :, :, 0]) ** 2, axis=(1, 2))
    tau, obj, nint = z["tau_s"], z["objects"], z["interaction_count"]
    ratio = np.full(n_pose, np.nan)
    dom = np.full(n_pose, -1)
    excess = np.full(n_pose, np.nan)
    has = np.zeros(n_pose, bool)
    order = np.argsort(pid, kind="stable")
    bounds = np.r_[0, np.flatnonzero(np.diff(pid[order])) + 1, len(order)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        rows = order[a:b]
        p = pid[rows[0]]
        has[p] = True
        lr = rows[los[rows]]
        nr = rows[~los[rows]]
        if len(lr) != 1:
            continue
        if not len(nr):
            ratio[p] = -np.inf
            continue
        ratio[p] = 10 * np.log10(energy[nr].sum() / energy[lr[0]])
        k = nr[np.argmax(energy[nr])]
        first = obj[k][obj[k] > 0]
        dom[p] = int(first[0]) if nint[k] == 1 else 10 + int(nint[k])  # 11/12/13 = multi-bounce
        excess[p] = (tau[k] - tau[lr[0]]) / tap_s
    return dict(near_ratio_db=ratio, near_dom=dom, near_excess_tap=excess, near_has=has)


def text(values):
    return np.array(["" if v is None else str(v) for v in values], dtype=str)


def elevation(delta):
    return np.degrees(np.arctan2(-delta[:, 2], np.hypot(delta[:, 0], delta[:, 1])))


def rel_bearing(xy, anchor, yaw_body):
    """Body yaw relative to the robot->anchor bearing, wrapped to (-180, 180]."""
    b = np.degrees(np.arctan2(anchor[1] - xy[:, 1], anchor[0] - xy[:, 0]))
    return (yaw_body - b + 180) % 360 - 180


def gt1_case(root, case, model, obs, banks, df, out):
    hdir, pdir = root / "H" / case, root / "poses" / case
    man = json.load(open(hdir / "MANIFEST.json"))
    for name, key in (("H_full.npy", "full_H_sha256"), ("H_LoS.npy", "los_H_sha256")):
        if sha(hdir / name) != man[key]:
            raise ValueError(f"{case} {name} hash mismatch")
    scene = json.load(open(pdir / "SCENE_ENTRY.json"))
    poses = json.load(open(pdir / "rf_poses.json"))
    samples = json.load(open(pdir / "SAMPLES.json"))
    anchor = np.asarray(scene["anchors_xyz_m"][case.split("_")[1]], float)
    xy = np.array([[p["x"], p["y"]] for p in poses])
    yaw = np.array([p["yaw_body_deg"] for p in poses])
    delta = np.c_[xy, np.full(len(xy), scene["rx_z_m"])] - anchor
    d = np.linalg.norm(delta, axis=1)
    full = np.load(hdir / "H_full.npy", mmap_mode="r")
    los = np.load(hdir / "H_LoS.npy", mmap_mode="r")
    e = errors(full, los, d, obs, df)
    g, s_syn = sensitivity(model, obs, banks, delta / d[:, None], yaw + man["mount_deg"], d, df)
    nf = near_features(root / "paths" / case / "PATHS_NEAR.npz", len(poses), 1 / (4 * 257 * df))
    first = {}
    for r in samples:
        first.setdefault(r["pose_id"], r)
    col = lambda k, default: np.array([first[i].get(k, default) if i in first else default for i in range(len(poses))])
    np.savez_compressed(out / f"ERRORS_{case}.npz", **e, **nf, g_psi=g, s_los_syn=s_syn, d=d, x=xy[:, 0], y=xy[:, 1],
                        yaw=yaw, mount=np.full(len(d), man["mount_deg"]), elev=elevation(delta),
                        rel_bearing=rel_bearing(xy, anchor, yaw), set=text(col("set", "")), motion=text(col("motion", "")),
                        along=col("along", np.nan).astype(float), station=text(col("station_id", "")),
                        planned_rel=np.array([np.nan if v is None else v for v in col("planned_rel_deg", None)], float))
    return dict(case=case, rt="NEW_G-T1", poses=len(d), anchor=anchor.tolist(), mount=man["mount_deg"],
                h_full_sha256=man["full_H_sha256"], h_los_sha256=man["los_H_sha256"],
                parity_p90_abs=float(np.quantile(np.abs(s_syn - e["s_los"]), 0.9)),
                near_poses=int(nf["near_has"].sum()))


def blockc_case(root, info, model, obs, banks, df, out):
    case = info["case"]
    fp, lp = root / "FULL_RF" / f"H_{case}.npy", root / f"H_LoS_{case}.npy"
    if sha(fp) != info["input_H_sha256"] or sha(lp) != info["H_sha256"]:
        raise ValueError(f"{case} hash mismatch")
    poses = json.load(open(root / case / "SAMPLES.json"))
    anchor = np.asarray(info["anchor_xyz"], float)
    xy = np.array([[p["x"], p["y"]] for p in poses])
    yaw = np.array([p["yaw_body_deg"] for p in poses])
    delta = np.c_[xy, np.full(len(xy), info["robot_z"])] - anchor
    d = np.linalg.norm(delta, axis=1)
    full, los = np.load(fp, mmap_mode="r"), np.load(lp, mmap_mode="r")
    e = errors(full, los, d, obs, df)
    g, s_syn = sensitivity(model, obs, banks, delta / d[:, None], yaw + info["mount_deg"], d, df)
    step = np.r_[0, np.hypot(*np.diff(xy, axis=0).T)]
    dyaw = np.r_[0, np.abs((np.diff(yaw) + 180) % 360 - 180)]
    motion = np.where((step < 0.01) & (dyaw > 0.5), "in_place",
                      np.where(dyaw <= 0.5, np.where(step < 0.01, "stationary", "straight"), "curve"))
    np.savez_compressed(out / f"ERRORS_{case}.npz", **e, g_psi=g, s_los_syn=s_syn, d=d, x=xy[:, 0], y=xy[:, 1],
                        yaw=yaw, mount=np.full(len(d), info["mount_deg"]), elev=elevation(delta),
                        rel_bearing=rel_bearing(xy, anchor, yaw), motion=motion, along=np.cumsum(step),
                        turn=np.cumsum(dyaw), set=np.full(len(d), case.split("_")[0]))
    return dict(case=case, rt="OLD_BLOCK_C", poses=len(d), anchor=anchor.tolist(), mount=info["mount_deg"],
                h_full_sha256=info["input_H_sha256"], h_los_sha256=info["H_sha256"],
                parity_p90_abs=float(np.quantile(np.abs(s_syn - e["s_los"]), 0.9)))


def main():
    ap = argparse.ArgumentParser()
    for k in ("src", "banks", "gt1", "blockc", "out"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    src = a.src.resolve()
    for name, prefix in SRC_SHA.items():
        if not sha(src / "qclean_uwb" / name).startswith(prefix):
            raise ValueError(f"source hash mismatch {name}")
    sys.path.insert(0, str(src))
    from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
    banks = []
    for name, h in BANK_SHA.items():
        if sha(a.banks / name) != h:
            raise ValueError(f"bank hash mismatch {name}")
        banks.append(pat.Bank(dict(np.load(a.banks / name, allow_pickle=False))))
    freq = banks[0].freqs_hz
    if not np.array_equal(freq, np.load(a.blockc / "freqs_hz.npy")):
        raise ValueError("BLOCK_C frequency grid differs")
    df = float(freq[1] - freq[0])
    a.out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    rows = [gt1_case(a.gt1, c, model, obs, banks, df, a.out) for c in ("G-T1_A", "G-T1_B", "G-T1_C")]
    for info in json.load(open(a.blockc / "CASES.json")):
        rows.append(blockc_case(a.blockc, info, model, obs, banks, df, a.out))
    for r in rows:
        print(r, flush=True)
    json.dump(dict(question_id="G1-CHAR-001", step="extract", started_utc=started,
                   finished_utc=datetime.now(timezone.utc).isoformat(), offset_o30_m=OFFSET_O30_M,
                   cases=rows, banks_sha256=BANK_SHA, command=sys.argv,
                   script_sha256=sha(Path(__file__)),
                   outputs={p.name: sha(p) for p in sorted(a.out.glob("ERRORS_*.npz"))}),
              open(a.out / "EXTRACT_MANIFEST.json", "w"), indent=1)


if __name__ == "__main__":
    main()
