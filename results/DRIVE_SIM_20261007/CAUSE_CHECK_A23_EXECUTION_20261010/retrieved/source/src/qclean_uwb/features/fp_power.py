"""First-path (FP) power of the two RX ports from a 2x2 channel.

Follows the project's own observation chain (``rt_cp_uwb_py.g2_scoped_channel.observe``):
Hann-windowed 1028-tap CIR (``contribution_cir``); the first-path index is the 30 % leading
edge (``extract_first_path``) of the strongest branch over all four RX x TX branches, and the
FP power of a branch is ``|CIR[index, branch]|^2``.  Noise-free unless the caller adds noise to ``h``.
"""
from __future__ import annotations

import numpy as np


def first_path_power(h, frequencies):
    """Return ``(power[rx, tx], index, delay_s)`` for a (n_freq, 2, 2) channel."""
    from rt_cp_uwb_py.features import extract_first_path
    from rt_cp_uwb_py.rf_channel_closure import contribution_cir

    cir, time = contribution_cir(np.asarray(h, complex), frequencies)
    peak = np.max(np.abs(cir), axis=0)
    rx, tx = np.unravel_index(np.argmax(peak), peak.shape)
    index, delay, _ = extract_first_path(cir[:, rx, tx], time)
    if index < 0:
        raise ValueError("NO_SIGNAL")
    return np.abs(cir[index]) ** 2, int(index), float(delay)


def signed_port_ratio(p1, p2):
    """Signed ratio ``s = (P1 - P2) / (P1 + P2)``; ``nan`` where both powers are zero."""
    p1 = np.asarray(p1, float)
    p2 = np.asarray(p2, float)
    den = p1 + p2
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0.0, (p1 - p2) / den, np.nan)


def first_path_power_single_tx(h, frequencies, tx: int = 0):
    """FP power of the two RX ports for one active TX port (single-port anchor).

    Same chain as ``first_path_power`` (Hann 1028-tap CIR, 30 % leading edge) but the first-path index comes from the
    stronger of the two RX branches in the selected TX column ``tx`` only (0 = TX +45).  Returns
    ``(power[rx], index, delay_s)``.  ``first_path_power`` (4-branch rule) is kept for reproducing earlier results.
    """
    from rt_cp_uwb_py.features import extract_first_path
    from rt_cp_uwb_py.rf_channel_closure import contribution_cir

    cir, time = contribution_cir(np.asarray(h, complex), frequencies)
    column = cir[:, :, tx]
    rx = int(np.argmax(np.max(np.abs(column), axis=0)))
    index, delay, _ = extract_first_path(column[:, rx], time)
    if index < 0:
        raise ValueError("NO_SIGNAL")
    return np.abs(column[index]) ** 2, int(index), float(delay)


def signed_s_single_tx(h, frequencies, tx: int = 0):
    """Signed ``s`` of the single-port-anchor chain: ``(s, power[rx], index, delay_s)``.

    Ideal on-axis LoS: ``s = sigma * cos(2 yaw)`` with ``sigma = -1`` for TX +45 and ``+1`` for TX -45.
    """
    power, index, delay = first_path_power_single_tx(h, frequencies, tx)
    return float(signed_port_ratio(power[0], power[1])), power, index, delay
