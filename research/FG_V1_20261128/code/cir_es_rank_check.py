"""How well do online CIR features rank |e_s| on the station sweep (RT labels)? Single-feature Spearman and a GBM with station-group CV."""
import json, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from common import *
d = pd.read_csv(I + "/dist_unc_m8/step3_sweep/dev_02/code/SWEEP_FEATURES.csv.gz"); d = d[d["valid"].astype(bool)].copy(); d["ae"] = d["e_s"].abs()
feats = ["range_m", "log_fp_power", "abs_s_fp", "early4", "early8", "early16", "delay_rms_ns", "peak_diff_ns", "eta_fp_win80", "s_diff4", "s_diff8", "s_diff16",
         "tap_pol_var80", "jones_diversity", "freq_s_var", "detector_s_span", "detector_delay_span_ns"]
d["rbin"] = pd.qcut(d["range_m"], 4, labels=False)
single = {f: dict(rho_all=float(spearmanr(d[f], d.ae).correlation), rho_within_range_bin=float(np.mean([spearmanr(g[f], g.ae).correlation for _, g in d.groupby("rbin")]))) for f in feats}
st = d.groupby(["x_eval", "y_eval"]).ngroup().values; X = d[feats].values; y = d.ae.values; pred = np.zeros(len(y))
for tr, te in GroupKFold(5).split(X, y, st):
    pred[te] = HistGradientBoostingRegressor(max_iter=300, learning_rate=.05).fit(X[tr], y[tr]).predict(X[te])
q = pd.qcut(pred, 5, labels=False); rng = np.random.default_rng(0); i = rng.integers(0, len(y), 200000); j = rng.integers(0, len(y), 200000)
sel = np.maximum(y[i], y[j]) > 2 * np.minimum(y[i], y[j]) + 1e-9
out = dict(rows=len(d), abs_e_s_median=float(np.median(y)), abs_e_s_p90=float(np.quantile(y, .9)), single_feature=single,
           gbm_station_group_cv=dict(spearman=float(spearmanr(pred, y).correlation), spearman_within_range_bin=float(np.mean([spearmanr(pred[d.rbin.values == b], y[d.rbin.values == b]).correlation for b in range(4)])),
                                    abs_e_s_mean_by_pred_quintile=[float(y[q == k].mean()) for k in range(5)], pair_order_accuracy_2x=float(np.mean(np.sign(pred[i] - pred[j])[sel] == np.sign(y[i] - y[j])[sel]))),
           note="RT labels (e_s); corridor station sweep only; magnitude only. Using this to weight s is Goal 2.")
print(json.dumps(out["gbm_station_group_cv"])); json.dump(out, open(OUT + "/CIR_ES_RANK_CHECK.json", "w"), indent=1)
