"""Aggregate M8 Step 3 fair-plan runs (out_s3) into decision / ladder / cross-family / route tables."""
import json, glob, sys, math, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1")
sys.path.insert(0, "/home/claude/m8")
from m7_assess import clopper_pearson
from m8s3_score import ARMS, REFS
OUT = "/home/claude/m8/out_s3"; TAB = "/home/claude/m8/s3_tables"
import os; os.makedirs(TAB, exist_ok=True)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 40)
SETS = [("A", "B0", "own", range(10, 30)), ("A", "L2_GYRO_ARW", "own", range(10, 30)), ("A", "B0", "fixed", range(10, 15)),
        ("A", "L2_GYRO_ARW", "fixed", range(10, 15)), ("A", "L2_GYRO_ARW_Q_B0_STRESS", "own", range(10, 30)),
        ("B", "B0", "own", range(30, 50)), ("B", "L2_GYRO_ARW", "own", range(30, 50))]


def load(cond, mode, seeds):
    G = {}
    for s in seeds:
        f = f"{OUT}/{cond}/{mode}/seed{s}/GROUP.json"
        if os.path.exists(f): G[s] = json.load(open(f))
    return G


def nomirror(sa):
    ok = all(not [x for x in g["integrity_failures"] if x != "mirror_fail"] for g in sa["groups"].values())
    return ok and sa["A_seed"]


rows, seedrows, ladder, cross, route = [], [], [], [], []
LAD = [("F2L", "F2S"), ("F2S", "F2SB"), ("F2SB", "F2SK"), ("F2SK", "F2SKRW"), ("F2SKRW", "F2SKRWV"), ("F2SKR", "F2SKRW")]
rng = np.random.default_rng(20261115)
for ph, cond, mode, seeds in SETS:
    G = load(cond, mode, seeds)
    if not G: continue
    n = len(G)
    for ref in REFS:
        for arm in ARMS:
            sa = {s: g["seed_assessments"][ref][arm] for s, g in G.items()}
            I = [s for s in sa if sa[s]["I_seed"]]; A = [s for s in sa if sa[s]["A_seed"]]; J = [s for s in sa if sa[s]["J_seed"]]
            mroutes = sum(v["mirror_routes"] for v in sa.values()); lo, hi = clopper_pearson(len(J), n)
            rows.append(dict(phase=ph, cond=cond, mode=mode, ref=ref, arm=arm, n=n, N_I=len(I), N_A=len(A), N_J=len(J),
                             J_CI95=f"[{lo:.2f},{hi:.2f}]", mirror_routes=mroutes,
                             mirror_seeds=",".join(str(s) for s in sa if sa[s]["mirror_routes"]),
                             N_J_noMirror=sum(nomirror(v) for v in sa.values()),
                             CONDITION_PASS=bool(mode == "own" and n == 20 and len(J) >= 18 and mroutes == 0)))
            for s, v in sa.items():
                seedrows.append(dict(phase=ph, cond=cond, mode=mode, ref=ref, arm=arm, seed=s, I=v["I_seed"], A=v["A_seed"], J=v["J_seed"],
                                     mirror=v["mirror_routes"],
                                     fail_I=";".join(f"{k}:{','.join(g['integrity_failures'])}" for k, g in v["groups"].items() if g["integrity_failures"]),
                                     fail_A=";".join(f"{k}:{','.join(g['accuracy_failures'])}" for k, g in v["groups"].items() if g["accuracy_failures"])))
        # ladder (McNemar 2x2 on J)
        for a, b in LAD:
            ja = np.array([G[s]["seed_assessments"][ref][a]["J_seed"] for s in sorted(G)]); jb = np.array([G[s]["seed_assessments"][ref][b]["J_seed"] for s in sorted(G)])
            n01, n10 = int(np.sum(~ja & jb)), int(np.sum(ja & ~jb)); k = n01 + n10
            p = 1.0 if k == 0 else min(1.0, 2 * sum(math.comb(k, i) for i in range(min(n01, n10) + 1)) / 2**k)
            ladder.append(dict(phase=ph, cond=cond, mode=mode, ref=ref, from_=a, to=b, both=int(np.sum(ja & jb)), only_from=n10, only_to=n01,
                               neither=int(np.sum(~ja & ~jb)), mcnemar_exact_p=round(p, 4)))
    # cross-family non-inferiority F2SKRW (and V) vs F2L, per-seed pooled RMSE ratios
    for cand in ("F2SKRW", "F2SKRWV"):
        r = {m: np.array([G[s]["point"]["pooled"][cand][m] / G[s]["point"]["pooled"]["F2L"][m] for s in sorted(G)]) for m in ("xy_rmse_cm", "heading_rmse_deg")}
        row = dict(phase=ph, cond=cond, mode=mode, cand=cand, n=n)
        for m, v in r.items():
            bs = np.median(v[rng.integers(0, len(v), (10000, len(v)))], axis=1)
            row[f"{m}_ratio_median"] = float(np.median(v)); row[f"{m}_ratio_ub95"] = float(np.quantile(bs, .975))
            row[f"{m}_NI_pass"] = bool(np.quantile(bs, .975) <= 1.10)
        NI = {a: sum(G[s]["seed_assessments"]["H2"][a]["I_seed"] for s in G) for a in (cand, "F2L")}
        row.update(N_I_cand=NI[cand], N_I_F2L=NI["F2L"], integrity_NI_pass=bool(NI[cand] >= NI["F2L"] - 1))
        cross.append(row)
    # route absolute
    for arm in ARMS:
        for g in ("R2", "R4", "R5", "pooled"):
            P = pd.DataFrame([G[s]["point"][g][arm] for s in G])
            route.append(dict(phase=ph, cond=cond, mode=mode, arm=arm, group=g, heading_rmse_deg=P.heading_rmse_deg.mean(), xy_rmse_cm=P.xy_rmse_cm.mean(),
                              pose95=P.pose95_coverage.mean(), heading95=P.heading95_coverage.mean(), xy95=P.xy95_coverage.mean(), nees3=P.mean_nees3.mean()))
T = pd.DataFrame(rows); S = pd.DataFrame(seedrows); L = pd.DataFrame(ladder); C = pd.DataFrame(cross); R = pd.DataFrame(route)
for name, df in (("DECISION", T), ("SEEDS", S), ("LADDER", L), ("CROSS", C), ("ROUTE_ABS", R)):
    df.to_csv(f"{TAB}/{name}.csv", index=False)
if __name__ == "__main__":
    show = sys.argv[1] if len(sys.argv) > 1 else "all"
    keep = ["H0", "H1", "H2", "H3", "H1S", "H2S", "F2L", "F2S", "F2SB", "F2SK", "F2SKR", "F2SKRW", "F2SKRWV"]
    for ph in ("A", "B"):
        t = T[T.phase == ph]
        if t.empty: continue
        print(f"\n===== Phase {ph}: N_I / N_A / N_J (mirror routes) =====")
        t = t.assign(cell=t.N_I.astype(str) + "/" + t.N_A.astype(str) + "/" + t.N_J.astype(str) + " (" + t.mirror_routes.astype(str) + ")")
        print(t.pivot_table(index="arm", columns=["ref", "cond", "mode"], values="cell", aggfunc="first").reindex(keep).to_string())
    print("\n===== cross-family (vs F2L) ====="); print(C.round(3).to_string(index=False))
    print("\n===== ladder (ref H2S) ====="); print(L[L.ref == "H2S"].to_string(index=False))
