"""Build E1-style packet inputs for the 7 original cases (parity gate vs stored CONTROL traces) and the 5 new mount-45 cases.
Output: PACKETS_<case>.npz with t_s, pose_id, truth_scoring_only, z (n,2), mu_B (n,2), mu_M (n,2), R (n,2,2).
Requires scikit-learn <= 1.7.2 (1.9.1 changes HistGradientBoosting results; 1.5.2/1.6.1/1.7.2 reproduce stored EXDS exactly)."""
import json, sys, numpy as np, pandas as pd, sklearn
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import tracegen as T
C = T.C; model = C.base_model(); SRC = T.SRC; OUT = T.HERE / "packets"; OUT.mkdir(exist_ok=True)
assert tuple(int(v) for v in sklearn.__version__.split(".")[:2]) <= (1, 7), sklearn.__version__
feat = pd.read_csv(SRC / "DS_INPUT_PROVENANCE_20261028/prepared/OBSERVATION_FEATURES_LABELS.csv.gz")
full = feat[feat.channel == "full"].copy()
# frozen training table for EXDS: stored features + taps of the original Full H
FT = []
for cid in C.CASES:
    d = T.features_for(cid, model); s = full[full.case == cid].set_index("pose_id").loc[d.pose_id].reset_index()
    for k in T.DS: s[k] = d[k].to_numpy()
    FT.append(s)
FT = pd.concat(FT, ignore_index=True)
report = {}
for cid in list(C.CASES) + list(T.NEW_CASES):
    te = FT[FT.case == cid] if cid in C.CASES else T.features_for(cid, model)
    mp, vr, vs, ntr = T.power_diag(full, te); pr, nex = T.exds(FT, te)
    base = cid.replace("m45", "m0") if cid in T.NEW_CASES else cid
    ref = C.load_control(base, "B0"); ids = ref["pose_id"]
    tt = te.set_index("pose_id"); pos = {p: i for i, p in enumerate(te.pose_id.to_numpy())}; ix = np.array([pos[p] for p in ids])
    z = tt.loc[ids][["range_m", "s_fp"]].to_numpy(float)
    muB = mp[ix]; muM = muB.copy(); muM[:, 0] = pr[ix]
    R = np.zeros((len(ids), 2, 2)); R[:, 0, 0] = vr[ix]; R[:, 1, 1] = vs[ix]
    np.savez_compressed(OUT / f"PACKETS_{cid}.npz", t_s=ref["t_s"], pose_id=ids, truth_scoring_only=ref["truth_scoring_only"], z=z, mu_B=muB, mu_M=muM, R=R,
                        mount_deg=float(T.case_spec(cid)["mount_deg"]), anchor=np.array(T.case_spec(cid)["anchor"]))
    r = dict(n=len(ids), n_train_power=ntr, n_train_exds=nex, power_bins_R_levels=int(len(np.unique(np.round(vr, 12)))))
    if cid in C.CASES:
        jb, jm = ref["jb"], ref["jm"]; zs = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
        r.update(z=float(np.max(np.abs(z - zs))), mu_B=float(np.max(np.abs(muB - ref["mu"][:, jb]))), mu_M=float(np.max(np.abs(muM - ref["mu"][:, jm]))),
                 R=float(np.max(np.abs(R - ref["R"][:, jb]))))
        if cid == "R2_aA_m45":
            r["pose_ids_equal_R2_aA_m0"] = bool(np.array_equal(ids, C.load_control("R2_aA_m0", "B0")["pose_id"]))
    report[cid] = r; print(cid, r, flush=True)
(T.HERE / "PACKETS_REPORT.json").write_text(json.dumps(dict(sklearn=sklearn.__version__, cases=report), indent=1))
