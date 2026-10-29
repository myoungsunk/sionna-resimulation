"""Controlled MB_VAR counterfactual replay. Evidence only, not an operational filter.

T: Shuffle paired RF residuals WITHIN true-distance x relative-bearing bins,
   solely among BASE-accepted measurements. This preserves every group's
   empirical residual marginal and cross-channel joint distribution; no new
   packet is accepted. Alters temporal ordering, but may also alter residual-
   geometry alignment WITHIN bins. Do not claim a perfect causal isolation.
W: Multiply the FULL variance-adjusted 2x2 R by m, holding original observations
   and BASE acceptance fixed. (Historical RSC did not scale sigma_b addition.)
O: Same-prior one-step gain counterfactual; no future propagation.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'mbvar_premodel_diag_20261029'/'code'))
import diag_mbvar as DG
SEEDS={'R5_aA_m0':range(8),'R4_aB_m0':range(6),'R5_aB_m0':range(6)}
MS=(1,2,4,8,16)

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def acf1(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)];x=x-x.mean()
    d=np.dot(x,x)
    return float(np.dot(x[:-1],x[1:])/d) if len(x)>1 and d>1e-25 else float('nan')

def metrics(D,X,P,L):
    s=DG.scores(D,X,P);u=L['used']&(D['t']>=30-1e-9)
    dh=D['hg']-L['hx']
    s.update(n_eval=int(u.sum()),n_total=int(L['used'].sum()),
             dh2_HPH_s=float(np.mean(dh[u,1]**2)/np.mean(L['HPH'][u,1,1])))
    for lo,hi in [(30,60),(60,120),(120,180),(180,300)]:
        m=(D['t']>=lo)&(D['t']<hi)
        if m.sum():
            err=np.angle(np.exp(1j*(D['gt'][m,2]-X[m,2])))
            s['H_'+str(lo)+'_'+str(hi)]=float(np.degrees(np.sqrt(np.mean(err*err))))
    return s

def scaled(D,model,m):
    """Same arithmetic as DG.run for m=1, verified with exact X and P parity."""
    n=len(D['t']);x=D['x0'].copy();P=D['P0'].copy();a=D['anchor']
    X=np.zeros((n,4));PX=np.zeros((n,4,4))
    L={'used':np.zeros(n,bool),'xp':np.full((n,4),np.nan),
       'Pp':np.full((n,4,4),np.nan),'hx':np.full((n,2),np.nan),
       'HPH':np.full((n,2,2),np.nan)}
    for k in range(n):
        sg=DG.sigf(math.hypot(x[0]-a[0],x[1]-a[1]),DG.HAND)
        if k:
            ds=float(D['ds'][k]);gy=float(D['gy'][k]);dt=float(D['dt'][k])
            q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
            x,P,_,_=DG.predict(x,P,ds,gy,dt,q)
        z=D['z'][k]
        if np.isfinite(z).all():
            h,H=model.batch(x[None],D['spec']);h=h[0];H=H[0]
            R=D['R'][k].copy();R[1,1]+=sg**2;R*=m
            v=z-h-D['mu']['MB'][k];HPH=H@P@H.T
            S=HPH+R;S=.5*(S+S.T)
            L['xp'][k]=x;L['Pp'][k]=P;L['hx'][k]=h;L['HPH'][k]=HPH
            if D['acc'][k]:
                K=np.linalg.solve(S,H@P).T;y=x+K@v;y[2]=DG.wrap(y[2])
                A=np.eye(4)-K@H;Pn=A@P@A.T+K@R@K.T
                x=y;P=.5*(Pn+Pn.T);L['used'][k]=True
        X[k]=x;PX[k]=P
    return X,PX,L

def shuffle_pair(D,seed):
    rng=np.random.default_rng(20261029+7919*seed)
    accept=D['acc']&np.isfinite(D['z']).all(1)
    eps=D['z']-D['hg']-D['mu']['MB'];new=eps.copy()
    rad=np.digitize(D['rho_true'],[1.5,3.,6.,10.])
    rel=(D['gt'][:,2]-np.arctan2(D['anchor'][1]-D['gt'][:,1],D['anchor'][0]-D['gt'][:,0])+np.pi)%(2*np.pi)-np.pi
    bearing=np.floor((rel+np.pi)/(np.pi/2)).astype(int).clip(0,3)
    keys=rad*4+bearing;swapped=0;groups=0
    for key in np.unique(keys[accept]):
        idx=np.flatnonzero(accept&(keys==key))
        if len(idx)<4:continue
        src=rng.permutation(idx);new[idx]=eps[src]
        swapped+=int(np.count_nonzero(src!=idx));groups+=1
    Dc=dict(D);Dc['z']=D['z'].copy()
    Dc['z'][accept]=D['hg'][accept]+D['mu']['MB'][accept]+new[accept]
    chk=dict(n_accept=int(accept.sum()),n_changed=int(swapped),n_groups=int(groups),
             lag1_original=acf1(eps[accept,1]),lag1_surrogate=acf1(new[accept,1]),
             mean_diff=float(np.max(np.abs(new[accept].mean(0)-eps[accept].mean(0)))),
             moment_diff=float(np.max(np.abs(new[accept].T@new[accept]-eps[accept].T@eps[accept]))/max(accept.sum(),1)))
    return Dc,chk

def one_step(D,model,L):
    rows=[];u=L['used']&(D['t']>=30-1e-9)
    for k in np.flatnonzero(u):
        x=L['xp'][k];P=L['Pp'][k]
        h,H=model.batch(x[None],D['spec']);h=h[0];H=H[0]
        v=D['z'][k]-h-D['mu']['MB'][k]
        rh=math.hypot(x[0]-D['anchor'][0],x[1]-D['anchor'][1])
        sg=DG.sigf(rh,DG.HAND);R=D['R'][k].copy();R[1,1]+=sg**2
        for m in (1,4,8):
            K=np.linalg.solve(H@P@H.T+m*R,H@P).T
            y=x+K@v;y[2]=DG.wrap(y[2])
            eh=np.degrees(np.angle(np.exp(1j*(y[2]-D['gt'][k,2]))))
            xy=100*np.linalg.norm(y[:2]-D['gt'][k,:2])
            rows.append(dict(m=m,t=float(D['t'][k]),head_sq=eh**2,xy_sq=xy**2))
    a=pd.DataFrame(rows);out=[]
    for m,g in a.groupby('m'):
        for label,subset in [('all',g),('60_120',g[(g.t>=60)&(g.t<120)])]:
            if len(subset):
                out.append(dict(m=int(m),phase=label,n=int(len(subset)),
                                head_rmse=float(np.sqrt(subset.head_sq.mean())),
                                xy_rmse_cm=float(np.sqrt(subset.xy_sq.mean()))))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True)
    ap.add_argument('--cases',nargs='+',default=list(SEEDS))
    arg=ap.parse_args();out=Path(arg.out);out.mkdir(parents=True,exist_ok=True)
    model=DG.C.base_model();scores=[];checks=[];local=[]
    for case in arg.cases:
        t0=time.monotonic();D=DG.load(case,'B0',model)
        X0,P0,L0=DG.run(D,'MB','var','fixed',model=model)
        scores.append(dict(case=case,kind='ORIGINAL',seed=-1,m=1,**metrics(D,X0,P0,L0)))
        Xa,Pa,_=scaled(D,model,1)
        errx=float(np.max(np.abs(X0-Xa)));errp=float(np.max(np.abs(P0-Pa)))
        if errx>1e-9 or errp>1e-9:
            raise RuntimeError('PARITY_FAILED '+case+' '+str((errx,errp)))
        for m in MS[1:]:
            X,P,L=scaled(D,model,m)
            scores.append(dict(case=case,kind='FULL_R_SCALE',seed=-1,m=m,**metrics(D,X,P,L)))
        for seed in SEEDS[case]:
            cf,ch=shuffle_pair(D,seed)
            X,P,L=DG.run(cf,'MB','var','fixed',model=model)
            scores.append(dict(case=case,kind='PAIR_TIME_SHUFFLE',seed=seed,m=1,**metrics(cf,X,P,L)))
            checks.append(dict(case=case,seed=seed,**ch))
        for row in one_step(D,model,L0):
            local.append(dict(case=case,**row))
        pd.DataFrame(scores).to_csv(out/'FILTER_REPLAYS.csv',index=False)
        pd.DataFrame(checks).to_csv(out/'SHUFFLE_VALIDATION.csv',index=False)
        pd.DataFrame(local).to_csv(out/'MATCHED_PRIOR.csv',index=False)
        print('DONE_CASE',case,'elapsed_s',round(time.monotonic()-t0,1),flush=True)
    summary=[]
    A=pd.DataFrame(scores);C=pd.DataFrame(checks)
    for case in arg.cases:
        original=A[(A.case==case)&(A.kind=='ORIGINAL')].iloc[0]
        sur=A[(A.case==case)&(A.kind=='PAIR_TIME_SHUFFLE')]
        chk=C[C.case==case]
        for key in ('head_rmse','xy_rmse_cm','head_z_rms','nees_xy','dh2_HPH_s'):
            summary.append(dict(case=case,metric=key,original=float(original[key]),
                shuffled_median=float(sur[key].median()),shuffled_min=float(sur[key].min()),
                shuffled_max=float(sur[key].max()),n_surrogate=int(len(sur)),
                n_improved=int((sur[key]<original[key]).sum()),
                lag1_before=float(chk.lag1_original.iloc[0]),
                lag1_after_median=float(chk.lag1_surrogate.median())))
    pd.DataFrame(summary).to_csv(out/'SURROGATE_SUMMARY.csv',index=False)
    manifest={'stage':'MBVAR_CAUSAL_ISOLATION','utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'run_id':os.environ.get('GITHUB_RUN_ID'),'git_sha':os.environ.get('GITHUB_SHA'),
        'config':{'cases':arg.cases,'B0_only':True,'fixed_BASE_gate':True,'m':MS,
          'shuffle_seeds':{k:list(v) for k,v in SEEDS.items() if k in arg.cases},
          'shuffle_conditioning':'true distance 5 bins x relative bearing 4 bins; same accepted paired residual multiset',
          'test_status':'mechanism counterfactual, not out-of-route generalization'},
        'code_sha256':{Path(__file__).name:sha(Path(__file__))},
        'outputs_sha256':{p.name:sha(p) for p in out.glob('*.csv')},
        'commands':['python causal_isolation.py --out <output>']}
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=list))
    print('SUMMARY_START',flush=True);print(pd.DataFrame(summary).to_string(index=False),flush=True);print('SUMMARY_END',flush=True)
if __name__=='__main__':main()
