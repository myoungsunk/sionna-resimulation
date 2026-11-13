"""v3.3 state validation, retaining the v3.2 candidate and KF update functions."""

import numpy as np

from v32_filter import _branch_update, candidate_features, wrap


def simulate(curve_at, dr, case_index, rho_by_case, calibration_by_case, *, e0_sd=0.0,
             w_sd=0.486, beta_sd=0.45, max_candidates=3, beta_rw_sd=0.0, gate=True):
    """Run §4.4 for paired DR trajectories, with a per-visit curve accessor.

    curve_at(visit_index) returns J, minimum-node chi2, valid pose counts,
    and optionally absolute truth headings (defaults to zero). dr holds
    unwrapped DR error relative to that truth. Both lookup models and LORO
    parameters are supplied by the caller, outside this filter.
    """
    dr = np.asarray(dr, dtype=np.float64)
    case_index = np.asarray(case_index)
    cases = np.unique(case_index)
    rho = np.array([rho_by_case[c] for c in case_index])
    sigma_a2 = rho * np.array([calibration_by_case[c].r_bar for c in case_index])
    x = np.zeros((len(dr), 3))
    f = np.broadcast_to(np.eye(3), (len(dr), 3, 3)).copy()
    f[:, 0, 1] = 1.0
    f[:, 2, 2] = rho
    q = np.zeros_like(f)
    q[:, 0, 0] = w_sd**2
    q[:, 1, 1] = beta_rw_sd**2
    q[:, 2, 2] = (1.0 - rho**2) * sigma_a2
    p = np.zeros_like(f)
    p[:, 0, 0] = e0_sd**2
    p[:, 1, 1] = beta_sd**2
    p[:, 2, 2] = sigma_a2
    err, nees, p_ee = (np.empty_like(dr) for _ in range(3))
    covered, miss, used, reject, invalid = (np.empty_like(dr, dtype=bool) for _ in range(5))
    masks = {c: case_index == c for c in cases}

    for k in range(dr.shape[1]):
        x = (f @ x[:, :, None])[:, :, 0]
        p = f @ p @ f.transpose(0, 2, 1) + q
        if not (np.isfinite(x).all() and np.isfinite(p).all() and np.all(p[:, 0, 0] > 0)):
            raise ValueError(f"Nonfinite prior or nonpositive raw P_EE at station {k+1}")
        inputs = curve_at(k)
        j, chi2, n_valid = inputs[:3]
        truth = np.broadcast_to(inputs[3] if len(inputs) == 4 else 0.0, (len(dr),))
        dr_absolute = truth + dr[:, k]
        center = dr_absolute - x[:, 0]
        half = np.minimum(180.0, np.maximum(3.0 * np.sqrt(np.maximum(p[:, 0, 0], 0.0)), 10.0))
        miss[:, k] = np.abs(wrap(center - truth)) > half
        features = candidate_features(j, chi2, n_valid, center, half, max_candidates)
        variance = np.full_like(features.r_raw, np.nan)
        for c, mask in masks.items():
            candidate = calibration_by_case[c]
            variance[mask] = (candidate.constant_r if candidate.constant_r is not None else
                              candidate.c_l * np.where(features.valid_curvature[mask],
                                                       features.r_raw[mask], candidate.cap_raw))
        x, p, used[:, k], reject[:, k], invalid[:, k] = _branch_update(
            x, p, features, variance, sigma_a2, dr_absolute, gate)
        if not (np.isfinite(x).all() and np.isfinite(p).all() and np.all(p[:, 0, 0] > 0)):
            raise ValueError(f"Nonfinite posterior or nonpositive raw P_EE at station {k+1}")
        p_ee[:, k] = p[:, 0, 0]
        err[:, k] = wrap(dr[:, k] - x[:, 0])
        nees[:, k] = err[:, k]**2 / p_ee[:, k]
        covered[:, k] = np.abs(err[:, k]) <= 1.96 * np.sqrt(p_ee[:, k])
    return dict(err=err, nees=nees, covered=covered, miss=miss, used=used, reject=reject,
                invalid=invalid, p_ee=p_ee)
