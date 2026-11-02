"""Independent row-count and archived-score checks of visualization input and exploratory LoS outputs."""
import json,hashlib,io,zipfile
from pathlib import Path
import pandas as pd,numpy as np
root=Path('/mnt/data/dual_lp_dramatic_figures_20261102');T=root/'tables'
legacy=pd.read_csv(io.BytesIO(zipfile.ZipFile('/mnt/data/DualLP_Physics_Link_Validation_20261101.zip').read('DualLP_Physics_Link_Validation_20261101/results/tables/LEGACY_PRESERVATION_12.csv')))
stage=pd.read_csv(T/'THREE_STAGE_COMPARISON_12_BIASES.csv');phys=pd.read_csv(T/'PHYSICAL_LOS_FULL_PACKET_3136.csv')
los=pd.read_csv(T/'LOS_COUNTERFACTUAL_24.csv');raw=pd.read_csv(T/'MATCHED_PRIOR_POLARIZATION_GAIN_12.csv')
assert len(stage)==48 and len(legacy)==12 and len(phys)==3136 and len(los)==24 and len(raw)==48
par=pd.read_csv(T/'LOS_PARITY.csv');bb=pd.read_csv(T/'FULL_REPLAY_PARITY_6.csv')
assert len(par)==3 and par.range_max_diff_m.max()<1e-10 and par.s_max_diff.max()<1e-12
assert len(bb)==6 and bb.state_max_abs.max()<1e-10 and bb.P_max_abs.max()<1e-10 and (bb.mask_mismatch==0).all()
errors=[]
for _,row in legacy.iterrows():
  d=stage[(stage.case==row.case)&(stage.bias==row.bias)]
  b=d[d.stage=='Full multipath — BB_ORIG'].iloc[0];m=d[d.stage=='Full multipath — MB_VAR'].iloc[0]
  errors.extend([abs(b.head_rmse_deg-row.head_rmse_BB_ORIG),abs(m.head_rmse_deg-row.head_rmse_MB_VAR),
   abs(b.xy_rmse_cm-row.xy_rmse_cm_BB_ORIG),abs(m.xy_rmse_cm-row.xy_rmse_cm_MB_VAR)])
err=max(errors);assert err<1e-12,err
# recalc all 24 clean LoS scores directly from saved new X,P and original truth - no extra model use
scored=[]
for _,r in los.iterrows():
  p=T/f'{r.case}_{r.bias}_{r.arm}.npz'
  with np.load(p,allow_pickle=False) as z:
    X=z['X'];GT=z['gt'];t=z['t'];P=z['PX'];use=z['used'];n=len(t)
  assert n==r.n
  ix=t>=30-1e-9;E=GT[:,:3]-X[:,:3]
  heading=np.degrees(np.arctan2(np.sin(E[:,2]),np.cos(E[:,2])))
  h=float(np.sqrt(np.mean(heading[ix]**2)))
  xy=float(100*np.sqrt(np.mean(np.sum(E[ix,:2]**2,axis=1))))
  scored.append(dict(case=r.case,bias=r.bias,arm=r.arm,heading_score_diff_deg=h-r.head_rmse,xy_score_diff_cm=xy-r.xy_rmse_cm,n=int(ix.sum()),n_used=int(use.sum())))
assert max(abs(x['heading_score_diff_deg']) for x in scored)<1e-11
assert max(abs(x['xy_score_diff_cm']) for x in scored)<1e-11
pd.DataFrame(scored).to_csv(T/'LOS_INDEPENDENT_RESCORE_24.csv',index=False)
# Physical bins counts (all + evaluation) and per-bin trial count
bin_df=pd.read_csv(T/'DISTANCE_BINS_PHYSICAL.csv');m=phys.groupby('case').size()
for c,n in m.items():
 assert int(bin_df[(bin_df.case==c)&(bin_df.window=='all')].n.sum())==n
 assert int(bin_df[(bin_df.case==c)&(bin_df.window=='t>=30')].n.sum())==int((phys[phys.case==c].t_s>=30-1e-9).sum())
fig=list((root/'figures').glob('F*.png'))
assert len(fig)==13 and len(list((root/'figures').glob('F*.svg')))==13
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
meta=dict(status='PASS_SOURCE_LOCKED_FIGURE_AND_COUNTERFACTUAL_QA',source_original_archive='DualLP_Physics_Link_Validation_20261101.zip',source_archive_SHA256=sha('/mnt/data/DualLP_Physics_Link_Validation_20261101.zip'),
  source_git_original_FullH='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13',
  n_LoS_source_observer_parity_cases=3,n_new_LoS_runs=24,n_saved_full_parity_runs=6,
  full_trace_score_max_abs=err,los_replay_score_max_abs=max([abs(x['heading_score_diff_deg']) for x in scored]+[abs(x['xy_score_diff_cm']) for x in scored]),
  los_native_observer_max_range_diff_m=float(par.range_max_diff_m.max()),los_native_observer_max_s_diff=float(par.s_max_diff.max()),
  full_bb_mb_state_max_abs=float(bb.state_max_abs.max()),full_bb_mb_P_max_abs=float(bb.P_max_abs.max()),full_mask_mismatch_sum=int(bb.mask_mismatch.sum()),
  original_physical_packet_rows=len(phys),original_12_gyro_conditions=12,n_original_archived_self_scores=24,n_total_stage_rows=len(stage),
  n_figures_png=len(fig),n_figures_svg=len(fig),n_rt_calls=0,
  all_cases_one_scene=True,original_full_rf_data_untouched=True,
  los_filter_reference='NEW_EXPLORATORY_ZERO_MEAN_AND_FROZEN_FULL_MEAN',
  los_multipath_only_causal_claim_allowed=False,
  publication_ready_as_controlled_physics_story='WITH_MEAN_CONFOUND_AND_SCENE_LIMITS')
(T/'VALIDATION_SUMMARY.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
print('VALIDATION_OK',json.dumps(meta,ensure_ascii=False))
