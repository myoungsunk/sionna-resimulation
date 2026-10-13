"""D15 fixed 16N dense single-tap candidate; additive diagnostic runner.
Derived from frozen D11/D12 plumbing. No scientific PASS.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
from collections import defaultdict
import numpy as np
from d15_dense_core import (EarlyWindowConfig,METHODS,extract_cir_methods,
  hann_pulse_template,new_output,write_rows,stage_finish,file_sha)
from d6_d9_common import (OBS,check_inputs,checked_path,spectrum,tap_metres)
from p3_compat import frozen_detector
from run_d5_regimes import timelines

ONLINE_KEYS=('case','route','channel','pose_id','sample_index','t_s',
 'method','s_value','frozen_fp_s','frozen_fp_tap','frozen_range_m',
 'reference_port','co_only_fp_index','window_start','window_stop_exclusive',
 'window_width_taps','cross_rise_onset','cross_rise_detected',
 'cross_to_co_ratio_at_fp','reference_selection_ambiguous',
 'stop_reason','unresolved_at_fp_unidentifiable')


def extract_case(p0, case, channel, freqs, route, cfg, chunk):
    t,truth,pids=route # truth deliberately NOT passed to the extractor
    samples=json.loads(checked_path(p0,case['samples_path']).read_text(encoding='utf-8'))
    positions={int(row['pose_id']):i for i,row in enumerate(samples)}
    if len(positions)!=len(samples):raise RuntimeError('Duplicate frozen RF pose id')
    ids=[positions[int(pid)] for pid in pids]
    H=np.load(checked_path(p0,case[channel+'_path']),mmap_mode='r',allow_pickle=False)
    if tuple(H.shape)!=tuple(case['H_shape']):raise RuntimeError('Frozen H shape mismatch')
    template=hann_pulse_template(len(freqs),4*len(freqs))
    output=[]
    for begin in range(0,len(ids),chunk):
        inds=np.asarray(ids[begin:begin+chunk],int)
        h=np.asarray(H[inds],complex)
        frozen=frozen_detector(h,freqs,float(case['mount_deg']),OBS,chunk_size=len(h))
        cir=OBS.cir_batch(h[...,0]);original=OBS.first_path_batch(cir,float(freqs[1]-freqs[0]))
        if (not np.array_equal(original['index'],frozen['index']) or
            not np.allclose(original['s'],frozen['s'],atol=1e-12,rtol=0) or
            not np.allclose(original['range_m'],frozen['range_raw_m'],atol=1e-10,rtol=0)):
            raise RuntimeError('Frozen detector parity mismatch - FAIL CLOSED')
        for j in range(len(inds)):
            values,extra=extract_cir_methods(cir[j],fp_index=int(original['index'][j]),
                                             config=cfg,template=template)
            if not np.isclose(values['W0_FP'],original['s'][j],atol=1e-12,rtol=0):
                raise RuntimeError('W0 must equal original signed FP s')
            i=begin+j
            for method in METHODS:
                row=dict(case=case['id'],route=case['route'],channel=channel,
                   pose_id=int(pids[i]),sample_index=i,t_s=float(t[i]),
                   method=method,s_value=float(values[method]),
                   frozen_fp_s=float(original['s'][j]),
                   frozen_fp_tap=int(original['index'][j]),
                   frozen_range_m=float(original['range_m'][j]),
                   reference_port=int(extra['selected_reference_rx']),
                   co_only_fp_index=int(extra['co_only_fp_index']),
                   window_start=float(original['index'][j]) if method=='W0_FP' else float(extra['window_begin']),
                   window_stop_exclusive=float(original['index'][j])+1 if method=='W0_FP' else float(extra['window_end_exclusive']),
                   window_width_taps=1.0 if method=='W0_FP' else float(extra['window_width_taps']),
                   cross_rise_onset=extra['cross_rise_onset'],
                   cross_rise_detected=extra['cross_rise_detected'],
                   cross_to_co_ratio_at_fp=float(extra['cross_to_co_ratio_at_fp']),
                   reference_selection_ambiguous=extra['reference_selection_ambiguous'],
                   stop_reason=extra['stop_reason'],
                   unresolved_at_fp_unidentifiable=1)
                if set(row)!=set(ONLINE_KEYS):raise RuntimeError('D11 online schema changed')
                output.append({key:row[key] for key in ONLINE_KEYS})
    return output


def score_pairs(records):
    """Create oracle Full-LoS comparison SEPARATELY from online s records."""
    bykey=defaultdict(dict)
    for r in records:
        key=(r['case'],r['sample_index'],r['method'])
        if r['channel'] in bykey[key]:raise RuntimeError('Duplicate D11 RF record')
        bykey[key][r['channel']]=r
    if not bykey:raise RuntimeError('Empty D11 pairs')
    paired=[]
    for (case,idx,method),two in sorted(bykey.items()):
        if set(two)!=set(('full','los')):raise RuntimeError('Unpaired Full/LoS D11 samples')
        a,b=two['full'],two['los']
        if a['pose_id']!=b['pose_id'] or a['t_s']!=b['t_s']:
            raise RuntimeError('D11 Full/LoS pose or timeline mismatch')
        if a['t_s']<30:continue
        paired.append(dict(case=case,route=a['route'],pose_id=a['pose_id'],
            sample_index=idx,t_s=a['t_s'],method=method,
            s_full=a['s_value'],s_los=b['s_value'],
            delta_s=float(a['s_value']-b['s_value']),
            abs_delta_s=float(abs(a['s_value']-b['s_value'])),
            full_cross_rise_detected=a['cross_rise_detected'],
            full_window_width_taps=a['window_width_taps'],
            los_window_width_taps=b['window_width_taps'],
            full_reference_port=a['reference_port'],
            los_reference_port=b['reference_port'],
            ambiguous_reference=int(a['reference_selection_ambiguous'] or b['reference_selection_ambiguous'])))
    if not paired:raise RuntimeError('No evaluable paired windows')
    groups=defaultdict(list)
    for r in paired:
        groups[(r['method'],'ALL_SCENE')].append(r)
        groups[(r['method'],r['route'])].append(r)
        groups[(r['method'],r['case'])].append(r)
    summary=[]
    for (method,group),rows in sorted(groups.items()):
        d=np.array([r['delta_s'] for r in rows],float)
        summary.append(dict(method=method,group=group,n=len(rows),
            rms_full_minus_los_s=float(np.sqrt(np.mean(d*d))),
            mean_full_minus_los_s=float(np.mean(d)),
            p95_abs_full_minus_los_s=float(np.quantile(abs(d),.95)),
            mean_full_window_taps=float(np.mean([r['full_window_width_taps'] for r in rows])),
            fraction_cross_rise_detected=float(np.mean([r['full_cross_rise_detected'] for r in rows])),
            fraction_reference_ambiguous=float(np.mean([r['ambiguous_reference'] for r in rows]))))
    return paired,summary


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--co-port',choices=['auto','rx1','rx2'],default='auto')
    ap.add_argument('--max-taps',type=int,default=4)
    ap.add_argument('--max-search-taps',type=int,default=9)
    ap.add_argument('--growth-ratio',type=float,default=1.7)
    ap.add_argument('--excess-over-co-fp',type=float,default=.025)
    ap.add_argument('--rise-factor',type=float,default=1.08)
    ap.add_argument('--consecutive',type=int,default=2)
    ap.add_argument('--noise-floor-power',type=float,default=0.)
    ap.add_argument('--chunk',type=int,default=64)
    args=ap.parse_args()
    if args.chunk<1:raise ValueError('Positive chunk required')
    cfg=EarlyWindowConfig(co_port=args.co_port,max_taps=args.max_taps,
      max_search_taps=args.max_search_taps,growth_ratio=args.growth_ratio,
      excess_over_co_fp=args.excess_over_co_fp,rise_factor=args.rise_factor,
      consecutive=args.consecutive,noise_floor_power=args.noise_floor_power).validate()
    p0=check_inputs()
    if (args.co_port!='auto' or args.max_taps!=4 or args.max_search_taps!=9 or args.growth_ratio!=1.7 or args.excess_over_co_fp!=.025 or args.rise_factor!=1.08 or args.consecutive!=2 or args.noise_floor_power!=0):raise ValueError('Dense candidate configuration frozen')
    frequency=spectrum(p0)
    cases={x['id']:x for x in p0['cases']}
    requested=args.cases or list(cases)
    if len(set(requested))!=len(requested) or any(k not in cases for k in requested):
        raise ValueError('Bad/duplicate case')
    routes=timelines(p0)
    online=[]
    for name in requested:
        case=cases[name]
        for ch in ('los','full'):
            online.extend(extract_case(p0,case,ch,frequency,routes[case['route']],cfg,args.chunk))
    paired, summary=score_pairs(online)
    out=new_output(args.out)
    a=out/'D11_ONLINE_WINDOW_S.csv';b=out/'D11_ORACLE_PAIR_EVAL.csv';c=out/'D11_CASE_SUMMARY.csv'
    write_rows(a,online);write_rows(b,paired);write_rows(c,summary)
    stage_finish(out,'D11',[a,b,c],config=vars(args),evidence={
        'p0_input_manifest_sha256':file_sha(Path(__file__).resolve().parents[1]/'P0_INPUT_MANIFEST.json')},warnings=[
       'Online CSV contains ONLY per-channel observables. Paired Full-LoS differences are oracle-only.',
       'auto reference is strongest at frozen FP; not geometrically invariant co/cross',
       'cross growth may be present in clean LoS; compare to fixed W1 and oracle labels',
       'unresolved interference present from the first tap cannot be separated by adaptive cutoff',
       '4N zero padding gives closely correlated samples, not 0.15 m physical resolution',
       'W3 Hann-only template is a numerical sensitivity control, not a verified direct-wave estimator',
       'Results are descriptive on ONE frozen scene and must not be called a scientific PASS'])
    print('D11_EXPLORATORY_DONE',str(out))
if __name__=='__main__':main()
