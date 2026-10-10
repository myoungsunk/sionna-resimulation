"""Analyze saved L1 channels; no new LoS calculation or filter execution."""
from pathlib import Path
import json, hashlib, sys, time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim.hs_lut import HsLut
from qclean_uwb.features.fp_power import signed_s_single_tx
OUT=ROOT/'results/DRIVE_SIM_L1_STAGE3_20261008'
def read(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def write(n,v): (OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    r=read('RESULT.json'); rows=read('ALL_POINTS.json');samples=read('SAMPLES_RESULTS.json');cells=read('CELL_DECOMPOSITION.json');sweeps=read('SWEEPS.json');boundaries=read('BOUNDARIES.json');plan=read('PLAN.json')
    data=np.load(OUT/'RAW_CHANNEL_CIR.npz'); S=np.load(OUT/'inputs/hs_lut_2deg.npy')
    lut=HsLut(dict(s=S,theta_deg=np.arange(0,91,2),phi_deg=np.arange(-180,180,2)))
    fp=[]
    for sample in samples:
        h=np.zeros((257,2,2),complex);h[:,:,0]=data['H_tx0'][sample['id']]
        s,p,ix,delay=signed_s_single_tx(h,data['frequencies_hz'],tx=0)
        fp.append(dict(sample_id=sample['sample_id'],s_error=abs(s-sample['s_direct']),power_error=float(np.max(abs(p-np.array(sample['power'])))),index_match=ix==sample['index'],delay_error=abs(delay-sample['index']/(1028*1950000.))))
    top=[]
    for i in r['top_ids']:
        c=cells[i]; x=samples[i];top.append(dict(sample_id=i,angles=x['angles'],direct=x['s_direct'],lut=x['s_lut'],delta=x['delta'],center_tap=x['index'],vertex_taps=c['vertex_indices'],fixed_tap_interpolation_error=c['smooth_fixed_tap_error'],selection_component=c['selection_component']))
    diag=[]
    for sw in sweeps:
        rr=[rows[p['id']] for p in sw['points']];ix=np.array([x['index'] for x in rr]);s=np.array([x['s_direct'] for x in rr]);fixed=np.array([x['s_fixed'] for x in sw['points']]); li=np.array([x['s_lut'] for x in rr]); change=np.diff(ix)!=0
        jumps=[]
        for j in np.flatnonzero(change):
            jumps.append(dict(offset_before=sw['points'][j]['offset'],offset_after=sw['points'][j+1]['offset'],tap_before=int(ix[j]),tap_after=int(ix[j+1]),direct_change=float(s[j+1]-s[j]),fixed_tap_change=float(fixed[j+1]-fixed[j]),lut_change=float(li[j+1]-li[j])))
        center=rr[40];val,gradient=lut(*center['angles'],with_grad=True)
        diag.append(dict(sample_id=sw['sample_id'],axis=sw['axis'],n_index_changes=int(change.sum()),transitions=jumps,
            direct_center_slope_per_degree=float((s[41]-s[39])/.1),fixed_center_slope_per_degree=float((fixed[41]-fixed[39])/.1),lut_center_gradient_per_degree=float(gradient[sw['axis']]),center_neighbors_same_tap=bool(ix[39]==ix[40]==ix[41]),same_adjacent_index_max_direct_change=float(np.max(abs(np.diff(s)[~change]))),max_direct_change=float(np.max(abs(np.diff(s)))),max_fixed_change=float(np.max(abs(np.diff(fixed))))))
    pole=[rows[x['id']] for x in boundaries if x['type']=='pole_endpoint']
    indep=read('INDEPENDENT_CHECKS.json')
    checks=dict(n_original=len(samples),finite=r['finite_all'],distinct=len(np.unique(data['angles'][:500],axis=0)),
        original_vs_current_s_max=r['original_current_s_error_max'],independent_s_max=r['independent_s_error_max'],independent_interp_max=r['independent_interp_error_max'],
        independent_full_channel_relative_max=max(x['h_abs_max']/np.max(abs(data['H_tx0'][samples[x['sample_id']]['id']])) for x in indep),
        single_tx_feature_s_max=max(x['s_error'] for x in fp),single_tx_feature_indices_all=all(x['index_match'] for x in fp),single_tx_feature_delay_max=max(x['delay_error'] for x in fp),
        decomposition_residual_max=max(abs(x['decomposition_residual']) for x in cells),pole_endpoint_max_error=max(abs(x['delta']) for x in pole),
        protected_changed=[p for p,h in read('PROTECTED_BEFORE.json').items() if sha(ROOT/p)!=h])
    assert checks['n_original']==checks['distinct']==500 and checks['finite']
    assert r['independent_indices_all'] and checks['single_tx_feature_indices_all']
    assert checks['original_vs_current_s_max']<1e-10 and checks['independent_s_max']<1e-10
    assert checks['independent_interp_max']<1e-12 and checks['single_tx_feature_s_max']<1e-10
    assert r['grid_error_max']<1e-10 and r['wrap_lut_period_max']<1e-10 and r['wrap_direct_period_max']<1e-10
    # The only changed protected file is this turn's new validator serialization fix.
    assert checks['protected_changed']==['scripts\\drive_sim\\validate_l1_stage3.py']
    write('POST_CHECKS.json',checks);write('SINGLE_TX_FEATURE_CHECK.json',fp);write('DIAGNOSTIC_SUMMARY.json',dict(top=top,sweeps=diag,pole_details=pole))
    print(json.dumps(dict(checks=checks,top=top,sweep_summary=diag),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
