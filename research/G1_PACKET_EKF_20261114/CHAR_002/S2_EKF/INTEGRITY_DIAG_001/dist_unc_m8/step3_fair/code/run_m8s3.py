"""M8 Step 3 fair plan (PLAN_M8_STEP3_FAIR_KO.md) runner: Phase A (seeds 10-29) and Phase B (seeds 30-49).

Sweep-family packets are rebuilt from measured/sensor fields only (z, controls, initial state); every calibration
field (muMB, muBASE, R) comes from the station sweep, D is zeroed (unused by replay), sigma_b = 0 (C4).
"""
import sys, json, time, os, numpy as np
from multiprocessing import Pool
sys.path.insert(0, "/home/claude/m8")
OUT = "/home/claude/m8/out_s3"
ZERO_SB = dict(knots_m=[0., 20.], sigma_b=[0., 0.])
MEAS = ("t", "pose_id", "z", "x0", "P0", "ds", "gy", "dt")


def sweep_packet(p, mu_r, mu_s, Rrr, Rss):
    q = {k: p[k] for k in MEAS}
    q["muMB"] = np.c_[mu_r, mu_s]; q["muBASE"] = q["muMB"].copy(); q["D"] = np.zeros(len(p["t"]))
    R = np.zeros((len(p["t"]), 2, 2)); R[:, 0, 0] = Rrr; R[:, 1, 1] = Rss; q["R"] = R
    return q


def job(key):
    cond, mode, seed = key
    d = f"{OUT}/{cond}/{mode}/seed{seed}"
    if os.path.exists(d + "/GROUP.json"): return key, "reuse", 0
    from common import packet, TRUTH, PARAMS, env, scorers, m7_kwargs, table, fixed_mask, R7
    import m8_replay as M, m8s3_score as S, krige_online as KO
    B = np.load("/home/claude/m8cal/SWEEP_CAL_B.npz"); CU = np.load("/home/claude/m8cal/SWEEP_CAL_ROUTES.npz")
    ST = json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json")); stab = dict(edges=ST["edges"], c1=ST["c1"], c0=ST["c0"])
    VT = json.load(open("/home/claude/m8cal/SWEEP_TABLE_V.json")); vtab = dict(edges=VT["edges"], c1=VT["c1"], c0=VT["c0"])
    e = env(); ft, swb, bm = scorers(); t0 = time.time()
    traces, truth, times = {}, {}, {}
    for r in ("R2", "R4", "R5"):
        p = packet(cond, seed, r); truth[r] = TRUTH[r]["truth"]; times[r] = p["t"]; traces[r] = {}
        fm = fixed_mask(r) if mode == "fixed" else None
        # ---- LORO family / M7 arms (packet as published)
        for arm in ("H0", "H1", "H2", "H3"):
            kw = m7_kwargs(arm, r, cond, "own")
            if fm is not None and arm != "H0": kw["fixed_mask"] = fm
            traces[r][arm] = R7.replay(p, e, arm, **kw)
        # ---- sweep G0 references: all calibration from sweep (b); no sigma_b
        ps = sweep_packet(p, B[f"{r}/mu_r"], B[f"{r}/mu_s"], B[f"{r}/Rrr"], B[f"{r}/Rss"])
        for arm, base in (("H1S", "H1"), ("H2S", "H2")):
            kw = dict(sigma_b=ZERO_SB, condition=cond, rref_policy="own", sigma_rad=0.)
            if fm is not None: kw["fixed_mask"] = fm
            traces[r][arm] = R7.replay(ps, e, base, **kw)
        # ---- F2 ladder
        pB = dict(p); pB["muMB"] = np.c_[p["muMB"][:, 0], B[f"{r}/mu_s"]]; pB["R"] = p["R"].copy(); pB["R"][:, 0, 0] = B[f"{r}/Rrr"]
        pR = sweep_packet(p, CU[f"{r}/mu_r_sweepHGB"], B[f"{r}/mu_s"], B[f"{r}/Rrr"], B[f"{r}/Rss"])     # (c) uniform-weight mu_r
        pRW = ps                                                                                    # (b) mu_r
        ladder = (("F2L", p, table(r), None, PARAMS[r]["sigma_b"]),
                  ("F2S", p, stab, None, PARAMS[r]["sigma_b"]),
                  ("F2SB", pB, stab, None, PARAMS[r]["sigma_b"]),
                  ("F2SK", pB, stab, "krige", PARAMS[r]["sigma_b"]),
                  ("F2SKR", pR, stab, "krige", ZERO_SB),
                  ("F2SKRW", pRW, stab, "krige", ZERO_SB),
                  ("F2SKRWV", pRW, vtab, "krige", ZERO_SB))
        for arm, pk, tab, kr, sb in ladder:
            kw = dict(table=tab, sigma_b=sb, condition=cond, **M.ARM_MODES["F2"])
            if fm is not None: kw["fixed_mask"] = fm
            if kr: kw["mu_s_fn"] = KO.make_fn(B[f"{r}/mu_s"])
            traces[r][arm] = M.replay_m8(pk, e, arm, **kw)
    g = S.score(seed, cond, mode, traces, truth, times, from_trace=ft, scores_with_blocks=swb, branch_metrics=bm)
    # small diagnostics (no traces kept: disk) -- range residual by distance bin and s-channel nu/sqrt(S) coverage
    diag = {}
    for r in traces:
        for arm in ("F2L", "F2SK", "F2SKRW", "F2SKRWV", "H2", "H2S"):
            tr = traces[r][arm]; nu = np.asarray(tr["nu"]); S_ = np.asarray(tr["S"]); dist = np.asarray(tr["distance"])
            mk = np.asarray(tr["mask"]).astype(bool) if "mask" in tr else np.ones(len(nu), bool)
            out = {}
            for lab, m in (("<3", dist < 3), ("3-6", (dist >= 3) & (dist < 6)), (">=6", dist >= 6)):
                m = m & mk
                if m.sum() < 5: continue
                zr = nu[m, 0]; out[lab] = dict(n=int(m.sum()), nu_r_mean_cm=float(100 * zr.mean()))
                if nu.shape[1] > 1 and S_.ndim == 3:
                    zs = nu[m, 1] / np.sqrt(S_[m, 1, 1]); out[lab]["s_cov95"] = float(np.mean(np.abs(zs) <= 1.96))
            diag[f"{r}/{arm}"] = out
    g["diag"] = diag
    os.makedirs(d, exist_ok=True)
    json.dump(g, open(d + "/GROUP.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else (o.tolist() if hasattr(o, "tolist") else str(o)))
    return key, "done", time.time() - t0


if __name__ == "__main__":
    which = sys.argv[1]; keys = []
    if which in ("A", "A_main"): keys += [(c, "own", s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 30)]
    if which in ("A", "A_fixed"): keys += [(c, "fixed", s) for c in ("B0", "L2_GYRO_ARW") for s in range(10, 15)]
    if which in ("A", "A_stress"): keys += [("L2_GYRO_ARW_Q_B0_STRESS", "own", s) for s in range(10, 30)]
    if which == "B": keys += [(c, "own", s) for c in ("B0", "L2_GYRO_ARW") for s in range(30, 50)]
    if which == "one": keys = [("B0", "own", 10)]
    with Pool(2) as pool:
        for key, st, dt in pool.imap_unordered(job, keys):
            print(json.dumps(dict(key=key, status=st, sec=round(dt, 1))), flush=True)
