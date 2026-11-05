#!/usr/bin/env python3
"""Complete the available, evidence-anchored subset; no C2 causal replay claim."""
from pathlib import Path
import numpy as np,pandas as pd,json,hashlib
O=Path(__file__).resolve().parent
c1=pd.read_csv(O/'C1_ALL_P0_B0_EVEN_FROZEN_AND_SELFGATE.csv')
raw=pd.read_csv(O/'PR36_FULL_SHARDS_PAIRED.csv')
windows={'R4':[(0,15,'initial'),(33,35.2,'33s'),(59,61,'near'),(99,105.4,'99s')],'R5':[(79,81,'79s'),(92,94,'92s'),(132,135,'near'),(195,198,'195s')]}
rows=[]
for route,ww in windows.items():
 for a,b,name in ww:
  rr=raw[(raw.route==route)&(raw.t_s>=a-1e-8)&(raw.t_s<=b+1e-8)]
  cc=c1[(c1.route==route)&(c1.t_s>=a-1e-8)&(c1.t_s<=b+1e-8)&(c1.gate_robust.astype(bool))]
  ff=cc[(cc.arm=='FF_original')&(cc.gate_policy=='self_gate')].set_index('pose_id')
  for arm in ['FL_s_LoS','LF_r_LoS','LL_both_LoS','FP_tap_s_only','FP_tap_and_range']:
   for policy in ['frozen_gate','self_gate']:
    arm_rows=cc[(cc.arm==arm)&(cc.gate_policy==policy)].set_index('pose_id')
    ix=ff.index.intersection(arm_rows.index)
    f=ff.loc[ix];g=arm_rows.loc[ix]
    rows.append({'route':route,'window':name,'arm':arm,'gate_policy':policy,'n_full_rf':len(rr),'n_snapshots':len(ix),
     'fp_shift_full_rf':int((rr.delta_tap!=0).sum()),'s_rms_full_rf':float(np.sqrt(np.mean(rr.total_delta_s**2))) if len(rr) else np.nan,
     'heading_RMSE_orig_deg':float(np.sqrt(np.mean(f.heading_error_cf_deg**2))) if len(ix) else np.nan,
     'heading_RMSE_single_step_cf_deg':float(np.sqrt(np.mean(g.heading_error_cf_deg**2))) if len(ix) else np.nan,
     'mean_heading_NEES_cf_minus_orig':float((g.heading_nees_cf-f.heading_nees_cf).mean()) if len(ix) else np.nan,
     'accepted_changed_count':int((g.accepted!=f.accepted).sum()),
     'improve_steps':int((g.heading_error_cf_deg.abs()<f.heading_error_cf_deg.abs()-1e-10).sum()),
     'worsen_steps':int((g.heading_error_cf_deg.abs()>f.heading_error_cf_deg.abs()+1e-10).sum())})
res=pd.DataFrame(rows);res.to_csv(O/'C1_WINDOW_LEVEL_PAIRED_RESULTS.csv',index=False)
assert int(raw.delta_tap.ne(0).sum())==69
assert len(raw)==154
assert (c1[(c1.arm=='FF_original')&(c1.gate_policy=='self_gate')].heading_error_cf_deg-c1[(c1.arm=='FF_original')&(c1.gate_policy=='self_gate')].heading_full_err_deg).abs().max()<1e-10
r={'new_rf_pairs':len(raw),'fp_moved':int(raw.delta_tap.ne(0).sum()),'high_s_error':int(raw.total_delta_s.abs().gt(.1).sum()),'window_results':len(res),'one_step_snapshots':int(len(c1[(c1.arm=='FF_original')&(c1.gate_policy=='self_gate')])),'original_snapshots_exact_parity':True,'C2_true_recursive':'NOT_EXECUTED: immutable original online controls, complete observation-to-prior H/Jacobian and model state needed for independent parity','label':'NONINDEPENDENT_EXPLORATORY'}
(O/'REMAINING_VERIFICATION_RECEIPT.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print(json.dumps(r,ensure_ascii=False,indent=2));print(res[(res.arm=='FL_s_LoS')&(res.gate_policy=='frozen_gate')].to_string(index=False))
