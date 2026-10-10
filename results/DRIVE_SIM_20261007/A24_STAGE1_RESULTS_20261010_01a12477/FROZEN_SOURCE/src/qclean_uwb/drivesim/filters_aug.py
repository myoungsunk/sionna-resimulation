"""A24: EKF with first-order Gauss-Markov measurement-bias states (legacy sensor model).

The stored 6-state filter (``filters.DriveFilter``) is not modified.  This subclass appends up to two states,

    beta_s : bias of the port ratio ``s``         z_s = h_LUT(x) + beta_s + v_s
    beta_r : bias of the first-path range         z_r = d(x) + offset + beta_r + v_r

each with ``beta_{k+1} = phi beta_k + eta_k``, ``Var(eta) = var_beta (1 - phi^2)`` (stationary variance ``var_beta``), initial mean 0 and
initial variance ``var_beta``, uncorrelated with the other states.  The measurement noise is the remaining white part: for ``s`` the thermal
term plus ``var_w`` (replacing the stored mismatch variance); for the range ``range_sigma**2`` (the known random UWB range component added by the
observation generator, which is not in the noise-free training residual) plus ``var_w`` (replacing the stored quantisation and 'extra' terms).

Every other equation (predict, odometry heading pseudo-measurement, gates, Joseph form, logging) is the stored one with the dimension
extended.  With ``aug_s = aug_r = False`` the arithmetic is the stored arithmetic on 6x6 arrays and the output is bit-identical to
``filters.run_filter`` (tested).  EKF with the direct-``s`` measurement only; other kinds raise.

``cfg.meas_state`` (dict)::

    aug_s, aug_r : bool
    s : dict(phi, var_beta, var_w)     r : dict(phi, var_beta, var_w)
    s_profile : None | (theta_geo_knots_deg, g_values)   # F3: var_beta_s(d) = var_beta * g(theta_geo) in the process noise
"""
from __future__ import annotations

import math

import numpy as np

from qclean_uwb.drivesim.filters import N, DriveFilter, FilterConfig, thermal_var_s, wrap
from qclean_uwb.drivesim.hs_lut import HsLut, s_model


def _spec(ms: dict, key: str) -> tuple[float, float, float]:
    d = ms[key]
    phi, vb, vw = float(d["phi"]), float(d["var_beta"]), float(d["var_w"])
    if not (0.0 <= phi < 1.0) or vb < 0.0 or vw < 0.0:
        raise ValueError(f"invalid measurement-state parameters for {key}: {d}")
    return phi, vb, vw


class AugmentedDriveFilter(DriveFilter):
    def __init__(self, cfg: FilterConfig, lut: HsLut | None, x0, P0=None):
        ms = cfg.meas_state
        if ms is None:
            raise ValueError("AugmentedDriveFilter needs cfg.meas_state")
        if cfg.kind != "ekf" or cfg.s_mode != "direct" or cfg.s_kind != "fp":
            raise ValueError("A24 supports the fp-s direct EKF only")
        super().__init__(cfg, lut, x0, P0)
        self.aug_s, self.aug_r = bool(ms.get("aug_s")), bool(ms.get("aug_r"))
        self.i_s = N if self.aug_s else None
        self.i_r = N + (1 if self.aug_s else 0) if self.aug_r else None
        self.D = N + int(self.aug_s) + int(self.aug_r)
        self.phi_s, self.vb_s, self.vw_s = _spec(ms, "s") if self.aug_s else (0.0, 0.0, 0.0)
        self.phi_r, self.vb_r, self.vw_r = _spec(ms, "r") if self.aug_r else (0.0, 0.0, 0.0)
        self.profile = ms.get("s_profile")
        c = self.comps[0]
        x = np.zeros(self.D)
        x[:N] = c.x
        P = np.zeros((self.D, self.D))
        P[:N, :N] = c.P
        if self.aug_s:
            P[self.i_s, self.i_s] = self.vb_s * self._g(c.x[:2])
        if self.aug_r:
            P[self.i_r, self.i_r] = self.vb_r
        c.x, c.P = x, P

    # ------------------------------------------------------------------ helpers
    def _g(self, xy) -> float:
        """F3 distance profile of the s-bias variance (1.0 when no profile)."""
        if self.profile is None:
            return 1.0
        a = self.cfg.anchor_xyz
        rho = math.hypot(xy[0] - a[0], xy[1] - a[1])
        theta_geo = math.degrees(math.atan2(rho, a[2] - self.cfg.robot_z))
        return float(np.interp(theta_geo, np.asarray(self.profile[0], float), np.asarray(self.profile[1], float)))

    def mean_cov(self):
        c = self.comps[0]
        return c.x.copy(), c.P.copy()

    def _apply(self, c, H, y, S, R):
        K = c.P @ H / S
        c.x = c.x + K * y
        c.x[2] = wrap(c.x[2])
        I_KH = np.eye(self.D) - np.outer(K, H)
        c.P = I_KH @ c.P @ I_KH.T + R * np.outer(K, K)

    # ------------------------------------------------------------------ predict (stored equations, dimension D)
    def predict(self, ds_o: float, dth_g: float):
        cfg = self.cfg
        q_s = cfg.k_s * abs(ds_o)
        D = self.D
        c = self.comps[0]
        x, P = c.x, c.P
        b, sf = x[3], x[4]
        th_prev = x[2]
        dth = (dth_g - b * cfg.dt) / (1.0 + sf)
        F = np.eye(D)
        F[0, 2], F[1, 2] = -ds_o * math.sin(th_prev), ds_o * math.cos(th_prev)
        F[2, 3], F[2, 4] = -cfg.dt / (1.0 + sf), -dth / (1.0 + sf)
        G = np.zeros((D, 2))
        G[0, 0], G[1, 0], G[2, 1] = math.cos(th_prev), math.sin(th_prev), 1.0 / (1.0 + sf)
        Qn = G @ np.diag([q_s, cfg.arw_var]) @ G.T
        Qn[3, 3] += cfg.bias_rw_std ** 2 * cfg.dt
        Qn[4, 4] += 1e-12
        Qn[5, 5] += 1e-12
        Qn[0, 0] += cfg.pos_process_std ** 2
        Qn[1, 1] += cfg.pos_process_std ** 2
        if self.aug_s:
            F[self.i_s, self.i_s] = self.phi_s
            Qn[self.i_s, self.i_s] += self.vb_s * self._g(x[:2]) * (1.0 - self.phi_s ** 2)
        if self.aug_r:
            F[self.i_r, self.i_r] = self.phi_r
            Qn[self.i_r, self.i_r] += self.vb_r * (1.0 - self.phi_r ** 2)
        c.P = F @ P @ F.T + Qn
        c.P = 0.5 * (c.P + c.P.T)
        x[0] += ds_o * math.cos(th_prev)
        x[1] += ds_o * math.sin(th_prev)
        x[2] = wrap(th_prev + dth)
        if self.aug_s:
            x[self.i_s] *= self.phi_s
        if self.aug_r:
            x[self.i_r] *= self.phi_r

    def predict_ukf(self, ds_o: float, dth_g: float):      # pragma: no cover - guarded by the constructor
        raise NotImplementedError

    # ------------------------------------------------------------------ updates
    def update_odom_heading(self, dth_o, dth_g, ds_o):
        cfg = self.cfg
        var = cfg.k_theta * abs(dth_o) + cfg.k_stheta * abs(ds_o) + cfg.arw_var
        c = self.comps[0]
        x = c.x
        h = x[5] * ds_o / cfg.wheel_base - x[4] * dth_g - x[3] * cfg.dt
        H = np.zeros(self.D)
        H[3], H[4], H[5] = -cfg.dt, -dth_g, ds_o / cfg.wheel_base
        y = (dth_o - dth_g) - h
        S = float(H @ c.P @ H + var)
        from qclean_uwb.drivesim.filters import CHI2_1_999
        if y * y / S > CHI2_1_999:
            self.stats["o_rejected"] += 1
            return
        K = c.P @ H / S
        c.x = x + K * y
        c.x[2] = wrap(c.x[2])
        I_KH = np.eye(self.D) - np.outer(K, H)
        c.P = I_KH @ c.P @ I_KH.T + var * np.outer(K, K)
        self.stats["o_updates"] += 1

    def update_range(self, z):
        cfg = self.cfg
        R = cfg.range_sigma ** 2 + self.vw_r if self.aug_r else cfg.range_sigma ** 2 + cfg.range_quant_var + cfg.range_extra_sigma ** 2
        a = cfg.anchor_xyz
        dz = a[2] - cfg.robot_z
        c = self.comps[0]
        x = c.x
        d = math.sqrt((x[0] - a[0]) ** 2 + (x[1] - a[1]) ** 2 + dz * dz)
        H = np.zeros(self.D)
        H[0], H[1] = (x[0] - a[0]) / d, (x[1] - a[1]) / d
        pred = d + cfg.range_offset
        if self.aug_r:
            H[self.i_r] = 1.0
            pred = pred + x[self.i_r]
        y = z - pred
        S = float(H @ c.P @ H + R)
        self.stats["r_log"].append((self.cur_k, y * y / S, bool(y * y / S <= cfg.gate), float(y), S, float(R), float(pred), float(z)))
        if y * y / S > cfg.gate:
            self.stats["r_rejected"] += 1
            return
        self._apply(c, H, y, S, R)
        self.stats["r_updates"] += 1

    def update_s(self, z, p1, p2):
        cfg = self.cfg
        c = self.comps[0]
        if self.aug_s:
            thermal = thermal_var_s(p1, p2, cfg.noise_var_cir_tap) if cfg.noise_var_cir_tap > 0 else 0.0
            R = thermal + self.vw_s
        else:
            R = self._s_R(p1, p2, xy=c.x[:2], psi=c.x[2])
        h, J = s_model(self.lut, cfg.anchor_xyz, cfg.robot_z, c.x[0], c.x[1], c.x[2], cfg.mount_deg, with_jac=True)
        H = np.zeros(self.D)
        H[:3] = J
        pred = float(h)
        if self.aug_s:
            H[self.i_s] = 1.0
            pred = pred + c.x[self.i_s]
        y = z - pred
        S = float(H @ c.P @ H + R)
        nis = y * y / S
        self.stats["nis_s"].append(nis)
        self.stats["s_log"].append((self.cur_k, nis, bool(self._gate_ok(nis)), float(y), S, float(R), float(pred), float(z)))
        if not self._gate_ok(nis):
            self.stats["s_rejected"] += 1
            return
        self._apply(c, H, y, S, R)
        self.stats["s_updates"] += 1


def run_filter_aug(cfg: FilterConfig, lut: HsLut | None, inputs: dict, obs: dict, flags: dict, x0, truth: dict | None = None, partial: dict | None = None) -> dict:
    """Same interface and loop as ``filters.run_filter``; returns the 6-state block plus ``beta_hat`` / ``beta_var`` (n, n_aug)."""
    n = len(inputs["ds_odom"])
    f = AugmentedDriveFilter(cfg, lut, x0)
    est = np.zeros((n, N))
    cov3 = np.zeros((n, 3, 3))
    cov6 = np.zeros((n, N, N))
    n_aug = f.D - N
    beta = np.zeros((n, n_aug))
    beta_var = np.zeros((n, n_aug))
    cross = np.zeros((n, n_aug, 3))                       # Cov(beta, [x, y, theta]) for the diagnostics
    if partial is not None:
        partial.update(est=est, cov3=cov3, cov6=cov6, k_done=-1)
    for k in range(n):
        f.cur_k = k
        if k > 0:
            ds, dg, do = inputs["ds_odom"][k], inputs["dtheta_gyro"][k], inputs["dtheta_odom"][k]
            f.predict(ds, dg)
            if cfg.use_odom_heading:
                f.update_odom_heading(do, dg, ds)
            if obs["detected"][k]:
                if cfg.use_range:
                    f.update_range(obs["range_m"][k] - 0.0)
                if cfg.use_s and not (cfg.skip_s_in_turn and flags["turn_phase"][k]):
                    f.update_s(obs["s"][k], obs["power"][k][0], obs["power"][k][1])
        m, P = f.mean_cov()
        est[k], cov3[k], cov6[k] = m[:N], P[:3, :3], P[:N, :N]
        if n_aug:
            beta[k], beta_var[k], cross[k] = m[N:], np.diag(P)[N:], P[N:, :3]
        if partial is not None:
            partial["k_done"] = k
    stats = {k: (v if k != "nis_s" else np.array(v)) for k, v in f.stats.items()}
    return dict(est=est, cov3=cov3, cov6=cov6, stats=stats, beta_hat=beta, beta_var=beta_var, beta_cross=cross)
