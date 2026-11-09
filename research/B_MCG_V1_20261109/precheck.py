"""Run usefulness diagnostics before any active recursive guard.

All truth access is in this offline evaluator/calibration file, not Monitor.
Thresholds are selected on other routes only. Failed gates remain failed.
"""
from pathlib import Path
import argparse,json,os,sys,time,traceback,csv
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import binary_dilation
from scipy.stats import rankdata
from numerics import *
from dataset import load,series,baselines,train_stats,calibration,ROUTES
from monitor import Monitor,MonitorConfig,weights

THRESHOLDS=(.5,1.,1.5,2.,3.,4.,6.,8.,12.,20.)

def plan():
    return dict(study='B-MCG-001-v1',status='EXPOSED_CORRIDOR_EXPLORATORY',window_s=5.,minimum_s=2.,profile_refit_s=1.,current_score_hz=5.,max_nfev=12,history_cost_slack=1.,history_mean_loss_limit=20.,target_width_sigma_limit=4.,threshold_grid=THRESHOLDS,beta_min=.25,lost_gain_budget=.05,route_rmse_ratio_limit=1.05,coverage_loss_pp_limit=3.,good_recovery_time_ratio_limit=1.1,stress_initial_yaw_deg=[-20,-10,-5,5,10,20],no_new_RF_simulation=True,staged_order='P0/P1/P2/P3/P4 -> P5 numerical/adversarial -> experimental implementation; failed usefulness forbids deployment',deviations=['History profile refit 1Hz, current score 5Hz. Window can extend 0.8s between refits.','Existing native mu/R lineage is not independently held out.','Calibration layer reuses frozen primary-policy thresholds to avoid nested calibration leakage.'])

def table(path,rows):
    if not rows:return
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def training_mask(traintruth,testtruth,t,embargo_s=20.):
    near=np.zeros(len(traintruth),bool);tree=cKDTree(testtruth[:,:2])
    for i,ids in enumerate(tree.query_ball_point(traintruth[:,:2],.05)):
        if ids and np.any(abs(wrap(testtruth[ids,2]-traintruth[i,2]))<=np.deg2rad(2)):near[i]=True
    radius=int(np.ceil(embargo_s/np.median(np.diff(t))))
    blocked=binary_dilation(near,iterations=radius) if near.any() else near
    # Windows at the very beginning have no training history.
    keep=~blocked;keep[t-t[0]<10]=False
    return keep,dict(exact_rule='5cm/2deg near-pose grouping plus 20s embargo',near_n=int(near.sum()),retained_n=int(keep.sum()),n=len(keep))

def envelope(data,traces,train):
    items=[]
    for route in train:
        e=traces[route]['prior'][:,:3]-data[route]['ev']['truth'];e[:,2]=wrap(e[:,2])
        items.append(np.quantile(abs(e),.995,axis=0))
    floor=np.maximum(np.max(items,axis=0),[.1,.1,np.deg2rad(1)])
    return np.r_[floor,np.deg2rad(.2)]

def observe(core,model,d,tr,env,out):
    s=series(d);mon=Monitor(core,model,s,env);logs=[]
    for k in range(len(s.t)):
        logs.append(mon.assess(k,tr['prior'],tr['Pprior']))
    ar={key:np.asarray([r[key] for r in logs]) for key in logs[0]}
    save(out,**ar,t=s.t)
    return ar

def P2(core,data,traces,out):
    summary=[];rows=[]
    for route in ROUTES:
      d=data[route];s=series(d);truth=d['ev']['truth'];tr=traces[route]
      for T in (2.,5.,10.):
        for k in range(1,len(s.t)):
          a=int(np.searchsorted(s.t,s.t[k]-T-1e-9))
          if s.t[k]-s.t[a]<T-1e-8:continue
          # Pure relative motion diagnostic, GT used only as common start alignment.
          for mode,b in [('raw_gyro',0.),('estimated_bias',tr['prior'][a,3])]:
            x=np.r_[truth[a],b]
            q,_=paths(core,x,s.ds,s.gy,s.dt,a,k,jac=False)
            er=q[-1,:3]-truth[k];er[2]=wrap(er[2])
            rows.append(dict(route=route,T=T,k=k,anchor=a,mode=mode,yaw_error_deg=float(np.rad2deg(er[2])),xy_shape_error_m=float(np.linalg.norm(er[:2])),anchor_bias_dps=float(np.rad2deg(b))))
        for mode in ('raw_gyro','estimated_bias'):
            q=[r for r in rows if r['route']==route and r['T']==T and r['mode']==mode]
            vals=np.array([r['yaw_error_deg'] for r in q]);xy=np.array([r['xy_shape_error_m'] for r in q])
            summary.append(dict(route=route,T=T,mode=mode,n=len(vals),yaw_RMS_deg=float(np.sqrt(np.mean(vals**2))),yaw_abs_p99_deg=float(np.quantile(abs(vals),.99)),yaw_abs_max_deg=float(max(abs(vals))),xy_RMS_cm=float(100*np.sqrt(np.mean(xy**2)))))
    table(out/'P2_MOTION_ROWS.csv',rows);dump(out/'P2_MOTION_SUMMARY.json',summary)
    return summary

def candidate_loss(tr,truth,obs,tau,channel,nis=False):
    n=len(tr['x']);x=np.empty_like(tr['x']);betas=np.ones((n,2))
    for k in range(n):
        if nis:
            S=tr['S'][k];m=abs(tr['nu'][k])/np.sqrt(np.diag(S));sc=np.r_[m,np.sqrt(tr['nis'][k])];valid=np.ones(2,bool)
        else:sc=obs['score'][k];valid=obs['valid'][k]
        b=weights(sc,valid,tau,channel);betas[k]=b
        x[k]=update(tr['prior'][k],tr['Pprior'][k],tr['H'][k],tr['nu'][k],tr['Reff'][k],bool(tr['mask'][k]),b)[0]
    return loss(x,truth),betas

def select_policy(train,data,traces,observations,masks,channel,nis=False):
    curves=[]
    if any(int(masks[r].sum())<25 for r in train):return dict(status='INSUFFICIENT_TRAIN_SUPPORT',threshold=None,curves=[])
    base=np.concatenate([loss(traces[r]['x'],data[r]['ev']['truth'])[masks[r]] for r in train])
    skip=np.concatenate([loss(traces[r]['prior'],data[r]['ev']['truth'])[masks[r]] for r in train])
    for tau in THRESHOLDS:
        cand=np.concatenate([candidate_loss(traces[r],data[r]['ev']['truth'],observations[r],tau,channel,nis)[0][masks[r]] for r in train])
        u=utility(base,skip,cand)
        valid=all(u[m]['lost_useful_gain'] is not None and u[m]['lost_useful_gain']<=.05 and u[m]['net_gain']>1e-12 for m in ('heading','xy'))
        score=sum(u[m]['net_gain']/max(float(base[:,j].sum()),1e-20) for j,m in enumerate(('heading','xy')))
        curves.append(dict(threshold=tau,utility=u,feasible=valid,selection_objective=score))
    passing=[r for r in curves if r['feasible']]
    if not passing:return dict(status='NO_NONTRIVIAL_FEASIBLE_POLICY',threshold=None,curves=curves)
    best=max(passing,key=lambda r:r['selection_objective'])
    return dict(status='TRAIN_RISK_PASS',threshold=best['threshold'],curves=curves)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--assets',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);dump(a.out/'EXECUTION_CONTRACT.json',plan())
    source={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')};dump(a.out/'SOURCE_LOCK.json',source)
    core,online,model,data,hashes=load(a.repo,a.assets,a.out)
    tr=baselines(core,online,model,data,a.repo,a.out/'baseline')
    stats=train_stats(model,data)
    P1=[];layers={'B_FROZEN':tr};layerfits={}
    for route in ROUTES:
        fit=calibration(stats,route);layerfits[route]=fit
        s=series(data[route],fit)
        t=online.replay(s.packet(),s.controls(),'W0',core,model,SPEC)
        layers.setdefault('B_BIAS_COV',{})[route]=t
        save(a.out/'baseline'/f'{route}_B_BIAS_COV.npz',**t,t=s.t,z=s.z)
        save(a.out/'baseline'/f'{route}_OFFLINE_EVALUATOR.npz',truth=data[route]['ev']['truth'],htrue=stats[route]['htrue'])
    dump(a.out/'LEGACY_CALIBRATION_FOLDS.json',layerfits)
    for layer,trs in layers.items():
      for route in ROUTES:
        d=data[route];trace=trs[route];truth=d['ev']['truth']
        L,X,parity,order=action_losses(trace,truth);Lp,_,_,_=action_losses(trace,truth,force=True)
        gains=L[:,0,None]-L
        rec=dict(layer=layer,route=route,n=len(L),accepted=int(trace['mask'].sum()),same_prior_parity_max=parity,minimum_covariance_difference_eigenvalue=order,pareto_opportunity=int(((gains[:,:,0]>1e-12)&(gains[:,:,1]>1e-12)).any(1).sum()),baseline_metrics=metrics(trace['x'],trace['P'],truth,trace['mask']),oracle_heading_mse=float(L[:,:,0].min(1).mean()),oracle_xy_mse=float(L[:,:,1].min(1).mean()))
        P1.append(rec);save(a.out/'actions'/f'{layer}_{route}.npz',losses=L,potential_losses=Lp,states=X,actions=ACTIONS,mask=trace['mask'])
    dump(a.out/'P1_ACTION_OPPORTUNITY.json',P1);print('P1_COMPLETE',json.dumps(P1),flush=True)
    p2=P2(core,data,tr,a.out);print('P2_COMPLETE',json.dumps(p2),flush=True)
    folds={}
    for test in ROUTES:
        train=[r for r in ROUTES if r!=test];env=envelope(data,tr,train)
        observations={};masks={};splits={}
        for r in ROUTES:
            observations[r]=observe(core,model,data[r],tr[r],env,a.out/'observe'/f'heldout_{test}_source_{r}.npz')
            if r!=test:masks[r],splits[r]=training_mask(data[r]['ev']['truth'],data[test]['ev']['truth'],data[r]['on']['t'])
            print('P3_OBSERVE',test,r,'VALID',int(observations[r]['valid'].all(1).sum()),'N',len(data[r]['z']),flush=True)
        policies={}
        for channel in ('R','S','RS'):
          for kind in ('MCG','NIS'):
            key=kind+'_'+channel;sel=select_policy(train,data,tr,observations,masks,channel,nis=kind=='NIS')
            policies[key]=sel
            if sel['threshold'] is not None:
                L,beta=candidate_loss(tr[test],data[test]['ev']['truth'],observations[test],sel['threshold'],channel,nis=kind=='NIS')
                sel['heldout_one_step']=utility(loss(tr[test]['x'],data[test]['ev']['truth']),loss(tr[test]['prior'],data[test]['ev']['truth']),L)
                sel['heldout_changed_n']=int(np.any(beta<1,axis=1).sum())
        fold=dict(test_route=test,train_routes=train,envelope=env,split=splits,policies=policies,valid_n=int(observations[test]['valid'].all(1).sum()),total_n=len(data[test]['z']),unknown_reasons={k:int((observations[test]['reason']==k).sum()) for k in np.unique(observations[test]['reason'])})
        folds[test]=fold;dump(a.out/'CALIBRATION_LOCKS.json',folds);print('P4_FOLD_COMPLETE',test,json.dumps(fold,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x),flush=True)
    final=dict(technical_status='P0_TO_P4_EXECUTED',science_status='REVIEW_FOLD_GATES_NO_AUTOMATIC_ADOPTION',folds=folds,limits='Current/future RF excluded; same-corridor exposed data; original mu/R independence unproven; no claimed online error probability')
    dump(a.out/'PRECHECK_RESULTS.json',final)
    print('PRECHECK_COMPLETE',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException as e:
        print('PRECHECK_FAILED',repr(e),traceback.format_exc(),flush=True);raise
