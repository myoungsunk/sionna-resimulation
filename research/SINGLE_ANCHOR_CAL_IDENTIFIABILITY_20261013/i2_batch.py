"""Independent latent-input batch posterior; never an automatic reference approval.

The target conditions on measured increments and assumes static calibration. It
does not reproduce a bounded-drift/slip generator's full likelihood. Every draw
uses the entire supplied observation horizon (smoothing, not online filtering).
"""
from __future__ import annotations

import numpy as np


class ConditionalBatchTarget:
    """Whitened pose/calibration prior and conditional shared-input noise target."""

    def __init__(self, public: dict, config: dict, arm: str):
        if arm not in ("DR", "RANGE"):
            raise ValueError("arm must be DR or RANGE")
        self.arm = arm
        self.t = np.asarray(public["t_s"], dtype=float)
        n = len(self.t)
        if n < 2 or self.t.ndim != 1 or not np.all(np.isfinite(self.t)) or np.any(np.diff(self.t) <= 0):
            raise ValueError("strictly increasing finite t_s required")
        arrays = {}
        for key in ("dt_s", "ds_odom", "dtheta_gyro", "dtheta_odom"):
            a = np.asarray(public[key], dtype=float)
            if a.shape != (n,) or not np.all(np.isfinite(a)):
                raise ValueError(f"invalid {key}")
            arrays[key] = a[1:]
        self.dt = arrays["dt_s"]
        if not np.allclose(self.dt, np.diff(self.t), rtol=1e-10, atol=1e-12):
            raise ValueError("dt_s differs from acquisition times")
        self.d, self.g, self.o = (arrays[k] for k in ("ds_odom", "dtheta_gyro", "dtheta_odom"))
        self.x0 = np.asarray(public["x0"], dtype=float)
        self.std = np.asarray(config["p0_std"], dtype=float)
        if self.x0.shape != (6,) or self.std.shape != (6,) or not np.all(np.isfinite(self.x0)) or not np.all(np.isfinite(self.std)) or np.any(self.std <= 0):
            raise ValueError("finite six-state prior with positive standard deviations required")
        self.b = float(config.get("wheel_base", .287))
        if not np.isfinite(self.b) or self.b <= 0 or config.get("known_wheelbase_error", 0) != 0:
            raise ValueError("positive wheelbase and known wheelbase error zero required")
        constants = np.array([config[k] for k in ("k_s", "k_theta", "k_stheta", "gyro_N_rad_sqrt_s")], dtype=float)
        if not np.all(np.isfinite(constants)) or np.any(constants < 0):
            raise ValueError("invalid noise constants")
        ks, kt, kst, gyro_n = constants
        self.qd = ks * np.abs(self.d)
        self.qg = gyro_n ** 2 * self.dt
        self.qo = kt * np.abs(self.o) + kst * np.abs(self.d)
        self.mask = np.asarray(public["range_mask"], dtype=bool)
        self.ranges = np.asarray(public["range_m"], dtype=float)
        if self.mask.shape != (n,) or self.ranges.shape != (n,):
            raise ValueError("range shapes differ")
        if arm == "RANGE" and not np.all(np.isfinite(self.ranges[self.mask])):
            raise ValueError("nonfinite observed range")
        self.anchor = np.asarray(config["anchor_xyz"], dtype=float)
        self.z = float(config["robot_z"])
        self.sigma = float(config["range_sigma"])
        if self.anchor.shape != (3,) or not np.all(np.isfinite(self.anchor)) or not np.isfinite(self.z) or not np.isfinite(self.sigma) or self.sigma <= 0:
            raise ValueError("invalid range model")

    def conditional(self, state: np.ndarray):
        bg, sf, eps = state[3:]
        den, level = 1 + sf, 1 - eps ** 2 / 4
        if den <= 0 or level <= 0 or not np.all(np.isfinite(state)):
            return None
        h = level * (self.g - bg * self.dt) / den + eps * self.d / self.b
        b1, b2 = -eps / self.b, -level / den
        s = b1 ** 2 * self.qd + b2 ** 2 * self.qg + self.qo
        if np.any(s <= 0) or not np.all(np.isfinite(s)):
            return None
        y = self.o - h
        c1, c2 = self.qd * b1, self.qg * b2
        rem = self.qo + b2 ** 2 * self.qg
        ld = np.sqrt(self.qd * rem / s)
        lgd = np.divide(-c1 * c2, s * ld, out=np.zeros_like(s), where=ld > 0)
        # Degenerate all-zero gyro/odom residual noise is rejected, not repaired.
        if np.any(rem <= 0):
            return None
        lgg = np.sqrt(self.qg * self.qo / rem)
        log_odo = -.5 * np.sum(np.log(2 * np.pi * s) + y ** 2 / s)
        return c1 * y / s, c2 * y / s, ld, lgd, lgg, float(log_odo)

    def evaluate(self, zparam: np.ndarray, znoise: np.ndarray, trajectory: bool = False):
        state = self.x0 + self.std * zparam
        cond = self.conditional(state)
        if cond is None:
            return (-np.inf, None) if trajectory else -np.inf
        md, mg, ld, lgd, lgg, loglike = cond
        nd = md + ld * znoise[0]
        ng = mg + lgd * znoise[0] + lgg * znoise[1]
        bg, sf, eps = state[3:]
        a = (self.g - ng - bg * self.dt) / (1 + sf)
        u = self.d - nd - eps * self.b * a / 4
        yaw = state[2] + np.r_[0., np.cumsum(a)]
        mid = yaw[:-1] + a / 2
        step = u * np.sinc(a / (2 * np.pi))
        x = state[0] + np.r_[0., np.cumsum(step * np.cos(mid))]
        y = state[1] + np.r_[0., np.cumsum(step * np.sin(mid))]
        poses = np.column_stack((x, y, yaw))
        if self.arm == "RANGE":
            distance = np.sqrt((x[self.mask] - self.anchor[0]) ** 2 + (y[self.mask] - self.anchor[1]) ** 2 + (self.z - self.anchor[2]) ** 2)
            residual = (self.ranges[self.mask] - distance) / self.sigma
            loglike += -.5 * np.sum(residual ** 2 + np.log(2 * np.pi * self.sigma ** 2))
        if not np.isfinite(loglike):
            loglike = -np.inf
        return (float(loglike), poses) if trajectory else float(loglike)


def chain_diagnostics(samples: np.ndarray) -> dict:
    """Classical split Rhat and initial-positive-pair autocorrelation ESS.

    Neither diagnostic is rank normalized; ESS is a within-chain mixing estimate
    and cannot rule out unvisited modes. Constants have undefined diagnostics.
    """
    m, n, p = samples.shape
    half = n // 2
    rhat, ess = [], []
    for j in range(p):
        a = samples[:, :, j]
        split = np.concatenate((a[:, :half], a[:, -half:]))
        w = np.mean(np.var(split, axis=1, ddof=1)) if half > 1 else 0
        if half < 2 or w <= 0:
            rhat.append(None)
            ess.append(None)
            continue
        between = half * np.var(np.mean(split, axis=1), ddof=1)
        variance = (half - 1) / half * w + between / half
        rhat.append(float(np.sqrt(variance / w)))
        centered = a - a.mean(axis=1, keepdims=True)
        fft = np.fft.rfft(centered, n=2 * n, axis=1)
        ac = np.fft.irfft(fft * fft.conj(), n=2 * n, axis=1)[:, :n]
        ac = np.mean(ac / np.arange(n, 0, -1), axis=0)
        rho = ac / ac[0] if ac[0] > 0 else np.zeros(n)
        pair_sum = 0.
        for k in range(1, n - 1, 2):
            pair = rho[k] + rho[k + 1]
            if pair <= 0:
                break
            pair_sum += pair
        ess.append(float(min(m * n, m * n / max(1., 1 + 2 * pair_sum))))
    return {"split_rhat": rhat, "within_chain_ess": ess,
            "method": "classical split Rhat; pooled within-chain initial-positive-pair ESS",
            "limitation": "not rank-normalized; cannot exclude unvisited modes"}


def batch_posterior(public: dict, config: dict, indices: list[int], arm: str,
                    seed: int, settings: dict) -> dict:
    target = ConditionalBatchTarget(public, config, arm)
    burn, retained, thin = (int(settings.get(k, d)) for k, d in (("burn", 500), ("retained", 500), ("thin", 2)))
    chains = int(settings.get("chains", 4))
    beta = float(settings.get("pCN_beta", .03))
    scale0 = float(settings.get("parameter_step", .08))
    if burn < 0 or retained < 4 or thin < 1 or chains < 2 or not 0 < beta <= 1 or scale0 <= 0:
        raise ValueError("invalid MCMC settings")
    snapshots = list(indices) if indices else [len(target.t) - 1]
    if any(i < 0 or i >= len(target.t) for i in snapshots):
        raise ValueError("snapshot index outside supplied horizon")
    samples, poses, acceptances = [], [], []
    for chain in range(chains):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 20261013, 220, chain]))
        zp = rng.normal(size=6)
        zn = rng.normal(size=(2, len(target.dt)))
        ll = target.evaluate(zp, zn)
        if not np.isfinite(ll):
            raise ValueError("initial chain state invalid")
        scale = scale0
        accepted = np.zeros(2, dtype=int)
        attempts = np.zeros(2, dtype=int)
        block_accepted = 0
        kept, path_kept = [], []
        for iteration in range(burn + retained * thin):
            proposal = zp + scale * rng.normal(size=6)
            proposed_ll = target.evaluate(proposal, zn)
            ratio = proposed_ll - ll - .5 * (proposal @ proposal - zp @ zp)
            ok = np.log(rng.random()) < ratio
            if ok:
                zp, ll = proposal, proposed_ll
            if iteration < burn:
                block_accepted += int(ok)
                if (iteration + 1) % 50 == 0:
                    # Adapt only during burn; retain target, not an inflated posterior.
                    scale *= np.exp(np.clip(block_accepted / 50 - .25, -.2, .2))
                    block_accepted = 0
            else:
                attempts[0] += 1
                accepted[0] += int(ok)
            noise_proposal = np.sqrt(1 - beta ** 2) * zn + beta * rng.normal(size=zn.shape)
            proposed_ll = target.evaluate(zp, noise_proposal)
            ok = np.log(rng.random()) < proposed_ll - ll
            if ok:
                zn, ll = noise_proposal, proposed_ll
            if iteration >= burn:
                attempts[1] += 1
                accepted[1] += int(ok)
                if (iteration - burn + 1) % thin == 0:
                    kept.append(target.x0 + target.std * zp)
                    _, path = target.evaluate(zp, zn, trajectory=True)
                    path_kept.append(path[snapshots])
        samples.append(kept)
        poses.append(path_kept)
        acceptances.append({"parameter": float(accepted[0] / attempts[0]),
                            "latent_pCN": float(accepted[1] / attempts[1]),
                            "frozen_parameter_step": float(scale)})
    samples = np.asarray(samples)
    return {"samples": samples, "calibration_samples": samples[:, :, 3:6],
            "pose_samples": np.asarray(poses), "snapshot_indices": snapshots,
            "acceptance": acceptances, "diagnostics": chain_diagnostics(samples),
            "chain_means": samples.mean(axis=1),
            "chain_quantiles": np.quantile(samples, [.025, .5, .975], axis=1),
            "reference_status": "REFERENCE_NOT_VALIDATED", "seed": int(seed),
            "target": "conditional measured-input likelihood, static calibration, full supplied horizon",
            "limitations": ["bounded drift, slip, and wheelbase mismatch not represented",
                            "Gaussian measured-input Q is an approximation to generator noise",
                            "MCMC diagnostics and multimode checks required before reference use",
                            "all snapshots condition on full supplied horizon"]}
