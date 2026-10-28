"""Gate: rebuild the 7 original cases from Full RF H and compare with the stored features, OOF, MR and E1 traces."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import tracegen as T
C = T.C; model = C.base_model()
SRC = T.SRC
feat = pd.read_csv(SRC / "DS_INPUT_PROVENANCE_20261028/prepared/OBSERVATION_FEATURES_LABELS.csv.gz")
par = pd.read_csv(SRC / "DS_INPUT_PROVENANCE_20261028/prepared/OOF_PARAMETERS.csv.gz")
mr = pd.read_csv(SRC / "PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz")
print("stored feat cases", feat.case.unique(), feat.channel.unique(), len(feat)); print("par models", par.model.unique()[:12])
mine = {cid: T.features_for(cid, model) for cid in C.CASES}
rows = []
for cid, d in mine.items():
    s = feat[(feat.case == cid) & (feat.channel == "full")].set_index("pose_id").loc[d.pose_id]
    for col in ["range_m", "s_fp", "e_r", "e_s"] + T.EXIST:
        a = d[col].to_numpy(float); b = s[col].to_numpy(float); rows.append(dict(case=cid, col=col, maxabs=float(np.nanmax(np.abs(a - b)))))
F = pd.DataFrame(rows); print("== feature parity (max |mine - stored|) worst per column"); print(F.groupby("col").maxabs.max().to_string())
# training table = STORED features (frozen) + my taps (DS)
FT = []
for cid, d in mine.items():
    s = feat[(feat.case == cid) & (feat.channel == "full")].set_index("pose_id").loc[d.pose_id].reset_index()
    for k in T.DS + ["s_fp_chk"]: s[k] = d[k].to_numpy()
    FT.append(s)
FT = pd.concat(FT, ignore_index=True); full = feat[feat.channel == "full"].copy()
res = []
for cid in C.CASES:
    te = FT[FT.case == cid]
    mp, vr, vs, ntr = T.power_diag(full, te)
    p = par[(par.case == cid) & (par.channel == "full") & (par.model == "POWER_DIAG")].set_index("pose_id").loc[te.pose_id]
    pr, _ = T.exds(FT, te)
    q = mr[(mr.case == cid) & (mr.bias == "B0") & (mr.channel == "full")].set_index("pose_id")
    ids = q.index.intersection(te.pose_id); tt = te.set_index("pose_id").loc[ids]
    stored_pred = tt.e_r.to_numpy() - q.loc[ids].MU_R_EXDS__meas_r_cm.to_numpy() / 100
    mine_pred = pd.Series(pr, index=te.pose_id.to_numpy()).loc[ids].to_numpy()
    res.append(dict(case=cid, n_train_power=ntr, mu_r=float(np.max(np.abs(mp[:, 0] - p.mu_r.to_numpy()))), mu_s=float(np.max(np.abs(mp[:, 1] - p.mu_s.to_numpy()))),
                    Vr=float(np.max(np.abs(vr - p.Vr.to_numpy()))), Vs=float(np.max(np.abs(vs - p.Vs.to_numpy()))),
                    exds_maxabs=float(np.max(np.abs(mine_pred - stored_pred))), exds_rms=float(np.sqrt(np.mean((mine_pred - stored_pred) ** 2))), exds_std=float(np.std(stored_pred))))
    print(res[-1], flush=True)
pd.DataFrame(res).to_csv(T.HERE / "GATE_OOF.csv", index=False); F.to_csv(T.HERE / "GATE_FEATURES.csv", index=False)
