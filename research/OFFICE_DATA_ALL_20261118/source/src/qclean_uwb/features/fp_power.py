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
