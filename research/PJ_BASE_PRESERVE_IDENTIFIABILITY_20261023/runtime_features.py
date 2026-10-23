"""Observable-only, current-packet feature construction. Never imports oracle_scoring."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import numpy as np
from .common import Packet, BASE_FEATURES, OFFSETS, require, digest
from .numerics import finite_jacobian, masked_projector

SCALE = np.array([0.05, 0.05, np.deg2rad(5.0)])


def profile_features(packet, x, model, omega, *, representation='own_fp', heading_only=False):
    fixed_fp = packet.fp if representation == 'measured_fp' else None
    q, valid, fp = model.profile(x, fixed_fp=fixed_fp)
    def func(xx):
        return model.profile(xx, fixed_fp=fixed_fp)[0]
    J = finite_jacobian(func, x)
    cols = [2] if heading_only else [0, 1, 2]
    mask = packet.profile_valid & valid & np.isfinite(J).all(1)
    d = packet.profile - q
    u, info = masked_projector(d, J[:, cols], omega, SCALE[cols], mask)
    return u, dict(**info, model_fp=int(fp), measured_fp=int(packet.fp), representation=representation,
                   valid_mask=mask.tolist()), (d, J, mask)


def feature_names(mode):
    names = list(BASE_FEATURES)
    if mode in ('PCIR3', 'CIR_ONLY'):
        return names
    names += ['dB' if mode in ('P2_DB', 'P3_VS', 'P4_PERP', 'P4_SHUFFLE', 'P5_CROSSFIT') else 'd0']
    if mode.startswith('P') and mode not in ('PWIDE_NOES', 'P0', 'PCIR3'):
        names += ['mu_s']
    if mode == 'P3_VS':
        names += ['V_s']
    if mode in ('P4_PERP', 'P4_SHUFFLE'):
        names += [f'u_perp_{o:+d}' for o in OFFSETS]
    return names


def build_features(packet: Packet, x, h, model, mode, omega=None):
    d0 = float(packet.z[1] - h[1]); db = d0 - float(packet.mu[1])
    values = list(packet.cir_features); flags = {'profile_status': 'NOT_USED'}
    if mode not in ('PCIR3', 'CIR_ONLY'):
        values += [db if mode in ('P2_DB', 'P3_VS', 'P4_PERP', 'P4_SHUFFLE', 'P5_CROSSFIT') else d0]
    if mode.startswith('P') and mode not in ('PWIDE_NOES', 'P0', 'PCIR3'):
        values += [float(packet.mu[1])]
    if mode == 'P3_VS':
        values += [float(packet.R[1, 1])]
    if mode in ('P4_PERP', 'P4_SHUFFLE'):
        require(omega is not None, 'Training-only profile covariance missing')
        u, info, _ = profile_features(packet, x, model, omega)
        values += list(u); flags.update(profile_status=info['status'], profile_valid=info.get('valid_mask'), projector=info)
    out = np.array(values, float)
    require(len(out) == len(feature_names(mode)), 'Feature order/length mismatch')
    return out, flags


@dataclass
class Corrector:
    name: str
    estimator: object | None = None
    mode: str = 'BASE'
    medians: np.ndarray | None = None
    omega: np.ndarray | None = None
    model_hash: str = 'NONE'
    diagnostic: bool = False
    mean_convention: str = 'incremental'

    def __call__(self, packet, x, h, model):
        if self.estimator is None:
            return 0.0, {'profile_status': 'NOT_USED'}
        values, flags = build_features(packet, x, h, model, self.mode, self.omega)
        require(self.medians is not None and len(self.medians) == len(values), 'Median schema mismatch')
        X = np.where(np.isfinite(values), values, self.medians)[None, :]
        require(np.isfinite(X).all(), 'Invalid imputation')
        # Use the frozen estimator feature names when available; this does not change ordering.
        if hasattr(self.estimator, 'feature_names_in_'):
            import pandas as pd
            X = pd.DataFrame(X, columns=self.estimator.feature_names_in_)
        c = float(self.estimator.predict(X)[0])
        if self.mean_convention == 'total':
            c -= float(packet.mu[1])  # mu + (total - mu) = total; never subtract POWER twice.
        require(np.isfinite(c), 'Nonfinite correction')
        return c, flags


def operational_profile_table(frame):
    """Explicit table allowlist; all labels are ignored rather than wildcard-selected."""
    return frame.loc[:, list(BASE_FEATURES)].copy()
