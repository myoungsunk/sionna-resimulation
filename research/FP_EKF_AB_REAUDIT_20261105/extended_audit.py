#!/usr/bin/env python3
"""Regression tests and archived-evaluation audit. Patches are isolated proposals.
No replacement of original results and no patched nonlinear-performance claim.
"""
from __future__ import annotations
import argparse, importlib.util, sys, json, math, difflib, hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import audit


def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def history_trial(H,k,corrupt=None):
    ids=np.arange(400);h=H(60,'audit-config',ids)
    state=SimpleNamespace(last_index=-1,last_pose_id=None,source_pose_ids=tuple(ids))
    h.save(-1,-1.,state)
    for i in range(k+1):
        assert h.append(i,i*.2,dict(pose_id=int(i)))
        state.last_index=i;state.last_pose_id=int(i)
        if i<k:h.save(i,i*.2,state)
    if corrupt=='missing':h.packets.popleft()
    if corrupt=='config':h.checkpoints[0].config_hash='wrong'
    if corrupt=='pose':h.packets[0][2]['pose_id']=-99
    selected=h.replay_input(0,k)
    return dict(available=selected is not None,checkpoint=selected[0].last_index if selected else None,suffix=len(selected[1]) if selected else 0,oldest_packet=h.packets[0][0],oldest_checkpoint=h.checkpoints[0].last_index)

def run(root):
    out=root/'evidence';inputs=out/'inputs';src=inputs/audit.BASE;patch=root/'patches';patch.mkdir(exist_ok=True)
    hp=src/'S3/history.py';raw=hp.read_text()
    old='while self.checkpoints and self.checkpoints[0].timestamp < cutoff:'
    new='while len(self.checkpoints) > 1 and self.checkpoints[1].timestamp < cutoff:'
    assert raw.count(old)==1
    fixed=raw.replace(old,new)
    (patch/'history_retention_fixed.py').write_text(fixed)
    (patch/'history_retention.diff').write_text(''.join(difflib.unified_diff(raw.splitlines(True),fixed.splitlines(True),fromfile='S3/history.py (original)',tofile='S3/history.py (proposed boundary fix)')))
    orig=module(hp,'audit_history_original');repaired=module(patch/'history_retention_fixed.py','audit_history_repaired')
    tests=[]
    for k in [290,295,296,299,300,301]:
        a=history_trial(orig.History,k);b=history_trial(repaired.History,k)
        tests.append(dict(test='initial_episode_boundary',index=k,t_s=.2*k,original_available=a['available'],patched_available=b['available'],patched_checkpoint=b['checkpoint'],patched_suffix=b['suffix'],oldest_packet=b['oldest_packet']))
    for mode in ['missing','config','pose']:
        r=history_trial(repaired.History,300,mode);assert not r['available'];tests.append(dict(test=mode,patched_available=r['available']))
    assert not history_trial(orig.History,300)['available']
    assert history_trial(repaired.History,300)['available']
    assert not history_trial(repaired.History,301)['available'] # packet zero genuinely unavailable
    audit.table(out/'HISTORY_BOUNDARY_REGRESSION.csv',tests)
    events=pd.DataFrame(json.loads((src/'S3/runs/EVAL_001/EVENTS.json').read_text()))
    insuff=events[events.disposition=='HISTORY_INSUFFICIENT'].copy();rescued=[]
    for e in insuff.itertuples():
        assert float(e.first)==0.
        a=history_trial(orig.History,int(e.index));b=history_trial(repaired.History,int(e.index))
        rescued.append(dict(route=e.route,bias=e.bias,channel=e.channel,seed=e.seed,arm=e.arm,index=e.index,time_s=e.index*.2,first_s=e.first,original_eligible=a['available'],patched_history_eligible=b['available'],patched_suffix=b['suffix'],claim='history eligibility only; candidate and performance not rerun'))
    audit.table(out/'ALL_28_HISTORY_FAILURES_REPRODUCED.csv',rescued)
    assert all(not x['original_eligible'] and x['patched_history_eligible'] for x in rescued)

    rp=src/'S2/recovery.py';rt=rp.read_text();r=module(rp,'audit_recovery_original')
    G=np.array([[2.,0,0,1.],[0,2.,0,0],[0,0,2.,0],[1.,0,0,1.]])
    H=np.linalg.cholesky(G).T/r.SCALES[None,:]
    geometry=r.Geometry();geometry.add(0,H,np.eye(4),np.eye(4),True)
    ok,logged_conditional,logged_marginal,actualG=geometry.information()
    assert np.allclose(actualG,G,atol=1e-12)
    conditional=float(np.linalg.eigvalsh(G[:3,:3]-np.outer(G[:3,3],G[:3,3])/G[3,3]).min())
    marginal=float(np.linalg.eigvalsh(G[:3,:3]).min())
    assert abs(logged_conditional-marginal)<1e-12 and abs(logged_marginal-conditional)<1e-12
    newrt=rt.replace("else:return False,float(np.linalg.eigvalsh(A)[0]),float('nan'),G","else:return False,float('nan'),float(np.linalg.eigvalsh(A)[0]),G").replace("return minimum>=1e-6,float(np.linalg.eigvalsh(A)[0]),minimum,G","return minimum>=1e-6,minimum,float(np.linalg.eigvalsh(A)[0]),G")
    assert newrt!=rt
    (patch/'recovery_labels_fixed.py').write_text(newrt)
    (patch/'information_labels.diff').write_text(''.join(difflib.unified_diff(rt.splitlines(True),newrt.splitlines(True),fromfile='S2/recovery.py (original)',tofile='S2/recovery.py (label-only proposed fix)')))
    r2=module(patch/'recovery_labels_fixed.py','audit_recovery_fixed');q=r2.Geometry();q.add(0,H,np.eye(4),np.eye(4),True);ok2,c2,m2,_=q.information()
    assert ok==ok2 and abs(c2-conditional)<1e-12 and abs(m2-marginal)<1e-12
    info=[];gate_rows=[];sensor=[];score_parity=[]
    recalc=pd.read_csv(out/'RECOMPUTED_SCORES.csv')
    for route in ('R4','R5'):
      truth=audit.artifact_truth(inputs,route);gt=truth['truth_scoring_only'];t=truth['t_s'];dt=np.r_[0.,np.diff(t)]
      angle=np.r_[0.,audit.wrap(np.diff(gt[:,2]))]
      ds=np.r_[0.,np.sum(np.diff(gt[:,:2],axis=0)*np.column_stack([np.cos(gt[:-1,2]),np.sin(gt[:-1,2])]),axis=1)]
      for seed in (10,14,20):
        noise=np.random.default_rng([2201008,seed,2]).standard_normal((len(t),2))
        odom=ds+noise[:,0]*np.sqrt(2e-5*np.abs(ds))
        gyro=angle+np.random.default_rng([2201008,seed,3]).standard_normal(len(t))*math.radians(.015)*np.sqrt(dt)
        ct=pd.read_csv(out/f'CONTROLS_RECONSTRUCTED_S3_{route}_{seed}.csv')
        de=float(np.max(abs(ct.ds-odom)));ge=float(np.max(abs(ct.gy-gyro)))
        assert max(de,ge)<1e-13
        sensor.append(dict(route=route,seed=seed,odom_max_abs=de,gyro_max_abs=ge,method='independent B0 sensor-v2 RNG equations; not loaded from evaluated states'))
        for stage,arms in [('S2',['A','B','C_P','D_P']),('S3',['A','B','C_CP','D_CP'])]:
          archived=pd.read_csv(src/stage/'runs/EVAL_001/SCORES_PER_SEED.csv')
          for arm in arms:
            name=f'{route}_aB_m0_B0_Full_{seed}_{arm}'+('_main' if stage=='S3' else '')
            tr=audit.load_npz(src/stage/'runs/EVAL_001'/(name+'.npz'))
            gate_rows.append(dict(stage=stage,route=route,seed=seed,arm=arm,n=len(t),shadow_accept_own_nis_reject=int(np.sum(tr['mask']&(tr['nis']>audit.GATE))),shadow_reject_own_nis_accept=int(np.sum(~tr['mask']&(tr['nis']<=audit.GATE)))))
            a=archived[(archived.route==route)&(archived.bias=='B0')&(archived.channel=='Full')&(archived.seed==seed)&(archived.arm==arm)&(archived.window=='primary')].iloc[0]
            b=recalc[(recalc.stage==stage)&(recalc.route==route)&(recalc.seed==seed)&(recalc.arm==arm)].iloc[0]
            err=max(abs(a.heading_rmse_deg-b.heading_rmse_deg),abs(a.xy_rmse_m-b.xy_rmse_m),abs(a.heading_coverage95-b.heading95))
            assert err<1e-11
            score_parity.append(dict(stage=stage,route=route,seed=seed,arm=arm,max_abs=err))
            if stage=='S2':
              for k,g in enumerate(tr['information']):
                A=g[:3,:3];v=g[:3,3];c=g[3,3];tol=1e-12*max(1.,np.linalg.norm(g,2))
                if c>tol:C=A-np.outer(v,v)/c
                elif np.linalg.norm(v)<=tol:C=A
                else:continue
                cond=float(np.linalg.eigvalsh((C+C.T)/2).min());marg=float(np.linalg.eigvalsh(A).min())
                info.append(dict(route=route,seed=seed,arm=arm,index=k,true_conditional=cond,true_marginal=marg,logged_conditional=float(tr['conditional_lambda'][k]),logged_marginal=float(tr['marginal_lambda'][k])))
    audit.table(out/'CONTROL_SENSOR_RNG_CROSSCHECK.csv',sensor);audit.table(out/'OWN_NIS_VS_SHADOW_GATE.csv',gate_rows);audit.table(out/'PUBLISHED_SCORE_PARITY.csv',score_parity);audit.table(out/'INFORMATION_LABEL_AUDIT.csv',info)
    info=pd.DataFrame(info)
    swap_error=max(float((info.true_conditional-info.logged_marginal).abs().max()),float((info.true_marginal-info.logged_conditional).abs().max()))
    assert swap_error<1e-8

    groups=[];pairs=[];event_counts=[]
    for stage in ('S2','S3'):
      d=pd.read_csv(src/stage/'runs/EVAL_001/SCORES_PER_SEED.csv');d=d[d.window=='primary']
      for key,g in d.groupby(['route','bias','channel','arm']):
        groups.append(dict(stage=stage,route=key[0],bias=key[1],channel=key[2],arm=key[3],n_seeds=len(g),mean_seed_heading_rmse_deg=float(g.heading_rmse_deg.mean()),mean_heading95=float(g.heading_coverage95.mean()),mean_seed_xy_rmse_m=float(g.xy_rmse_m.mean())))
      for key,g in d.groupby(['route','bias','channel']):
        w=g.pivot(index='seed',columns='arm',values='heading_rmse_deg');xy=g.pivot(index='seed',columns='arm',values='xy_rmse_m')
        comparisons=[('B','A'),('C_P','A'),('D_P','B')] if stage=='S2' else [('B','A'),('C_CP','A'),('D_CP','B')]
        for treatment,control in comparisons:
          delta=w[treatment]-w[control];dx=xy[treatment]-xy[control]
          pairs.append(dict(stage=stage,route=key[0],bias=key[1],channel=key[2],treatment=treatment,control=control,n=len(delta),mean_heading_delta_deg=float(delta.mean()),median_heading_delta_deg=float(delta.median()),heading_better=int((delta<-1e-9).sum()),heading_worse=int((delta>1e-9).sum()),heading_unchanged=int((delta.abs()<=1e-9).sum()),xy_worse=int((dx>1e-9).sum())))
    for key,g in events.groupby(['route','bias','channel','arm','disposition']):event_counts.append(dict(zip(['route','bias','channel','arm','disposition'],key),count=len(g)))
    audit.table(out/'ALL_EVAL_PRIMARY_GROUPS.csv',groups);audit.table(out/'ALL_EVAL_PAIRED_OUTCOMES.csv',pairs);audit.table(out/'ALL_S3_EVENT_DISPOSITIONS.csv',event_counts)

    # Counterfactual gate regression independent of archived partial recovery of S.
    P=np.array([[1.,.15],[.15,.5]]);H=np.array([[1.,.2],[.1,1.]]);R=np.diag([.2,.3]);S=H@P@H.T+R;K=np.linalg.solve(S,H@P).T
    J=np.eye(2)-K@H;correct=J@P@J.T+K@R@K.T;algebra=P-K@S@K.T
    assert np.allclose(correct,algebra,atol=1e-14) and not np.allclose(P,correct)
    audit.dump(out/'EXTENDED_QA.json',dict(history_failure_events=len(rescued),all_28_buffer_failures_reproduced=True,all_28_patch_history_eligible=True,patched_full_nonlinear_performance_run=False,missing_packets_config_and_pose_fail_closed=True,geometry_synthetic=dict(true_conditional=conditional,true_marginal=marginal,original_logged_conditional=logged_conditional,original_logged_marginal=logged_marginal,decision_unchanged=ok==ok2),geometry_actual_rows=len(info),geometry_swap_error_max=swap_error,independent_sensor_control_pairs=len(sensor),max_sensor_control_difference=max(max(r['odom_max_abs'],r['gyro_max_abs']) for r in sensor),score_parity_runs=len(score_parity),max_score_parity_difference=max(r['max_abs'] for r in score_parity),C1_Joseph_covariance_identity_max=float(np.max(abs(correct-algebra))),important_limits=['Buffer patch only preserves one predecessor checkpoint; does not fabricate missing packets.','A newly available candidate may still fail adoption bounds or worsen state error. No corrected performance claimed.','S3 uses a common shadow BASE gate by design, not target-chain self-gating.','All new files are evidence and isolated patches; original historical results remain unchanged.']))
    audit.dump(out/'OUTPUT_SHA256.json',{str(p.relative_to(root)):audit.digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='OUTPUT_SHA256.json' and '__pycache__' not in p.parts})
    print((out/'EXTENDED_QA.json').read_text(),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root)
