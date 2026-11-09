"""Pinned driver; reference labels are scoring/calibration only, never IMM inputs."""
from __future__ import annotations
import argparse, hashlib, json, math, platform, sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import ndtr,logsumexp
import imm_model_a as mod
from calibrate import fit
BIAS={'B0':0.,'L0':.01,'L1':.05,'L2':.2};DEG=180/np.pi

def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')

class Adapter:
    def __init__(self,data):
        sys.path.insert(0,str((Path(data)/'vendor').resolve()))
        import common
        self.raw=common.Engine(Path(data)/'cache')
        import r2_bias_replay
        self.motion=r2_bias_replay;self.core=self.raw.core
    def observe(self,x):
        h,H=self.raw.scalar_lut.model(np.asarray(x[:4]),self.raw.case)
        a=self.raw.case['anchor'];th=np.arctan2(np.hypot(x[0]-a[0],x[1]-a[1]),a[2]-self.raw.case['robot_z_m'])*DEG
        return float(h[1]),H[1],bool(th/self.raw.dt>self.raw.nt-1-1e-9 or th<0)
    def predict(self,x,P,c,k):
        if k==0:return x.copy(),P.copy()
        return self.motion.predict_one(x,P,float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
    def baseline(self,z,c,x0,P0,gate):
        N=len(z);X=np.empty((N,4));Pout=np.empty((N,4,4));nis=np.full(N,np.nan);accepted=np.zeros(N,bool)
        x,P=x0.copy(),P0.copy()
        for k in range(N):
            x,P=self.predict(x,P,c,k)
            if gate is not None:
                def observation(v):
                    h,H=self.raw.scalar_lut.model(v,self.raw.case)
                    return h[1:],H[1:,:]
                x,P,d=self.core.gaussian_update(x,P,np.array([z[k]]),observation,np.array([[mod.RS]]),gate_threshold=gate)
                nis[k]=d['NIS'];accepted[k]=d['accepted']
            X[k]=x;Pout[k]=P
        return dict(X=X,P=Pout,nis=nis,accepted=accepted)

def provenance(data,out):
    manifest=json.loads((data/'shared/SOURCE_MANIFEST.json').read_text());receipts=[]
    for a in manifest['files']:
        path=data/'cache'/a['local'];b=path.read_bytes();d=hashlib.sha256(b).hexdigest()
        git=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        assert d==a['sha256'] and len(b)==a['bytes'] and git==a['git_blob'],path
        receipts.append(dict(path=a['local'],sha256=d,bytes=len(b)))
    dump(out/'INPUT_AUDIT.json',dict(status='PASS',n_files=len(receipts),files=receipts))

def preflight(e,out):
    records=[];goodall=True
    for ch in ('full','los'):
        for lv in BIAS:
            for name,gate,j in [('DR',None,1),('S4',6.6348966010212145,3)]:
                x0,P0=e.raw.initial(ch,lv)
                r=e.baseline(e.raw.trace[ch]['z_s'],e.raw.controls[ch,lv],x0,P0,gate);o=e.raw.original[ch,lv]
                dx=float(abs(r['X']-o['estimate'][:,j,:]).max());dp=float(abs(r['P']-o['covariance'][:,j,:,:]).max())
                dn=0. if name=='DR' else float(abs(r['nis']-o['nis'][:,j]).max())
                bad=0 if name=='DR' else int(np.sum(r['accepted']!=(o['status'][:,j]=='APPLIED')))
                good=dx<1e-7 and dp<1e-8 and dn<1e-7 and bad==0;goodall&=good
                records.append(dict(channel=ch,level=lv,method=name,X_max=dx,P_max=dp,NIS_max=dn,mask_mismatch=bad,pass_strict=good))
    dump(out/'BASELINE_PARITY.json',dict(status='PASS' if goodall else 'FAIL',records=records,python=platform.python_version(),numpy=np.__version__,tolerances={'X':1e-7,'P':1e-8,'NIS':1e-7},unchanged_tolerances=True))
    if not goodall:raise RuntimeError('Historical parity failed; new science blocked.')

def scores(r,t,gt,truebias,ch,lv,name,case):
    X=r['X'][:,:4];P=r['P'][:,:4,:4];ep=X[:,:2]-gt[:,:2];eh=mod.wrap(X[:,2]-gt[:,2]);eb=X[:,3]-truebias/DEG
    hn=eh**2/P[:,2,2];bn=eb**2/P[:,3,3]
    pn=np.einsum('ni,ni->n',ep,np.linalg.solve(P[:,:2,:2],ep[:,:,None])[:,:,0])
    if 'mode_X' in r:
        err=mod.wrap(r['mode_X'][:,:,2]-gt[:,None,2]);cdf=(r['weights']*ndtr(-err/np.sqrt(r['mode_P'][:,:,2,2]))).sum(1)
        mc=(cdf>=.025)&(cdf<=.975);pc=r['weights'][:,1];ll=r['logevidence'];sn=r['nu'][:,0]/np.sqrt(r['S'][:,0])
    else:mc=hn<=3.841458820694124;pc=np.zeros(len(t));ll=pc.copy();sn=pc.copy()
    masks={'all_ge40':t>=40,'development_lt120':t<120,'evaluation_ge140':t>=140,'event_96_100':(t>=96)&(t<=100)}
    for start in np.arange(40,t[-1],10):
        m=(t>=start)&(t<start+10)
        if m.sum()>=10:masks[f'block_{start:g}']=m
    rows=[]
    for w,m in masks.items():
        if not m.any():continue
        h=eh[m]*DEG;xy=np.linalg.norm(ep[m],axis=1);b=eb[m]*DEG;si=sn[m]
        lag=float(np.corrcoef(si[:-1],si[1:])[0,1]) if len(si)>2 and np.std(si)>1e-14 else None
        rows.append(dict(case=case,channel=ch,level=lv,method=name,window=w,n=int(m.sum()),heading_rmse_deg=float(np.sqrt(np.mean(h*h))),xy_rmse_m=float(np.sqrt(np.mean(xy*xy))),bias_rmse_deg_s=float(np.sqrt(np.mean(b*b))),head95=float(np.mean(hn[m]<=3.841458820694124)),mix_head95=float(mc[m].mean()),xy95=float(np.mean(pn[m]<=5.991464547107979)),bias95=float(np.mean(bn[m]<=3.841458820694124)),head_nees=float(hn[m].mean()),xy_nees=float(pn[m].mean()),bias_nees=float(bn[m].mean()),head_q99_deg=float(np.quantile(abs(h),.99)),head_max_deg=float(abs(h).max()),mean_piC=float(pc[m].mean()),predictive_score=float(ll[m].sum()),normal_innov_lag1=lag))
    return rows

def audit_output(r):
    n=len(r['X']);mm=mp=ml=0.;mineig=float('inf')
    assert all(np.isfinite(r[k]).all() for k in ('X','P','mode_X','mode_P','weights','logL','logweights','prior_P'))
    for k in range(n):
        w=r['weights'][k];xs=r['mode_X'][k];Ps=r['mode_P'][k]
        x=sum(float(w[j])*xs[j] for j in range(2));x[2]=math.atan2(sum(w[j]*math.sin(xs[j,2]) for j in range(2)),sum(w[j]*math.cos(xs[j,2]) for j in range(2)))
        P=np.zeros_like(r['P'][k])
        for j in range(2):
            d=xs[j]-x;d[2]=(d[2]+math.pi)%(2*math.pi)-math.pi;P+=w[j]*(Ps[j]+np.outer(d,d))
        mm=max(mm,float(abs(x-r['X'][k]).max()));mp=max(mp,float(abs(P-r['P'][k]).max()))
        l=r['logprior'][k]+r['logL'][k];ml=max(ml,float(abs(np.exp(l-logsumexp(l))-w).max()))
        mineig=min(mineig,float(np.linalg.eigvalsh(Ps).min()),float(np.linalg.eigvalsh(r['P'][k]).min()))
    assert mm<1e-10 and mp<1e-10 and ml<1e-12 and mineig>0
    return dict(n=n,max_moment_mean_error=mm,max_moment_cov_error=mp,max_probability_error=ml,minimum_cov_eigenvalue=mineig,component_count_always_two=True,pruned_mass=0.,minimum_mode_weight=float(r['weights'].min()),maximum_angular_gap_deg=float(abs(mod.wrap(r['mode_X'][:,0,2]-r['mode_X'][:,1,2])).max()*DEG),mode_G_below01=int((r['weights'][:,0]<.01).sum()),mode_G_above99=int((r['weights'][:,0]>.99).sum()))

def experiment(data,out,phase,case):
    out.mkdir(parents=True,exist_ok=True);e=Adapter(data)
    if phase=='prepare':
        provenance(data,out);preflight(e,out)
        y=np.array([e.raw.trace['full']['z_s'][k]-e.observe(np.r_[e.raw.truth[k],0.])[0] for k in range(600)])
        cfg,g,xi=fit(y);cfg.update(case='R2_aB_m0',k_min=0,k_max=599,seconds_exclusive_end=120,RF_unequal_variance_not_calibrated_truth_probability=True)
        dump(out/'FROZEN_CALIBRATION.json',cfg);np.savez_compressed(out/'CALIBRATION_DIAGNOSTIC.npz',residual=y,gamma=g,xi=xi);return
    cfg=json.loads((Path('prep')/'FROZEN_CALIBRATION.json').read_text())
    if case=='R2_aB_m0':
        t=e.raw.t;gt=e.raw.truth;zch={ch:e.raw.trace[ch]['z_s'] for ch in ('los','full')};controls=e.raw.controls;init={key:e.raw.initial(*key) for key in controls}
    else:
        import route_loader
        cse,t,gt,pid,zch,fps,meta=route_loader.load_case(case);e.raw.case=cse;controls={};init={}
        for lv in BIAS:
            ctrl,pose=e.motion.build_positive_bias_controls(t,gt,lv,seed=0)
            for ch in ('full','los'):controls[ch,lv]=ctrl;init[ch,lv]=(np.r_[pose,0.],np.diag(np.array([.1,.1,np.deg2rad(5),np.deg2rad(.1)])**2))
        dump(out/f'{case}_PROVENANCE.json',dict(meta=meta,inputs=route_loader.INPUTS))
    metrics=[];audits=[];exceptions=[]
    if phase=='A':impl=mod
    else:import imm_model_b as impl
    for ch in ('full','los'):
        z=zch[ch]
        for lv in BIAS:
            c=controls[ch,lv];x0,P0=init[ch,lv]
            for name,gate in [('DR',None),('S4',6.6348966010212145),('NIS_0p5',.5),('NIS_2',2.)]:
                r=e.baseline(z,c,x0,P0,gate);metrics.extend(scores(r,t,gt,BIAS[lv],ch,lv,name,case));np.savez_compressed(out/f'{case}_{ch}_{lv}_{name}.npz',**r,t=t,truth=gt)
            for kind in ('collapse','imm'):
                try:
                    kw={} if phase=='A' else dict(rho=cfg['rho_C'])
                    r=impl.run(z,c,x0,P0,e.predict,e.observe,np.array(cfg['T']),np.array(cfg['pi0']),cfg['Rc'],kind=kind,**kw)
                    q=audit_output(r);q.update(case=case,channel=ch,level=lv,method=f'{phase}_{kind}');audits.append(q)
                    np.savez_compressed(out/f'{case}_{ch}_{lv}_{phase}_{kind}.npz',**r,t=t,truth=gt);metrics.extend(scores(r,t,gt,BIAS[lv],ch,lv,f'{phase}_{kind}',case))
                    if ch=='full' and lv=='B0':
                        short=impl.run(z[:200],c,x0,P0,e.predict,e.observe,np.array(cfg['T']),np.array(cfg['pi0']),cfg['Rc'],kind=kind,**kw)
                        assert np.array_equal(short['X'],r['X'][:200]) and np.array_equal(short['P'],r['P'][:200]);q['prefix_causality_pass']=True
                    print('COMPLETE',phase,case,ch,lv,kind,flush=True)
                except Exception as err:exceptions.append(dict(case=case,channel=ch,level=lv,method=f'{phase}_{kind}',error=repr(err)));print('MODEL_FAILED',exceptions[-1],flush=True)
    pd.DataFrame(metrics).to_csv(out/f'{case}_METRICS.csv',index=False);dump(out/f'{case}_RESULT_AUDIT.json',dict(status='PASS' if not exceptions else 'FAILED_MODEL_INCLUDED',records=audits,exceptions=exceptions))
    if exceptions:raise RuntimeError('Model failed: raw failures preserved')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['prepare','A','B'],required=True);p.add_argument('--data',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);p.add_argument('--case',default='R2_aB_m0');a=p.parse_args();experiment(a.data,a.out,a.phase,a.case)
