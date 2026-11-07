#!/usr/bin/env python3
"""PALO R2 / Anchor B: exact-model causal replay and hindsight-oracle comparisons.

Run from an unpacked, *actual-binary* POL_HEADING_RESEARCH_20261107 folder.
Uses the frozen S4 motion model, s-domain LUT, same gyro/odom controls,
R_s=0.0081 and NIS99 gate.  No Sionna RT, no refitting, no RF creation.

Ground truth is consulted ONLY by oracle decisions and offline scoring,
NEVER by the model, measurement generation, covariance formula, or dynamics.
The outcome-oracle is a hindsight diagnostic, not an implementable estimator.
"""
from __future__ import annotations
import argparse
import csv
import importlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

CH = ("los", "full")
LV = ("B0", "L0", "L1", "L2")
S4_IDX = 3
RS = 0.0081
GATE = 6.6348966010212145
Q_SCALES = (.02, .05, .10, .20)  # Predeclared RF quality thresholds, not optimized.


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def statistics(samples):
    # Each entry is a row at t >= 40s; no independence claim.
    a = samples
    rad = np.asarray([r['heading_rad'] for r in a], float)
    xy = np.asarray([r['xy_m'] for r in a], float)
    ppsi = np.asarray([r['Ppsi'] for r in a], float)
    xyv = np.asarray([r['Pxy_trace'] for r in a], float)
    return {
        'n': len(a), 'heading_rmse_deg': float(np.sqrt(np.mean(rad**2))*180/np.pi),
        'xy_rmse_m': float(np.sqrt(np.mean(xy**2))),
        'heading_95_coverage': float(np.mean(rad**2 <= 3.841458820694124*ppsi)),
        'heading_nees': float(np.mean(rad**2/ppsi)),
        'heading_sigma_rms_deg': float(np.sqrt(np.mean(ppsi))*180/np.pi),
        'xy_sigma_rms_m': float(np.sqrt(np.mean(xyv))),
        'applied': int(sum(r['applied'] for r in a)),
        'heading_p95_deg': float(np.quantile(np.abs(rad)*180/np.pi,.95)),
        'xy_p95_m': float(np.quantile(xy,.95)),
    }


def load_deps(root):
    frozen = root/'experiments'/'POL_FGO_CORR_20261106_v1'/'frozen'/'repo'
    folder = frozen/'research'/'EKF4_RANGE_S_STAGED_20261014'
    sys.path.insert(0, str(folder))
    import core
    import p3_rf_adapter4
    lut = p3_rf_adapter4.FrozenLut(root=frozen)
    manifest = json.loads((frozen/'research'/'EKF3_INDEPENDENT_20261013'/'P0_INPUT_MANIFEST.json').read_text())
    cases = {c['id']: c for c in manifest['cases']}
    return core, lut, cases['R2_aB_m0']


def get_input(root, ch):
    path=root/'inputs'/'original_run'/'verified_inputs'/f'R2_aB_m0_{ch}_seed0_ONE_STEP.npz'
    data=np.load(path,allow_pickle=False)
    return {k: data[k] for k in ('t_s','pose_id','z_s','truth_for_offline_scoring_only')}


def get_original(root, ch, lv):
    path=root/'inputs'/'original_run'/'results'/'replay'/f'R2_aB_m0_{ch}_{lv}_seed0_recursive.npz'
    return np.load(path,allow_pickle=False)


def get_controls(root, ch, lv):
    path=root/'experiments'/'POL_FGO_CORR_20261106_v1'/'outputs'/f'controls_{ch}_{lv}.npz'
    c=np.load(path,allow_pickle=False)
    return {k: c[k] for k in ('initial_pose','ds_odom','dtheta_gyro','dt_s')}


def make_initial(c):
    mean=np.r_[c['initial_pose'],0.0].astype(float)
    std=np.array([.1,.1,math.radians(5),math.radians(.1)])
    return mean,np.diag(std**2)


def predict(core,x,P,c,k):
    if k==0: return x,P
    ds=float(c['ds_odom'][k]); da=float(c['dtheta_gyro'][k]); dt=float(c['dt_s'][k])
    q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt])
    return core.predict(x,P,ds,da,dt,q)[:2]


def candidate(core,lut,case,xm,Pm,s):
    # Compute s likelihood/Jacobian at the policy's own predicted pose.
    def model(z):
        h,H=lut.model(z,case)
        return h[1:],H[1:]
    return core.gaussian_update(xm,Pm,np.array([float(s)]),model,np.array([[RS]]),gate_threshold=None)


def scored(x,P,truth):
    err=float(wrap(x[2]-truth[2]))
    xy=float(np.linalg.norm(x[:2]-truth[:2]))
    return {'heading_rad': err, 'xy_m': xy, 'Ppsi': float(P[2,2]),
            'Pxy_trace': float(P[0,0]+P[1,1])}


def select(policy,before,after,nis,channel,diff):
    head_good=abs(after['heading_rad'])+1e-12 < abs(before['heading_rad'])
    xy_good=after['xy_m']+1e-12 < before['xy_m']
    if policy=='s4': return nis<=GATE
    if policy=='dr': return False
    if policy=='oracle_heading': return head_good
    if policy=='oracle_xy': return xy_good
    if policy=='oracle_both': return head_good and xy_good
    if policy=='oracle_heading_gate': return head_good and nis<=GATE
    if policy=='oracle_both_gate': return head_good and xy_good and nis<=GATE
    if policy.startswith('rf_quality_'):
        tau=float(policy.removeprefix('rf_quality_'))
        return nis<=GATE and abs(diff)<=tau
    raise ValueError(policy)


def run_case(root,ch,lv,core,lut,case,los,full,output):
    frame=get_input(root,ch)
    truth=frame['truth_for_offline_scoring_only']
    t=frame['t_s']; s=frame['z_s']
    c=get_controls(root,ch,lv)
    original=get_original(root,ch,lv)
    n=len(t)
    assert n==979 and t.shape==los['t_s'].shape==full['t_s'].shape
    assert np.array_equal(t,los['t_s']) and np.array_equal(t,full['t_s'])
    assert np.array_equal(frame['pose_id'],los['pose_id']) and np.array_equal(frame['pose_id'],full['pose_id'])
    deltas=full['z_s']-los['z_s']
    policies=['dr','s4','oracle_heading','oracle_xy','oracle_both','oracle_heading_gate','oracle_both_gate']
    if ch=='full':policies.extend(f'rf_quality_{tau:.2f}' for tau in Q_SCALES)
    states={p:make_initial(c) for p in policies}
    outputs=defaultdict(list)
    cause=[]
    parity={'max_state':0.,'max_cov':0.,'max_nis':0.,'status_mismatch':0}
    for k in range(n):
        for policy in policies:
            prev_x,prev_P=states[policy]
            xm,Pm=predict(core,prev_x,prev_P,c,k)
            before=scored(xm,Pm,truth[k])
            xupd,Pupd,diag=candidate(core,lut,case,xm,Pm,s[k])
            after=scored(xupd,Pupd,truth[k])
            nis=diag['NIS']
            accept=select(policy,before,after,nis,ch,deltas[k])
            x,P=(xupd,Pupd) if accept else (xm,Pm)
            states[policy]=(x,P)
            val=scored(x,P,truth[k])
            outputs[policy].append({'t':float(t[k]),'k':int(k),'applied':int(accept),'NIS':nis,
                                    'heading_rad':val['heading_rad'],'xy_m':val['xy_m'],
                                    'Ppsi':val['Ppsi'],'Pxy_trace':val['Pxy_trace'],
                                    'prior_heading_rad':before['heading_rad'],'prior_xy_m':before['xy_m'],
                                    'candidate_heading_rad':after['heading_rad'],'candidate_xy_m':after['xy_m'],
                                    'full_los_s_difference':float(deltas[k])})
            if policy=='s4':
                expected_x=original['estimate'][k,S4_IDX]
                expected_P=original['covariance'][k,S4_IDX]
                expected_nis=original['nis'][k,S4_IDX]
                expected_status=str(original['status'][k,S4_IDX])
                parity['max_state']=max(parity['max_state'],float(np.max(np.abs(x-expected_x))))
                parity['max_cov']=max(parity['max_cov'],float(np.max(np.abs(P-expected_P))))
                parity['max_nis']=max(parity['max_nis'],abs(nis-expected_nis))
                parity['status_mismatch']+=int((expected_status=='APPLIED')!=accept)
                # Exact gain-side comparisons, not hindsight oracle evaluations.
                if k>=200:
                    cause.append({
                        'k':k,'t':float(t[k]),'prior_x':float(xm[0]),'prior_y':float(xm[1]),
                        'prior_heading_deg':float(np.rad2deg(xm[2])),
                        'Hpsi_abs':abs(float(diag['H'][0,2])),
                        'Hxy_norm':float(np.linalg.norm(diag['H'][0,:2])),
                        'nis':float(nis),'innovation':float(diag['innovation'][0]),
                        'innovation_sign':int(np.sign(diag['innovation'][0])),
                        's_diff_full_los':float(deltas[k]),
                        'Ppsi_prior':float(Pm[2,2]),
                        'Ppsi_post_if_update':float(Pupd[2,2]),
                        'Pxypsi_abs':float(np.linalg.norm(Pm[:2,2])),
                        'accepted_by_s4':int(accept),
                        'pre_heading_abs_deg':float(abs(before['heading_rad'])*180/np.pi),
                        'post_heading_abs_deg':float(abs(after['heading_rad'])*180/np.pi),
                        'pre_xy_m':float(before['xy_m']),
                        'post_xy_m':float(after['xy_m']),
                        'heading_good':int(abs(after['heading_rad'])<abs(before['heading_rad'])),
                        'xy_good':int(after['xy_m']<before['xy_m']),
                        'both_good':int(abs(after['heading_rad'])<abs(before['heading_rad']) and after['xy_m']<before['xy_m'])
                    })
    # Critical fail-closed: an apparently precise oracle result is invalid
    # unless the original S4 parity is reproduced first.
    if parity['max_state']>1e-7 or parity['max_cov']>1e-8 or parity['max_nis']>1e-7 or parity['status_mismatch']:
        raise RuntimeError(f'S4_REPLAY_PARITY_FAIL {ch}/{lv}: {parity}')
    summary={'channel':ch,'level':lv,'parity':parity,'policies':{},'oracle_scope': 'all 979 causal steps, report t>=40',
             'source': 'same frozen LUT, same controls, no refit'}
    for p in policies:
        summary['policies'][p]=statistics([z for z in outputs[p] if z['t']>=40])
        summary['policies'][p]['applied_all']=int(sum(z['applied'] for z in outputs[p]))
    output.mkdir(parents=True,exist_ok=True)
    for name,rows in (('candidate_diagnostics',cause),('policy_rows', [dict(policy=p,**z) for p in policies for z in outputs[p]])):
        with (output/f'{ch}_{lv}_{name}.csv').open('w',newline='',encoding='utf-8') as f:
            if rows:
                wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True,help='research/POL_HEADING_RESEARCH_20261107')
    p.add_argument('--output',type=Path,default=Path('PALO_ORACLE_CLOSEDLOOP_RESULT'))
    a=p.parse_args()
    root=a.root.resolve();out=a.output.resolve()
    core,lut,case=load_deps(root)
    los=get_input(root,'los');full=get_input(root,'full')
    result={'status':'PARTIAL','contract':{'evaluated_frames':'t>=40, 779 samples per channel/level',
              'true_pose_used_by_oracles':True,'physical_quality_oracle_uses_matched_Full_minus_LoS':True,
              'LUT':'same original frozen LUT','noise':'Rs=0.0081; original Q and 99% NIS gate',
              'holdout':'single route / seed 0; NOT blinded'},'cases':[]}
    for ch in CH:
        for lv in LV:
            case_result=run_case(root,ch,lv,core,lut,case,los,full,out)
            result['cases'].append(case_result)
            print(json.dumps({'completed':f'{ch}/{lv}','S4_parity':case_result['parity'],
                   'head_RMSE':{k:v['heading_rmse_deg'] for k,v in case_result['policies'].items()}},ensure_ascii=False),flush=True)
    result['status']='REPLAY_PARITY_PASS / HINDSIGHT_ORACLE_DIAGNOSTIC'
    (out/'SUMMARY.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('RESULT',out/'SUMMARY.json')


if __name__=='__main__': main()
