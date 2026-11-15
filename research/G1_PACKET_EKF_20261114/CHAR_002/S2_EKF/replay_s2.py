"""Offline G1-CHAR-002 S2 replay of frozen O30 packets."""

from dataclasses import dataclass
from pathlib import Path
import csv
import gzip
import hashlib
import json

import numpy as np
from scipy.optimize import least_squares


D_MAX = 10.89
NU = 2.63
ARMS = ("E0", "E1", "E2", "E3", "E4", "E5")


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_npz(path):
    with np.load(path, allow_pickle=False) as source:
        return {key: source[key] for key in source.files}


def wrap(yaw):
    return (yaw + np.pi) % (2 * np.pi) - np.pi


def geometry(states, spec):
    states = np.asarray(states)
    delta = np.asarray(spec["anchor"]) - np.concatenate(
        [states[..., :2], np.full((*states.shape[:-1], 1), spec["robot_z_m"])], axis=-1
    )
    distance = np.linalg.norm(delta, axis=-1)
    heading = np.mod(np.rad2deg(states[..., 2] - np.arctan2(delta[..., 1], delta[..., 0])), 180.)
    return distance, heading


@dataclass(frozen=True)
class Learned:
    loc: np.ndarray
    slope: float
    log_scale: np.ndarray
    exponent: float
    nu: float | None
    slots: np.ndarray

    @classmethod
    def load(cls, fit):
        supported = np.asarray(fit["bin_supported"], dtype=bool)
        if supported.shape != (12,) or not fit["success"]:
            raise ValueError("Invalid S1 model fit")
        return cls(np.asarray(fit["loc"]), fit["loc_slope_per_m"], np.asarray(fit["log_scale"]),
                   fit["k"], fit["nu"], np.where(supported, np.arange(12), 12))

    def predict(self, bearing, distance):
        slot = self.slots[np.minimum(np.asarray(bearing / 15., dtype=int), 11)]
        loc = self.loc[slot] if len(self.loc) > 1 else self.loc[0]
        log_scale = self.log_scale[slot] if len(self.log_scale) > 1 else self.log_scale[0]
        # The S1 power law is exactly the specified continuation above D_MAX.
        scale = np.exp(log_scale + self.exponent * np.log(distance / 4.))
        return loc + self.slope * (distance - 4.), scale


def fit_sweep(files, samples, s3):
    """Fit scaled e_s autocorrelation on fixed-position TEACH sweeps only."""
    lag, product = [], []
    n_sweeps = 0
    for file, sample in zip(files, samples, strict=True):
        with gzip.open(file, "rt", newline="") as stream:
            rows = {int(row["pose_id"]): row for row in csv.DictReader(stream)}
        stations = {}
        for row in json.loads(sample.read_bytes()):
            if row["set"] == "P-A_TEACH" and row["protocol"] == "dense49":
                error = rows[row["pose_id"]]
                if not np.allclose([float(error[k]) for k in ("x", "y", "yaw")],
                                   [row["x"], row["y"], row["yaw_body_deg"]], atol=1e-9, rtol=0.):
                    raise ValueError("TEACH sweep pose join mismatch")
                stations.setdefault(row["station_id"], []).append(error)
        for station in stations.values():
            yaw = np.deg2rad(np.array([float(row["yaw"]) for row in station]))
            if len(yaw) != 49 or len(np.unique(np.round(yaw, 9))) != 49:
                raise ValueError("A dense49 station does not contain 49 different yaw positions")
            xy = {(float(row["x"]), float(row["y"])) for row in station}
            if len(xy) != 1:
                raise ValueError("A dense49 station has multiple positions")
            d = np.array([float(row["d"]) for row in station])
            bearing = np.mod([float(row["rel_bearing"]) for row in station], 180.)
            es = np.array([float(row["e_s"]) for row in station]) / s3.predict(bearing, d)[1]
            es = es - es.mean()
            i, j = np.triu_indices(len(es), k=1)
            lag.extend(np.abs(wrap(yaw[i] - yaw[j])))
            product.extend(es[i] * es[j] / np.mean(es**2))
            n_sweeps += 1
    if n_sweeps == 0:
        raise ValueError("No dense49 TEACH sweep found")
    lag, product = np.asarray(lag), np.asarray(product)
    result = least_squares(lambda v: v[0] * np.exp(-lag / v[1]) - product,
                           [0.8, np.deg2rad(10.)], bounds=([0., 1e-6], [1., np.pi]))
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError("TEACH yaw fit did not converge")
    return {"correlated_share": float(result.x[0]), "ell_yaw_rad": float(result.x[1]),
            "ell_yaw_deg": float(np.rad2deg(result.x[1])), "sweeps": n_sweeps, "pairs": len(lag),
            "inputs": {str(file): sha(file) for file in (*files, *samples)},
            "estimator": "station-centered e_s divided by frozen S3 scale; normalize by station mean square; "
                         "least squares on all positive-lag pair products; amplitude plus exponential length"}


def student_variance(residual, projected_variance, variance, nu):
    for _ in range(3):
        weight = (nu + 1.) / (nu + residual**2 / (projected_variance + variance))
        variance /= weight
    return variance


def learned_replay(packet, controls, e0_mask, core, online, model, spec, arm, rfit, sfit, yawfit):
    augmented = arm == "E4"
    nx = 5 if augmented else 4
    x = np.r_[controls["x0"], 0., 0.] if augmented else np.r_[controls["x0"], 0.]
    P = np.eye(nx)
    P[:4, :4] = packet["P0"]
    n = len(packet["z"])
    arrays = {name: np.empty((n, *shape)) for name, shape in {
        "x": (nx,), "P": (nx, nx), "prior": (nx,), "Pprior": (nx, nx), "h": (2,), "H": (2, nx),
        "mu": (2,), "Rvar": (2, 2), "Reff": (2, 2), "K": (nx, 2), "nu": (2,),
        "prior_range": (), "prior_bearing_deg": (), "phi": (), "latent_scale": (),
    }.items()}
    previous = None
    for k, measurement in enumerate(packet["z"]):
        xp, pp = online.predict(core, x[:4], P[:4, :4], k, controls)
        distance, bearing = geometry(xp, spec)
        h, H = (v[0] for v in model.batch(xp[None], spec))
        mu_r, sigma_r = rfit.predict(bearing, distance)
        _, sigma_s = sfit.predict(bearing, distance)
        mu = np.array([mu_r, 0.])
        phi, latent_scale = 0., 0.
        if augmented:
            share = yawfit["correlated_share"]
            latent_scale = np.sqrt(share) * sigma_s
            # c is unit-scale. The physical error c_s = latent_scale * c.
            if previous is not None and np.linalg.norm(xp[:2] - previous[:2]) <= 0.02:
                phi = np.exp(-abs(wrap(xp[2] - previous[2])) / yawfit["ell_yaw_rad"])
            previous = xp.copy()
            cov = np.empty((5, 5))
            cov[:4, :4] = pp
            if k:
                _, F, _ = core.transition(x[:4], *(float(controls[key][k]) for key in ("ds", "gy", "dt")))
                cov[:4, 4] = (F @ P[:4, 4]) * phi
            else:
                cov[:4, 4] = 0.
            cov[4, :4] = cov[:4, 4]
            cov[4, 4] = 1. + phi**2 * (P[4, 4] - 1.)
            xp, pp = np.r_[xp, phi * x[4]], cov
            h = h + np.array([0., latent_scale * xp[4]])
            H = np.column_stack((H, [0., latent_scale]))
            sigma_s *= np.sqrt(1. - share)
        innovation = measurement - h - mu
        Rvar = np.diag([sigma_r**2, sigma_s**2])
        R = Rvar.copy()
        if arm in ("E3", "E4", "E5"):
            R[1, 1] = student_variance(innovation[1], H[1] @ pp @ H[1], R[1, 1],
                                       sfit.nu if arm == "E5" else NU)
        if not augmented:
            x, P, K, _ = online.joseph(xp, pp, H, innovation, R, e0_mask[k], 1.)
        elif e0_mask[k]:
            S = H @ pp @ H.T + R
            K = np.linalg.solve((S + S.T) * .5, H @ pp).T
            x = xp + K @ innovation
            x[2] = wrap(x[2])
            A = np.eye(nx) - K @ H
            P = A @ pp @ A.T + K @ R @ K.T
            P = (P + P.T) * .5
        else:
            x, P, K = xp, pp, np.zeros((nx, 2))
        values = (x, P, xp, pp, h, H, mu, Rvar, R, K, innovation, distance, bearing, phi, latent_scale)
        for key, value in zip(arrays, values, strict=True):
            arrays[key][k] = value
    arrays["mask"] = e0_mask.copy()
    validate_trace(arrays)
    return arrays


def validate_trace(trace):
    if not all(np.isfinite(array).all() for array in trace.values()):
        raise ValueError("Nonfinite trace")
    for key in ("P", "Pprior"):
        P = trace[key]
        if np.max(np.abs(P - P.swapaxes(-1, -2))) > 1e-12 or np.linalg.eigvalsh(P).min() < -1e-12:
            raise ValueError(f"Invalid covariance {key}")


def b0_reference(packet):
    archived = {key: packet["trace_" + key] for key in ("prior", "Pprior", "h", "H", "K", "Reff", "mask")}
    innovation = packet["z"] - archived["h"] - packet["muMB"]
    x = archived["prior"] + np.einsum("nij,nj->ni", archived["K"], innovation)
    x[archived["mask"], 2] = wrap(x[archived["mask"], 2])
    A = np.eye(4) - archived["K"] @ archived["H"]
    P = A @ archived["Pprior"] @ A.swapaxes(-1, -2) + archived["K"] @ archived["Reff"] @ archived["K"].swapaxes(-1, -2)
    return {**archived, "x": x, "P": (P + P.swapaxes(-1, -2)) * .5}


def parity(actual, expected):
    errors = {}
    for key, value in expected.items():
        compared = actual[key]
        if compared.shape != value.shape:
            raise ValueError(f"Parity shape mismatch for {key}")
        difference = np.abs(compared.astype(float) - value.astype(float))
        maximum = float(np.max(difference / np.maximum(1., np.abs(value))))
        errors[key] = {"max_abs_error": float(difference.max()), "max_normalized_error": maximum}
        if not np.isfinite(maximum) or maximum > 1e-10 or (value.dtype.kind == "b" and maximum != 0.):
            raise ValueError(f"Parity failed on {key}: {maximum:.17g}")
    return errors
