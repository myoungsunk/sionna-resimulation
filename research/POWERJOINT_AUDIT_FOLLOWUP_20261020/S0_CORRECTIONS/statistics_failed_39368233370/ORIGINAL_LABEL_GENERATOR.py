"""A-E causal hypothesis tests. New routes/office stay untouched and held out.
No GT enters inference. Reconstruct source-trained POWER using its pinned fitter.
P4 is explicitly a reconstructed classifier for policy-isolation, not parity
with the unavailable historical P4 binary. All negative results are retained.
"""
from __future__ import annotations
from pathlib import Path
import os,sys,json,zipfile,io,hashlib,time,traceback,argparse,shutil
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2]; DATA=ROOT.parent; HERE=Path(__file__).resolve().parent
for path in ['research/EKF4_RANGE_S_STAGED_20261014','research/FFD_P0P3_20261016','research/R5_N4B_20261015','research/PHYSICS_RS_STAGED_20261015/code','results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
    sys.path.insert(0,str(ROOT/path))
from source_model import SourceFFD
from features import extract,FEATURES,GROUPS
from n4b_rf_errors import fit_model,site_weights,feature_splits
from r2_bias_replay import build_positive_bias_controls,BIAS_LEVELS
from core import wrap,gaussian_update
import engine

def savej(path,data):
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)))

def frozen_inputs():
    out={}
    with zipfile.ZipFile(DATA/'rf_frozen.zip') as z:
        name=next(x for x in z.namelist() if x.endswith('P2_ONE_STEP_SUMMARY.json'))
        meta=json.loads(z.read(name));parent=str(Path(name).parent)
        for rec in meta['per_case']:
            p=parent+'/'+rec['trace_file']
            if p not in z.namelist():p=next(x for x in z.namelist() if x.endswith(rec['trace_file']))
            raw=z.read(p)
            with np.load(io.BytesIO(raw),allow_pickle=False) as a:
                out[(rec['case'],rec['channel'])]={k:a[k].copy() for k in a.files}
    return out

def dataset(model,cases,out):
    frames=[];physical=[];t0=time.time()
    for c in cases:
        samples=pd.DataFrame(json.loads((ROOT/c['samples_path']).read_text()))
        truth=np.column_stack([samples.x,samples.y,np.radians(samples.yaw_body_deg),np.zeros(len(samples))])
        ph=[];jac=[]
        for start in range(0,len(samples),48):
            h,H=model.batch(truth[start:start+48],c);ph.append(h);jac.append(H)
        pred=np.concatenate(ph);J=np.concatenate(jac)
        qs={}
        for channel,key in [('full','full_path'),('los','los_path')]:
            h=np.load(ROOT/c[key],mmap_mode='r',allow_pickle=False);chunks=[]
            for start in range(0,len(h),64):
                chunks.append(pd.DataFrame(extract(h[start:start+64,:,:,0],model.freqs)))
            q=pd.concat(chunks,ignore_index=True)
            q['case']=c['id'];q['route']=c['id'].split('_')[0];q['channel']=channel
            q['pose_id']=samples.pose_id.to_numpy(int);q['x_eval']=samples.x;q['y_eval']=samples.y
            q['yaw_rad']=truth[:,2];q['mount_feature']=c['mount_deg']/45.;q['anchor_x_feature']=c['anchor'][0]/10.
            q['e_r']=q.range_m-pred[:,0];q['e_s']=q.s_fp-pred[:,1];q['gpsi']=J[:,1,2]
            q['fp_tap']=q['tap'];q['strong_port']=q['branch']
            q['rho_m']=np.hypot(q.x_eval-c['anchor'][0],q.y_eval-c['anchor'][1])
            qs[channel]=q;frames.append(q)
        ds=qs['full'].s_fp.to_numpy()-qs['los'].s_fp.to_numpy()
        dr=qs['full'].range_m.to_numpy()-qs['los'].range_m.to_numpy()
        physical.append(dict(case=c['id'],n=len(samples),los_s_rmse=float(np.sqrt(np.mean(qs['los'].e_s**2))),los_s_max=float(abs(qs['los'].e_s).max()),full_minus_los_s_rmse=float(np.sqrt(np.mean(ds**2))),full_minus_los_r_rmse=float(np.sqrt(np.mean(dr**2)))))
        print('SOURCE_DATASET',c['id'],len(samples),'seconds',round(time.time()-t0,1),flush=True)
    df=pd.concat(frames,ignore_index=True)
    df.to_csv(out/'PACKETS_SOURCE_LABELS.csv.gz',index=False,compression='gzip');pd.DataFrame(physical).to_csv(out/'PHYSICAL_PARITY.csv',index=False)
    return df

def fit_memory(train,mu,C,raw):
    """Training-only two-lag moments, common stationary marginal maintained.
    This is a fitted effective correlation model, not proof of stochastic AR physics.
    No selected route evaluation outcomes enter tau/fraction estimation.
    """
    q=train.copy();err=q[['e_r','e_s']].to_numpy()-mu
    u=np.linalg.solve(np.linalg.cholesky(C),err[...,None])[...,0]
    u=u-u.mean(axis=0);q['u0']=u[:,0];q['u1']=u[:,1]
    pairs1=[];pairs2=[];zero=[];dtlist=[]
    for case,g in q.groupby('case'):
        a=raw[(case,'full')];ids=a['pose_id'];t=a['t_s'];g=g.set_index('pose_id')
        keep=np.isin(ids,g.index);ii=np.where(keep)[0]
        if len(ii)<5:continue
        U=g.loc[ids[ii],['u0','u1']].to_numpy();zero.append(U)
        for lag,target in [(1,pairs1),(2,pairs2)]:
            ok=(ii[lag:]-ii[:-lag])==lag
            target.extend((U[:-lag][ok]*U[lag:][ok]).sum(axis=1).tolist())
        dtlist.extend(np.diff(t).tolist())
    c0=float(np.mean(np.concatenate(zero)**2));c1=float(np.mean(pairs1)/2);c2=float(np.mean(pairs2)/2)
    rho=float(np.clip(c2/max(c1,1e-8),.02,.995));dt=float(np.median(dtlist));tau=float(-dt/np.log(rho))
    fraction=float(np.clip(c1/(rho*max(c0,1e-8)),.05,.90))
    return dict(rho_dt=rho,dt_s=dt,tau_s=tau,fraction=fraction,c0=c0,c1=c1,c2=c2,n_lag1=len(pairs1),n_lag2=len(pairs2),fit_scope='training routes only; standardized residual moments; no independent RF repetitions')

def fit_all(df,cases,raw,out):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score,brier_score_loss
    full=df[df.channel=='full'].copy().reset_index(drop=True)
    plans={};allpred=[];mem=[];quality=[]
    cols=[c for c in FEATURES if c not in ['range_m','abs_s_fp']]
    for held,tr,te in feature_splits(np,full):
        train=full.loc[tr].copy();test_cases=[c['id'] for c in cases if c['id'].startswith(held)]
        target=df[df.route==held].copy();combined=pd.concat([train,target],ignore_index=True)
        mu,C,info=fit_model(np,train,combined,site_weights(np,pd,train),'POWER_BIN_JOINT',GROUPS)
        nt=len(train);mp=fit_memory(train,mu[:nt],C[:nt],raw);mp['held_route']=held;mem.append(mp)
        # Targets reproduce the historical contamination definition; learner is new and explicit.
        pairs=df.pivot(index=['case','pose_id'],columns='channel',values=['range_m','s_fp'])
        diff_r=abs(pairs[('range_m','full')]-pairs[('range_m','los')]);diff_s=abs(pairs[('s_fp','full')]-pairs[('s_fp','los')])
        labels=((diff_r>=.15)|(diff_s>=.10)).astype(int)
        alltrain=df[(df.route!=held)].copy()
        distance=cKDTree(target[['x_eval','y_eval']].to_numpy()).query(alltrain[['x_eval','y_eval']].to_numpy())[0]
        alltrain=alltrain.loc[distance>1e-4].copy()
        def lab(frame):
            y=labels.reindex(pd.MultiIndex.from_frame(frame[['case','pose_id']])).to_numpy()
            return np.where(frame.channel.to_numpy()=='los',0,y).astype(int)
        learner=HistGradientBoostingClassifier(max_iter=120,max_leaf_nodes=15,l2_regularization=1.,learning_rate=.05,random_state=20261019)
        learner.fit(alltrain[cols].to_numpy(),lab(alltrain));risk=learner.predict_proba(target[cols].to_numpy())[:,1]
        for channel,mask in [('full',target.channel.to_numpy()=='full'),('paired',np.ones(len(target),bool))]:
            y=lab(target)[mask];pr=risk[mask]
            quality.append(dict(held_route=held,scope=channel,n=len(y),auc=float(roc_auc_score(y,pr)) if len(np.unique(y))>1 else None,brier=float(brier_score_loss(y,pr)),model='reconstructed HGB, not historical classifier parity'))
        target['mu_r']=mu[nt:,0];target['mu_s']=mu[nt:,1];target['C00']=C[nt:,0,0];target['C11']=C[nt:,1,1];target['C01']=C[nt:,0,1];target['risk']=risk
        threshold=float(np.quantile(train.detector_s_span,.75))
        for case in test_cases:
            plans[case]=dict(memory=mp,feature_threshold=threshold,power_fit=info,frame=target[target.case==case].copy())
        allpred.append(target)
        print('TRAIN_FOLD',held,json.dumps(mp),flush=True)
    pd.concat(allpred).to_csv(out/'OOF_PARAMETERS.csv.gz',index=False,compression='gzip')
    savej(out/'MEMORY_TRAIN_PARAMS.json',mem);pd.DataFrame(quality).to_csv(out/'P4_RECONSTRUCTED_CLASSIFIER.csv',index=False)
    return plans

def feature_event(frame,t,threshold):
    """Causal observed-feature trigger, no posterior/GT-based event selection.
    First 3 consecutive high detector-sensitivity packets; end after 5 low,
    min duration 2s and max 20s. Declared before evaluating outcomes.
    """
    on=frame.detector_s_span.to_numpy()>threshold;start=None;count=0
    for k in range(len(t)):
        count=count+1 if on[k] and t[k]>=5 else 0
        if count==3:start=k;break
    if start is None:return None
    low=0;end=len(t)
    for k in range(start+1,len(t)):
        low=0 if on[k] else low+1
        if (low>=5 and t[k]-t[start]>=2) or t[k]-t[start]>=20:end=k+1;break
    return [int(start),int(end)]

def metrics(result,truth,t,bias,case,event=None):
    rows=[];err=result['state'][:,:,:4]-np.c_[truth,np.full(len(t),np.radians(bias))][:,None,:]
    err[:,:,2]=wrap(err[:,:,2]);e=np.degrees(err[:,:,2]);var=np.degrees(np.sqrt(result['cov'][:,:,2,2]))**2
    ep=result['prior'][:,:,2]-truth[:,None,2];ep=np.degrees(wrap(ep));proposal=np.degrees(result['proposal_dpsi'])
    for j,name in enumerate(result['names']):
        scopes=[('evaluation',t>=30),('whole',np.ones(len(t),bool))]
        if event is not None:
            a,b=event;scopes += [('pre_event',np.arange(len(t))<a),('event',(np.arange(len(t))>=a)&(np.arange(len(t))<b)),('after_event',np.arange(len(t))>=b)]
        for scope,mask in scopes:
            if not np.any(mask):continue
            ee=e[mask,j];vv=var[mask,j];ne=ee**2/vv
            rows.append(dict(case=case,bias_dps=bias,method=str(name),scope=scope,n=int(mask.sum()),signed_heading_deg=float(ee.mean()),heading_rmse_deg=float(np.sqrt(np.mean(ee**2))),heading_sigma_rms_deg=float(np.sqrt(vv.mean())),heading_nees=float(ne.mean()),heading95=float(np.mean(ne<=3.841458820694124)),heading_nll=float(np.mean(.5*(np.log(2*np.pi*vv)+ne))),p95_abs_deg=float(np.quantile(abs(ee),.95)),bias_rmse_dps=float(np.degrees(np.sqrt(np.mean(err[mask,j,3]**2)))),xy_rmse_m=float(np.sqrt(np.mean(np.sum(err[mask,j,:2]**2,axis=1)))),accepted_fraction=float(result['accepted'][mask,j].mean()),rejected_helpful_proposal=int(np.sum((~result['accepted'][mask,j])&((ep[mask,j]+proposal[mask,j])**2<ep[mask,j]**2))),accepted_harmful_proposal=int(np.sum(result['accepted'][mask,j]&((ep[mask,j]+proposal[mask,j])**2>ep[mask,j]**2)))))
    return rows

def audit_updates(model,case):
    rng=np.random.default_rng(1942);rows=[]
    for _ in range(32):
        xx=np.array([rng.uniform(2,18),rng.uniform(-.6,.6),rng.uniform(-np.pi,np.pi),0.])
        A=rng.normal(size=(4,4));P=(A@A.T)*.001+np.diag([.01,.01,.003,.00001]);R=np.array([[.02,.002],[.002,.01]])
        h,H=model.model(xx,case);z=h+rng.normal(size=2)*.05
        y,Q,diag=gaussian_update(xx,P,z,lambda a:model.model(a,case),R)
        y6,Q6,*_=engine.single_update(np.r_[xx,[0.,0.]],np.block([[P,np.zeros((4,2))],[np.zeros((2,4)),np.eye(2)]]),z,h,np.c_[H,np.zeros((2,2))],R)
        rows.append(dict(state_max=float(np.max(abs(y-y6[:4]))),cov_max=float(np.max(abs(Q-Q6[:4,:4])))))
    if max(max(r.values()) for r in rows)>1e-10:raise RuntimeError('INDEPENDENT_UPDATE_PARITY')
    return rows

def scalar_memory_test(out):
    """Independent linear-Gaussian simulation: same marginal measurement variance.
    Not a RF/robot performance claim. 500 Monte Carlo repeats.
    """
    rng=np.random.default_rng(161019);N=500;T=100;rho=.98;f=.8
    xtrue=rng.normal(size=N);b=rng.normal(size=N);obs=[]
    for k in range(T):
        if k:b=rho*b+np.sqrt(1-rho*rho)*rng.normal(size=N)
        obs.append(xtrue+np.sqrt(f)*b+np.sqrt(1-f)*rng.normal(size=N))
    obs=np.array(obs);rows=[]
    for name,a in [('independent',0.),('memory_correct',rho)]:
        m=np.zeros((N,2));P=np.eye(2);H=np.array([1.,np.sqrt(f)]);R=1-f
        for z in obs:
            F=np.diag([1.,a]);m=m@F.T;P=F@P@F.T+np.diag([0.,1-a*a]);K=P@H/(H@P@H+R)
            m=m+(z-m@H)[:,None]*K;A=np.eye(2)-np.outer(K,H);P=A@P@A.T+R*np.outer(K,K)
        e=m[:,0]-xtrue;nees=e*e/P[0,0]
        rows.append(dict(model=name,rmse=float(np.sqrt(np.mean(e*e))),sigma=float(np.sqrt(P[0,0])),nees=float(nees.mean()),coverage95=float(np.mean(nees<3.8414588)),n=N))
    pd.DataFrame(rows).to_csv(out/'LINEAR_MEMORY_UNIT_TEST.csv',index=False);print('LINEAR_MEMORY_TEST',json.dumps(rows),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args();out=args.out;out.mkdir(exist_ok=True)
    (out/'traces').mkdir(exist_ok=True);(out/'scripts').mkdir(exist_ok=True)
    for f in HERE.glob('*.py'):shutil.copy2(f,out/'scripts'/f.name)
    warnings=[];errors=[];scores=[];parities=[];events=[];origins=[]
    savej(out/'PROTOCOL_LOCK.json',dict(stage='A-E',source_sha='4b82e9801a1e065593fdd67a0f3ebd721ba29848',new_source_sha=os.getenv('GITHUB_SHA'),main_methods=['JOINT4','POWER1'],mount_comparison='R2 A only',biases=BIAS_LEVELS,model='normalized correlated RF latent state; stationary marginal equals frozen POWER covariance',event_rule='observed detector span exceeds training Q75 for 3 samples; first event >=5 seconds; max20s',p4='new HGB classifier with historical target; NOT historical classifier parity',f_stage='new continuous office/corridor RF not accessed; independent final validation NOT_TESTED',online_gt=False))
    scalar_memory_test(out)
    model=SourceFFD();cases=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases'];raw=frozen_inputs()
    savej(out/'UPDATE_PARITY.json',audit_updates(model,cases[0]))
    df=dataset(model,cases,out);plans=fit_all(df,cases,raw,out)
    for case in cases:
        cid=case['id'];a=raw[(cid,'full')];t=a['t_s'];truth=a['truth_for_offline_scoring_only'][:,:3];ids=a['pose_id'].astype(int)
        frame=plans[cid]['frame'];frame=frame[frame.channel=='full'].set_index('pose_id').loc[ids].reset_index()
        z=np.c_[a['z_r_m'],a['z_s']];delta=max(float(np.max(abs(z[:,0]-frame.range_m))),float(np.max(abs(z[:,1]-frame.s_fp))))
        if delta>1e-10:raise RuntimeError('RAW_OBSERVER_ALIGNMENT:'+cid+':'+str(delta))
        mu=frame[['mu_r','mu_s']].to_numpy();C=np.zeros((len(t),2,2));C[:,0,0]=frame.C00;C[:,1,1]=frame.C11;C[:,0,1]=C[:,1,0]=frame.C01
        event=feature_event(frame,t,plans[cid]['feature_threshold']);specs=engine.specifications(event,plans[cid]['memory'])
        ev=dict(case=cid,index_range=event,threshold=plans[cid]['feature_threshold'])
        if event is not None:
            i0,i1=event;ev.update(t_start=float(t[i0]),t_end=float(t[min(i1,len(t)-1)]),x=float(truth[i0,0]),y=float(truth[i0,1]),yaw_deg=float(np.degrees(truth[i0,2])),rho_m=float(frame.rho_m.iloc[i0]),raw_detector_s_span=float(frame.detector_s_span.iloc[i0]))
        events.append(ev)
        print('EVENT',json.dumps(ev),flush=True)
        for label,bias in BIAS_LEVELS.items():
            try:
                controls,initial=build_positive_bias_controls(t,truth,label,0)
                result=engine.run(t,controls,initial,z,mu,C,frame.risk.to_numpy(),case,model,specs)
                names=list(result['names']);j=names.index('POWER1');k=names.index('POWER_INDEPENDENT')
                dx=float(np.max(abs(result['state'][:,j,:4]-result['state'][:,k,:4])));dp=float(np.max(abs(result['cov'][:,j,:4,:4]-result['cov'][:,k,:4,:4])));flip=int(np.sum(result['accepted'][:,j]!=result['accepted'][:,k]))
                parities.append(dict(case=cid,bias=label,no_memory_state_max=dx,no_memory_cov_max=dp,no_memory_gate_flips=flip,pass_=max(dx,dp)<1e-7 and flip==0))
                if max(dx,dp)>=1e-7 or flip:warnings.append('NO_MEMORY_PARITY_FAILED:'+cid+label)
                sc=metrics(result,truth,t,bias,cid,event);scores.extend(sc)
                result.update(truth_for_offline_scoring_only=truth,pose_id=ids,observations=z,controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'],controls_dt=controls['dt_s'])
                np.savez_compressed(out/'traces'/f'{cid}_{label}.npz',**result)
                # Recorded first-entry events are descriptive, not GT-based intervention triggers.
                for method in ['JOINT4','POWER1','POWER_MEMORY']:
                    jj=names.index(method);e=np.degrees(wrap(result['state'][:,jj,2]-truth[:,2]));sigma=np.degrees(np.sqrt(result['cov'][:,jj,2,2]));mask=(abs(e)>3)&(abs(e)>1.9599639845*sigma)
                    runs=[];begin=None
                    for ii,yes in enumerate(np.r_[mask,False]):
                        if yes and begin is None:begin=ii
                        if not yes and begin is not None:
                            if ii-begin>=5:runs.append((begin,ii))
                            begin=None
                    for i0,i1 in runs:
                        origins.append(dict(case=cid,bias=label,method=method,start_index=i0,end_index=i1,x=float(truth[i0,0]),y=float(truth[i0,1]),body_yaw_deg=float(np.degrees(truth[i0,2])),rho_m=float(frame.rho_m.iloc[i0]),gpsi=float(frame.gpsi.iloc[i0]),detector_s_span=float(frame.detector_s_span.iloc[i0]),signed_mean_deg=float(np.mean(e[i0:i1])),rmse_deg=float(np.sqrt(np.mean(e[i0:i1]**2))),sigma_rms_deg=float(np.sqrt(np.mean(sigma[i0:i1]**2))),accepted_fraction=float(np.mean(result['accepted'][i0:i1,jj]))))
                pd.DataFrame(scores).to_csv(out/'SCORES.csv',index=False);pd.DataFrame(parities).to_csv(out/'NO_MEMORY_PARITY.csv',index=False);pd.DataFrame(events).to_json(out/'EVENTS.json',orient='records',indent=2);pd.DataFrame(origins).to_csv(out/'OVERCONFIDENT_EPISODES.csv',index=False)
                selected=[r for r in sc if r['scope']=='evaluation' and r['method'] in ['JOINT4','POWER1','POWER_MEMORY','POWER_MEMORY_NO_CROSS','POWER_ITERATED','P4_HARD_RECONSTRUCTED']]
                print('CASE_RESULT',cid,label,json.dumps(selected),flush=True)
            except Exception as ex:
                errors.append(dict(case=cid,bias=label,error=repr(ex),traceback=traceback.format_exc()));savej(out/'ERRORS.json',errors);print('CASE_FAILURE_CONTINUE',cid,label,repr(ex),flush=True)
    savej(out/'WARNINGS.json',warnings);savej(out/'ERRORS.json',errors)
    s=pd.DataFrame(scores);ev=s[s.scope=='evaluation'];ev.to_csv(out/'EVALUATION_METRICS.csv',index=False)
    pairs=ev.pivot(index=['case','bias_dps'],columns='method',values=['heading_rmse_deg','heading95','heading_nees','heading_nll','bias_rmse_dps'])
    rows=[]
    for method in ev.method.unique():
        if method=='POWER1':continue
        dd=pairs[('heading_rmse_deg',method)]/pairs[('heading_rmse_deg','POWER1')]-1
        dn=pairs[('heading_nll',method)]-pairs[('heading_nll','POWER1')]
        rows.append(dict(method=method,n_comparable=int(dd.notna().sum()),rmse_improved=int((dd<-.001).sum()),rmse_worse10pct=int((dd>.1).sum()),mean_relative_rmse=float(dd.mean()),nll_improved=int((dn<0).sum())))
    pd.DataFrame(rows).to_csv(out/'MODEL_COMPARISON.csv',index=False)
    summary=dict(completed_case_bias=int(len(parities)),expected_case_bias=len(cases)*len(BIAS_LEVELS),methods_per_case=[dict(case=e['case'],event=e['index_range']) for e in events],no_memory_parity_all=all(x['pass_'] for x in parities),errors=errors,warnings=warnings,comparisons=rows,status='EXECUTED_EXPLORATORY_NOT_GENERALIZATION',F='NOT_TESTED_NEW_RF')
    savej(out/'SUMMARY.json',summary);print('FINAL_SUMMARY',json.dumps(summary),flush=True)
    manifest=[]
    for f in sorted(out.rglob('*')):
        if f.is_file():
            with f.open('rb') as v:h=hashlib.file_digest(v,'sha256').hexdigest()
            manifest.append(dict(path=str(f.relative_to(out)),bytes=f.stat().st_size,sha256=h))
    savej(out/'MANIFEST.json',manifest)

if __name__=='__main__':main()
