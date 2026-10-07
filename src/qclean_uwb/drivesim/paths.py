"""Path bookkeeping for the corridor: image-method signatures of simulated paths (G3 continuity gate)."""
from __future__ import annotations

from collections import Counter

import numpy as np

from qclean_uwb.features.reflection_attribution import image_delays


def path_signature(tau, tx, rx, length, half_width, height, tol: float = 5e-14):
    """Return (sorted list of matched image-method sequences as strings, number of unmatched paths).

    The same multiset of sequences at two neighbouring stations means no path appeared or disappeared.
    """
    table = image_delays(tx, rx, length, half_width, height)
    seqs = list(table)
    d = np.array([table[s] for s in seqs])
    tau = np.asarray(tau, float)
    pick = np.abs(tau[:, None] - d[None, :]).argmin(axis=1)
    ok = np.abs(tau - d[pick]) <= tol
    names = ["LOS" if not seqs[p] else ">".join(seqs[p]) for p, good in zip(pick, ok) if good]
    return sorted(names), int((~ok).sum())


def signature_diff(a: list[str], b: list[str]) -> dict:
    ca, cb = Counter(a), Counter(b)
    return dict(removed=sorted((ca - cb).elements()), added=sorted((cb - ca).elements()))
