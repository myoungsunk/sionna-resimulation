"""Per-station polarization angle chi and degree L from the 2-psi term of each 36-yaw sweep (RT Corridor), for s_full and s_LoS.
Multipath shift dchi_mp = chi_full - chi_LoS; LoS change relative to the nadir station chi_LoS - chi_LoS(nadir).
Outputs: STATION_CHI_L.csv (per station), STATION_CHI_L_SUMMARY.csv (per distance bin)."""
import numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["sL"] = SW.s_fp - ES0; SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str); SW = SW.sort_values(["pos", "yaw_deg"])
rows = []
for p, g in SW.groupby("pos"):
    psi = np.radians(g.yaw_deg.values)
    def chiL(s):  # s ~ L sin(2(chi - psi))
        c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return 0.5 * np.arctan2(c, -d), np.hypot(c, d)
    cf, Lf = chiL(g.s_fp.values); cl, Ll = chiL(g.sL.values)
    rows.append(dict(x=g.x_eval.iloc[0], y=g.y_eval.iloc[0], rho=g.rho.iloc[0], chi_full=np.degrees(cf), chi_los=np.degrees(cl), L_full=Lf, L_los=Ll))
D = pd.DataFrame(rows); w = lambda a: (a + 90) % 180 - 90; nad = D.loc[D.rho.idxmin()]
D["dchi_mp"] = w(D.chi_full - D.chi_los); D["dchi_los_vs_nadir"] = w(D.chi_los - nad.chi_los); D["dchi_full_vs_nadir"] = w(D.chi_full - nad.chi_full)
D["bin"] = pd.cut(D.rho, [0, 1, 3, 6, 10], labels=["<1 m", "1-3 m", "3-6 m", ">=6 m"]); D.to_csv("STATION_CHI_L.csv", index=False)
S = D.groupby("bin", observed=True).agg(n=("rho", "size"), dchi_mp_mean=("dchi_mp", "mean"), dchi_mp_sd=("dchi_mp", "std"),
    los_vs_nadir_mean=("dchi_los_vs_nadir", "mean"), los_vs_nadir_sd=("dchi_los_vs_nadir", "std"), los_vs_nadir_absmax=("dchi_los_vs_nadir", lambda v: np.abs(v).max()),
    L_los=("L_los", "mean"), L_full=("L_full", "mean")).reset_index()
S.to_csv("STATION_CHI_L_SUMMARY.csv", index=False)
print("nadir station", nad[["x", "y", "rho", "chi_full", "chi_los", "L_full", "L_los"]].round(3).to_dict()); print(S.round(2).to_string(index=False))
print("corr(full-vs-nadir, LoS-vs-nadir) =", round(np.corrcoef(D.dchi_full_vs_nadir, D.dchi_los_vs_nadir)[0, 1], 3))
