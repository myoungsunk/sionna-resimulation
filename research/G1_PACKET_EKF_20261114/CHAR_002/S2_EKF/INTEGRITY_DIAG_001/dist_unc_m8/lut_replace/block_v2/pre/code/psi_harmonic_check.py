"""Within-station view: harmonic content over the 36-yaw sweep (psi period 360 deg).
For each station: FFT of s_LoS and of e = s_full - s_LoS. Energy share per harmonic m (0 = mean, 2 = the Stokes 2-psi term).
Also: keep only the harmonics where s_LoS lives (set M) and check how much of e is removed by that psi-domain filter,
and how much of e survives in the 2-psi term (co-directional part: exactly L*sin2(chi - psi), cannot be filtered)."""
import numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["e"] = ES0; SW["sL"] = SW.s_fp - ES0; SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)
SW["b"] = np.clip(np.searchsorted([0, 3, 6, 10], SW.rho, side="right") - 1, 0, 2); SW = SW.sort_values(["pos", "yaw_deg"])
EL, EE, B = [], [], []
for p, g in SW.groupby("pos"):
    EL.append(np.abs(np.fft.rfft(g.sL.values))**2); EE.append(np.abs(np.fft.rfft(g.e.values))**2); B.append(g.b.iloc[0])
EL, EE, B = np.array(EL), np.array(EE), np.array(B)
for k, name in enumerate(["<3 m", "3-6 m", ">=6 m"]):
    m = B == k; l = EL[m].sum(0); e = EE[m].sum(0)
    print(name, "s_LoS share m=0..6:", np.round(l[:7] / l.sum(), 3), " e share m=0..6:", np.round(e[:7] / e.sum(), 3), " e share m>=7:", round(e[7:].sum() / e.sum(), 3))
    for M in ([0, 2], [0, 1, 2, 3, 4], list(range(0, 9))):
        keep = np.zeros(EE.shape[1], bool); keep[M] = True
        print("   keep harmonics", M, ": e energy removed", round(e[~keep].sum() / e.sum(), 3), " s_LoS energy lost", round(l[~keep].sum() / l.sum(), 4))
