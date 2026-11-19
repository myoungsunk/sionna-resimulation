"""Stage 0-A: LUT domain check with the frozen FFD observer.
Question: can s_LoS and a = ds/dpsi be written as functions of (psi, el) only (D1), or is the anchor azimuth beta needed (D2)?
D3 = (psi - beta, el) is the relative-bearing control.
Grid G3: rho = 1..9 m, beta = 0..350 deg (10 deg), psi on a 0.5-deg grid; anchor (10, 0, 2.65), receiver z 0.45 (Office has the
same heights and anchor convention, O1 parity), so el = atan(2.2 / rho) is shared by both sites.
Decision rule (plan section 4, fixed before running): D1 if, on deployment poses (Corridor R2/R4/R5, Office O01/O03L) in every
distance bin, RMS_beta(s) <= 0.3 * sigma_res(rho) of the site S0 table AND median[SD_beta(a)/mean_beta|a|] <= 0.2; else D2."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_model003_src")
sys.path.insert(0, "/home/claude/m8")
from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
banks = [pat.Bank(dict(np.load(f"/home/claude/rel/{n}", allow_pickle=False))) for n in ("LP_plus45_bank.npz", "LP_minus45_bank.npz")]
DH = 2.65 - 0.45; PSI = np.arange(0, 360, 0.5); RHO = np.arange(1, 10); BETA = np.arange(0, 360, 10)
def o30(c):
    m = np.abs(c); b = m.max(axis=1).argmax(axis=1); s = np.take_along_axis(m, b[:, None, None], axis=2)[:, :, 0]; pk = s.max(axis=1)
    return (s >= .3 * pk[:, None]).argmax(axis=1)
def s_curve(dx, dy):
    d = np.sqrt(dx**2 + dy**2 + DH**2); dirn = np.array([dx, dy, -DH]) / d
    H = np.stack([model.los_h(banks, dirn, float(p), float(d)) for p in PSI]); c = obs.cir_batch(H[..., 0])
    p = np.abs(c[np.arange(len(c)), o30(c), :])**2; return (p[:, 0] - p[:, 1]) / p.sum(axis=1)
# direction convention check: delta = rx - anchor; robot below anchor -> dirn z negative (matches earlier scripts: delta=[x,y,zr]-A)
S = np.empty((len(RHO), len(BETA), len(PSI)))
for i, r in enumerate(RHO):
    for j, b in enumerate(BETA):
        S[i, j] = s_curve(r * np.cos(np.radians(b)), r * np.sin(np.radians(b)))
dpsi = np.radians(0.5); A = (np.roll(S, -1, axis=2) - np.roll(S, 1, axis=2)) / (2 * dpsi)        # per rad, periodic
np.savez_compressed("/home/claude/lut0/G3_FFD_GRID.npz", rho=RHO, beta=BETA, psi=PSI, s=S, a=A)
# D1 spread at fixed (rho, psi) across beta; D3 spread at fixed (rho, psi - beta)
sd_s_D1 = S.std(axis=1); sd_a_D1 = A.std(axis=1); ma_D1 = np.abs(A).mean(axis=1)
k = (BETA / 0.5).astype(int)                                                                      # beta index shift on psi grid
S3 = np.stack([np.roll(S[:, j], -k[j], axis=1) for j in range(len(BETA))], axis=1)             # S3[i,j,phi] = s(rho, beta_j, phi + beta_j)
A3 = np.stack([np.roll(A[:, j], -k[j], axis=1) for j in range(len(BETA))], axis=1)
sd_s_D3 = S3.std(axis=1); sd_a_D3 = A3.std(axis=1); ma_D3 = np.abs(A3).mean(axis=1)
grid_rows = []
for i, r in enumerate(RHO):
    grid_rows.append(dict(rho=int(r), el_deg=float(np.degrees(np.arctan2(DH, r))), s_amp=float(np.abs(S[i]).max()),
                          D1_rms_sd_s=float(np.sqrt(np.mean(sd_s_D1[i]**2))), D1_med_sd_a_rel=float(np.median(sd_a_D1[i] / ma_D1[i])),
                          D3_rms_sd_s=float(np.sqrt(np.mean(sd_s_D3[i]**2))), D3_med_sd_a_rel=float(np.median(sd_a_D3[i] / ma_D3[i])),
                          corridor_pair_rms_s=float(np.sqrt(np.mean(((S[i, 0] - S[i, 18]) / 2)**2)))))   # beta in {0,180} only
G = pd.DataFrame(grid_rows)
# deployment poses
from common import TRUTH
dep = []
for r in ("R2", "R4", "R5"):
    tr = TRUTH[r]["truth"]; dep.append(pd.DataFrame(dict(site="Corridor", route=r, rho=np.hypot(tr[:, 0] - 10, tr[:, 1]), psi=np.degrees(tr[:, 2]))))
RT = np.load("/home/claude/office/O3_ROUTES.npz")
for r in ("O01", "O03L"):
    tr = RT[f"{r}/truth"]; dep.append(pd.DataFrame(dict(site="Office", route=r, rho=np.hypot(tr[:, 0] - 5, tr[:, 1] - 2.2), psi=np.degrees(tr[:, 2]))))
SWc = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); OSw = pd.read_csv("/home/claude/office/OFFICE_SWEEP_FEATURES.csv.gz")
dep.append(pd.DataFrame(dict(site="Corridor", route="G1_sweep", rho=SWc.rho, psi=SWc.yaw_deg)))
dep.append(pd.DataFrame(dict(site="Office", route="G2_sweep", rho=np.hypot(OSw.x_eval - 5, OSw.y_eval - 2.2), psi=OSw.yaw_deg)))
D = pd.concat(dep, ignore_index=True)
def interp(field, rho, psi):
    ip = (np.round(np.mod(psi, 360) / 0.5).astype(int)) % len(PSI); rr = np.clip(rho, RHO[0], RHO[-1])
    lo = np.clip(np.floor(rr).astype(int) - 1, 0, len(RHO) - 2); w = rr - RHO[lo]
    return (1 - w) * field[lo, ip] + w * field[lo + 1, ip]
for name, f in (("sd_s_D1", sd_s_D1), ("sd_a_rel_D1", sd_a_D1 / ma_D1), ("sd_s_D3", sd_s_D3), ("sd_a_rel_D3", sd_a_D3 / ma_D3)):
    D[name] = interp(f, D.rho.to_numpy(), D.psi.to_numpy())
D["bin"] = np.clip(np.searchsorted([0, 3, 6, 10], D.rho, side="right") - 1, 0, 2)
SIG = {"Corridor": np.sqrt(json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json"))["c0"]).tolist(),
       "Office": np.sqrt(json.load(open("/home/claude/office/O3_INFO.json"))["table_office"]["c0"]).tolist()}
rows = []
for (site, route, b), g in D.groupby(["site", "route", "bin"]):
    sig = SIG[site][b]
    rms1 = float(np.sqrt(np.mean(g.sd_s_D1**2))); rms3 = float(np.sqrt(np.mean(g.sd_s_D3**2)))
    rows.append(dict(site=site, route=route, bin=["<3 m", "3-6 m", ">=6 m"][b], n=len(g), sigma_res=sig,
                     D1_rms_sd_s=rms1, D1_ratio_to_sigma=rms1 / sig, D1_med_sd_a_rel=float(g.sd_a_rel_D1.median()),
                     D1_pass=bool(rms1 <= 0.3 * sig and g.sd_a_rel_D1.median() <= 0.2),
                     D3_rms_sd_s=rms3, D3_ratio_to_sigma=rms3 / sig, D3_med_sd_a_rel=float(g.sd_a_rel_D3.median()),
                     D3_pass=bool(rms3 <= 0.3 * sig and g.sd_a_rel_D3.median() <= 0.2)))
R = pd.DataFrame(rows)
dep_only = R[R.route.isin(["R2", "R4", "R5", "O01", "O03L"])]
decision = "D1" if dep_only.D1_pass.all() else "D2"
G.to_csv("/home/claude/lut0/DOMAIN_GRID.csv", index=False); R.to_csv("/home/claude/lut0/DOMAIN_CHECK.csv", index=False)
json.dump(dict(decision=decision, rule="D1 iff all deployment (route) bins pass RMS_beta(s)<=0.3*sigma_res and median SD_beta(a)/|a|<=0.2",
               D1_pass_by_site={s: bool(dep_only[dep_only.site == s].D1_pass.all()) for s in ("Corridor", "Office")},
               D3_pass_by_site={s: bool(dep_only[dep_only.site == s].D3_pass.all()) for s in ("Corridor", "Office")}),
          open("/home/claude/lut0/DOMAIN_DECISION.json", "w"), indent=1)
pd.set_option("display.width", 250)
print(G.round(4).to_string(index=False)); print(R.round(4).to_string(index=False)); print("decision:", decision)
