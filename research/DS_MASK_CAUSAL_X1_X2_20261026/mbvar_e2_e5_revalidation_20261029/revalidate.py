#!/usr/bin/env python3
"""Post-hoc corrective validation of run 40820579727, NOT a new preregistration.

E2: keep the learned mean and training rows unchanged; compare the legacy plug-in,
state-dependent h_eff=h+m with its full Jacobian, and a frozen donor-prior correction.
E5: correct the information congruence (multiply by state scales, never divide),
transport sensitivities through F, and marginalize the existing process noise Q.
No historical code/results are overwritten. No filter hyperparameter is tuned here.
All training remains the original second-stage held-route construction, NOT E7.
"""
from __future__ import annotations
import argparse, contextlib, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
SRC=HERE.parent/'mbvar_control_correction_20261029'
SOURCE_REF='422b6c0'
CASES=['R2_aA_m0','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']
FD=np.array([1e-4,1e-4,1e-5,1e-7])
# Fixed physical scales for cross-case sensitivity comparisons, not tuned to outputs.
FIXED_SCALES=np.array([.1,.1,np.deg2rad(5),np.deg2rad(.2)])

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_core():
    sys.path.insert(0,str(SRC))
    import ctl_core as K
    from core import transition
    original_load=K.load; cache={}
    def cached(case,seed=0,bias='B0'):
        key=(case,seed,bias)
        if key not in cache: cache[key]=original_load(case,seed,bias)
        return cache[key]
    K.load=cached
    return K,transition

def features(K,x,h,H,anchor):
    return np.array([K.online_features(a,b,c,anchor) for a,b,c in zip(x,h,H)])

def mean_value(K,mods,x,h,H,anchor):
    f=features(K,x,h,H,anchor)
    return np.column_stack([K.ridge_pred(mods[j],f) for j in range(2)])

class EffectiveModel:
    """Effective measurement mean, with derivative of all learned mean features.
    The original FFD Jacobian is retained; only dm/dx is centrally differenced.
    FD branch crossings are diagnosed separately, not hidden by clipping.
    """
    def __init__(self,K,base,mods,anchor,step=FD):
        self.K,self.base,self.mods,self.anchor,self.step=K,base,mods,anchor,step
    def correction(self,x,spec):
        x=np.atleast_2d(x)
        h,H=self.base.batch(x,spec)
        return mean_value(self.K,self.mods,x,h,H,self.anchor)
    def batch(self,states,spec,gradient=True):
        x=np.atleast_2d(np.asarray(states,float))
        h,H=self.base.batch(x,spec)
        mu=mean_value(self.K,self.mods,x,h,H,self.anchor)
        if not gradient:return h+mu,None
        n=len(x); xx=[]
        for j in range(3):
            p=x.copy();q=x.copy();p[:,j]+=self.step[j];q[:,j]-=self.step[j]
            xx.extend([p,q])
        xx=np.concatenate(xx)
        hh,HH=self.base.batch(xx,spec)
        mm=mean_value(self.K,self.mods,xx,hh,HH,self.anchor).reshape(3,2,n,2)
        J=np.zeros_like(H)
        for j in range(3):J[:,:,j]=(mm[j,0]-mm[j,1])/(2*self.step[j])
        return h+mu,H+J

@contextlib.contextmanager
def model_override(K,m):
    old=K.model;K.model=lambda:m
    try:yield
    finally:K.model=old

def train(K,case):
    xs=[];ys=[];membership=[]
    base=K.model()
    for c in CASES:
        if c[:2]==case[:2]:continue
        D=K.load(c,0);X,P,L=K.run(D,'MB',K.R_orig)
        ii=np.flatnonzero(D['fin']&np.isfinite(L['nis']))
        xs.append(features(K,L['xp'][ii],L['hx'][ii],L['H'][ii],D['anchor']))
        ys.append((D['z']-D['hg']-D['mu']['MB'])[ii])
        membership.append({'case':c,'n':len(ii),'seed':0})
    xx=np.concatenate(xs);yy=np.concatenate(ys)
    rr=np.random.default_rng(2026103200+CASES.index(case))
    sh=yy[rr.permutation(len(yy))]
    mods={'COND':[K.ridge_fit(xx,yy[:,j]) for j in range(2)],
          'SHUF':[K.ridge_fit(xx,sh[:,j]) for j in range(2)]}
    return mods,membership

def jacobian_checks(K,D,base,mods,L):
    ii=np.flatnonzero(D['fin'])
    ii=ii[np.linspace(0,len(ii)-1,min(48,len(ii))).astype(int)]
    x=L['xp'][ii];m=EffectiveModel(K,base,mods,D['anchor'])
    h,H=m.batch(x,D['spec']);half=EffectiveModel(K,base,mods,D['anchor'],FD*.5)
    _,Hhalf=half.batch(x,D['spec'])
    # Independently differentiate the complete effective observation.
    Hnum=np.zeros_like(H);crossed=np.zeros(len(ii),bool)
    _,_,diag0=base.batch(x,D['spec'],return_diagnostics=True)
    for j in range(3):
        p=x.copy();q=x.copy();p[:,j]+=FD[j]*.5;q[:,j]-=FD[j]*.5
        hp,_=m.batch(p,D['spec'],gradient=False);hq,_=m.batch(q,D['spec'],gradient=False)
        Hnum[:,:,j]=(hp-hq)/FD[j]
        for v in (p,q):
            _,_,dg=base.batch(v,D['spec'],return_diagnostics=True)
            crossed |= (dg['tap']!=diag0['tap'])|(dg['strong_port']!=diag0['strong_port'])
            crossed |= np.any(dg['cells']!=diag0['cells'],axis=1)
    rel=np.linalg.norm((H-Hnum).reshape(len(ii),-1),axis=1)/np.maximum(np.linalg.norm(Hnum.reshape(len(ii),-1),axis=1),1e-9)
    stab=np.linalg.norm((H-Hhalf).reshape(len(ii),-1),axis=1)/np.maximum(np.linalg.norm(Hhalf.reshape(len(ii),-1),axis=1),1e-9)
    rows=[]
    for a,k in enumerate(ii):rows.append(dict(case=D['case'],k=int(k),t=float(D['t'][k]),branch_crossing=bool(crossed[a]),relative_full_jacobian_error=float(rel[a]),relative_step_halving=float(stab[a])))
    good=~crossed
    if good.any() and np.quantile(rel[good],.95)>1e-2:raise RuntimeError('JACOBIAN_QA_FAIL')
    return rows

def score_mean(K,D,base,mods,Rfn,name,Ldonor):
    if name=='FROZEN_COND':
        mm=mean_value(K,mods,Ldonor['xp'],Ldonor['hx'],Ldonor['H'],D['anchor'])
        X,P,L=K.run(D,'MB',Rfn,mu_add=lambda k,x,h,H:mm[k])
        eps=D['z']-D['hg']-D['mu']['MB']-mm
        dh=D['hg']-L['hx']
    elif name.startswith('LEGACY'):
        fn=lambda k,x,h,H:mean_value(K,mods,x[None],h[None],H[None],D['anchor'])[0]
        X,P,L=K.run(D,'MB',Rfn,mu_add=fn)
        eps=D['z']-D['hg']-L['mu_used'];dh=D['hg']-L['hx']
    else:
        eff=EffectiveModel(K,base,mods,D['anchor'])
        with model_override(K,eff):X,P,L=K.run(D,'MB',Rfn)
        gt4=np.c_[D['gt'][:,:3],np.full(len(D['t']),D['b_true'])]
        hgt,_=eff.batch(gt4,D['spec'],gradient=False)
        eps=D['z']-hgt-D['mu']['MB'];dh=hgt-L['hx']
    valid=D['fin']&(D['t']>=30)
    contract=float(np.nanmax(abs(L['nu'][valid]-eps[valid]-dh[valid])))
    assert contract<1e-9
    ep=D['gt'][:,:3]-L['xp'][:,:3];ep[:,2]=np.angle(np.exp(1j*ep[:,2]))
    e4=np.c_[ep,np.full(len(ep),D['b_true'])-L['xp'][:,3]]
    He=np.einsum('nij,nj->ni',L['H'],e4)
    sel=valid&D['acc'];ell=dh-He
    s=K.scores(D,X,P)
    s.update(decomposition_max_abs_error=contract,
             effective_rf_s_rms=float(np.sqrt(np.mean(eps[valid,1]**2))),
             effective_rf_s_mean=float(np.mean(eps[valid,1])),
             ell_share=float(np.mean(ell[sel,1]**2)/max(np.mean(dh[sel,1]**2),1e-30)),
             n_used=int(L['upd'][:,0].sum()))
    return s

def e5_correct(K,transition,D,X,P,L,arm):
    """Nominal linear-Gaussian sensitivity information; not empirical RF Fisher.
    Dynamic_Q uses innovation whitening of the process-only state to marginalize Q.
    Mean functions are baseline frozen means; residual temporal covariance is NOT assumed known.
    """
    t=D['t'];err=K.state_err(D,X)[:,2];starts=np.arange(30,t[-1]-30+1e-9,10.)
    fw=max(starts,key=lambda st:np.mean(err[(t>=st)&(t<st+30)]**2))
    wins=[(lo,min(hi,t[-1]+.01),str(lo)) for lo,hi in K.WINDOWS if lo<t[-1]]+[(fw,fw+30,'FAIL')]
    output=[]
    for lo,hi,tag in wins:
        ks=np.flatnonzero((t>=lo)&(t<hi));k0=int(ks[0]);used=ks[L['upd'][ks].any(1)]
        if len(used)<3:continue
        km=int(used[len(used)//2]);ur=D['gt'][km,:2]-D['anchor'];ur/=np.linalg.norm(ur)
        T=np.eye(4);T[:2,:2]=[ur,[-ur[1],ur[0]]
        P0=L['Pp'][k0];Prt=T@P0@T.T;sd=np.sqrt(np.diag(Prt))
        I0=np.zeros((4,4));Id=np.zeros((4,4));Iq=np.zeros((4,4))
        Phi=np.eye(4);V=np.zeros((4,4));E=np.zeros((4,4))
        for k in ks:
            if k!=k0:
                _,F,G=transition(X[k-1],float(D['ds'][k]),float(D['gy'][k]),float(D['dt'][k]))
                q=np.diag([2e-5*abs(D['ds'][k]),np.deg2rad(.015)**2*D['dt'][k],0.])
                Phi=F@Phi;V=F@V@F.T+G@q@G.T;E=F@E
            rows=np.flatnonzero(L['upd'][k])
            if not len(rows):continue
            H=L['H'][k][rows];R=L['Ru'][k][np.ix_(rows,rows)]
            I0+=H.T@np.linalg.solve(R,H)
            A=H@Phi;Id+=A.T@np.linalg.solve(R,A)
            B=A-H@E;S=H@V@H.T+R
            Iq+=B.T@np.linalg.solve(S,B)
            Kg=np.linalg.solve(S,H@V).T;E=E+Kg@B
            M=np.eye(4)-Kg@H;V=M@V@M.T+Kg@R@Kg.T;V=(V+V.T)*.5
        for method,I in [('STATIC',I0),('DYNAMIC_NO_Q',Id),('DYNAMIC_Q',Iq)]:
            Irt=T@I@T.T
            for scale,ss in [('PRIOR_DIAG',sd),('FIXED_PHYSICAL',FIXED_SCALES)]:
                N=np.diag(ss)@Irt@np.diag(ss);N=(N+N.T)*.5
                # Direct pose subspace: gyro-bias held fixed. Separate 4-D spectrum also emitted.
                w,v=np.linalg.eigh(N[:3,:3]);w4=np.linalg.eigvalsh(N)
                # Correct normalization must be invariant to changing metres to centimetres / radians to degrees.
                U=np.diag([100.,100.,180/np.pi,180/np.pi]);Ii=np.linalg.solve(U.T,Irt)@np.linalg.inv(U);si=np.diag(U)*ss
                Ni=np.diag(si)@Ii@np.diag(si)
                unit_error=float(np.max(abs(N-Ni))/max(np.max(abs(N)),1e-30));assert unit_error<1e-10
                output.append(dict(case=D['case'],arm=arm,window=tag,t_lo=lo,t_hi=hi,method=method,scale=scale,n_upd=len(used),
                    eig_pose_min=w[0],eig_pose_mid=w[1],eig_pose_max=w[2],eig4_min=w4[0],eig4_max=w4[-1],
                    vmin_rad=abs(v[0,0]),vmin_tan=abs(v[1,0]),vmin_psi=abs(v[2,0]),unit_invariance_rel_error=unit_error,
                    prior_rad_sd=sd[0],prior_tan_sd=sd[1],prior_head_sd=sd[2],prior_bg_sd=sd[3]))
    return output

def compute(case,part,out):
    K,transition=load_core();base=K.model();t0=time.time()
    mods,membership=train(K,case)
    dump(out/f'TRAIN_{case}_{part}.json',dict(source_ref=SOURCE_REF,held_route=case[:2],training=membership,models=mods,nested_loro=False))
    seeds=range(0,5) if part=='lo' else range(5,10)
    rows=[];qa=[];geo=[];parity=[];acf=[]
    old=pd.read_csv(SRC/'results/run_40820579727'/f'E23_{case}.csv')
    for seed in seeds:
        D=K.load(case,seed)
        for arm,Rf in [('MB_ORIG',K.R_orig),('MB_VAR',K.R_var)]:
            X,P,L=K.run(D,'MB',Rf);ss=K.scores(D,X,P)
            ref=old[(old.seed==seed)&(old.arm==arm)&(old.family=='BASE')].iloc[0]
            dif=max(abs(ss['head_rmse']-ref.head_rmse),abs(ss['xy_rmse_cm']-ref.xy_rmse_cm))
            assert dif<1e-5,(case,seed,arm,dif)
            parity.append(dict(case=case,seed=seed,arm=arm,max_score_difference_vs_original_csv=dif))
            rows.append(dict(case=case,seed=seed,arm=arm,treat='BASE',**ss))
            if seed==0:
                qa+=jacobian_checks(K,D,base,mods['COND'],L)
                geo+=e5_correct(K,transition,D,X,P,L,arm)
                # Original missing-Jacobian execution is retained as an explicitly legacy comparator.
                for name in ('COND','SHUF'):
                    s=score_mean(K,D,base,mods[name],Rf,'LEGACY_'+name,L)
                    rr=old[(old.seed==seed)&(old.arm==arm)&(old.treat=='MEAN_'+name)].iloc[0]
                    dd=max(abs(s['head_rmse']-rr.head_rmse),abs(s['xy_rmse_cm']-rr.xy_rmse_cm));assert dd<1e-4,(dd,case,arm,name)
                    rows.append(dict(case=case,seed=seed,arm=arm,treat='LEGACY_'+name,**s))
                valid=D['fin']&(D['t']>=30)
                baseeps=D['z']-D['hg']-D['mu']['MB']
                for name in ('NONE','COND','SHUF'):
                    ep=baseeps.copy()
                    if name!='NONE':ep-=mean_value(K,mods[name],L['xp'],L['hx'],L['H'],D['anchor'])
                    for j,comp in enumerate('rs'):
                        acf.append(dict(case=case,arm=arm,model=name,comp=comp,n=int(valid.sum()),rms=float(np.sqrt(np.mean(ep[valid,j]**2))),**K.acf_stats(ep[valid,j])))
            for name,ms in [('FULL_JAC_COND','COND'),('FULL_JAC_SHUF','SHUF'),('FROZEN_COND','COND')]:
                ss=score_mean(K,D,base,mods[ms],Rf,name,L)
                rows.append(dict(case=case,seed=seed,arm=arm,treat=name,**ss))
            pd.DataFrame(rows).to_csv(out/f'E2R_{case}_{part}.csv',index=False,float_format='%.12g')
        print('DONE',case,seed,'elapsed',round(time.time()-t0,1),flush=True)
    for name,rr in [('QA_JAC',qa),('E5R',geo),('PARITY',parity),('E2R_ACF',acf)]:
        if rr:pd.DataFrame(rr).to_csv(out/f'{name}_{case}_{part}.csv',index=False,float_format='%.12g')
    files=list(out.glob('*'))
    dump(out/f'MANIFEST_{case}_{part}.json',dict(source_ref=SOURCE_REF,git_sha=os.getenv('GITHUB_SHA'),run_id=os.getenv('GITHUB_RUN_ID'),
       utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),command=sys.argv,case=case,seeds=list(seeds),
       config=dict(fd=FD,fixed_scales=FIXED_SCALES,gate='frozen original BASE',new_training=False,nested_loro=False),
       input_lock=(Path(os.environ['REFLECT_ROOT'])/'out/INPUT_LOCK.sha256').read_text(),
       code_sha256={str(p):digest(p) for p in [Path(__file__),SRC/'ctl_core.py',SRC/'run_stage.py']},
       outputs={p.name:digest(p) for p in files if p.is_file()},sec=time.time()-t0))


def aggregate(out):
    fs=sorted(out.glob('E2R_*_lo.csv'))+sorted(out.glob('E2R_*_hi.csv'))
    d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
    # Empty grouping values are explicit; never let pandas discard E2 groups as NaN.
    assert not d.duplicated(['case','seed','arm','treat']).any()
    d.to_csv(out/'E2R_ALL.csv',index=False)
    rows=[]
    for (case,arm,tr),g in d.groupby(['case','arm','treat'],dropna=False):
        if tr=='BASE':continue
        b=d[(d.case==case)&(d.arm==arm)&(d.treat=='BASE')].set_index('seed')
        g=g.set_index('seed');dh=g.head_rmse-b.loc[g.index].head_rmse;dp=g.xy_rmse_cm-b.loc[g.index].xy_rmse_cm
        rows.append(dict(case=case,arm=arm,treat=tr,n=len(g),head_median=g.head_rmse.median(),head_min=g.head_rmse.min(),head_max=g.head_rmse.max(),
            xy_median=g.xy_rmse_cm.median(),delta_head_median=dh.median(),delta_xy_median=dp.median(),head_improved=int((dh<0).sum()),both_improved=int(((dh<0)&(dp<0)).sum()),
            nees4_median=g.nees4.median(),head_z_rms_median=g.head_z_rms.median()))
    j=pd.DataFrame(rows);j.to_csv(out/'JUDGE_E2R.csv',index=False)
    gg=list(out.glob('E5R_*_lo.csv'));geo=pd.concat([pd.read_csv(f) for f in gg],ignore_index=True)
    geo.to_csv(out/'E5R_ALL.csv',index=False)
    fail=geo[(geo.window=='FAIL')&(geo.method=='DYNAMIC_Q')];fail.to_csv(out/'JUDGE_E5R_FAIL.csv',index=False)
    lines=['# E2/E5 corrective rerun','', 'Post-hoc corrective experiment; original run 40820579727 remains unchanged.',
           'E2 full Jacobian and frozen-donor corrections are different estimators, not interchangeable fixes.',
           'E5 DYNAMIC_Q is nominal linear-Gaussian initial-state sensitivity under existing white Q/R; not empirical RF Fisher.',
           'E7 nested LORO and new environments were not executed.','',j.to_markdown(index=False),'',fail.to_markdown(index=False)]
    (out/'RESULTS_CORRECTIVE.md').write_text('\n'.join(lines))
    dump(out/'COMPLETION.json',dict(shards=len(fs),expected_shards=12,rows=len(d),expected_cases=CASES,
         seed_counts=d[d.treat=='BASE'].groupby(['case','arm']).seed.nunique().to_dict().__repr__(),all_12_shards=len(fs)==12))
    assert len(fs)==12


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES);p.add_argument('--part',choices=['lo','hi']);p.add_argument('--out',required=True);p.add_argument('--aggregate',action='store_true');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if a.aggregate:aggregate(out)
    else:compute(a.case,a.part,out)
if __name__=='__main__':main()
