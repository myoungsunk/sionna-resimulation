"""Audited non-destructive candidate. ONLY frozen ceiling-anchor R=diag(1,-1,-1), Rx Rz(yaw), 2deg 46x180x180 LUT."""
import numpy as np

def candidate_pole_consistent_table(original):
    s = np.asarray(original)
    if s.shape != (46, 180, 180) or s.dtype != np.float64 or not np.isfinite(s).all():
        raise ValueError("FROZEN_LUT_SCHEMA_UNSUPPORTED")
    if np.max(np.abs(s)) > 1 + 1e-12:
        raise ValueError("POLARIZATION_RATIO_OUT_OF_BOUNDS")
    if np.max(np.abs(s[0] - s[0, 0:1, :])) > 1e-12:
        raise ValueError("FROZEN_THETA_ZERO_COLLAPSE_NOT_PRESENT_OR_ALREADY_FIXED")
    j, k = np.indices((180, 180), dtype=np.int64)
    result = s.copy()
    # phi_tx + phi_rx = wrap(-180 - psi_ant); original theta0 uses v_az=-180.
    result[0, :, :] = s[0, 0, (j + k + 90) % 180]
    assert np.array_equal(result[1:, :, :], s[1:, :, :])
    return result
