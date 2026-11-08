#!/usr/bin/env python3
"""Native vs B closed-loop [range,s] 2x2 causal ablation.

Read-only source; never fits/calibrates anything; evaluator truth is loaded only
AFTER all natural and forced-mask recursive runs are complete.

Requirements: working checkout of pinned sionna-resimulation repository with
R45_sources, source SHA, FFD banks and archived online/evaluator NPZ payloads
materialized exactly as specified by r45.py and RUN_002/SUMMARY.json.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import pathlib
import sys
import traceback
from replay_evidence import replay_checkpoint,baseline_parity

for _key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[_key]='1'
import numpy as np
from scipy.stats import chi2

ARMS=('NN','BN','NB','BB')
ALT=('BN','NB','BB')
SOURCE_COMMIT='c141839093d1a2e4a76f91eea632cb6467163e28'
EPS=1e-10


def wrap(a):
    return (a+np.pi)%(2*np.pi)-np.pi


def rehash(path:pathlib.Path)->str:
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def synthetic_selftest():
    # Algebraic one-step additive effect at common K / fixed gate.
    K=np.array([[.15,.04],[-.10,.27],[.02,.63],[0.,0.]])
    dr,ds=-.14955225880474907,+.073
    combined=K@np.array([dr,ds]); parts=K[:,0]*dr+K[:,1]*ds
    assert np.allclose(combined,parts,atol=1e-15)
    # A measurement chosen from the prediction can decrease variance while
    # leaving an erroneous estimate untouched: demonstration, NOT RF evidence.
    x_true,x_prior,P_prior,R=0.,1.,.2,.01
    z_pseudo=x_prior;gain=P_prior/(P_prior+R)
    x_after=x_prior+gain*(z_pseudo-x_prior)
    P_after=(1-gain)**2*P_prior+gain*gain*R
    assert x_after==x_prior and P_after<P_prior
    assert (x_after-x_true)**2/P_after>(x_prior-x_true)**2/P_prior
    return {'synthetic_additive_innovation':'PASS',
            'synthetic_self_confirmation':'PASS',
            'note':'Synthetic QA is NOT full-Sionna scientific execution'}


def json_dump(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')


def dump_csv(path,rows):
    if not rows:return
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)


def metrics(x,P,truth,accepted):
    err=x[:,:3]-truth;err[:,2]=wrap(err[:,2])
    hd=np.degrees(err[:,2]);xy=np.linalg.norm(err[:,:2],axis=1)
    c=P[:,:3,:3]; n3=np.einsum('ni,ni->n',err,np.linalg.solve(c,err[...,None])[...,0])
    nxy=np.einsum('ni,ni->n',err[:,:2],np.linalg.solve(c[:,:2,:2],err[:,:2,None])[...,0])
    nh=err[:,2]**2/P[:,2,2]
    return dict(n=len(x),heading_mse_deg2=float(np.mean(hd**2)),
                xy_mse_m2=float(np.mean(xy**2)),
                heading_rmse_deg=float(np.sqrt(np.mean(hd**2))),
                xy_rmse_cm=float(100*np.sqrt(np.mean(xy**2))),
                heading_MAE_deg=float(np.mean(abs(hd))),
                mean_nees3=float(np.mean(n3)),
                pose95_coverage=float(np.mean(n3<=chi2.ppf(.95,3))),
                xy95_coverage=float(np.mean(nxy<=chi2.ppf(.95,2))),
                heading95_coverage=float(np.mean(nh<=chi2.ppf(.95,1))),
                accepted=int(np.sum(accepted)))


def load_original_replay(repo:pathlib.Path):
    # Imports only after the archival source hierarchy is verified.
    fp=repo/'research'/'FP_SC_RECOVERY_R0_R5_20261107'
    if not (fp/'r45.py').is_file():
        raise FileNotFoundError('Missing pinned R0-R5 folder: '+str(fp))
    sys.path.insert(0,str(fp))
    import r45
    if r45.ROOT.resolve()!=fp.resolve():raise ValueError('R45_SOURCE_MISMATCH')
    core,online,model,hashes=r45.load_original_model(r45.SRC)
    return r45,core,online,model,hashes


def identical_input_condition(on, r45, case):
    # SAME NOISY Full channel.  These are alternative detection functions, not
    # alternative RF channels or re-synthesized noise realizations.
    from qclean_uwb.drivesim import observation as obs
    cir=obs.cir_batch(on['Hrf']);a=np.abs(cir)
    own_peak=a.max(axis=1)
    own_edges=np.argmax(a>=.30*own_peak[:,None,:],axis=1)
    B=own_edges.min(axis=1).astype(int)
    native=obs.first_path_batch(cir,1950000)
    n=np.asarray(native['index'],int)
    p=a**2;den=p.sum(axis=2)
    assert np.isfinite(den).all() and np.all(den>0)
    s_by_tap=(p[:,:,0]-p[:,:,1])/den
    zN=np.asarray(on['z'],float)
    zB=np.column_stack([B*r45.STEP,s_by_tap[np.arange(len(B)),B]])
    assert np.max(abs(zN[:,0]-n*r45.STEP)) < 1e-9,(case,'NATIVE_RANGE_MISMATCH')
    assert np.max(abs(zN[:,1]-native['s'])) < 1e-10,(case,'NATIVE_S_MISMATCH')
    assert np.all(B<=n),(case,'UNEXPECTED_B_LATER_THAN_NATIVE')
    equal=B==n
    assert np.max(abs(zB[equal]-zN[equal]))<1e-10,(case,'SAME_TAP_BUT_DIFFERENT_MEASUREMENT')
    return B,n,zN,zB


def common_shadow_gate(core,online,model,spec,controls,on,zs):
    n=len(on['z']);sx=on['x0'].copy();sp=on['P0'].copy()
    nis=np.zeros((n,len(ARMS))); masks=np.zeros((n,len(ARMS)),bool)
    for k in range(n):
        sx,sp=online.predict(core,sx,sp,k,controls)
        hh,HH=model.batch(sx[None],spec);h=hh[0];H=HH[0]
        R=on['R'][k];S=H@sp@H.T+R
        for j,arm in enumerate(ARMS):
            v=zs[arm][k]-h-on['muBASE'][k]
            nis[k,j]=float(v@np.linalg.solve(S,v))
            masks[k,j]=nis[k,j]<=online.GATE
        if masks[k,0]:
            v=zs['NN'][k]-h-on['muBASE'][k]
            gain=np.linalg.solve(S,H@sp).T
            sx+=gain@v;sx[2]=wrap(sx[2])
            A=np.eye(4)-gain@H
            sp=A@sp@A.T+gain@R@gain.T
            sp=(sp+sp.T)*.5
    return nis,masks


def calc_one_step(trN, zs, on):
    z0=zs['NN'];K=np.asarray(trN['K'])
    dr=zs['BB'][:,0]-z0[:,0];ds=zs['BB'][:,1]-z0[:,1]
    # Ungated hypothetical gain from the SAME native prior/H/Reff, even when
    # the shadow gate rejected. This is a counterfactual, not an actual update.
    H=trN['H'];P=trN['Pprior'];R=trN['Reff']
    S=H@P@H.transpose(0,2,1)+R;S=(S+S.transpose(0,2,1))*.5
    hypothetical=np.linalg.solve(S,H@P).transpose(0,2,1)
    assert np.allclose(K[trN['mask']],hypothetical[trN['mask']],atol=1e-12,rtol=1e-12)
    dR=K[:,:,0]*dr[:,None];dS=K[:,:,1]*ds[:,None]
    potentialR=hypothetical[:,:,0]*dr[:,None];potentialS=hypothetical[:,:,1]*ds[:,None]
    direct=np.einsum('nij,nj->ni',K,zs['BB']-z0)
    assert np.max(abs(direct-dR-dS))<1e-12
    return dr,ds,dR,dS,potentialR,potentialS,hypothetical


def case_data(case,on,ev_loader,zs,native,B,core,online,model,r45,output,hashes,baseline,calibration):
    controls={k:on[k] for k in ['ds','gy','dt']}
    controls['x0']=on['x0'][:3]
    # Truth is not accessed until all genuine recursive calculations finish.
    route=case.split('_')[0]
    traces={}
    for arm in ARMS:
        packet=dict(on);packet['z']=zs[arm]
        checkpoint=(baseline/(route+'_'+arm+'.npz')) if calibration=='frozen' and arm in ('NN','BB') else output/'checkpoints'/(route+'_'+arm+'.npz')
        traces[arm]=replay_checkpoint(checkpoint,packet,controls,core,online,model,r45.SPEC,hashes)
    tN=traces['NN'];tB=traces['BB']
    if calibration=='frozen':
        parity=baseline_parity(case,on,tN,tB,r45.ROOT/'R45_RUN_001'/(route+'_TRACE.npz'))
        native_errors={k:v for k,v in parity.items() if k.startswith('NN_')}
        b_errors={k:v for k,v in parity.items() if k.startswith('BB_')}
    else:
        native_errors={'status':'NOT_APPLICABLE_MODIFIED_CALIBRATION'}
        b_errors={'status':'NOT_APPLICABLE_MODIFIED_CALIBRATION'}

    common_nis,common_mask=common_shadow_gate(core,online,model,r45.SPEC,controls,on,zs)
    assert np.array_equal(common_mask[:,0],tN['mask']),(case,'SHADOW_GATE_REPLAY_FAIL')
    # Third design: each arm receives NN gate decisions at ALL timesteps.
    fixed={'NN':tN}
    for arm in ALT:
        packet=dict(on);packet['z']=zs[arm]
        fixed[arm]=replay_checkpoint(output/'checkpoints'/(route+'_'+arm+'_fixed.npz'),packet,controls,core,online,model,r45.SPEC,hashes,mask=tN['mask'])
        assert np.array_equal(fixed[arm]['mask'],tN['mask'])

    dr,ds,dR,dS,potentialR,potentialS,hypothetical=calc_one_step(tN,zs,on)
    # Exact innovation accounting: muMB is fixed in every arm.
    # nu_BB - nu_NN = (z_BB - z_NN) - (h_BB - h_NN).
    direct_z=zs['BB']-zs['NN']
    changed_model=tB['h']-tN['h']
    observed_nu=tB['nu']-tN['nu']
    innovation_identity=float(np.max(abs(observed_nu-(direct_z-changed_model))))
    assert innovation_identity<1e-10
    equal_current_z=np.all(abs(direct_z)<1e-10,axis=1)
    def rms(v):return float(np.sqrt(np.mean(np.asarray(v)**2)))
    innovation_accounting=dict(
        direct_observation_rms_range_m=rms(direct_z[:,0]),
        direct_observation_rms_s=rms(direct_z[:,1]),
        model_feedback_rms_range_m=rms(changed_model[:,0]),
        model_feedback_rms_s=rms(changed_model[:,1]),
        final_innovation_difference_rms_range_m=rms(observed_nu[:,0]),
        final_innovation_difference_rms_s=rms(observed_nu[:,1]),
        identical_observation_n=int(equal_current_z.sum()),
        identical_observation_model_feedback_rms_range_m=rms(changed_model[equal_current_z,0]),
        identical_observation_model_feedback_rms_s=rms(changed_model[equal_current_z,1]),
        exact_identity_max_error=innovation_identity)
    # Post-inference-only evaluation begins here. Evaluator is loaded now,
    # never before either natural or fixed-gate prediction finishes.
    ev=ev_loader()
    assert np.array_equal(ev['t'],on['t']) and np.array_equal(ev['pose_id'],on['pose_id'])
    truth=ev['truth']
    assert truth.shape==(len(zs['NN']),3)
    results={arm:metrics(t['x'],t['P'],truth,t['mask']) for arm,t in traces.items()}
    results_fixed={arm:metrics(t['x'],t['P'],truth,t['mask']) for arm,t in fixed.items()}
    # Loss effects: MSE has additive population sums; RMSE does not.
    interactions={}
    for metric in ['heading_mse_deg2','xy_mse_m2']:
        v={arm:results[arm][metric] for arm in ARMS}
        interactions[metric]={
            'range_only_BN_minus_NN':v['BN']-v['NN'],
            's_only_NB_minus_NN':v['NB']-v['NN'],
            'total_BB_minus_NN':v['BB']-v['NN'],
            'interaction_BB_minus_BN_minus_NB_plus_NN':v['BB']-v['BN']-v['NB']+v['NN']}
    interactions_fixed=interaction_effects(results_fixed)
    same=np.all(abs(zs['NN']-zs['BB'])<1e-10,axis=1)
    state_xy=np.linalg.norm(tB['x'][:,:2]-tN['x'][:,:2],axis=1)
    state_psi=np.degrees(abs(wrap(tB['x'][:,2]-tN['x'][:,2])))
    persistent=same & ((state_xy>1e-7)|(state_psi>1e-6))
    contamination=dict(same_current_NN_BB_observation=int(same.sum()),
         same_observation_but_diverged_states=int(persistent.sum()),
         same_observation_mean_XY_state_separation_cm=float(100*state_xy[same].mean()) if same.any() else None,
         same_observation_mean_heading_state_separation_deg=float(state_psi[same].mean()) if same.any() else None,
         same_observation_gate_disagreement=int(np.sum((tN['mask']!=tB['mask'])&same)),
         common_NN_prior_gate_disagreements={arm:int(np.count_nonzero(common_mask[:,j]!=common_mask[:,0])) for j,arm in enumerate(ARMS) if arm!='NN'},
         natural_gating_disagreements={arm:int(np.count_nonzero(traces[arm]['mask']!=tN['mask'])) for arm in ALT},
         n_native_B_difference=int(np.sum(abs(dr)>1e-10)),
         step_delta_r_mean_changed_cm=float(100*np.mean(dr[abs(dr)>1e-10])) if np.any(abs(dr)>1e-10) else 0.,
         delta_s_MAE=float(np.mean(abs(ds))),
         instant_same_prior_mean_abs_heading_effect_range_deg=float(np.degrees(np.mean(abs(dR[:,2]))),),
         instant_same_prior_mean_abs_heading_effect_s_deg=float(np.degrees(np.mean(abs(dS[:,2]))),),
         instant_same_prior_heading_delta_correlation=float(np.corrcoef(dR[:,2],dS[:,2])[0,1]) if np.std(dR[:,2])>0 and np.std(dS[:,2])>0 else None)
    one_step_groups={}
    for label,mask in [('all',np.ones(len(dr),bool)),('native_accepted',tN['mask']),('native_rejected',~tN['mask'])]:
        one_step_groups[label]={'n':int(mask.sum()),'counterfactual':True}
        for name,v in [('actual_range',dR),('actual_s',dS),('potential_range',potentialR),('potential_s',potentialS)]:
            one_step_groups[label][name+'_heading_mean_abs_deg']=float(np.degrees(np.mean(abs(v[mask,2])))) if mask.any() else None
    rows=[]
    for k in range(len(on['t'])):
        row={'case':case,'k':k,'t_s':float(on['t'][k]),'native_tap':int(native[k]),'B_tap':int(B[k]),
             'delta_r_m':float(dr[k]),'delta_s':float(ds[k]),'same_observation':bool(same[k]),
             'NN_accepted':bool(tN['mask'][k]),'BB_accepted':bool(tB['mask'][k]),
             'NN_nis':float(tN['nis'][k]),'BB_nis':float(tB['nis'][k]),
             'NN_shadow_common_nis':float(common_nis[k,0]),
             'BB_shadow_common_nis':float(common_nis[k,3]),
             'NN_to_BB_state_xy_cm':float(state_xy[k]*100),
             'NN_to_BB_state_heading_deg':float(state_psi[k]),
             'instant_psi_delta_range_deg':float(np.degrees(dR[k,2])),
             'instant_psi_delta_s_deg':float(np.degrees(dS[k,2])),
             'potential_psi_delta_range_deg':float(np.degrees(potentialR[k,2])),
             'potential_psi_delta_s_deg':float(np.degrees(potentialS[k,2])),
             'NN_heading_abs_error_deg':float(abs(np.degrees(wrap(tN['x'][k,2]-truth[k,2])))),
             'BB_heading_abs_error_deg':float(abs(np.degrees(wrap(tB['x'][k,2]-truth[k,2])))),
             'NN_XY_error_cm':float(100*np.linalg.norm(tN['x'][k,:2]-truth[k,:2])),
             'BB_XY_error_cm':float(100*np.linalg.norm(tB['x'][k,:2]-truth[k,:2]))}
        rows.append(row)
    dump_csv(output/(route+'_ROWS.csv'),rows)
    np.savez_compressed(output/(route+'_TRACES.npz'),
        native_tap=native,B_tap=B,delta_r_m=dr,delta_s=ds,
        actual_delta_range=dR,actual_delta_s=dS,potential_delta_range=potentialR,potential_delta_s=potentialS,hypothetical_K=hypothetical,
        common_gate_nis=common_nis,common_gate_mask=common_mask,
        **{a+'_'+key:value for a,tr in traces.items() for key,value in tr.items()},
        **{a+'_fixedgate_'+key:value for a,tr in fixed.items() for key,value in tr.items()},
        **{a+'_z':zs[a] for a in ARMS},base_R=on['R'],muBASE=on['muBASE'],muMB=on['muMB'],
        t=on['t'],pose_id=on['pose_id'])
    return dict(case=case,n=len(on['t']),metrics=results,metrics_fixed_mask=results_fixed,
                interactions=interactions,interactions_fixed_mask=interactions_fixed,one_step_groups=one_step_groups,contamination=contamination,
                innovation_accounting=innovation_accounting,
                original_W0_parity=native_errors,old_R5_B_parity=b_errors)


def interaction_effects(results):
    ans={}
    for metric in ['heading_mse_deg2','xy_mse_m2']:
        v={arm:results[arm][metric] for arm in ARMS}
        ans[metric]={'range_BN_minus_NN':v['BN']-v['NN'],'s_NB_minus_NN':v['NB']-v['NN'],
            'total_BB_minus_NN':v['BB']-v['NN'],'interaction':v['BB']-v['BN']-v['NB']+v['NN']}
    return ans


def pool(case_results):
    n=sum(s['n'] for s in case_results)
    ans={'n':n}
    for field in ['metrics','metrics_fixed_mask']:
        pooled={}
        for arm in ARMS:
            d={key:float(sum(v['n']*v[field][arm][key] for v in case_results)/n) for key in
                ['heading_mse_deg2','xy_mse_m2','mean_nees3','pose95_coverage','xy95_coverage','heading95_coverage']}
            d['heading_RMSE_deg']=float(np.sqrt(d['heading_mse_deg2']))
            d['XY_RMSE_cm']=float(100*np.sqrt(d['xy_mse_m2']))
            d['accepted']=sum(v[field][arm]['accepted'] for v in case_results)
            pooled[arm]=d
        ans[field]=pooled
        ans['interactions' if field=='metrics' else 'interactions_fixed_mask']=interaction_effects(pooled)
    ans['natural_minus_fixed_interaction']={key:ans['interactions'][key]['interaction']-ans['interactions_fixed_mask'][key]['interaction'] for key in ['heading_mse_deg2','xy_mse_m2']}
    ans['interpretation']='Natural-minus-fixed is a coupled mask/state intervention contrast, not uniquely identified gate-only causality.'
    return ans


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo',type=pathlib.Path,help='Pinned repository checkout')
    ap.add_argument('--out',type=pathlib.Path,help='NEW directory, must not already exist')
    ap.add_argument('--routes',nargs='+',choices=['R2','R4','R5'],default=['R2','R4','R5'])
    ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--baseline',type=pathlib.Path)
    ap.add_argument('--resume',action='store_true',help='Resume only same-code incomplete output; completed results immutable')
    ap.add_argument('--calibration',choices=['frozen','zero_mean','zero_mean_common_R'],default='frozen')
    args=ap.parse_args()
    if args.selftest:
        print(json.dumps(synthetic_selftest(),indent=2));return
    if args.repo is None or args.out is None:ap.error('--repo and --out are required unless --selftest')
    if args.baseline is None:ap.error('--baseline is required')
    gate=json.loads((args.baseline/'BASELINE_PASS.json').read_text())
    assert gate['status']=='PASS' and set(args.routes)<=set(gate['routes'])
    for name,digest in gate['checkpoint_sha256'].items():assert rehash(args.baseline/name)==digest
    repo=args.repo.resolve();output=args.out.resolve()
    if output.exists():
        if not args.resume:raise FileExistsError('Output exists; explicit --resume required: '+str(output))
        old=json.loads((output/'CONTRACT.json').read_text())
        assert old['status']=='RUNNING','COMPLETED_OUTPUT_IMMUTABLE'
        assert old['routes']==args.routes and old['calibration']==args.calibration
        assert old['baseline_gate_sha256']==rehash(args.baseline/'BASELINE_PASS.json')
        assert old['code_sha256']=={p.name:rehash(p) for p in pathlib.Path(__file__).parent.glob('*.py')},'RESUME_CODE_MISMATCH'

    r45,core,online,model,hashes=load_original_replay(repo)
    output.mkdir(parents=True,exist_ok=args.resume)
    contract=dict(source_commit=SOURCE_COMMIT,status='RUNNING',question='Native/B range-s 2x2 and closed-loop mechanisms',
                  running_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  routes=args.routes,arms=list(ARMS),calibration=args.calibration,
                  baseline_gate_sha256=rehash(args.baseline/'BASELINE_PASS.json'),
                  code_sha256={p.name:rehash(p) for p in pathlib.Path(__file__).parent.glob('*.py')},
                  execution_git_sha=os.environ.get('GITHUB_SHA','LOCAL_UNCOMMITTED_SELF_CHECK'),
                  causal_claim='Same initial state and RF/DR inputs; source-fixed no refit. Main and shadow gate evolve per arm.',
                  fixed_gate='Original NN gate mask frozen for counterfactual; all other recursion updates evolve',
                  source_hashes=hashes,
                  input_truth_separation='Evaluator loaded only after all recursive runs for a case',
                  caveats=['Exposed single seed, one corridor, no independent-scene inference',
                           'BN and NB mix components from two tap definitions; diagnostic ablation, not physical receiver policy',
                           'No re-training of muMB/muBASE, R, Q after detector change'])
    json_dump(output/'CONTRACT.json',contract)
    try:
        results=[]
        for route in args.routes:
            case=f'{route}_B0_Full_10'
            on=r45.data(case,'online.npz')
            B,native,zN,zB=identical_input_condition(on,r45,case)
            if args.calibration!='frozen':
                on=dict(on);on['muMB']=np.zeros_like(on['muMB']);on['muBASE']=np.zeros_like(on['muBASE'])
            if args.calibration=='zero_mean_common_R':
                # Common constant covariance from frozen input R only, no truth.
                # Retrospective sensitivity, not detector-specific calibration.
                common=np.mean(on['R'],axis=0);assert np.linalg.eigvalsh(common).min()>0
                on['R']=np.broadcast_to(common,on['R'].shape).copy()
            zs={'NN':zN,'BN':np.column_stack([zB[:,0],zN[:,1]]),
                'NB':np.column_stack([zN[:,0],zB[:,1]]),'BB':zB}
            # Replay without evaluator truth first.  The model is an identical
            # pinned SourceFFD model; no shortcut or geometry substitution.
            s=case_data(case,on,lambda case=case: r45.data(case,'evaluator.npz'),
                        zs,native,B,core,online,model,r45,output,hashes,args.baseline,args.calibration)
            results.append(s)
            json_dump(output/'SUMMARY_PARTIAL.json',dict(cases=results))
            print('CASE_COMPLETE',route,flush=True)
        ans=dict(status='PASS_IMPLEMENTER_SELF_CHECK',independent_audit=False,cases=results,pooled=pool(results))
        json_dump(output/'RESULTS.json',ans)
        contract['status']='PASS_IMPLEMENTER_SELF_CHECK'
        contract['ended_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        contract['outputs_sha256']={p.name:rehash(p) for p in output.iterdir() if p.is_file() and p.name not in ['CONTRACT.json','OUTPUT_SHA.json']}
        json_dump(output/'CONTRACT.json',contract)
        json_dump(output/'OUTPUT_SHA.json',{p.name:rehash(p) for p in output.iterdir() if p.is_file() and p.name!='OUTPUT_SHA.json'})
        print(json.dumps(ans['pooled'],ensure_ascii=False,indent=2))
    except BaseException as e:
        json_dump(output/'FAILURE.json',{'error':repr(e),'traceback':traceback.format_exc()})
        raise

if __name__=='__main__':main()
