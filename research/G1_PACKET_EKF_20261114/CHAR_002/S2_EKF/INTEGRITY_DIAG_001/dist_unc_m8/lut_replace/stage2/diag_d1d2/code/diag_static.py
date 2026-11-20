"""Stage 2 cause-split diagnostics (DIAGNOSTIC ONLY, dev seeds). Static part.
  K_S0id : control. FFD, S0-id labels, kriging mean for ALL bins (far bin: S0 hyperparameters e_s|2), V far refit on LOSO kriging residual
  D1_P1  : FFD'_P1, P1 labels, kriging for all bins (as K_S0id)                       -> is far-range POWER the cause?
  D2_P1  : h'_P1 prediction with FFD Jacobian; tables (rule B, V) fit with a_FFD; POWER far as 2b_P1 -> is the Jacobian error the cause?
  D12_P1 : both"""
import sys, json, numpy as np
sys.path.insert(0, "/home/claude/lut2"); import stage2_static as S2
KP = S2.KP; prm = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}; BIN, POS, X3 = S2.BIN, S2.POS, S2.X3; A0 = S2.A0
ES0 = S2.ES0; EP = np.load("/home/claude/lut2/ES_P1.npy"); AP = np.load("/home/claude/lut2/A_P1.npy")
def loso_far_krige(es):
    mu = np.empty(len(es)); m2 = BIN == 2
    for st in np.unique(POS[m2]):
        te = POS == st; trk = (~te) & m2; Xt, yt = X3[trk], es[trk]; mu0 = yt.mean()
        for i in np.flatnonzero(te): mu[i] = S2.kr_one(Xt, yt, mu0, X3[i], prm[2])
    return mu
def tables(es, a, mu):
    tab = dict(edges=[0., 3., 6., 10.], c1=[], c0=[])
    for k in range(3): c1, c0 = S2.fitB(es[BIN == k], a[BIN == k]); tab["c1"].append(c1); tab["c0"].append(c0)
    V = dict(edges=tab["edges"], c1=list(tab["c1"]), c0=list(tab["c0"]))
    for k in range(3):
        if mu[k] is None: continue
        m = BIN == k; V["c1"][k], V["c0"][k] = S2.fitB((es - mu[k])[m], a[m])
    return tab, V
mu_s0 = np.load("/home/claude/lut2/MU_LOSO_S0ID.npy"); mu_p1 = np.load("/home/claude/lut2/MU_LOSO_P1.npy")
far_s0 = loso_far_krige(ES0); far_p1 = loso_far_krige(EP)
mK_s0 = np.where(BIN == 2, far_s0, mu_s0); mK_p1 = np.where(BIN == 2, far_p1, mu_p1)
np.save("/home/claude/lut2/MU_LOSO_K_S0ID.npy", mK_s0); np.save("/home/claude/lut2/MU_LOSO_K_P1.npy", mK_p1)
out = {}
for name, es, a, mu in (("K_S0id", ES0, A0, mK_s0), ("D1_P1", EP, AP, mK_p1), ("D2_P1", EP, A0, mu_p1), ("D12_P1", EP, A0, mK_p1)):
    tab, V = tables(es, a, {0: mu, 1: mu, 2: (mu if name != "D2_P1" else None)})
    cov, z = S2.gate(es - mu, a, V)
    rms = lambda v: float(np.sqrt(np.mean(v**2)))
    out[name] = dict(table5=tab, tableV=V, zcov=cov, loso_resid_rms=[rms((es - mu)[BIN == k]) for k in range(3)],
                     loso_resid_mean=[float(np.mean((es - mu)[BIN == k])) for k in range(3)])
    print(name, json.dumps({k: [round(x, 4) for x in out[name][k]] for k in ("zcov", "loso_resid_rms")}), "V far", round(V["c1"][2], 4), round(V["c0"][2], 4), flush=True)
out["far_unabsorbed_rms_P1_krige"] = float(np.sqrt(np.mean(((EP - mK_p1) - (ES0 - mK_s0))[BIN == 2]**2)))
print("far unabsorbed (kriging)", out["far_unabsorbed_rms_P1_krige"])
json.dump(out, open("/home/claude/lut2/DIAG_STATIC.json", "w"), indent=1)
