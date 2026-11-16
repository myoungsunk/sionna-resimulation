"""G1-CHAR-001 addendum: mount 0 vs 45 on identical poses (pose-level) and in prior EKF results.

Usage: python -I char_mount.py --src <qclean_uwb src> --banks <dir> --blockc <BLOCK_C> --m45 <R4/R5 m45 delivery root>
                              --results <dir with results_*.csv> --out <dir>
LoS-only channels for R4/R5 mount 45 are synthesized with the frozen los_h (parity checked on R2_aA_m45).
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from char_extract import BANK_SHA, SRC_SHA, errors, o30, s_at, sha  # noqa: E402

M45_SHA = {"R4_aA": "5eabb1e44677bdf82630cdf9eea43cad729af2459b9b790d246310d62b725724",
           "R4_aB": "3f76d713edccf90ed1d20c8e0f65064add3ca5c5340b56d11c1f391ca81c791d",
           "R5_aA": "1e2c2f36c8d4945e3868c418875b6f08e459c669bcdad981318daf4521ecfbc2",
           "R5_aB": "8f0d87f213a04d6861d6de12f557ce5ce4ae2ba369b9c94e49496bc4f3e154e9"}
PAIRS = ("R2_aA", "R4_aA", "R4_aB", "R5_aA", "R5_aB")
ARMS = ("range_s_P0|ekf", "range_s_P0|ukf", "range_s_P0|gsf", "range_s_P0_noturn|ekf", "range_s_P1_T10|ekf",
        "range_s_P1_T20|ekf", "range_s_P1_T60|ekf", "inverse_heading_P0|ekf", "range|ekf")


def synth_los(model, banks, direction, yaw_ant, dist):
    return np.stack([model.los_h(banks, direction[i], float(yaw_ant[i]), float(dist[i])) for i in range(len(dist))])


def sens(model, obs, banks, direction, yaw_ant, dist, step=0.5):
    out = []
    for dy in (-step, 0.0, step):
        h = synth_los(model, banks, direction, yaw_ant + dy, dist)
        out.append(obs.cir_batch(h[..., 0]))
    idx = o30(out[1])
    return (s_at(out[2], idx) - s_at(out[0], idx)) / (2 * step)


def motion_class(xy, yaw):
    step = np.r_[0, np.hypot(*np.diff(xy, axis=0).T)]
    dyaw = np.r_[0, np.abs((np.diff(yaw) + 180) % 360 - 180)]
    return np.where((step < 0.01) & (dyaw > 0.5), "in_place",
                    np.where(dyaw <= 0.5, np.where(step < 0.01, "stationary", "straight"), "curve"))


def summarize(e0, e45, mask):
    a0, a45 = np.abs(e0[mask]), np.abs(e45[mask])
    ok = np.isfinite(a0) & np.isfinite(a45)
    a0, a45 = a0[ok], a45[ok]
    if len(a0) < 10:
        return None
    return dict(n=int(len(a0)), median_abs_m0=float(np.median(a0)), median_abs_m45=float(np.median(a45)),
                q90_abs_m0=float(np.quantile(a0, .9)), q90_abs_m45=float(np.quantile(a45, .9)),
                frac_m45_smaller=float(np.mean(a45 < a0)))


def pose_level(a, model, obs, banks):
    cases = {c["case"]: c for c in json.load(open(a.blockc / "CASES.json"))}
    res = {}
    for pair in PAIRS:
        info = cases[f"{pair}_m0"]
        poses = json.load(open(a.blockc / f"{pair}_m0" / "SAMPLES.json"))
        xy = np.array([[p["x"], p["y"]] for p in poses])
        yaw = np.array([p["yaw_body_deg"] for p in poses])
        anchor = np.asarray(info["anchor_xyz"], float)
        delta = np.c_[xy, np.full(len(xy), info["robot_z"])] - anchor
        d = np.linalg.norm(delta, axis=1)
        u = delta / d[:, None]
        h0 = np.load(a.blockc / "FULL_RF" / f"H_{pair}_m0.npy", mmap_mode="r")
        l0 = np.load(a.blockc / f"H_LoS_{pair}_m0.npy", mmap_mode="r")
        if pair == "R2_aA":
            info45 = cases["R2_aA_m45"]
            p45 = a.blockc / "FULL_RF" / "H_R2_aA_m45.npy"
            if sha(p45) != info45["input_H_sha256"]:
                raise ValueError("R2_aA m45 hash")
            h45 = np.load(p45, mmap_mode="r")
            l45 = np.load(a.blockc / "H_LoS_R2_aA_m45.npy", mmap_mode="r")
            los_src = "RT"
        else:
            p45 = a.m45 / f"H_{pair}_m45.npy"
            if sha(p45) != M45_SHA[pair]:
                raise ValueError(f"{pair} m45 hash")
            h45 = np.load(p45, mmap_mode="r")
            l45 = synth_los(model, banks, u, yaw + 45.0, d)
            los_src = "los_h synthesized"
        if h45.shape != h0.shape:
            raise ValueError(f"{pair} shape mismatch")
        e0 = errors(h0, l0, d, obs, 1.95e6)
        e45 = errors(h45, l45, d, obs, 1.95e6)
        g0 = sens(model, obs, banks, u, yaw, d)
        g45 = sens(model, obs, banks, u, yaw + 45.0, d)
        ep0, ep45 = e0["e_s"] / g0, e45["e_s"] / g45
        mot = motion_class(xy, yaw)
        bearing = np.degrees(np.arctan2(-delta[:, 1], -delta[:, 0]))
        rel = np.abs(((yaw - bearing) + 90) % 180 - 90)  # 0 = facing/away from anchor, 90 = broadside
        along = np.abs(((yaw) + 90) % 180 - 90)  # 0 = along corridor axis
        row = dict(los_m45_source=los_src, poses=len(d),
                   g_abs_median=dict(m0=float(np.median(np.abs(g0))), m45=float(np.median(np.abs(g45)))),
                   frac_g_m45_larger=float(np.mean(np.abs(g45) > np.abs(g0))),
                   e_s_std=dict(m0=float(e0["e_s"].std()), m45=float(e45["e_s"].std())),
                   all=summarize(ep0, ep45, np.ones(len(d), bool)))
        row["by_motion"] = {m: summarize(ep0, ep45, mot == m) for m in ("straight", "in_place", "curve")}
        row["by_yaw_vs_corridor"] = {lab: summarize(ep0, ep45, m) for lab, m in
                                     (("along_0_20", along < 20), ("oblique_20_70", (along >= 20) & (along < 70)),
                                      ("across_70_90", along >= 70))}
        row["by_yaw_vs_anchor_bearing"] = {lab: summarize(ep0, ep45, m) for lab, m in
                                           (("radial_0_20", rel < 20), ("oblique_20_70", (rel >= 20) & (rel < 70)),
                                            ("broadside_70_90", rel >= 70))}
        row["by_distance"] = {lab: summarize(ep0, ep45, m) for lab, m in
                              (("d<4", d < 4), ("4<=d<8", (d >= 4) & (d < 8)), ("d>=8", d >= 8))}
        if los_src == "RT":
            syn = synth_los(model, banks, u, yaw + 45.0, d)
            cs, cr = obs.cir_batch(syn[..., 0]), obs.cir_batch(np.asarray(l45)[..., 0])
            row["los_h_parity_p90_abs_s"] = float(np.quantile(np.abs(s_at(cs, o30(cs)) - s_at(cr, o30(cr))), .9))
        res[pair] = row
        print(pair, "done", flush=True)
    return res


def ekf_level(results_dir):
    rows = {}
    for p in sorted(results_dir.glob("results_*.csv")):
        for r in csv.DictReader(open(p)):
            if r["error"]:
                continue
            case = f"{r['route']}_a{r['anchor']}" if r.get("route") else f"R1_y{float(r['lateral']):g}"
            arm = f"{r['baseline']}|{r['filter']}"
            if arm not in ARMS:
                continue
            key = (case, arm, r["drift"], r["snr_db"], r["seed"], r["period_s"])
            rows.setdefault(key, {})[float(r["mount_deg"])] = (float(r["heading_rmse_deg"]),
                                                               float(r["nees_mean"]) if r["nees_mean"] else np.nan)
    out = {}
    for (case, arm, *_), v in rows.items():
        if 0.0 in v and 45.0 in v:
            t = out.setdefault(case, {}).setdefault(arm, dict(m0=[], m45=[], n0=[], n45=[]))
            t["m0"].append(v[0.0][0]); t["m45"].append(v[45.0][0]); t["n0"].append(v[0.0][1]); t["n45"].append(v[45.0][1])
    return {case: {arm: dict(n=len(t["m0"]), heading_rmse_median_m0=float(np.median(t["m0"])),
                             heading_rmse_median_m45=float(np.median(t["m45"])),
                             frac_m45_better=float(np.mean(np.array(t["m45"]) < np.array(t["m0"]))),
                             nees_median_m0=float(np.nanmedian(t["n0"])), nees_median_m45=float(np.nanmedian(t["n45"])))
                   for arm, t in arms.items()} for case, arms in sorted(out.items())}


def main():
    ap = argparse.ArgumentParser()
    for k in ("src", "banks", "blockc", "m45", "results", "out"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    src = a.src.resolve()
    for name, prefix in SRC_SHA.items():
        if not sha(src / "qclean_uwb" / name).startswith(prefix):
            raise ValueError(name)
    sys.path.insert(0, str(src))
    from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
    banks = []
    for name, h in BANK_SHA.items():
        if sha(a.banks / name) != h:
            raise ValueError(name)
        banks.append(pat.Bank(dict(np.load(a.banks / name, allow_pickle=False))))
    a.out.mkdir(parents=True, exist_ok=True)
    result = dict(question_id="G1-CHAR-001", step="mount_addendum", pose_level=pose_level(a, model, obs, banks),
                  ekf_level_prior_pipeline=ekf_level(a.results), command=sys.argv, script_sha256=sha(__file__),
                  results_sha256={p.name: sha(p) for p in sorted(a.results.glob("results_*.csv"))})
    json.dump(result, open(a.out / "C8_MOUNT.json", "w"), indent=1)


if __name__ == "__main__":
    main()
