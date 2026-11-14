import json, numpy as np, pandas as pd
from scipy.stats import spearmanr, pearsonr
d = pd.DataFrame(json.load(open('/tmp/diag/q1_rows.json')))
cal = {k: v['calibration'] for k, v in json.load(open('/tmp/diag/loro.json')).items()}
out = {}
# 0. reproduce c_L via fit_e1 rule on sample B (winner raw) per holdout
chk = {}
for ho in ['R2', 'R4', 'R5']:
    tr = d[d.route != ho]
    raw = tr.r_e1 / cal[tr.route.iloc[0]]['c_l']  # placeholder, recomputed below
chk = {}
for ho in ['R2','R4','R5']:
    tr = d[d.route != ho].copy()
    tr['raw'] = [r / cal[rt]['c_l'] for r, rt in zip(tr.r_e1, tr.route)]
    # raw stored with own-route c_l; recover raw then refit
    q95 = np.quantile(np.abs(tr.err) / np.sqrt(tr.raw), 0.95)
    chk[ho] = dict(c_l_refit=float((q95/1.96)**2), c_l_frozen=cal[ho]['c_l'])
out['c_l_reproduction'] = chk
d['z'] = d.err / np.sqrt(d.r_e1)
d['sd'] = np.sqrt(d.r_e1)
rows = []
for c, g in d.groupby('case'):
    st = g.groupby('group').agg(x=('x','first'), y=('y','first'), hd=('hdist','first'), el=('elev_deg','first'),
                                emean=('err','mean'), esd=('err','std'), sdmean=('sd','mean'))
    var_total = g.err.var(); var_station = st.emean.var(); var_within = (st.esd**2).mean()
    # adjacent stations along each lane (same y within 0.05), sorted by x
    pairs = []
    for _, lane in st.groupby(st.y.round(1)):
        lane = lane.sort_values('x')
        pairs += list(zip(lane.emean.values[:-1], lane.emean.values[1:]))
    pa = np.array(pairs)
    rho_adj = float(pearsonr(pa[:,0], pa[:,1])[0]) if len(pa) > 3 else np.nan
    # per-seed adjacent correlation (raw sweep errors, includes noise)
    sp_all = spearmanr(np.abs(g.err), g.sd)[0]
    sp_within = np.nanmean([spearmanr(np.abs(gg.err), gg.sd)[0] for _, gg in g.groupby('group') if gg.sd.std() > 0])
    sp_station = spearmanr(np.abs(st.emean), st.sdmean)[0]
    rows.append(dict(case=c, stations=len(st), sweeps=len(g), mean_err=g.err.mean(), median_err=g.err.median(),
                     rms_err=np.sqrt((g.err**2).mean()), mean_sd_e1=g.sd.mean(), median_sd_e1=g.sd.median(),
                     cover95_meas=float((np.abs(g.z) <= 1.96).mean()), mean_z=g.z.mean(), rms_z=np.sqrt((g.z**2).mean()),
                     spearman_abs_err_vs_sd=sp_all, spearman_within_station=sp_within, spearman_station_level=sp_station,
                     station_var_frac=var_station/var_total, rho_adj_station_mean=rho_adj, adj_pairs=len(pa),
                     tail_lt_m5=float((g.err < -5).mean()), tail_gt_p5=float((g.err > 5).mean()), flat_frac=float(g.flat.mean()),
                     corr_station_bias_hdist=float(spearmanr(st.emean, st.hd)[0])))
t = pd.DataFrame(rows).set_index('case')
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 40)
print(t.round(3).T)
print(json.dumps(out, indent=1))
# pooled
print('pooled spearman |e| vs sd', spearmanr(np.abs(d.err), d.sd)[0], 'pooled meas coverage', (np.abs(d.z)<=1.96).mean())
t.to_csv('/tmp/diag/q1_case_table.csv')
