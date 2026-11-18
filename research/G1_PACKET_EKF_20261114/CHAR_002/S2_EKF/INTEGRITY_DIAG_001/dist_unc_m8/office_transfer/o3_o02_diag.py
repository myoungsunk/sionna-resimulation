"""O02 diagnostics (not a judgement run). B0, seeds 10-29, same inputs and calibrations as O3.
D1 range-only vs range+polarization per route; D2 O02 counterfactuals (far kriging, far s off, oracle mu_s);
D3 polarization on in one distance bin only; D4 heading error by O02 phase and correlation with initial heading error;
D5 instantaneous heading-position trade-off from the measurement Jacobian at truth (cm of position shift that
   leaves range and s unchanged for +1 deg heading)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/office")
from common import R7
import o3_run as R, m8_replay as M
O = "/home/claude/office"
e = R.office_env(); C = np.load(f"{O}/O3_CAL.npz"); RT = np.load(f"{O}/O3_ROUTES.npz"); INFO = json.load(open(f"{O}/O3_INFO.json"))
T0 = INFO["table_office"]
def tb(ks=(0, 1, 2)): return dict(edges=T0["edges"], c1=[T0["c1"][k] if k in ks else 0. for k in range(3)], c0=[T0["c0"][k] if k in ks else 1e2 for k in range(3)])
src = open(f"{O}/o3_run.py").read()
g = dict(R.__dict__); exec(src[src.index("def make_krige"):src.index("def pk")].replace("if distance < 6. else", "if distance < 99. else"), g)
make_krige_all = g["make_krige"]
FEAT = pd.read_csv(f"{O}/OFFICE_ROUTE_FEATURES.csv.gz")
def run(r, arm, seed, table=None, fn=None):
    b = dict(np.load(f"{O}/inputs/{r}_B0_{seed}.npz")); cal = {k: C[f"{r}/T1/{k}"] for k in ("mu_r", "mu_s", "Rrr", "Rss")}; p = R.pk(b, cal)
    if arm in ("H0", "H1"): return R7.replay(p, e, arm, sigma_b=R.ZERO, condition="B0", rref_policy="own", sigma_rad=0.), b
    return M.replay_m8(p, e, "F2", table=table, sigma_b=R.ZERO, condition="B0", mu_s_fn=fn, **M.ARM_MODES["F2"]), b
def errs(tr, truth):
    x = np.asarray(tr["x"]); P = np.asarray(tr["P"])
    return np.c_[np.degrees(wrapd(x[:, 2] - truth[:, 2])), 100 * np.hypot(x[:, 0] - truth[:, 0], x[:, 1] - truth[:, 1]), np.degrees(np.sqrt(P[:, 2, 2]))]
def wrapd(a): return (a + np.pi) % (2 * np.pi) - np.pi
def summ(V):
    V = np.stack(V); hd, xy, sd = V[..., 0], V[..., 1], V[..., 2]
    return dict(xy_rms_cm=float(np.sqrt(np.mean(xy**2))), heading_rms_deg=float(np.sqrt(np.mean(hd**2))),
                heading_sd_median_deg=float(np.median(sd)), heading_outside95=float(np.mean(np.abs(hd) / sd > 1.96)), end_heading_rms_deg=float(np.sqrt(np.mean(hd[:, -1]**2))))
OUT = {}; SEEDS = range(10, 30)
# D1
OUT["D1_range_only_vs_pol"] = {}
for r in ("O01", "O02", "O03L"):
    fn = R.make_krige(C[f"{r}/T1/mu_s"]); truth = RT[f"{r}/truth"]; acc = {"H0_DR": [], "H1_range_only": [], "F2T1_range_pol": []}
    for s in SEEDS:
        acc["H0_DR"].append(errs(run(r, "H0", s)[0], truth)); acc["H1_range_only"].append(errs(run(r, "H1", s)[0], truth))
        acc["F2T1_range_pol"].append(errs(run(r, "F2", s, tb(), fn)[0], truth))
    OUT["D1_range_only_vs_pol"][r] = {k: summ(v) for k, v in acc.items()}
# D2, D3, D4 on O02
r = "O02"; truth = RT[f"{r}/truth"]; mu_far = C[f"{r}/T1/mu_s"]
F = FEAT[FEAT.route == "O02"].reset_index(drop=True); oracle = lambda nav, d, i: float(F.e_s[i])
P = pd.read_csv(f"{O}/rel/O02_M0/CASES/O02_O0_M0_FULL/RADIO_POSE.csv")
ph = np.select([P.t_s <= 52.5, P.t_s < 66, P.t_s <= 118], ["1_out_rho2to9", "2_far_turn_rho9.2", "3_back_rho9to2"], "4_restore_rho2.2")
cases = {"F2T1": (tb(), R.make_krige(mu_far)), "F2T1_krige_all_distances": (tb(), make_krige_all(mu_far)),
         "F2T1_s_off_rho_ge6": (tb((0, 1)), R.make_krige(mu_far)), "F2T1_oracle_mu_s": (tb(), oracle),
         "F2T1_s_only_lt3": (tb((0,)), R.make_krige(mu_far)), "F2T1_s_only_3to6": (tb((1,)), R.make_krige(mu_far)),
         "F2T1_s_only_ge6": (tb((2,)), R.make_krige(mu_far))}
OUT["D2_D3_O02_counterfactuals"] = {}; phase = {}
dpsi0 = np.array([np.degrees(wrapd(np.load(f"{O}/inputs/O02_B0_{s}.npz")["x0"][2] - truth[0, 2])) for s in SEEDS])
for name, (t_, f_) in cases.items():
    V = [errs(run(r, "F2", s, t_, f_)[0], truth) for s in SEEDS]; OUT["D2_D3_O02_counterfactuals"][name] = summ(V)
    if name in ("F2T1", "F2T1_krige_all_distances"):
        A = np.stack(V); hd = A[..., 0]; i1 = np.flatnonzero(ph == "1_out_rho2to9")
        phase[name] = {l: dict(heading_rms=float(np.sqrt(np.mean(hd[:, ph == l]**2))), heading_mean=float(hd[:, ph == l].mean())) for l in sorted(set(ph))}
        phase[name]["corr_with_dpsi0"] = {lab: float(np.corrcoef(hd[:, i], dpsi0)[0, 1]) for lab, i in (("t6s", i1[5]), ("end_outbound", i1[-1]), ("end", len(ph) - 1))}
V = [errs(run(r, "H1", s)[0], truth) for s in SEEDS]; A = np.stack(V)[..., 0]
phase["H1_range_only"] = {l: dict(heading_rms=float(np.sqrt(np.mean(A[:, ph == l]**2))), heading_mean=float(A[:, ph == l].mean())) for l in sorted(set(ph))}
OUT["D4_O02_heading_by_phase"] = phase
# D5 trade-off
OUT["D5_tradeoff_cm_per_deg"] = {}
for r in ("O01", "O02", "O03L"):
    tr = RT[f"{r}/truth"]; t = RT[f"{r}/t"]; rho = RT[f"{r}/rho"]; x = np.c_[tr, np.zeros(len(tr))]
    H = np.asarray(e["model"].batch(x, e["spec"])[1])[:, :, :3]; n = np.cross(H[:, 0], H[:, 1]); sh = n[:, :2] / n[:, 2:3] * np.pi / 180 * 100
    OUT["D5_tradeoff_cm_per_deg"][r] = [dict(t=float(t[i]), x=float(tr[i, 0]), y=float(tr[i, 1]), yaw_deg=float(np.degrees(tr[i, 2])), rho=float(rho[i]),
                                             abs_ds_dpsi_per_deg=float(abs(H[i, 1, 2]) * np.pi / 180), shift_cm=[float(sh[i, 0]), float(sh[i, 1])], shift_norm_cm=float(np.hypot(*sh[i])))
                                        for i in range(len(t))]
json.dump(OUT, open(f"{O}/O3_O02_DIAG.json", "w"), indent=1)
for k in ("D1_range_only_vs_pol", "D2_D3_O02_counterfactuals"):
    print("==", k); print(pd.DataFrame(OUT[k]).T.round(3).to_string() if k.startswith("D2") else pd.concat({r: pd.DataFrame(v).T for r, v in OUT[k].items()}).round(3).to_string())
print(json.dumps(OUT["D4_O02_heading_by_phase"], indent=0)[:1500])
