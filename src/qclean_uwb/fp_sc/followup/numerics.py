"""E3 extraction, residual attribution, calibration and one-update arithmetic."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Any
import numpy as np
from .contracts import ContractError, STEP_M, covariance, digest, finite


def cir_from_spectrum(H: np.ndarray) -> np.ndarray:
    h = np.asarray(H)
    if h.shape[-2:] != (257, 2) or not np.iscomplexobj(h) or not np.isfinite(h).all():
        raise ContractError("EXPECTED_FINITE_COMPLEX_257_2_SPECTRUM")
    w = .5 - .5*np.cos(2*np.pi*np.arange(257)/256.)
    return np.fft.ifft(h*w[:, None], n=1028, axis=-2)*257


def raw_detection(cir: np.ndarray):
    """Unchanged strongest-RX amplitude-30% rule, no candidate enumeration."""
    c = np.asarray(cir)
    if c.shape != (1028, 2) or not np.iscomplexobj(c):
        raise ContractError("EXPECTED_COMPLEX_CIR_1028_2")
    if not np.isfinite(c).all():
        return None, None, None
    magnitude = abs(c)
    rx = int(magnitude.max(axis=0).argmax())
    peak = float(magnitude[:, rx].max())
    if peak <= 0:
        return None, rx, None
    tap = int(np.flatnonzero(magnitude[:, rx] >= .3*peak)[0])
    return tap, rx, measurement(c, tap, tap)


def measurement(cir: np.ndarray, range_tap: int | None, pol_tap: int | None) -> np.ndarray | None:
    c = np.asarray(cir)
    if c.shape != (1028, 2) or not np.iscomplexobj(c):
        raise ContractError("EXPECTED_COMPLEX_CIR_1028_2")
    if range_tap is None or pol_tap is None:
        return None
    if not 0 <= range_tap < 1028 or not 0 <= pol_tap < 1028:
        raise ContractError("TAP_OUT_OF_RANGE")
    power = np.abs(c[pol_tap])**2
    den = float(power.sum())
    if not np.isfinite(power).all() or den <= 0:
        return None
    return np.array([range_tap*STEP_M, (power[0]-power[1])/den], dtype=float)


def factorial(cir: np.ndarray, raw: int | None, selected: int | None) -> dict:
    return {name: measurement(cir, r, s) for name, r, s in
            (("F00", raw, raw), ("F10", selected, raw),
             ("F01", raw, selected), ("F11", selected, selected))}


def residual_decomposition(full: np.ndarray, direct: np.ndarray,
                           raw: int, selected: int, reference: int) -> dict:
    f0, fs, fl, ll = (measurement(full, raw, raw), measurement(full, selected, selected),
                      measurement(full, reference, reference), measurement(direct, reference, reference))
    if any(x is None for x in (f0, fs, fl, ll)):
        return {"valid": False, "reason": "INVALID_POWER_DENOMINATOR"}
    same = fl - ll
    original_choice, selected_choice = f0-fl, fs-fl
    total0, total1 = f0-ll, fs-ll
    closure = max(float(np.max(np.abs(total0-same-original_choice))),
                  float(np.max(np.abs(total1-same-selected_choice))))
    if closure > 1e-12:
        raise ContractError("RESIDUAL_DECOMPOSITION_DID_NOT_CLOSE")
    return dict(valid=True, same_reference_tap=same, raw_choice=original_choice,
                selected_choice=selected_choice, total_raw=total0, total_selected=total1,
                closure_max=closure)


def update(x: np.ndarray, P: np.ndarray, h: np.ndarray, H: np.ndarray,
           z: np.ndarray, mu: np.ndarray, R: np.ndarray, *, permitted: bool = True) -> dict:
    x, h, H = finite(x, (4,), "STATE"), finite(h, (2,), "H_PRED"), finite(H, (2, 4), "JACOBIAN")
    P, R = covariance(P, 4), covariance(R, 2, positive=True)
    v = finite(z, (2,), "OBSERVATION") - h - finite(mu, (2,), "MEAN")
    S = covariance(H@P@H.T+R, 2, positive=True)
    pre_K = np.linalg.solve(S, H@P).T
    K = pre_K if permitted else np.zeros((4, 2))
    delta = K@v
    y = x+delta
    if permitted:
        y[2] = (y[2]+math.pi) % (2*math.pi)-math.pi
    A = np.eye(4)-K@H
    post = covariance(A@P@A.T+K@R@K.T, 4) if permitted else P.copy()
    return dict(x=y, P=post, K=K, pre_gate_K=pre_K, S=S, innovation=v,
                unwrapped_delta=delta, nis=float(v@np.linalg.solve(S, v)), accepted=bool(permitted))


def same_prior_factorial(x, P, h, H, observations: dict, mu, R, accepted: bool) -> dict:
    if any(z is None for z in observations.values()):
        return {"valid": False, "reason": "INVALID_MEASUREMENT"}
    results = {a: update(x, P, h, H, z, mu, R, permitted=accepted) for a, z in observations.items()}
    base = results["F00"]
    checks = {}
    for name, result in results.items():
        expected = base["K"]@(observations[name]-observations["F00"])
        actual = result["unwrapped_delta"]-base["unwrapped_delta"]
        checks[name] = {"K_delta_z_error": float(np.max(np.abs(expected-actual))),
                        "P_exact_equal": bool(np.array_equal(result["P"], base["P"]))}
    if any(c["K_delta_z_error"] > 1e-10 or not c["P_exact_equal"] for c in checks.values()):
        raise ContractError("FIXED_PRIOR_FACTORIAL_ARITHMETIC_FAIL")
    return {"valid": True, "checks": checks, "updates": results,
            "claim": "ONE_LIKELIHOOD_FIXED_PRIOR_MECHANISM_NOT_COVARIANCE_IMPROVEMENT"}


def residual_bin(changed: bool, confidence: float | None) -> str:
    if not changed:
        return "unchanged"
    return "changed_high" if confidence is not None and confidence >= .5 else "changed_low"


def fit_residual_model(residuals: np.ndarray, bins: list[str], sample_ids: list[str],
                       routes: list[str], *, target_route: str, split: str,
                       extractor: str, policy_sha: str, min_samples: int = 20,
                       variance_floor: tuple[float, float] = (1e-6, 1e-6),
                       domain: dict | None = None) -> dict:
    """Train residual delta-mean and FULL covariance in fixed-context strata.

    Residuals are z-h(xGT)-original_mu. Fitted covariance REPLACES original
    R and distance-dependent sigma, it is not added a second time. Context
    (selector decision) is held fixed in the Jacobian; this is disclosed, not
    a claim of an exact selection-independent Gaussian posterior.
    """
    e = np.asarray(residuals, dtype=float)
    if e.ndim != 2 or e.shape[1] != 2 or not np.isfinite(e).all():
        raise ContractError("INVALID_CALIBRATION_RESIDUALS")
    if not len(e) or len(e) != len(bins) or len(e) != len(sample_ids) or len(e) != len(routes):
        raise ContractError("CALIBRATION_LENGTH_MISMATCH")
    if split not in {"TRAIN", "CAL"} or target_route in routes:
        raise ContractError("CALIBRATION_LEAKAGE_OR_SEALED_FIT")
    if len(sample_ids) != len(set(sample_ids)) or min_samples < 2:
        raise ContractError("CALIBRATION_DUPLICATE_OR_INVALID_MINIMUM")
    if extractor not in {"F00", "F01", "F11"} or len(policy_sha) != 64:
        raise ContractError("CALIBRATION_IDENTITY_REQUIRED")
    floors = finite(variance_floor, (2,), "VARIANCE_FLOOR")
    if np.any(floors <= 0):
        raise ContractError("VARIANCE_FLOOR_MUST_BE_POSITIVE")
    strata = {}
    for key in sorted(set(bins)):
        indices = [i for i, b in enumerate(bins) if b == key]
        values = e[indices]
        if len(values) < min_samples:
            strata[key] = dict(status="INSUFFICIENT_SUPPORT", n=len(values))
            continue
        mean = values.mean(axis=0)
        empirical = np.cov(values.T, ddof=1)
        scale = np.sqrt(floors)
        standardized = empirical / scale[:, None] / scale[None, :]
        vals, vecs = np.linalg.eigh(standardized)
        R = ((vecs * np.maximum(vals, 1.)) @ vecs.T) * scale[:, None] * scale[None, :]
        covariance(R, 2, positive=True)
        strata[key] = dict(status="FIT", n=len(values), delta_mu=mean.tolist(), R=R.tolist(),
                           empirical_R=empirical.tolist(), eigen_floor_applied=bool(np.any(vals < 1.)))
    result = dict(schema="FP_SC_RESIDUAL_MODEL_V1", split=split, target_route=target_route,
                  training_routes=sorted(set(routes)), training_sample_ids=sorted(sample_ids),
                  measurement_domain=domain,
                  extractor=extractor, policy_sha=policy_sha, min_samples=min_samples,
                  strata=strata, covariance_mode="TOTAL_RESIDUAL_NO_EXTRA_SIGMA",
                  context_jacobian="DECISION_HELD_FIXED_NOT_GLOBALLY_DIFFERENTIABLE",
                  confidence_probability=False, external_independent_accept=False)
    result["sha256"] = digest(result)
    return result


def apply_residual_model(model: dict, *, target_route: str, extractor: str,
                         policy_sha: str, sample_id: str, bin_name: str,
                         original_mu: np.ndarray, domain: dict | None = None) -> tuple[np.ndarray, np.ndarray]:
    check = dict(model)
    signature = check.pop("sha256", None)
    if digest(check) != signature:
        raise ContractError("RESIDUAL_MODEL_HASH_MISMATCH")
    if (model["target_route"] != target_route or model["extractor"] != extractor or
            model["policy_sha"] != policy_sha or sample_id in model["training_sample_ids"] or
            target_route in model["training_routes"] or model["measurement_domain"] != domain):
        raise ContractError("RESIDUAL_MODEL_IDENTITY_OR_EXPOSURE_MISMATCH")
    if model["covariance_mode"] != "TOTAL_RESIDUAL_NO_EXTRA_SIGMA":
        raise ContractError("UNKNOWN_CALIBRATION_VARIANCE_SEMANTICS")
    b = model["strata"].get(bin_name, {})
    if b.get("status") != "FIT":
        raise ContractError(f"CALIBRATION_STRATUM_UNSUPPORTED:{bin_name}")
    return (finite(original_mu, (2,), "ORIGINAL_MEAN") + finite(b["delta_mu"], (2,), "DELTA_MEAN"),
            covariance(b["R"], 2, positive=True))


def inject_noise(H: np.ndarray, *, variance: float, namespace: str,
                 packet_id: str, seed: int) -> tuple[np.ndarray, str]:
    """Packet-keyed noise before Hann/IFFT. Policy/arm cannot advance RNG."""
    h = np.asarray(H)
    if h.shape != (257, 2) or not np.iscomplexobj(h) or not np.isfinite(h).all():
        raise ContractError("INVALID_NOISE_INPUT")
    if not math.isfinite(variance) or variance < 0 or not namespace:
        raise ContractError("INVALID_NOISE_RECIPE")
    identity = digest(dict(namespace=namespace, packet_id=packet_id, seed=int(seed)))
    rng = np.random.default_rng(int(identity[:16], 16))
    noise = math.sqrt(variance/2.)*(rng.standard_normal(h.shape)+1j*rng.standard_normal(h.shape))
    # Retain exact noise bytes identity as well as the seed namespace.
    import hashlib
    return h+noise, hashlib.sha256(np.ascontiguousarray(noise).tobytes()).hexdigest()


def stress_grid(base_noise_variance: float) -> list[dict]:
    if not math.isfinite(base_noise_variance) or base_noise_variance < 0:
        raise ContractError("INVALID_STRESS_VARIANCE")
    rows = [{"kind": "identity", "value": 0.}]
    for kind, values in (
        ("radial_m", (-.6, -.3, -.15, -.04, .04, .15, .3, .6)),
        ("tangential_m", (-.3, -.1, .1, .3)),
        ("yaw_deg", (-10., -5., -1., 1., 5., 10.)),
        ("P_radial_scale", (.25, 1., 4.)), ("P_heading_scale", (.25, 1., 4.)),
        ("missing_ticks", (2, 5, 10)), ("wrong_history_taps", (-2, 2)),
        ("snr_delta_db", (-6., 0., 6.)), ("null_cir", (1,))):
        rows.extend({"kind": kind, "value": v} for v in values)
    if base_noise_variance == 0:
        # A clean source has no finite original SNR. Do not invent an SNR baseline.
        rows = [r for r in rows if r["kind"] != "snr_delta_db"]
    return rows


def perturb_prior(x, P, anchor_xy, kind, value) -> tuple[np.ndarray, np.ndarray]:
    x, P = finite(x, (4,), "PRIOR").copy(), covariance(P, 4).copy()
    d = x[:2] - finite(anchor_xy, (2,), "ANCHOR")
    norm = float(np.linalg.norm(d))
    if norm <= 1e-12:
        raise ContractError("RADIAL_DIRECTION_UNDEFINED")
    u = d/norm
    tangent = np.array([-u[1], u[0]])
    if kind == "radial_m":
        x[:2] += value*u
    elif kind == "tangential_m":
        x[:2] += value*tangent
    elif kind == "yaw_deg":
        x[2] = (x[2]+math.radians(value)+math.pi) % (2*math.pi)-math.pi
    elif kind in {"P_radial_scale", "P_heading_scale"}:
        if value <= 0:
            raise ContractError("INVALID_COVARIANCE_SCALE")
        T = np.eye(4)
        if kind == "P_radial_scale":
            T[:2, :2] += (math.sqrt(value)-1.)*np.outer(u, u)
        else:
            T[2, 2] = math.sqrt(value)
        P = covariance(T@P@T.T, 4)
    elif kind != "identity":
        raise ContractError("UNKNOWN_PRIOR_STRESS")
    return x, P
