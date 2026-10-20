#!/usr/bin/env python3
"""Aggregate fixed event comparisons; no learned threshold or tested RF gate.
Higher values of each prelisted indicator are the predeclared suspect direction.
Episode annotations and prior skip gains are offline labels, never predictors.
"""
from pathlib import Path
import csv,json,sys
import numpy as np
source=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
rows=[];timing=[];receipts=[]
for p in sorted(source.glob('*_ONLINE_EVENTS.csv')):
    with p.open(newline='') as f:rows+=list(csv.DictReader(f))
for p in sorted(source.glob('*_FP_TIMING_EVAL.csv')):
    with p.open(newline='') as f:timing+=list(csv.DictReader(f))
for p in sorted(source.glob('*_AUDIT.json')):receipts.append(json.loads(p.read_text()))
assert len(rows)==12 and len(receipts)==6,(len(rows),len(receipts))
assert sum(x['total_packets'] for x in receipts)==2647
for r in rows:
    for k,v in list(r.items()):
        if k not in ('route','anchor','coordinate','skip_reference_replayed_now'):
            try:r[k]=float(v) if v!='' else None
            except ValueError:pass
keys=['pol_fp_vs_early4_abs_median','pol_delay_std16_median','pol_early4_vs16_abs_median','late_energy_fraction40_median','delay_spread40_ns_median','peak_minus_detected_fp_ns_median','port_envelope_mismatch16_median','detector_time_span_ns_median','detector_pol_span_median','abs_s_full_median','saturation_full_mean']
def auc(y,x):
    pos=x[y];neg=x[~y]
    if not len(pos) or not len(neg):return None
    return float(np.mean((pos[:,None]>neg[None,:])+.5*(pos[:,None]==neg[None,:])))
def rank(a):
    order=np.argsort(a);r=np.empty(len(a),float);start=0
    while start<len(a):
        end=start+1
        while end<len(a) and a[order[end]]==a[order[start]]:end+=1
        r[order[start:end]]=(start+end-1)/2;start=end
    return r
results=[]
for scope,rs in [('all12',rows),('exclude_initial_transient', [r for r in rows if r['t_start_s']>=30])]:
    y=np.array([r['historical_skip_gain_deg']>.2 for r in rs]);g=np.array([r['historical_skip_gain_deg'] for r in rs])
    for key in keys:
        x=np.array([r[key] for r in rs],float);valid=np.isfinite(x)
        a=auc(y[valid],x[valid]);rho=float(np.corrcoef(rank(x[valid]),rank(g[valid]))[0,1]) if len(set(x[valid]))>1 else None
        results.append({'scope':scope,'feature':key,'n':int(valid.sum()),'skip_benefit_positive':int(y[valid].sum()),'AUC_high_is_suspect':a,'spearman_gain':rho,'new_policy_trained':False})
# nearest-neighbour only exploratory waveform-phenotype matching, normalization uses
# the compared event set and therefore must never be called prospective validation.
match_keys=['pol_fp_vs_early4_abs_median','pol_delay_std16_median','late_energy_fraction40_median','abs_s_full_median']
X=np.array([[r[k] for k in match_keys] for r in rows]);median=np.median(X,axis=0);scale=np.median(abs(X-median),axis=0);scale=np.maximum(scale,.01);Z=(X-median)/scale
pairs=[]
for i,r in enumerate(rows):
    choices=[j for j,s in enumerate(rows) if s['route']!=r['route']]
    order=sorted(choices,key=lambda j:float(np.sum((Z[i]-Z[j])**2)))[:2]
    for j in order:
        s=rows[j];pairs.append({'reference':f"{r['route']}_{r['anchor']}_{r['low']}_{r['high']}_V{r['visit']}",'reference_skip_gain':r['historical_skip_gain_deg'],'other':f"{s['route']}_{s['anchor']}_{s['low']}_{s['high']}_V{s['visit']}",'other_skip_gain':s['historical_skip_gain_deg'],'feature_distance':float(np.linalg.norm(Z[i]-Z[j])),'direction_agrees':(r['historical_skip_gain_deg']>.2)==(s['historical_skip_gain_deg']>.2),'prospective_validation':False})
def write(name,rs):
    allkeys=list(dict.fromkeys(k for r in rs for k in r))
    with (out/name).open('w',newline='') as f:w=csv.DictWriter(f,allkeys);w.writeheader();w.writerows(rs)
write('ALL_ONLINE_EVENTS.csv',rows);write('ONLINE_EVENT_DISCRIMINATION.csv',results);write('CROSS_ROUTE_PHENOTYPE_MATCHES.csv',pairs);write('FP_TIMING_ALL.csv',timing)
report={'status':'EXECUTED_FULL_ONLY_FEATURE_DESCRIPTIVE_AUDIT','n_observed_packets':2647,'n_routes':6,'n_anchors_routes':9,'n_preselected_events':12,'n_positive_skip_events':sum(r['historical_skip_gain_deg']>.2 for r in rows),'online_input':['two time-aligned port CIR powers from current Full packet'], 'excluded_predictors':['H_LoS','H_Full-H_LoS','true_pose','true_heading','true_arrival','future_packets','coherent_cross_port_phase'],'feature_windows_ns':[4,16,40],'offline_use':['known geometry episode identity','historical causal RF skip effects','Direct-LoS and geometric arrival timing diagnostics'], 'new_EKF_runs':0,'online_gate_or_model_selected':False,'independent_event_or_environment_validation':False,'hardware_replay':False,'notes':['Raw H ideal simulation; hardware noise and sequential port synchronization not emulated','Measured |s| saturation is not Heading Jacobian','No current-prior covariance or likelihood-branch metrics computed in this artifact','Scalar AUROC is 12 selected correlated events, not validation','R4/R5 old or regenerated Mount45 excluded from this new six-route audit','Time oversampling compares grid only, no repeated CIR acquisition'],'pure_path_qa':receipts[0]['unit_checks']}
(out/'FINAL_QA.json').write_text(json.dumps(report,indent=2))
lines=['# Full-only observable RF indicators: executed descriptive audit','',json.dumps(report,ensure_ascii=False,indent=2),'','## Event metrics (candidate features only)','|event|skip gain deg|Dpol4|sigma_pol16|late E40|detector Ds|abs s|','|--|--:|--:|--:|--:|--:|--:|']
for r in rows:
    lines.append('|%s %s [%.0f,%.0f) V%.0f|%+.3f|%.4f|%.4f|%.4f|%.4f|%.4f|'%(r['route'],r['anchor'],r['low'],r['high'],r['visit'],r['historical_skip_gain_deg'],r['pol_fp_vs_early4_abs_median'],r['pol_delay_std16_median'],r['late_energy_fraction40_median'],r['detector_pol_span_median'],r['abs_s_full_median']))
lines+=['','## All12 single-feature rankings (no policy fitting)']
for r in results:
    if r['scope']=='all12':lines.append(json.dumps(r))
lines+=['','## Fixed physical-reference firstpath checks (ns, no antenna/calibration offset removed)']
for r in timing:
    if r.get('scope')!='ALL_CASE':lines.append(json.dumps(r))
(out/'RESULTS.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines),flush=True)
print('AGGREGATE_ONLINE_PASS',2647,12,flush=True)
