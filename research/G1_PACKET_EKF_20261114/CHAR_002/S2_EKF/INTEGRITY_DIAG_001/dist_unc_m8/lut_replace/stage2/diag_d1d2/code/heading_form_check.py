"""Review of a heading-form far-range correction (no filter runs). Per station (36 yaws), least squares on the label e:
   e(psi) = -a(psi)*delta + kappa*(-h(psi)) + c     (heading shift delta, gain/depolarisation kappa, constant c)
Variance explained by each term, per distance bin, for the S0-id label (channel only) and the P1 label (channel + 5 deg model shift).
Also the pooled single-delta fit per bin (what a global mounting-yaw term would capture)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/lut2"); import stage2_static as S2
BIN, POS, A0, S = S2.BIN, S2.POS, S2.A0, S2.S; ES0 = S2.ES0; H0 = S - ES0; EP = np.load("ES_P1.npy")
rows = []
for lab, e in (("S0id", ES0), ("P1", EP)):
    for k in range(3):
        st = np.unique(POS[BIN == k]); tot = r_c = r_ca = r_cah = 0.; dl = []
        for p in st:
            m = POS == p; y = e[m]; a = A0[m]; h = H0[m]; tot += np.sum((y - 0)**2)
            def ss(X): b = np.linalg.lstsq(X, y, rcond=None)[0]; return np.sum((y - X @ b)**2), b
            r_c += ss(np.c_[np.ones(m.sum())])[0]; s2, b = ss(np.c_[np.ones(m.sum()), -a]); r_ca += s2; dl.append(np.degrees(b[1])); r_cah += ss(np.c_[np.ones(m.sum()), -a, -h])[0]
        m = BIN == k; X = np.c_[np.ones(m.sum()), -A0[m]]; bg = np.linalg.lstsq(X, e[m], rcond=None)[0]
        rows.append(dict(label=lab, bin=["<3 m", "3-6 m", ">=6 m"][k], stations=len(st), rms=float(np.sqrt(tot / m.sum())),
                         frac_const=1 - r_c / tot, frac_const_shift=1 - r_ca / tot, frac_const_shift_gain=1 - r_cah / tot,
                         delta_station_mean_deg=float(np.mean(dl)), delta_station_sd_deg=float(np.std(dl)), delta_global_deg=float(np.degrees(bg[1])),
                         resid_rms_after_shift_gain=float(np.sqrt(r_cah / m.sum()))))
D = pd.DataFrame(rows); D.to_csv("HEADING_FORM_CHECK.csv", index=False); pd.set_option("display.width", 250); print(D.round(3).to_string(index=False))
