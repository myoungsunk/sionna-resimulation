"""Truth-based reproduction of the V8 g^2 fit (run after check.py, which writes rows.npz).

Per distance bin b in [1.5,3), [3,6), [6,10) m (truth d), on D3-supported packets (no gate mask):
target y = (slow - mean_bin(slow))^2, design [1, g^2] (g = |dh_s/dpsi| at the truth pose),
each donor scaled by 1/sqrt(n) (equal donor weight), NNLS -> (a0, a1^2) >= 0.
Prediction = a0 + a1^2 * mean(g_holdout^2); ratio = prediction / var(slow_holdout).
"""
import numpy as np
from scipy.optimize import nnls
Z = np.load('/home/claude/audit/m45/rows.npz')


def get(r, m, b):
    sup, bins = Z[f'{r}_{m}_support'], Z[f'{r}_{m}_bins']
    idx = np.flatnonzero(sup & (bins == b))
    s = Z[f'{r}_{m}_slow'][idx, 1]
    return Z[f'{r}_{m}_g'][idx], (s - s.mean()) ** 2, np.var(s)


def fit(donors, hold, distance_only=False):
    ratios = []
    for b in range(3):
        X, Y = [], []
        for r, m in donors:
            g, y, _ = get(r, m, b)
            n = np.sqrt(len(g))
            X.append((np.ones((len(g), 1)) if distance_only else np.c_[np.ones(len(g)), g ** 2]) / n)
            Y.append(y / n)
        coef, _ = nnls(np.vstack(X), np.concatenate(Y))
        gh, _, vh = get(hold, 0, b)
        pred = coef[0] + (0. if distance_only else coef[1] * np.mean(gh ** 2))
        ratios.append(round(pred / vh, 2))
    return ratios


if __name__ == '__main__':
    print('R4 | m0 donors', fit([('R2', 0), ('R5', 0)], 'R4'))
    print('R4 | m0+m45', fit([('R2', 0), ('R5', 0), ('R2', 45), ('R5', 45)], 'R4'))
    print('R4 | m45 only', fit([('R2', 45), ('R5', 45)], 'R4'))
    print('R4 | distance only', fit([('R2', 0), ('R5', 0)], 'R4', distance_only=True))
