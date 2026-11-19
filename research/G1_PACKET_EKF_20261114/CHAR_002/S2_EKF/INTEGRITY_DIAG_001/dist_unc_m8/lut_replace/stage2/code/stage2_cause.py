"""Stage 2 cause split from the static outputs (no new replays): per distance bin, LOSO mean-correction residual of the 2b labels vs S0-id,
the part left unabsorbed, injected h error, and the Jacobian error |a' - a| (labels cannot correct the Jacobian)."""
import json, numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); a0 = SW.a.to_numpy(); b = np.clip(np.searchsorted([0, 3, 6, 10], SW.rho, side="right") - 1, 0, 2)
ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); mu0 = np.load("MU_LOSO_S0ID.npy"); S = SW.s_fp.to_numpy(); rows = []
rms = lambda v: float(np.sqrt(np.mean(v**2)))
for P in ("P1", "P1m", "P2", "P3"):
    aP = np.load(f"A_{P}.npy"); e = np.load(f"ES_{P}.npy"); mu = np.load(f"MU_LOSO_{P}.npy")
    for k in range(3):
        m = b == k
        rows.append(dict(P=P, bin=["<3 m", "3-6 m", ">=6 m"][k], mean_model=("kriging" if k < 2 else "POWER"), injected_h_err_rms=rms((ES0 - e)[m]),
                         label_rms_2b=rms(e[m]), label_rms_s0id=rms(ES0[m]), loso_resid_rms_2b=rms((e - mu)[m]), loso_resid_rms_s0id=rms((ES0 - mu0)[m]),
                         unabsorbed_rms=rms(((e - mu) - (ES0 - mu0))[m]), a_rms=rms(a0[m]), jacobian_err_rms=rms((aP - a0)[m]), jacobian_err_rel=rms((aP - a0)[m]) / rms(a0[m])))
D = pd.DataFrame(rows); D.to_csv("STAGE2_CAUSE_BIN.csv", index=False); pd.set_option("display.width", 250); print(D.round(4).to_string(index=False))
