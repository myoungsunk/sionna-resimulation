"""Diagnostic only: iterated (IEKF) s update inside the augmented filter, same matched world as p1_deep.  Not a proposed model change."""
import sys, os, math, numpy as np, pandas as pd, multiprocessing as mp
sys.argv = ["x"]; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a24_p1_diagnosis as D, a24_p1_deep as P1
import qclean_uwb.drivesim.filters_aug as FA
from qclean_uwb.drivesim.filters import wrap, thermal_var_s
ITERS = int(os.environ.get("ITERS", "3"))

def update_s_iter(self, z, p1, p2):
    cfg = self.cfg; c = self.comps[0]
    thermal = thermal_var_s(p1, p2, cfg.noise_var_cir_tap) if cfg.noise_var_cir_tap > 0 else 0.0
    R = thermal + self.vw_s if self.aug_s else self._s_R(p1, p2, xy=c.x[:2], psi=c.x[2])
    x_prior, P_prior = c.x.copy(), c.P.copy(); xi = c.x.copy()
    for it in range(ITERS):
        h, J = FA.s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, xi[0], xi[1], xi[2], cfg.mount_deg, with_jac=True)
        H = np.zeros(self.D); H[:3] = J
        pred = float(h)
        if self.aug_s:
            H[self.i_s] = 1.0; pred += xi[self.i_s]
        dx = x_prior - xi; dx[2] = wrap(dx[2])
        y = z - pred - float(H @ dx)
        S = float(H @ P_prior @ H + R)
        if it == 0:
            nis = (z - (float(h) + (x_prior[self.i_s] if self.aug_s else 0.0))) ** 2 / S
            self.stats["nis_s"].append(nis)
            self.stats["s_log"].append((self.cur_k, nis, bool(self._gate_ok(nis)), float(z - float(h) - (x_prior[self.i_s] if self.aug_s else 0.0)), S, float(R), 0.0, float(z)))
            if not self._gate_ok(nis):
                self.stats["s_rejected"] += 1; return
        K = P_prior @ H / S
        xi = x_prior + K * y; xi[2] = wrap(xi[2])
    I_KH = np.eye(self.D) - np.outer(K, H)
    c.x, c.P = xi, I_KH @ P_prior @ I_KH.T + R * np.outer(K, K)
    self.stats["s_updates"] += 1

if __name__ == "__main__":
    FA.AugmentedDriveFilter.update_s = update_s_iter
    jobs = [(s, d, "F2") for s in range(20) for d in (0, 1, 2)]
    with mp.get_context("fork").Pool(4, initializer=D.init) as p:
        df = pd.concat(p.map(P1.run, jobs), ignore_index=True)
    df["nees"] = df.pos + df.hd; df["thb"] = pd.cut(df.th, [0, 15, 25, 40, 60, 90])
    print(f"IEKF iterations={ITERS}: eval samples {len(df)}  overall NEES mean {df.nees.mean():.2f} median {df.nees.median():.2f}; pos {df.pos.mean():.2f} head {df.hd.mean():.2f}; beta z-sd {df.zs.std():.2f}")
    print(df.groupby("thb", observed=True).agg(n=("nees", "size"), nees_mean=("nees", "mean"), nees_med=("nees", "median"), hd_mean=("hd", "mean"), zs_sd=("zs", "std")).round(2).to_string())
    runs = df.groupby(["seed", "drift"]).nees.mean(); print("per-run NEES quantiles", np.round(runs.quantile([.1, .25, .5, .75, .9, 1.0]).values, 1))
