"""S5 filters for the corridor drive: EKF, iterated EKF, UKF and a Gaussian-sum EKF.

State ``[x, y, theta, b_g, SF_g, eps_d]`` (body position, body yaw, gyro bias [rad/s], gyro scale-factor error, wheel diameter-ratio error).
Per 5 Hz sample (inputs describe the step from the previous sample):

* predict: position moves by the odometer distance along the *previous* heading (the convention of the scripted truth),
  heading by the bias/scale-corrected gyro increment ``(dth_g - b dt)/(1+SF)``;
* odometry heading pseudo-measurement ``dth_o - dth_g = eps_d ds/b - SF dth_g - b dt`` (identifies b_g, SF_g, eps_d), slip-gated;
* UWB range ``|p - anchor| + range_offset``;
* the port ratio ``s`` against the LoS-only LUT (``hs_lut.s_model``), NIS-gated (chi2_1 99 %).

Every update is gated with the same chi-square rule; rejected updates are counted.  Nothing here reads the truth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from qclean_uwb.drivesim.hs_lut import HsLut, s_model

CHI2_1_99 = 6.6349
CHI2_1_999 = 10.8276
N = 6


@dataclass
class FilterConfig:
    kind: str = "ekf"                    # ekf | iekf | ukf | gsf
    use_range: bool = True
    use_s: bool = True
    use_odom_heading: bool = True        # False: heading from the gyro only (odometry used for distance)
    s_mode: str = "direct"               # direct (LUT measurement) | inverse (heading pseudo-measurement from inverting s)
    skip_s_in_turn: bool = False         # P0-noturn
    mount_deg: float = 0.0
    anchor_xyz: tuple = (4.0, 0.0, 2.65)
    robot_z: float = 0.45
    dt: float = 0.2
    wheel_base: float = 0.287
    p0_std: tuple = (0.1, 0.1, math.radians(5.0), math.radians(0.12), 0.0104, 0.0064)     # PREREG_AMENDMENTS A5
    bias_rw_std: float = math.radians(1e-3)          # rad/s/sqrt(s)
    pos_process_std: float = 0.0                     # extra position random walk per step [m] (slack for unmodelled odometry/range errors)
    s_mismatch_sigma: float = 0.09                   # model-mismatch part of R_s (S4 reports the measured value)
    range_extra_sigma: float = 0.05
    range_quant_var: float = (299792458.0 / (1028 * 1.953125e6)) ** 2 / 12.0
    range_offset: float = 0.0
    arw_var: float = math.radians(0.015) ** 2 * 0.2
    k_s: float = 2e-5
    k_theta: float = 1e-4
    k_stheta: float = 1e-5
    range_sigma: float = 0.05
    noise_var_cir_tap: float = 0.0                   # 6 * noise_var of the observation chain (thermal part of R_s); 0 -> none
    s_kind: str = "fp"                               # fp: first-path power ratio | rx: total received power ratio (A11, exploratory)
    noise_var_bin: float = 0.0                       # per-bin complex noise variance (used by the rx thermal term)
    n_bins: int = 257
    iekf_iters: int = 3
    gsf_components: int = 5
    gsf_prune: float = 1e-4
    ukf_alpha: float = 0.4
    inverse_min_slope_per_deg: float = 0.01
    gate: float = CHI2_1_99


def wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def thermal_var_s(p1: float, p2: float, tap_var: float) -> float:
    """Delta-method variance of s = (P1-P2)/(P1+P2) for tap noise variance ``tap_var`` (8 var P1 P2 / (P1+P2)^3)."""
    tot = p1 + p2
    return 8.0 * tap_var * p1 * p2 / tot ** 3 if tot > 0 else float("inf")


class Component:
    __slots__ = ("w", "x", "P")

    def __init__(self, w, x, P):
        self.w, self.x, self.P = w, x, P


class DriveFilter:
    def __init__(self, cfg: FilterConfig, lut: HsLut | None, x0, P0=None):
        self.cfg, self.lut = cfg, lut
        P = np.diag(np.array(cfg.p0_std, float) ** 2) if P0 is None else P0
        self.comps = [Component(1.0, np.array(x0, float), P)]
        self.stats = dict(s_updates=0, s_rejected=0, r_updates=0, r_rejected=0, o_updates=0, o_rejected=0, nis_s=[])
        if cfg.kind == "gsf":
            self.reseed()

    # ---------------------------------------------------------------- mixture helpers
    def mean_cov(self):
        w = np.array([c.w for c in self.comps])
        xs = np.array([c.x for c in self.comps])
        if len(xs) == 1:
            return xs[0].copy(), self.comps[0].P.copy()
        th = xs[:, 2]
        ref = th[np.argmax(w)]
        d = wrap(th - ref)
        mean = (w[:, None] * xs).sum(0)
        mean[2] = ref + (w * d).sum()
        cov = np.zeros((N, N))
        for wi, c in zip(w, self.comps):
            dx = c.x - mean
            dx[2] = wrap(c.x[2] - mean[2])
            cov += wi * (c.P + np.outer(dx, dx))
        return mean, cov

    def reseed(self, std_theta: float | None = None):
        """Moment-preserving split of the (collapsed) Gaussian into ``gsf_components`` components spread along the heading.

        The component means are shifted along ``u = P[:, 2] / sqrt(P[2, 2])`` (heading shift z_i*sigma, correlated position shift), and every
        component keeps ``P_c = P - t u u^T`` with ``t = sum_i w_i z_i^2`` (capped at 0.95).  ``P - u u^T`` is the Schur complement of the heading
        variance, hence PSD, so ``P_c`` is PSD for every ``t <= 1`` including the position-heading cross terms (A15: the earlier version shrank
        only ``P[2, 2]`` and could produce an indefinite matrix).  When the cap is active the shift is scaled by ``sqrt(cap / t)`` so that the
        mixture mean and covariance still equal the input exactly.
        """
        mean, cov = self.mean_cov()
        if std_theta is not None:
            cov = cov.copy()
            cov[2, 2] = max(cov[2, 2], std_theta ** 2)
        k = self.cfg.gsf_components
        z = np.linspace(-1.5, 1.5, k)
        w = np.exp(-0.5 * z ** 2)
        w /= w.sum()
        var_between = float((w * z ** 2).sum())
        sig = math.sqrt(max(cov[2, 2], 1e-12))
        u = cov[:, 2] / sig
        t_cap = 0.95
        kappa = min(1.0, math.sqrt(t_cap / var_between)) if var_between > 0 else 1.0
        P_c = cov - var_between * kappa ** 2 * np.outer(u, u)
        P_c = 0.5 * (P_c + P_c.T)
        self.comps = [Component(float(wi), mean + zi * kappa * u, P_c.copy()) for zi, wi in zip(z, w)]

    # ---------------------------------------------------------------- predict
    def predict(self, ds_o: float, dth_g: float):
        cfg = self.cfg
        q_s = cfg.k_s * abs(ds_o)
        for c in self.comps:
            x, P = c.x, c.P
            b, sf = x[3], x[4]
            th_prev = x[2]
            dth = (dth_g - b * cfg.dt) / (1.0 + sf)
            F = np.eye(N)
            F[0, 2], F[1, 2] = -ds_o * math.sin(th_prev), ds_o * math.cos(th_prev)
            F[2, 3], F[2, 4] = -cfg.dt / (1.0 + sf), -dth / (1.0 + sf)
            G = np.zeros((N, 2))
            G[0, 0], G[1, 0], G[2, 1] = math.cos(th_prev), math.sin(th_prev), 1.0 / (1.0 + sf)
            Qn = G @ np.diag([q_s, cfg.arw_var]) @ G.T
            Qn[3, 3] += cfg.bias_rw_std ** 2 * cfg.dt
            Qn[4, 4] += 1e-12
            Qn[5, 5] += 1e-12
            Qn[0, 0] += cfg.pos_process_std ** 2
            Qn[1, 1] += cfg.pos_process_std ** 2
            c.P = F @ P @ F.T + Qn
            c.P = 0.5 * (c.P + c.P.T)
            x[0] += ds_o * math.cos(th_prev)
            x[1] += ds_o * math.sin(th_prev)
            x[2] = wrap(th_prev + dth)

    def predict_ukf(self, ds_o: float, dth_g: float):
        cfg = self.cfg
        c = self.comps[0]
        q_s = cfg.k_s * abs(ds_o)
        pts, wm, wc = self._sigma(c.x, c.P)
        out = np.empty_like(pts)
        for i, x in enumerate(pts):
            th_prev = x[2]
            out[i] = x
            out[i, 0] = x[0] + ds_o * math.cos(th_prev)
            out[i, 1] = x[1] + ds_o * math.sin(th_prev)
            out[i, 2] = th_prev + (dth_g - x[3] * cfg.dt) / (1.0 + x[4])
        mean = self._wmean(out, wm, c.x[2])
        d = out - mean
        d[:, 2] = wrap(out[:, 2] - mean[2])
        P = (wc[:, None, None] * d[:, :, None] * d[:, None, :]).sum(0)
        th_prev, sf = c.x[2], c.x[4]
        G = np.zeros((N, 2))
        G[0, 0], G[1, 0], G[2, 1] = math.cos(th_prev), math.sin(th_prev), 1.0 / (1.0 + sf)
        Qn = G @ np.diag([q_s, cfg.arw_var]) @ G.T
        Qn[3, 3] += cfg.bias_rw_std ** 2 * cfg.dt
        Qn[4, 4] += 1e-12
        Qn[5, 5] += 1e-12
        Qn[0, 0] += cfg.pos_process_std ** 2
        Qn[1, 1] += cfg.pos_process_std ** 2
        c.x, c.P = mean, 0.5 * (P + Qn + (P + Qn).T)

    # ---------------------------------------------------------------- generic measurement updates
    def _gate_ok(self, nis: float) -> bool:
        return nis <= self.cfg.gate

    def _ekf_update(self, c: Component, z, h, H, R, wrap_idx=None):
        y = z - h
        if wrap_idx is not None:
            y = wrap(y)
        S = float(H @ c.P @ H + R)
        return y, S

    def update_odom_heading(self, dth_o, dth_g, ds_o):
        cfg = self.cfg
        var = cfg.k_theta * abs(dth_o) + cfg.k_stheta * abs(ds_o) + cfg.arw_var
        for c in self.comps:
            x = c.x
            h = x[5] * ds_o / cfg.wheel_base - x[4] * dth_g - x[3] * cfg.dt
            H = np.zeros(N)
            H[3], H[4], H[5] = -cfg.dt, -dth_g, ds_o / cfg.wheel_base
            y = (dth_o - dth_g) - h
            S = float(H @ c.P @ H + var)
            if y * y / S > CHI2_1_999:
                self.stats["o_rejected"] += 1
                continue
            K = c.P @ H / S
            c.x = x + K * y
            c.x[2] = wrap(c.x[2])
            I_KH = np.eye(N) - np.outer(K, H)
            c.P = I_KH @ c.P @ I_KH.T + var * np.outer(K, K)
            self.stats["o_updates"] += 1

    def _range_model(self, x, y):
        a = self.cfg.anchor_xyz
        dz = a[2] - self.cfg.robot_z
        d = np.sqrt((x - a[0]) ** 2 + (y - a[1]) ** 2 + dz * dz)
        return d + self.cfg.range_offset

    def update_range(self, z):
        cfg = self.cfg
        R = cfg.range_sigma ** 2 + cfg.range_quant_var + cfg.range_extra_sigma ** 2
        if cfg.kind == "ukf":
            return self._ukf_update(lambda pts: self._range_model(pts[:, 0], pts[:, 1]), z, R, "r")
        a = cfg.anchor_xyz
        dz = a[2] - cfg.robot_z
        for c in self.comps:
            x = c.x
            d = math.sqrt((x[0] - a[0]) ** 2 + (x[1] - a[1]) ** 2 + dz * dz)
            H = np.zeros(N)
            H[0], H[1] = (x[0] - a[0]) / d, (x[1] - a[1]) / d
            y = z - (d + cfg.range_offset)
            S = float(H @ c.P @ H + R)
            if y * y / S > cfg.gate:
                self.stats["r_rejected"] += 1
                continue
            self._apply(c, H, y, S, R)
            self.stats["r_updates"] += 1

    def _apply(self, c, H, y, S, R):
        K = c.P @ H / S
        c.x = c.x + K * y
        c.x[2] = wrap(c.x[2])
        I_KH = np.eye(N) - np.outer(K, H)
        c.P = I_KH @ c.P @ I_KH.T + R * np.outer(K, K)

    def _s_R(self, p1, p2):
        cfg = self.cfg
        if cfg.s_kind == "rx":
            from qclean_uwb.drivesim.observation import thermal_var_rx_s
            thermal = thermal_var_rx_s(p1, p2, cfg.noise_var_bin, cfg.n_bins) if cfg.noise_var_bin > 0 else 0.0
        else:
            thermal = thermal_var_s(p1, p2, cfg.noise_var_cir_tap) if cfg.noise_var_cir_tap > 0 else 0.0
        return thermal + cfg.s_mismatch_sigma ** 2

    def update_s(self, z, p1, p2):
        cfg = self.cfg
        R = self._s_R(p1, p2)
        if cfg.s_mode == "inverse":
            return self._update_inverse_heading(z, R)
        if cfg.kind == "ukf":
            return self._ukf_update(lambda pts: s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, pts[:, 0], pts[:, 1], pts[:, 2], cfg.mount_deg), z, R, "s")
        if cfg.kind == "gsf":
            return self._gsf_update_s(z, R)
        c = self.comps[0]
        x_prior, P_prior = c.x.copy(), c.P.copy()
        xi = c.x.copy()
        iters = cfg.iekf_iters if cfg.kind == "iekf" else 1
        for it in range(iters):
            h, J = s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, xi[0], xi[1], xi[2], cfg.mount_deg, with_jac=True)
            H = np.zeros(N)
            H[:3] = J
            y = z - float(h) - float(H @ wrap_vec(x_prior - xi))
            S = float(H @ P_prior @ H + R)
            if it == 0:
                nis = y * y / S
                self.stats["nis_s"].append(nis)
                if not self._gate_ok(nis):
                    self.stats["s_rejected"] += 1
                    return
            K = P_prior @ H / S
            xi = x_prior + K * y
            xi[2] = wrap(xi[2])
        I_KH = np.eye(N) - np.outer(K, H)
        c.x, c.P = xi, I_KH @ P_prior @ I_KH.T + R * np.outer(K, K)
        self.stats["s_updates"] += 1

    def _gsf_update_s(self, z, R):
        cfg = self.cfg
        like, upd = [], []
        for c in self.comps:
            h, J = s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, c.x[0], c.x[1], c.x[2], cfg.mount_deg, with_jac=True)
            H = np.zeros(N)
            H[:3] = J
            y = z - float(h)
            S = max(float(H @ c.P @ H + R), 1e-12)
            like.append((y * y / S, math.exp(-0.5 * y * y / S) / math.sqrt(2 * math.pi * S)))
            upd.append((H, y, S))
        nis_min = min(v[0] for v in like)
        self.stats["nis_s"].append(nis_min)
        if nis_min > cfg.gate:
            self.stats["s_rejected"] += 1
            return
        for c, (nis, lk), (H, y, S) in zip(self.comps, like, upd):
            c.w *= max(lk, 1e-300)
            self._apply(c, H, y, S, R)
        tot = sum(c.w for c in self.comps)
        for c in self.comps:
            c.w /= tot
        self.comps = [c for c in self.comps if c.w > cfg.gsf_prune] or self.comps
        tot = sum(c.w for c in self.comps)
        for c in self.comps:
            c.w /= tot
        self.stats["s_updates"] += 1

    def _update_inverse_heading(self, z, R):
        """Baseline: invert s for the antenna yaw (candidate closest to the current heading) and use it as a heading measurement."""
        cfg = self.cfg
        c = self.comps[0]
        grid = np.radians(np.arange(-180.0, 180.0, 0.5))
        s_grid = s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, c.x[0], c.x[1], grid - math.radians(cfg.mount_deg), cfg.mount_deg)
        # s_model takes body yaw; the grid above is antenna yaw - mount = body yaw
        body = grid - math.radians(cfg.mount_deg)
        diff = s_grid - z
        cand = []
        for i in range(len(grid)):
            j = (i + 1) % len(grid)
            if diff[i] == 0.0 or diff[i] * diff[j] < 0:
                t = diff[i] / (diff[i] - diff[j]) if diff[i] != diff[j] else 0.0
                cand.append((body[i] + t * wrap(body[j] - body[i]), (s_grid[j] - s_grid[i]) / math.degrees(wrap(body[j] - body[i]))))
        if not cand:
            self.stats["s_rejected"] += 1
            return
        best = min(cand, key=lambda ct: abs(wrap(ct[0] - c.x[2])))
        slope = abs(best[1])
        if slope < cfg.inverse_min_slope_per_deg:
            self.stats["s_rejected"] += 1
            return
        Rh = R / (slope * 180.0 / math.pi) ** 2
        H = np.zeros(N)
        H[2] = 1.0
        y = wrap(best[0] - c.x[2])
        S = float(H @ c.P @ H + Rh)
        nis = y * y / S
        self.stats["nis_s"].append(nis)
        if not self._gate_ok(nis):
            self.stats["s_rejected"] += 1
            return
        self._apply(c, H, y, S, Rh)
        self.stats["s_updates"] += 1

    # ---------------------------------------------------------------- UKF helpers
    def _sigma(self, x, P):
        n = N
        lam = self.cfg.ukf_alpha ** 2 * n - n
        L = np.linalg.cholesky(0.5 * (P + P.T) + 1e-15 * np.eye(n))
        s = math.sqrt(n + lam)
        pts = [x] + [x + s * L[:, i] for i in range(n)] + [x - s * L[:, i] for i in range(n)]
        wm = np.full(2 * n + 1, 0.5 / (n + lam))
        wc = wm.copy()
        wm[0] = lam / (n + lam)
        wc[0] = wm[0] + (1.0 - self.cfg.ukf_alpha ** 2 + 2.0)
        return np.array(pts), wm, wc

    @staticmethod
    def _wmean(pts, wm, th_ref):
        mean = (wm[:, None] * pts).sum(0)
        mean[2] = th_ref + (wm * wrap(pts[:, 2] - th_ref)).sum()
        return mean

    def _ukf_update(self, hfun, z, R, kind):
        c = self.comps[0]
        pts, wm, wc = self._sigma(c.x, c.P)
        zs = np.asarray(hfun(pts), float)
        zbar = float((wm * zs).sum())
        S = float((wc * (zs - zbar) ** 2).sum() + R)
        d = pts - c.x
        d[:, 2] = wrap(pts[:, 2] - c.x[2])
        Pxz = (wc[:, None] * d * (zs - zbar)[:, None]).sum(0)
        y = z - zbar
        nis = y * y / S
        if kind == "s":
            self.stats["nis_s"].append(nis)
        if not self._gate_ok(nis):
            self.stats["s_rejected" if kind == "s" else "r_rejected"] += 1
            return
        K = Pxz / S
        c.x = c.x + K * y
        c.x[2] = wrap(c.x[2])
        c.P = c.P - S * np.outer(K, K)
        c.P = 0.5 * (c.P + c.P.T)
        self.stats["s_updates" if kind == "s" else "r_updates"] += 1


def wrap_vec(v):
    v = np.array(v, float)
    v[2] = wrap(v[2])
    return v


def run_filter(cfg: FilterConfig, lut: HsLut | None, inputs: dict, obs: dict, flags: dict, x0, truth: dict | None = None) -> dict:
    """Run one filter over a timeline.

    inputs: dtheta_gyro, ds_odom, dtheta_odom (n,);  obs: s, range_m, detected, power (n,2);  flags: turn_phase (n,) bool.
    Returns estimates and covariance blocks per sample (+ NEES/NIS statistics when ``truth`` is given).
    """
    n = len(inputs["ds_odom"])
    f = DriveFilter(cfg, lut, x0)
    est = np.zeros((n, N))
    cov3 = np.zeros((n, 3, 3))
    turn_prev = False
    for k in range(n):
        if k > 0:
            ds, dg, do = inputs["ds_odom"][k], inputs["dtheta_gyro"][k], inputs["dtheta_odom"][k]
            if cfg.kind == "ukf":
                f.predict_ukf(ds, dg)
            else:
                f.predict(ds, dg)
            if cfg.use_odom_heading:
                f.update_odom_heading(do, dg, ds)
            if cfg.kind == "gsf" and turn_prev and not flags["turn_phase"][k]:
                f.reseed(std_theta=math.radians(5.0))
            if obs["detected"][k]:
                if cfg.use_range:
                    f.update_range(obs["range_m"][k] - 0.0)
                if cfg.use_s and not (cfg.skip_s_in_turn and flags["turn_phase"][k]):
                    f.update_s(obs["s"][k], obs["power"][k][0], obs["power"][k][1])
        turn_prev = bool(flags["turn_phase"][k])
        m, P = f.mean_cov()
        est[k], cov3[k] = m, P[:3, :3]
    out = dict(est=est, cov3=cov3, stats={k: (v if k != "nis_s" else np.array(v)) for k, v in f.stats.items()})
    return out
