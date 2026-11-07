"""Path bookkeeping for the corridor: image-method signatures of simulated paths (G3 continuity gate).

Different reflection sequences can have *identical* images (e.g. ``end_x_max>floor>end_x_max`` has the same image as ``floor`` because two
mirrors in the same plane cancel; ``wall_y_neg`` and ``wall_y_pos`` coincide when the robot is on the corridor axis).  Such sequences are one
geometric path, so delays closer than ``tie`` are merged into a class named after the shortest member.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from qclean_uwb.features.reflection_attribution import image_delays

TIE_S = 1e-13


def _classes(table: dict, tie: float = TIE_S):
    seqs = list(table)
    d = np.array([table[s] for s in seqs])
    order = np.argsort(d, kind="stable")
    class_delay, class_name, owner = [], [], np.empty(len(seqs), int)
    for i in order:
        if class_delay and d[i] - class_delay[-1] <= tie:
            k = len(class_delay) - 1
            if (len(seqs[i]), seqs[i]) < class_name[k]:
                class_name[k] = (len(seqs[i]), seqs[i])
        else:
            class_delay.append(d[i])
            class_name.append((len(seqs[i]), seqs[i]))
            k = len(class_delay) - 1
        owner[i] = k
    names = ["LOS" if not n[1] else ">".join(n[1]) for n in class_name]
    return np.array(class_delay), names


def path_residuals(tau, tx, rx, length, half_width, height, tie: float = TIE_S):
    """(delay residual to the nearest image class [s] per path, class index per path, class delays, class names)."""
    cd, names = _classes(image_delays(tx, rx, length, half_width, height), tie)
    tau = np.asarray(tau, float)
    pick = np.abs(tau[:, None] - cd[None, :]).argmin(axis=1)
    return np.abs(tau - cd[pick]), pick, cd, names


def path_signature(tau, tx, rx, length, half_width, height, tol: float = 5e-14):
    """Return (sorted list of matched image classes as strings, number of unmatched paths at ``tol``)."""
    res, pick, _, names = path_residuals(tau, tx, rx, length, half_width, height)
    ok = res <= tol
    return sorted(names[p] for p, good in zip(pick, ok) if good), int((~ok).sum())


def signature_diff(a: list[str], b: list[str]) -> dict:
    ca, cb = Counter(a), Counter(b)
    return dict(removed=sorted((ca - cb).elements()), added=sorted((cb - ca).elements()))
