"""A24 P1 diagnosis (post-hoc, exploratory): exactly model-matched error worlds on the R2-A route, F0 vs F2."""
import sys, types, importlib.util, json, math, multiprocessing as mp
import numpy as np, pandas as pd
from pathlib import Path
import os
R = os.environ.get("A24_REPO", "/home/user/sionna-resimulation")
S = os.environ.get("A24_SCRATCH", ".") + "/"
spec = importlib.util.spec_from_file_location("snc", f"{R}/scripts/drive_sim/structured_noise_control.py"); m = importlib.util.module_from_spec(spec); sys.modules["snc"] = m; spec.loader.exec_module(m)
E, F, S_ = m.E, m.F, m.S
FIT = m.load_fit(f"{R}/results/DRIVE_SIM_20261007/A24/A24_FIT_PARAMS.json")
ARGS = dict(s1=Path(f"{R}/results/DRIVE_SIM_20261007/S1"), h_dir=Path(S + "a24run/h"), lut=Path(S + "a23in/hs_lut_2deg.npy"), lut_meta=Path(S + "a23in/hs_lut_meta.json"), bank_freqs=Path(S + "a23in/freqs_hz.npy"), mismatch_sigma=0.16095229605409875)
G = {}

def init():
    a = types.SimpleNamespace(**ARGS); m.setup(a); G["w"] = m.make_world(a, "R2A", 0.0); G["g"] = m._G

def ar(z, phi, var):
    return m.ar1_from(z, 0.0, var, phi)

def scaled_fit(c):
    f = json.loads(json.dumps({k: FIT[k] for k in ("s", "r")}))
    for k in ("s", "r"):
        f[k]["var_beta"] *= c
    return dict(FIT, **f)

def world_noise(kind, seed, drift, n, p):
    z = lambda t: m.stream(seed, drift, t, n)
    base, _, c = kind.partition("@"); c = float(c) if c else 1.0
    s_fit, r_fit = scaled_fit(c)["s"], scaled_fit(c)["r"]; kind = base
    if kind == "matched":            # exactly the F2 model: zero-mean AR(1) betas + white parts
        es = ar(z(201), s_fit["phi"], s_fit["var_beta"]); er = ar(z(202), r_fit["phi"], r_fit["var_beta"]) + z(203) * math.sqrt(0.05 ** 2 + r_fit["var_w"])
    elif kind == "matched_s_only":   # s matched, range white at the stored R (F0's model)
        es = ar(z(201), s_fit["phi"], s_fit["var_beta"]); er = z(203) * math.sqrt(G["g"]["R_range"])
    elif kind == "matched_mean":     # matched plus the real constant offsets (as S3/J1)
        es = 0.0465 + ar(z(201), s_fit["phi"], s_fit["var_beta"]); er = 0.052 + ar(z(202), r_fit["phi"], r_fit["var_beta"]) + z(203) * math.sqrt(0.05 ** 2 + r_fit["var_w"])
    elif kind == "range_only_matched":  # s perfect (thermal only), range matched
        es = np.zeros(n); er = ar(z(202), r_fit["phi"], r_fit["var_beta"]) + z(203) * math.sqrt(0.05 ** 2 + r_fit["var_w"])
    elif kind == "s_only_matched":   # range white at the matched white level only
        es = ar(z(201), s_fit["phi"], s_fit["var_beta"]); er = z(203) * math.sqrt(0.05 ** 2 + r_fit["var_w"])
    else:
        raise ValueError(kind)
    return es, er

def make_t(kind, seed, drift):
    def f(obs, world, _):
        n = len(world.rows); tr = world.truth; ax, rz = G["g"]["anchor"], G["g"]["robot_z"]
        s0 = m.s_model(G["g"]["lut"], ax, rz, tr[:, 0], tr[:, 1], tr[:, 2], world.mount_deg)
        d3 = np.sqrt((tr[:, 0] - ax[0]) ** 2 + (tr[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
        es, er = world_noise(kind, seed, drift, n, None)
        obs = dict(obs); tap = 6.0 * obs["noise_var"]; p1, p2 = obs["power"][:, 0], obs["power"][:, 1]
        th = np.array([F.thermal_var_s(x, y, tap) if tap > 0 and np.isfinite(x) and np.isfinite(y) else 0.0 for x, y in zip(p1, p2)])
        obs["s"] = np.where(obs["detected"], s0 + es + np.sqrt(np.maximum(th, 0)) * m.stream(seed, drift, 103, n), np.nan)
        obs["range_m"] = d3 + obs["range_offset"] + er
        return obs
    return f

def unit(args):
    kind, variant, seed, drift = args
    g = G["g"]; ax, rz = m.anchor_of("R2A"); g["anchor"], g["robot_z"] = ax, rz
    c = float(kind.partition("@")[2]) if "@" in kind else 1.0
    cfgt = m.make_cfg_transform(variant, scaled_fit(c))
    cap = {}
    E.TRACE_HOOK = lambda world, out, err, nees, inputs, obs: cap.update(nees=nees, t=world.t, d3=np.sqrt((world.truth[:, 0] - ax[0]) ** 2 + (world.truth[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2), err=err, cov=out["cov3"])
    rows, _ = E.run_unit({None: G["w"]}, g["lut"], sensor=S_.SensorNoise(), mismatch_sigma=ARGS["mismatch_sigma"], anchor_xyz=ax, robot_z=rz, range_offset=g["range_offset"], snr_db=30.0, snr_idx=0,
                         drift_idx=drift, seed=seed, compare_filters=False, baselines=[m.BASE], obs_transform=make_t(kind, seed, drift), cfg_transform=cfgt)
    E.TRACE_HOOK = None
    ev = cap["t"] >= 30; d = cap["d3"][ev]; ne = cap["nees"]
    bins = {f"nees_d{lo}_{hi}": float(ne[(d >= lo) & (d < hi)].mean()) for lo, hi in ((0, 5), (5, 10), (10, 99))}
    pos = np.array([e[:2] @ np.linalg.solve(P[:2, :2], e[:2]) for e, P in zip(cap["err"][ev], cap["cov"][ev])]); hd = cap["err"][ev][:, 2] ** 2 / cap["cov"][ev][:, 2, 2]
    r = rows[0]; r = dict(r, nees_pos=float(pos.mean()), nees_head=float(hd.mean()), **bins); return dict(kind=kind, variant=variant, seed=seed, drift=drift, error=r.get("error", ""), **{k: r[k] for k in ("nees_pos", "nees_head", "nees_d0_5", "nees_d5_10", "nees_d10_99", "nees_mean", "nees_cov95", "heading_cov95", "heading_rmse_common_deg", "pos_rmse_common_m", "s_reject_frac_eval", "r_reject_frac_eval", "nis_s_eval_acc", "nis_r_eval_acc") if k in r})

if __name__ == "__main__":
    seeds = int(sys.argv[1]); kinds = sys.argv[2].split(","); out = sys.argv[3]
    jobs = [(k, v, s, d) for k in kinds for v in ("F2",) for s in range(seeds) for d in (0, 1, 2)]
    with mp.get_context("fork").Pool(4, initializer=init) as p:
        rows = p.map(unit, jobs, chunksize=3)
    df = pd.DataFrame(rows); df.to_csv(out, index=False)
    print(df.groupby(["kind", "variant"])[["nees_mean", "nees_pos", "nees_head", "nees_d0_5", "nees_d5_10", "nees_d10_99", "nees_cov95", "heading_cov95", "heading_rmse_common_deg", "pos_rmse_common_m", "s_reject_frac_eval", "nis_s_eval_acc", "nis_r_eval_acc"]].mean().round(3).to_string())
