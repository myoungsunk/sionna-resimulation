#!/usr/bin/env python3
"""Route-held-out B-only observation calibration pilot.

Uses only R2/R4/R5 B0 Full seed 10, with a leave-one-route-out training
contract. The heldout truth is loaded *after* all its online filters complete.
The historical native observer, RF, controls, Q and initial states are frozen.
Offline training may use truth solely for residual covariance estimation.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback

for env in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[env] = "1"
import numpy as np
from fp_ns_ablation import load_original_replay, identical_input_condition, metrics, json_dump, rehash, wrap
from replay_evidence import baseline_parity, replay_checkpoint

ROUTES = ("R2", "R4", "R5")
ARMS = ("NATIVE_FROZEN", "B_FROZEN", "B_BIAS", "B_COV", "B_BIAS_COV", "B_BIAS_FULLCOV")
NO_CAL = ("NATIVE_FROZEN", "B_FROZEN")
EPS = 1e-12


def sym(a):
    a = np.asarray(a, float)
    return (a + a.T) * .5


def psd_positive_part(a):
    vals, vecs = np.linalg.eigh(sym(a))
    return sym((vecs * np.maximum(vals, 0.)[None, :]) @ vecs.T)


def summarize_residuals(v):
    v = np.asarray(v, float)
    if v.ndim != 2 or v.shape[1] != 2 or not np.isfinite(v).all():
        raise ValueError('INVALID_RESIDUAL')
    centered = v - v.mean(axis=0)
    cov = sym(centered.T @ centered / len(v))
    lag1 = np.array([float(np.corrcoef(centered[:-1,i],centered[1:,i])[0,1]) if np.std(centered[:,i])>0 else 0. for i in range(2)])
    return dict(n=len(v), mean=v.mean(axis=0).tolist(), rms=np.sqrt(np.mean(v*v,axis=0)).tolist(),
                centered_std=np.sqrt(np.diag(cov)).tolist(), cov=cov.tolist(), lag1=lag1.tolist(),
                median=np.median(v,axis=0).tolist(), p95_abs=np.quantile(abs(v), .95, axis=0).tolist())


def truth_h(model, spec, truth, chunk=16):
    # x=(x,y,heading,bias), where bias does not enter this measurement model.
    truth = np.asarray(truth,float)
    assert truth.ndim == 2 and truth.shape[1] == 3
    predicted=[]
    for k in range(0,len(truth),chunk):
        x=np.column_stack((truth[k:k+chunk],np.zeros(min(chunk,len(truth)-k))))
        h,_=model.batch(x,spec)
        predicted.append(h)
    predicted=np.concatenate(predicted)
    assert predicted.shape==(len(truth),2) and np.isfinite(predicted).all()
    return predicted


def read_observations(r45, route):
    case=f'{route}_B0_Full_10'
    on=r45.data(case,'online.npz')
    B,native,zN,zB=identical_input_condition(on,r45,case)
    return case,on,B,native,zN,zB


def training_route_stats(r45,model,route):
    case,on,B,native,zN,zB=read_observations(r45,route)
    ev=r45.data(case,'evaluator.npz')
    assert np.array_equal(ev['t'],on['t']) and np.array_equal(ev['pose_id'],on['pose_id'])
    htruth=truth_h(model,r45.SPEC,ev['truth'])
    resid_N=zN-htruth-on['muMB']
    resid_B=zB-htruth-on['muMB']
    diff=zB-zN
    assert np.max(abs(resid_B-resid_N-diff))<1e-10
    return dict(route=route,n=len(on['t']),rN=resid_N,rB=resid_B,diff=diff,
                Rmean=on['R'].mean(axis=0),
                descriptive={'native_residual':summarize_residuals(resid_N),
                             'B_residual_frozen':summarize_residuals(resid_B),
                             'B_minus_native_observation':summarize_residuals(diff),
                             'tap_changed_n':int((B!=native).sum())})


def route_balanced_fit(training):
    # route-macro rather than sample-micro weights, to prevent R5 dominating.
    assert len(training)==2 and len({g['route'] for g in training})==2
    delta=np.mean([g['diff'].mean(axis=0) for g in training],axis=0)
    # Route-balanced *centered* detector-specific covariance difference.
    # Measurement mean's route offsets are tracked separately in diagnostics.
    cB=np.mean([sym(np.cov(g['rB'].T,ddof=0)) for g in training],axis=0)
    cN=np.mean([sym(np.cov(g['rN'].T,ddof=0)) for g in training],axis=0)
    differential=sym(cB-cN)
    cov_diag=np.diag(np.maximum(np.diag(differential),0.))
    cov_full=psd_positive_part(differential)
    assert np.linalg.eigvalsh(cov_diag).min()>=-EPS
    assert np.linalg.eigvalsh(cov_full).min()>=-EPS
    return dict(delta_mu=delta,R_add_diag=cov_diag,R_add_full=cov_full,
                var_B=cB,var_N=cN,cov_difference=differential,
                train_routes=[g['route'] for g in training],train_n=sum(g['n'] for g in training),
                delta_by_route={g['route']:g['diff'].mean(axis=0).tolist() for g in training})


def make_packet(on,zB,fit,arm):
    packet=dict(on)
    if arm=='NATIVE_FROZEN':return packet
    packet['z']=zB.copy()
    if arm in ('B_BIAS','B_BIAS_COV','B_BIAS_FULLCOV'):
        # Same change to shadow and main mean: keeps the frozen gate contract.
        packet['muMB']=np.asarray(on['muMB'])+fit['delta_mu'][None,:]
        packet['muBASE']=np.asarray(on['muBASE'])+fit['delta_mu'][None,:]
    if arm in ('B_COV','B_BIAS_COV'):
        packet['R']=np.asarray(on['R'])+fit['R_add_diag'][None,:,:]
    elif arm=='B_BIAS_FULLCOV':
        packet['R']=np.asarray(on['R'])+fit['R_add_full'][None,:,:]
    assert np.linalg.eigvalsh(packet['R']).min()>0,('R_NOT_SPD',arm)
    return packet


def expected_parity(route,on,tr,arm,r45):
    # Original W0 and BB must match independently stored old R45 run.
    if arm=='NATIVE_FROZEN':
        for key in ('prior','Pprior','h','H','Reff','K','mask'):
            exp=on['trace_'+key];actual=tr[key]
            assert actual.shape==exp.shape
            e=float(np.max(abs(actual.astype(float)-exp.astype(float))/np.maximum(1.,abs(exp.astype(float)))))
            assert e<=1e-10,('NN_BASELINE_PARITY_FAIL',route,key,e)
    elif arm=='B_FROZEN':
        with np.load(r45.ROOT/'R45_RUN_001'/(route+'_TRACE.npz'),allow_pickle=False) as old:
            for key,target in [('x','x'),('P','P'),('prior','prior'),('Pprior','Pprior'),('h','h'),('H','H'),('K','K'),('Reff','R'),('mask','accepted')]:
                exp=old[target][:,0];actual=tr[key]
                e=float(np.max(abs(actual.astype(float)-exp.astype(float))/np.maximum(1.,abs(exp.astype(float)))))
                assert e<=1e-10,('B_BASELINE_PARITY_FAIL',route,key,e)


def evaluate_route(route, on, zB, fit, r45, core, online, model, hashes, out):
    case=f'{route}_B0_Full_10'
    controls={key:on[key] for key in ('ds','gy','dt')};controls['x0']=on['x0'][:3]
    traces={}
    for arm in ARMS:
        packet=make_packet(on,zB,fit,arm)
        path=out/(route+'_'+arm+'.npz')
        traces[arm]=replay_checkpoint(path,packet,controls,core,online,model,r45.SPEC,hashes)
        expected_parity(route,on,traces[arm],arm,r45)
    # Truth never enters the heldout calibration process. Only now evaluate.
    ev=r45.data(case,'evaluator.npz')
    assert np.array_equal(ev['t'],on['t']) and np.array_equal(ev['pose_id'],on['pose_id'])
    scores={arm:metrics(t['x'],t['P'],ev['truth'],t['mask']) for arm,t in traces.items()}
    nn=scores['NATIVE_FROZEN'];bb=scores['B_FROZEN']
    for arm in ARMS:
        scores[arm]['delta_heading_mse_vs_B']=scores[arm]['heading_mse_deg2']-bb['heading_mse_deg2']
        scores[arm]['delta_xy_mse_vs_B']=scores[arm]['xy_mse_m2']-bb['xy_mse_m2']
        scores[arm]['gate_flip_vs_B']=int(np.count_nonzero(traces[arm]['mask']!=traces['B_FROZEN']['mask']))
    rows=[]
    for k,t in enumerate(on['t']):
        row={'route':route,'k':k,'t_s':float(t)}
        for arm in ARMS:
            e=traces[arm]['x'][k,:3]-ev['truth'][k];e[2]=wrap(e[2]);m=traces[arm]['mask'][k]
            row[arm+'_heading_err_deg']=float(np.degrees(e[2]));row[arm+'_xy_err_cm']=float(100*np.linalg.norm(e[:2]))
            row[arm+'_accepted']=int(m);row[arm+'_nis']=float(traces[arm]['nis'][k]);row[arm+'_Pheading']=float(traces[arm]['P'][k,2,2]);row[arm+'_Pxy_trace']=float(np.trace(traces[arm]['P'][k,:2,:2]))
        rows.append(row)
    with (out/(route+'_SCORES.csv')).open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    return dict(route=route,n=len(on['t']),metrics=scores,
                fit={'train_routes':fit['train_routes'],'train_n':fit['train_n'],
                     'delta_mu':fit['delta_mu'].tolist(),
                     'R_add_diag':fit['R_add_diag'].tolist(),'R_add_full':fit['R_add_full'].tolist(),
                     'cov_B':fit['var_B'].tolist(),'cov_N':fit['var_N'].tolist(),
                     'cov_difference':fit['cov_difference'].tolist(),
                     'delta_by_route':fit['delta_by_route']})


def pool(routes):
    n=sum(x['n'] for x in routes)
    answer={}
    for arm in ARMS:
        d={field:sum(route['n']*route['metrics'][arm][field] for route in routes)/n for field in
           ('heading_mse_deg2','xy_mse_m2','mean_nees3','pose95_coverage','xy95_coverage','heading95_coverage')}
        d['heading_rmse_deg']=math.sqrt(d['heading_mse_deg2'])
        d['xy_rmse_cm']=100*math.sqrt(d['xy_mse_m2'])
        d['accepted']=sum(route['metrics'][arm]['accepted'] for route in routes)
        d['delta_heading_mse_vs_B']=d['heading_mse_deg2']-sum(route['n']*route['metrics']['B_FROZEN']['heading_mse_deg2'] for route in routes)/n
        d['delta_xy_mse_vs_B']=d['xy_mse_m2']-sum(route['n']*route['metrics']['B_FROZEN']['xy_mse_m2'] for route in routes)/n
        answer[arm]=d
    return answer


def selftest():
    train=[{'route':'R2','n':4,'diff':np.array([[-1.,0.1],[-1.,-.1],[0.,0.],[0.,0.]]),
            'rN':np.array([[0.,0.], [0.,0.], [.1,.1],[-.1,-.1]]),
            'rB':np.array([[-1.,0.1],[-1.,-.1],[.1,.1],[-.1,-.1]])},
           {'route':'R5','n':3,'diff':np.array([[0.,0.],[0.,0.],[-.3,.6]]),
            'rN':np.array([[0.,0.],[.1,-.1],[-.1,.1]]),
            'rB':np.array([[0.,0.],[.1,-.1],[-.4,.7]])}]
    fit=route_balanced_fit(train)
    assert np.allclose(fit['delta_mu'],np.array([(-.5-.1)/2,(0.+.2)/2]))
    assert np.linalg.eigvalsh(fit['R_add_full']).min()>-1e-12
    assert np.linalg.eigvalsh(fit['R_add_diag']).min()>-1e-12
    base={'z':np.zeros((3,2)),'R':np.tile(np.diag([.01,.02]),(3,1,1)),
          'muMB':np.ones((3,2))*.05,'muBASE':np.ones((3,2))*.04}
    n=make_packet(base,np.ones((3,2)),fit,'NATIVE_FROZEN')
    b=make_packet(base,np.ones((3,2)),fit,'B_FROZEN')
    mu=make_packet(base,np.ones((3,2)),fit,'B_BIAS')
    rc=make_packet(base,np.ones((3,2)),fit,'B_COV')
    mrc=make_packet(base,np.ones((3,2)),fit,'B_BIAS_COV')
    full=make_packet(base,np.ones((3,2)),fit,'B_BIAS_FULLCOV')
    assert n['z'] is base['z'] and b['z'] is not n['z']
    assert np.allclose(mu['muMB']-base['muMB'],fit['delta_mu'])
    assert np.allclose(mu['muBASE']-base['muBASE'],fit['delta_mu'])
    assert np.allclose(rc['R']-base['R'],fit['R_add_diag'])
    assert np.allclose(mrc['R']-base['R'],fit['R_add_diag'])
    assert np.allclose(full['R']-base['R'],fit['R_add_full'])
    assert np.allclose(b['muMB'],base['muMB'])
    return {'status':'SYNTHETIC_QA_PASS','split':'R2 R4 R5 leave-one-route-out',
            'no_fit_on_heldout':True,'fit_mean':fit['delta_mu'].tolist(),'fit_cov':fit['R_add_diag'].tolist()}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('--selftest',action='store_true')
    p.add_argument('--heldout',choices=ROUTES)
    a=p.parse_args()
    if a.selftest:
        print(json.dumps(selftest(),indent=2));return
    if a.repo is None or a.out is None or a.heldout is None:p.error('--repo, --out and --heldout are required')
    repo=a.repo.resolve();out=a.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    src=Path(__file__).resolve()
    contract=dict(status='RUNNING',role='IMPLEMENTER_SELF_CHECK',
       time_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
       reference_commit='c141839093d1a2e4a76f91eea632cb6467163e28',
       execution_git_sha=os.environ.get('GITHUB_SHA','LOCAL'),
       code_sha256=rehash(src),
       scope='B-only, NO K1 K2; R2 R4 R5 B0 Full seed10',
       split=f'Holdout {a.heldout}; train exclusively other two routes',
       target='B detector vs pinned native W0 with unchanged motion, Q, and SourceFFD',
       arms=list(ARMS),
       mean='Route macro-average of zB-zN; added to muMB and muBASE; constant at inference',
       R='Route balanced positive eigenvalue part of Cov(resB)-Cov(resN); diagonal-only primary; PSD full sensitivity',
       fit_truth_use='Training routes only; SourceFFD h(true) used in training residual covariance. Heldout truth read after replay.',
       caveats=['same corridor, one seed; route holdout is not scene or seed holdout',
                'existing native-conditioned mu/R were previously frozen with unknown original fit split',
                'R inflation alone cannot detect coherent bias; direct detector correction not guaranteed',
                'B_BIAS_FULLCOV is sensitivity, not data-selected winner'])
    json_dump(out/'CONTRACT.json',contract)
    try:
        r45,core,online,model,hashes=load_original_replay(repo)
        heldout=a.heldout
        training=[training_route_stats(r45,model,r) for r in ROUTES if r!=heldout]
        fit=route_balanced_fit(training)
        assert heldout not in fit['train_routes']
        # This process does not access the heldout evaluator until *after* the
        # actual recursive filter predictions have been completed.
        case,on,B,n,zN,zB=read_observations(r45,heldout)
        score=evaluate_route(heldout,on,zB,fit,r45,core,online,model,hashes,out)
        descriptions={g['route']:g['descriptive'] for g in training}
        report=dict(status='PASS_IMPLEMENTER_SELF_CHECK',independent_audit=False,
                    heldout=heldout,n=score['n'],fit=score['fit'],
                    training_routes=[g['route'] for g in training],
                    score=score['metrics'],training_descriptive=descriptions,
                    scientific_decision='Route-held-out exploratory pilot only; do not tune on holdout')
        json_dump(out/'RESULTS.json',report)
        print('HELDOUT_COMPLETE',heldout,json.dumps({arm:{'heading_deg':round(val['heading_rmse_deg'],4),'xy_cm':round(val['xy_rmse_cm'],4)} for arm,val in score['metrics'].items()}),flush=True)
        contract['status']='PASS_IMPLEMENTER_SELF_CHECK';contract['ended_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
        json_dump(out/'CONTRACT.json',contract)
        json_dump(out/'SHA256.json',{x.name:rehash(x) for x in out.iterdir() if x.is_file() and x.name!='SHA256.json'})
        print('HELDOUT_CHECKS_PASS', heldout, 'n=', score['n'], flush=True)
    except BaseException as e:
        json_dump(out/'FAILURE.json',{'error':repr(e),'traceback':traceback.format_exc()})
        raise

if __name__=='__main__':main()