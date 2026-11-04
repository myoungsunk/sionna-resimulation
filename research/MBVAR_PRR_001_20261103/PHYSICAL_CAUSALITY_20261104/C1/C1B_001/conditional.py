"""Truth-free same-prior BASE gate and conditional MB_VAR single update."""
import importlib.util
from pathlib import Path
import numpy as np

path = Path(__file__).resolve().parent.parent/'C1A_001/core.py'
spec = importlib.util.spec_from_file_location('c1a_frozen_update', path)
c1a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c1a)
ARMS = c1a.ARMS
GATE = 9.210340371976184


def observations(full, los):
    return np.array((full, [los[0], full[1]], [full[0], los[1]], los))


def joint_gate(z, h, H, P, mean, noise):
    innovation = z-h-mean
    S = H @ P @ H.T+noise
    if not all(np.isfinite(v).all() for v in (innovation, S)):
        raise ValueError('nonfinite BASE gate')
    # Original shadow uses the unsymmetrized S and scalar dot/solve per packet.
    nis = np.array([v @ np.linalg.solve(S, v) for v in innovation])
    if not np.isfinite(nis).all():
        raise ValueError('nonfinite BASE NIS')
    return nis <= GATE, nis, S


def update(prior, covariance, h, H, mean, noise, accepted, full, los):
    n = len(prior)
    if accepted.shape != (n, 4) or accepted.dtype != np.dtype(bool):
        raise ValueError('four boolean joint gates required')
    potential = c1a.update(prior, covariance, h, H, mean, noise,
                          np.ones(n, dtype=bool), full, los)
    return dict(
        x=np.where(accepted[:, :, None], potential['x'], prior[:, None, :]),
        u=np.where(accepted[:, :, None], potential['u'], prior[:, None, :]),
        P=np.where(accepted[:, :, None, None], potential['P'][:, None], covariance[:, None]),
        K=np.where(accepted[:, :, None, None], potential['K'][:, None], 0.),
        K_star=potential['K'], S=potential['S'])
