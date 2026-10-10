"""Linear-measurement check of the augmented EKF: replace the LUT by a linear function of (x, y, theta); generate AR(1) beta exactly as the filter assumes."""
import sys, os, math, numpy as np, pandas as pd, multiprocessing as mp
sys.argv = ["x"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a24_p1_diagnosis as D
import qclean_uwb.drivesim.filters_aug as FA
m, E = D.m, D.E
A_LIN = np.array([0.15, 0.25, 0.9])           # ds = a . (x, y, theta); heading/position sensitivity of the same order as the real model

def h_lin(lut, anchor, rz, x, y, th, mount, with_jac=False):
    val = A_LIN[0] * np.asarray(x) + A_LIN[1] * np.asarray(y) + A_LIN[2] * np.asarray(th)
    if with_jac:
        return val, np.broadcast_to(A_LIN, np.shape(val) + (3,)).copy() if np.ndim(val) else A_LIN.copy()
    return val
FA.s_model = h_lin
m.s_model = h_lin
sfit = D.FIT["s"]; rfit = D.FIT["r"]

def make_t(seed, drift, mode):
    def f(obs, world, _):
        n = len(world.rows); tr = world.truth; ax, rz = D.G["g"]["anchor"], D.G["g"]["robot_z"]
        d3 = np.sqrt((tr[:, 0] - ax[0]) ** 2 + (tr[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
        z = lambda t: m.stream(seed, drift, t, n)
        es = D.ar(z(201), sfit["phi"], sfit["var_beta"]); er = D.ar(z(202), rfit["phi"], rfit["var_beta"]) + z(203) * math.sqrt(0.05 ** 2 + rfit["var_w"])
        obs = dict(obs); obs["s"] = np.where(obs["detected"], h_lin(None, None, None, tr[:, 0], tr[:, 1], tr[:, 2], 0.0) + es, np.nan)
        obs["range_m"] = d3 + obs["range_offset"] + er
        return obs
    return f

def run(args):
    seed, drift = args
    g = D.G["g"]; ax, rz = m.anchor_of("R2A"); g["anchor"], g["robot_z"] = ax, rz
    cap = {}
    E.TRACE_HOOK = lambda world, out, err, nees, inputs, obs: cap.update(nees=nees, t=world.t, err=err, out=out)
    cfg = D.m.make_cfg_transform("F2", D.FIT)
    # no thermal term in this check: cfg_transform also zeroes noise_var_cir_tap
    cfg2 = lambda c, b: cfg(__import__("dataclasses").replace(c, noise_var_cir_tap=0.0), b)
    E.run_unit({None: D.G["w"]}, g["lut"], sensor=D.S_.SensorNoise(), mismatch_sigma=D.ARGS["mismatch_sigma"], anchor_xyz=ax, robot_z=rz, range_offset=g["range_offset"], snr_db=30.0, snr_idx=0,
               drift_idx=drift, seed=seed, compare_filters=False, baselines=[m.BASE], obs_transform=make_t(seed, drift, None), cfg_transform=cfg2)
    E.TRACE_HOOK = None
    out, t, err = cap["out"], cap["t"], cap["err"]; ev = t >= 30; P = out["cov3"]
    n = len(t)
    es = D.ar(m.stream(seed, drift, 201, n), sfit["phi"], sfit["var_beta"])
    zs = ((out["beta_hat"][:, 0] - es) / np.sqrt(out["beta_var"][:, 0]))[ev]
    pos = np.array([e[:2] @ np.linalg.solve(p[:2, :2], e[:2]) for e, p in zip(err[ev], P[ev])]); hd = err[ev][:, 2] ** 2 / P[ev][:, 2, 2]
    return dict(seed=seed, drift=drift, pos=pos.mean(), head=hd.mean(), nees=cap["nees"].mean(), zs_sd=zs.std(), zs_mean=zs.mean())

if __name__ == "__main__":
    with mp.get_context("fork").Pool(4, initializer=D.init) as p:
        r = pd.DataFrame(p.map(run, [(s, d) for s in range(30) for d in (0, 1, 2)]))
    print(r[["pos", "head", "nees", "zs_sd", "zs_mean"]].agg(["mean", "median"]).round(3).to_string())
