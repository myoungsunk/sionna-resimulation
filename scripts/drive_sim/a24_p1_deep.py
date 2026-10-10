import sys, os, numpy as np, pandas as pd, multiprocessing as mp
sys.argv = ["x"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a24_p1_diagnosis as D
m, E = D.m, D.E

def run(args):
    seed, drift, variant = args
    g = D.G["g"]; ax, rz = m.anchor_of("R2A"); g["anchor"], g["robot_z"] = ax, rz
    cap = {}
    E.TRACE_HOOK = lambda world, out, err, nees, inputs, obs: cap.update(nees=nees, t=world.t, truth=world.truth, err=err, out=out)
    rows, _ = E.run_unit({None: D.G["w"]}, g["lut"], sensor=D.S_.SensorNoise(), mismatch_sigma=D.ARGS["mismatch_sigma"], anchor_xyz=ax, robot_z=rz, range_offset=g["range_offset"], snr_db=30.0, snr_idx=0,
                         drift_idx=drift, seed=seed, compare_filters=False, baselines=[m.BASE], obs_transform=D.make_t("matched", seed, drift), cfg_transform=m.make_cfg_transform(variant, D.FIT))
    E.TRACE_HOOK = None
    t, tr, out = cap["t"], cap["truth"], cap["out"]; n = len(t); ev = t >= 30
    rho = np.hypot(tr[:, 0] - ax[0], tr[:, 1] - ax[1]); th = np.degrees(np.arctan2(rho, ax[2] - rz))
    es, er = D.world_noise("matched", seed, drift, n, None)          # true beta_s, beta_r + white (white part of s is thermal only; es is the pure AR beta_s)
    zs = zr = np.full(n, np.nan)
    if variant == "F2":
        zs = (out["beta_hat"][:, 0] - es) / np.sqrt(out["beta_var"][:, 0])
    P = out["cov3"]; err = cap["err"]
    pos = np.array([e[:2] @ np.linalg.solve(p[:2, :2], e[:2]) for e, p in zip(err, P)]); hd = err[:, 2] ** 2 / P[:, 2, 2]
    return pd.DataFrame(dict(seed=seed, drift=drift, variant=variant, t=t, th=th, rho=rho, pos=pos, hd=hd, zs=zs))[ev]

if __name__ == "__main__":
    jobs = [(s, d, "F2") for s in range(20) for d in (0, 1, 2)]
    with mp.get_context("fork").Pool(4, initializer=D.init) as p:
        df = pd.concat(p.map(run, jobs), ignore_index=True)
    df.to_pickle(sys.argv[0] + ".pkl") if False else None
    df["nees"] = df.pos + df.hd
    bins = [0, 15, 25, 40, 60, 90]
    df["thb"] = pd.cut(df.th, bins)
    print("eval samples", len(df), " min rho %.2f m" % df.rho.min())
    print(df.groupby("thb", observed=True).agg(n=("nees", "size"), nees_mean=("nees", "mean"), nees_med=("nees", "median"), pos_med=("pos", "median"), pos_mean=("pos", "mean"), hd_mean=("hd", "mean"), zs_sd=("zs", "std"), zs_mean=("zs", "mean")).round(2).to_string())
    runs = df.groupby(["seed", "drift"]).nees.mean(); print("per-run NEES quantiles", np.round(runs.quantile([.1, .25, .5, .75, .9, 1.0]).values, 1))
    sub = df[df.th >= 25]; print("NEES excluding theta_geo<25deg: mean %.2f median %.2f; pos %.2f head %.2f" % (sub.nees.mean(), sub.nees.median(), sub.pos.mean(), sub.hd.mean()))
    sub2 = df[df.th >= 40]; print("excluding <40deg: mean %.2f median %.2f" % (sub2.nees.mean(), sub2.nees.median()))
