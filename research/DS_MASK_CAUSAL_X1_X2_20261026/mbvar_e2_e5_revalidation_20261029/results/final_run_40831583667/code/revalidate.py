#!/usr/bin/env python3
"""Post-hoc E2/E5 correction of run 40820579727; original evidence is untouched.
E2 reuses the original mean fits: full Jacobian vs frozen donor-prior correction.
E5 fixes normalization, transports H by F, and marginalizes the existing white Q.
These are diagnostics, NOT E7 nested LORO or new-environment validation.
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
FIXED_SCALES=np.array([.1,.1,np.deg2rad(5),np.deg2rad(.2)])
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load_core():
    sys.path.insert(0,str(SRC));import ctl_core as K
    from core import transition
    original=K.load;cache={}
    def cached(case,seed=0,bias='B0'):
        key=(case,seed,bias)
        if key not in cache:cache[key]=original(case,seed,bias)
        return cache[key]
    K.load=cached
    return K,transition

def features(K,x,h,H,a):return np.array([K.online_features(u,v,w,a) for u,v,w in zip(x,h,H)])
def mean_value(K,mods,x,h,H,a):
    f=features(K,x,h,H,a)
    return np.column_stack([K.ridge_pred(mods[j],f) for j in range(2)])

class EffectiveModel:
    """h_eff=h+m; derivative of ALL mean features, including the H-based features.
    Central differences approximate dm/dx. Detector/interpolation branch crossings
    are checked separately; no clipping or favorable-sample selection is applied.
    """
    def __init__(self,K,base,mods,anchor,step=FD):self.K,self.base,self.mods,self.anchor,self.step=K,base,mods,anchor,step
    def batch(self,states,spec,gradient=True):
        x=np.atleast_2d(np.asarray(states,float));h,H=self.base.batch(x,spec)
        mu=mean_value(self.K,self.mods,x,h,H,self.anchor)
        if not gradient:return h+mu,None
        n=len(x);xx=[]
        for j in range(3):
            p=x.copy();q=x.copy();p[:,j]+=self.step[j];q[:,j]-=self.step[j];xx.extend([p,q])
        xx=np.concatenate(xx);hh,HH=self.base.batch(xx,spec)
        mm=mean_value(self.K,self.mods,xx,hh,HH,self.anchor).reshape(3,2,n,2)
        J=np.zeros_like(H)
        for j in range(3):J[:,:,j]=(mm[j,0]-mm[j,1])/(2*self.step[j])
        return h+mu,H+J

@contextlib.contextmanager
def override(K,m):
    old=K.model;K.model=lambda:m
    try:yield
    finally:K.model=old

def train(K,case):
    xs=[];ys=[];members=[]
    for c in CASES:
        if c[:2]==case[:2]:continue
        D=K.load(c,0);_,_,L=K.run(D,'MB',K.R_orig)
        ii=np.flatnonzero(D['fin']&np.isfinite(L['nis']))
        xs.append(features(K,L['xp'][ii],L['hx'][ii],L['H'][ii],D['anchor']))
        ys.append((D['z']-D['hg']-D['mu']['MB'])[ii]);members.append(dict(case=c,n=len(ii),seed=0))
    xx=np.concatenate(xs);yy=np.concatenate(ys)
    sh=yy[np.random.default_rng(2026103200+CASES.index(case)).permutation(len(yy))]
    return {'COND':[K.ridge_fit(xx,yy[:,j]) for j in range(2)],'SHUF':[K.ridge_fit(xx,sh[:,j]) for j in range(2)]},members

def jacobian_qa(K,D,base,mods,L):
    ii=np.flatnonzero(D['fin']);ii=ii[np.linspace(0,len(ii)-1,min(48,len(ii))).astype(int)]
    x=L['xp'][ii];m=EffectiveModel(K,base,mods,D['anchor']);_,H=m.batch(x,D['spec'])
    _,Hhalf=EffectiveModel(K,base,mods,D['anchor'],FD*.5).batch(x,D['spec'])
    Hnum=np.zeros_like(H);cross=np.zeros(len(ii),bool)
    _,_,diag=base.batch(x,D['spec'],return_diagnostics=True)
    for j in range(3):
        p=x.copy();q=x.copy();p[:,j]+=FD[j]*.5;q[:,j]-=FD[j]*.5
        hp,_=m.batch(p,D['spec'],gradient=False);hq,_=m.batch(q,D['spec'],gradient=False);Hnum[:,:,j]=(hp-hq)/FD[j]
        for v in (p,q):
            _,_,dg=base.batch(v,D['spec'],return_diagnostics=True)
            cross|=(dg['tap']!=diag['tap'])|(dg['strong_port']!=diag['strong_port'])|np.any(dg['cells']!=diag['cells'],axis=1)
    def rel(a,b):return np.linalg.norm((a-b).reshape(len(ii),-1),axis=1)/np.maximum(np.linalg.norm(b.reshape(len(ii),-1),axis=1),1e-9)
    rr,st=rel(H,Hnum),rel(H,Hhalf);good=~cross
    if good.any() and np.quantile(rr[good],.95)>1e-2:raise RuntimeError('JACOBIAN_QA_FAIL')
    return [dict(case=D['case'],k=int(k),t=float(D['t'][k]),branch_crossing=bool(cross[j]),relative_full_jacobian_error=rr[j],relative_step_halving=st[j]) for j,k in enumerate(ii)]

def mean_run(K,D,base,mods,Rf,name,donor):
    if name=='FROZEN_COND':
        mm=mean_value(K,mods,donor['xp'],donor['hx'],donor['H'],D['anchor'])
        X,P,L=K.run(D,'MB',Rf,mu_add=lambda k,x,h,H:mm[k])
        eps=D['z']-D['hg']-D['mu']['MB']-mm;dh=D['hg']-L['hx']
    elif name.startswith('LEGACY'):
        fn=lambda k,x,h,H:mean_value(K,mods,x[None],h[None],H[None],D['anchor'])[0]
        X,P,L=K.run(D,'MB',Rf,mu_add=fn);eps=D['z']-D['hg']-L['mu_used'];dh=D['hg']-L['hx']
    else:
        eff=EffectiveModel(K,base,mods,D['anchor'])
        with override(K,eff):X,P,L=K.run(D,'MB',Rf)
        gt4=np.c_[D['gt'][:,:3],np.full(len(D['t']),D['b_true'])]
        hgt,_=eff.batch(gt4,D['spec'],gradient=False)
        eps=D['z']-hgt-D['mu']['MB'];dh=hgt-L['hx']
    valid=D['fin']&(D['t']>=30);sel=valid&D['acc']
    contract=float(np.nanmax(abs(L['nu'][valid]-eps[valid]-dh[valid])));assert contract<1e-9
    ep=D['gt'][:,:3]-L['xp'][:,:3];ep[:,2]=np.angle(np.exp(1j*ep[:,2]));e4=np.c_[ep,D['b_true']-L['xp'][:,3]]
    ell=dh-np.einsum('nij,nj->ni',L['H'],e4)
    s=K.scores(D,X,P)
    s.update(decomposition_max_abs_error=contract,effective_rf_s_rms=float(np.sqrt(np.mean(eps[valid,1]**2))),effective_rf_s_mean=float(np.mean(eps[valid,1])),
             ell_share=float(np.mean(ell[sel,1]**2)/max(np.mean(dh[sel,1]**2),1e-30)),n_used=int(L['upd'][:,0].sum()))
    return s

def synthetic_info_qa():
    """Independent stacked-covariance check of the Q-marginalized information recursion."""
    rg=np.random.default_rng(20261029);n=4;steps=6
    Fs=[np.eye(n)]+[np.eye(n)+rg.normal(size=(n,n))*.03 for _ in range(steps-1)]
    Hs=[rg.normal(size=(2,n)) for _ in range(steps)];Qs=[np.zeros((n,n))]+[np.eye(n)*.01 for _ in range(steps-1)];R=np.diag([.2,.4])
    Phi=np.eye(n);V=np.zeros((n,n));E=np.zeros((n,n));I=np.zeros((n,n));As=[];process=[];W=np.zeros((n,n*steps))
    for k in range(steps):
        Phi=Fs[k]@Phi;W=Fs[k]@W;W[:,n*k:n*(k+1)]+=np.eye(n)
        V=Fs[k]@V@Fs[k].T+Qs[k];E=Fs[k]@E;A=Hs[k]@Phi;B=A-Hs[k]@E;S=Hs[k]@V@Hs[k].T+R
        I+=B.T@np.linalg.solve(S,B);K=np.linalg.solve(S,Hs[k]@V).T;E+=K@B;M=np.eye(n)-K@Hs[k];V=M@V@M.T+K@R@K.T
        As.append(A);process.append(Hs[k]@W)
    A=np.vstack(As);B=np.vstack(process);QQ=np.zeros((n*steps,n*steps))
    for k in range(steps):QQ[n*k:n*(k+1),n*k:n*(k+1)]=Qs[k]
    Sigma=B@QQ@B.T+np.kron(np.eye(steps),R);direct=A.T@np.linalg.solve(Sigma,A)
    err=float(np.max(abs(I-direct)));assert err<1e-9
    return dict(process_marginalization_max_abs_error=err)

def geometry(K,transition,D,X,P,L,arm):
    t=D['t'];er=K.state_err(D,X)[:,2];starts=np.arange(30,t[-1]-30+1e-9,10.)
    fw=max(starts,key=lambda st:np.mean(er[(t>=st)&(t<st+30)]**2))
    wins=[(lo,min(hi,t[-1]+.01),str(lo)) for lo,hi in K.WINDOWS if lo<t[-1]]+[(fw,fw+30,'FAIL')];out=[]
    for lo,hi,tag in wins:
        ks=np.flatnonzero((t>=lo)&(t<hi));k0=int(ks[0]);used=ks[L['upd'][ks].any(1)]
        if len(used)<3:continue
        km=int(used[len(used)//2]);ur=D['gt'][km,:2]-D['anchor'];ur/=np.linalg.norm(ur)
        T=np.eye(4);T[:2,:2]=np.array([ur,[-ur[1],ur[0]]])
        Prt=T@L['Pp'][k0]@T.T;sd=np.sqrt(np.diag(Prt))
        I0=np.zeros((4,4));Id=I0.copy();Iq=I0.copy();Phi=np.eye(4);V=I0.copy();E=I0.copy()
        for k in ks:
            if k!=k0:
                _,F,G=transition(X[k-1],float(D['ds'][k]),float(D['gy'][k]),float(D['dt'][k]))
                q=np.diag([2e-5*abs(D['ds'][k]),np.deg2rad(.015)**2*D['dt'][k],0.])
                Phi=F@Phi;V=F@V@F.T+G@q@G.T;E=F@E
            rs=np.flatnonzero(L['upd'][k])
            if not len(rs):continue
            H=L['H'][k][rs];R=L['Ru'][k][np.ix_(rs,rs)];I0+=H.T@np.linalg.solve(R,H)
            A=H@Phi;Id+=A.T@np.linalg.solve(R,A);B=A-H@E;S=H@V@H.T+R;Iq+=B.T@np.linalg.solve(S,B)
            Kg=np.linalg.solve(S,H@V).T;E+=Kg@B;M=np.eye(4)-Kg@H;V=M@V@M.T+Kg@R@Kg.T;V=(V+V.T)*.5
        for method,I in [('STATIC',I0),('DYNAMIC_NO_Q',Id),('DYNAMIC_Q',Iq)]:
            Irt=T@I@T.T
            for scale,ss in [('PRIOR_DIAG',sd),('FIXED_PHYSICAL',FIXED_SCALES)]:
                Dm=np.diag(ss);N=Dm@Irt@Dm;N=(N+N.T)*.5;w,v=np.linalg.eigh(N[:3,:3]);w4=np.linalg.eigvalsh(N)
                J=Dm@(Irt+np.linalg.inv(Prt))@Dm;J=(J+J.T)*.5
                Sm=J[:3,:3]-J[:3,3:4]@J[3:4,:3]/J[3,3];wm,vm=np.linalg.eigh(Sm)
                U=np.diag([100.,100.,180/np.pi,180/np.pi]);Ii=np.linalg.solve(U.T,Irt)@np.linalg.inv(U);si=np.diag(U)*ss
                Ni=np.diag(si)@Ii@np.diag(si);ue=float(np.max(abs(N-Ni))/max(np.max(abs(N)),1e-30));assert ue<1e-10
                out.append(dict(case=D['case'],arm=arm,window=tag,t_lo=lo,t_hi=hi,method=method,scale=scale,n_upd=len(used),
                    eig_pose_min=w[0],eig_pose_mid=w[1],eig_pose_max=w[2],eig4_min=w4[0],eig4_max=w4[-1],
                    vmin_rad=abs(v[0,0]),vmin_tan=abs(v[1,0]),vmin_psi=abs(v[2,0]),
                    posterior_pose_marg_eig_min=wm[0],posterior_pose_marg_vmin_tan=abs(vm[1,0]),
                    unit_invariance_rel_error=ue,prior_rad_sd=sd[0],prior_tan_sd=sd[1],prior_head_sd=sd[2],prior_bg_sd=sd[3]))
    return out

def compute(case,part,out):
    qa_math=synthetic_info_qa();K,transition=load_core();base=K.model();t0=time.time();mods,members=train(K,case)
    dump(out/f'TRAIN_{case}_{part}.json',dict(source_ref=SOURCE_REF,held_route=case[:2],training=members,models=mods,nested_loro=False))
    seeds=range(0,5) if part=='lo' else range(5,10);rows=[];qa=[];geo=[];parity=[];acf=[]
    old=pd.read_csv(SRC/'results/run_40820579727'/f'E23_{case}.csv')
    for seed in seeds:
        D=K.load(case,seed)
        for arm,Rf in [('MB_ORIG',K.R_orig),('MB_VAR',K.R_var)]:
            X,P,L=K.run(D,'MB',Rf);ss=K.scores(D,X,P);ref=old[(old.seed==seed)&(old.arm==arm)&(old.family=='BASE')].iloc[0]
            dif=max(abs(ss['head_rmse']-ref.head_rmse),abs(ss['xy_rmse_cm']-ref.xy_rmse_cm));assert dif<1e-5,(case,seed,arm,dif)
            parity.append(dict(case=case,seed=seed,arm=arm,max_score_difference_vs_original_csv=dif));rows.append(dict(case=case,seed=seed,arm=arm,treat='BASE',**ss))
            if seed==0:
                qa+=jacobian_qa(K,D,base,mods['COND'],L);geo+=geometry(K,transition,D,X,P,L,arm)
                for name in ('COND','SHUF'):
                    s=mean_run(K,D,base,mods[name],Rf,'LEGACY_'+name,L);rr=old[(old.seed==seed)&(old.arm==arm)&(old.treat=='MEAN_'+name)].iloc[0]
                    dd=max(abs(s['head_rmse']-rr.head_rmse),abs(s['xy_rmse_cm']-rr.xy_rmse_cm));assert dd<1e-4,(dd,case,arm,name)
                    rows.append(dict(case=case,seed=seed,arm=arm,treat='LEGACY_'+name,**s))
                valid=D['fin']&(D['t']>=30);baseeps=D['z']-D['hg']-D['mu']['MB']
                for name in ('NONE','COND','SHUF'):
                    ep=baseeps.copy()
                    if name!='NONE':ep-=mean_value(K,mods[name],L['xp'],L['hx'],L['H'],D['anchor'])
                    for j,c in enumerate('rs'):acf.append(dict(case=case,arm=arm,model=name,comp=c,n=int(valid.sum()),rms=float(np.sqrt(np.mean(ep[valid,j]**2))),**K.acf_stats(ep[valid,j])))
            for name,ms in [('FULL_JAC_COND','COND'),('FULL_JAC_SHUF','SHUF'),('FROZEN_COND','COND')]:rows.append(dict(case=case,seed=seed,arm=arm,treat=name,**mean_run(K,D,base,mods[ms],Rf,name,L)))
            pd.DataFrame(rows).to_csv(out/f'E2R_{case}_{part}.csv',index=False,float_format='%.12g')
        print('DONE',case,seed,'elapsed',round(time.time()-t0,1),flush=True)
    for name,rr in [('QA_JAC',qa),('E5R',geo),('PARITY',parity),('E2R_ACF',acf)]:
        if rr:pd.DataFrame(rr).to_csv(out/f'{name}_{case}_{part}.csv',index=False,float_format='%.12g')
    dump(out/f'MANIFEST_{case}_{part}.json',dict(source_ref=SOURCE_REF,git_sha=os.getenv('GITHUB_SHA'),run_id=os.getenv('GITHUB_RUN_ID'),utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),command=sys.argv,case=case,seeds=list(seeds),
       config=dict(fd=FD,fixed_scales=FIXED_SCALES,gate='frozen original BASE',new_training=False,nested_loro=False),math_qa=qa_math,
       input_lock=(Path(os.environ['REFLECT_ROOT'])/'out/INPUT_LOCK.sha256').read_text(),code_sha256={str(p):digest(p) for p in [Path(__file__),SRC/'ctl_core.py',SRC/'run_stage.py']},outputs={p.name:digest(p) for p in out.glob('*') if p.is_file()},sec=time.time()-t0))

def aggregate(out):
    fs=sorted(out.glob('E2R_*_lo.csv'))+sorted(out.glob('E2R_*_hi.csv'));d=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True)
    assert not d.duplicated(['case','seed','arm','treat']).any();d.to_csv(out/'E2R_ALL.csv',index=False);rows=[]
    for (case,arm,tr),g in d.groupby(['case','arm','treat'],dropna=False):
        if tr=='BASE':continue
        b=d[(d.case==case)&(d.arm==arm)&(d.treat=='BASE')].set_index('seed');g=g.set_index('seed');dh=g.head_rmse-b.loc[g.index].head_rmse;dp=g.xy_rmse_cm-b.loc[g.index].xy_rmse_cm
        rows.append(dict(case=case,arm=arm,treat=tr,n=len(g),head_median=g.head_rmse.median(),head_min=g.head_rmse.min(),head_max=g.head_rmse.max(),xy_median=g.xy_rmse_cm.median(),delta_head_median=dh.median(),delta_xy_median=dp.median(),head_improved=int((dh<0).sum()),both_improved=int(((dh<0)&(dp<0)).sum()),nees4_median=g.nees4.median(),head_z_rms_median=g.head_z_rms.median()))
    j=pd.DataFrame(rows);j.to_csv(out/'JUDGE_E2R.csv',index=False)
    geo=pd.concat([pd.read_csv(f) for f in sorted(out.glob('E5R_*_lo.csv'))],ignore_index=True);geo.to_csv(out/'E5R_ALL.csv',index=False)
    fail=geo[(geo.window=='FAIL')&(geo.method=='DYNAMIC_Q')];fail.to_csv(out/'JUDGE_E5R_FAIL.csv',index=False)
    text=['# E2/E5 corrective rerun','','Post-hoc corrective experiment; original run 40820579727 remains unchanged.',
       'Full Jacobian and frozen-donor mean corrections are different estimators.',
       'E5 DYNAMIC_Q is nominal initial-state information under existing white Q/R, not empirical RF Fisher.',
       'E7 nested LORO and new environments were not executed.','',j.to_markdown(index=False),'',fail.to_markdown(index=False)]
    (out/'RESULTS_CORRECTIVE.md').write_text('\n'.join(text))
    counts=d[d.treat=='BASE'].groupby(['case','arm']).seed.nunique()
    dump(out/'COMPLETION.json',dict(shards=len(fs),expected_shards=12,rows=len(d),baseline_seed_counts={str(k):int(v) for k,v in counts.items()},all_12_shards=len(fs)==12))
    assert len(fs)==12 and len(counts)==12 and (counts==10).all()

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=CASES);p.add_argument('--part',choices=['lo','hi']);p.add_argument('--out',required=True);p.add_argument('--aggregate',action='store_true');p.add_argument('--math-qa',action='store_true');a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if a.math_qa:dump(out/'SYNTHETIC_INFO_QA.json',synthetic_info_qa())
    elif a.aggregate:aggregate(out)
    else:compute(a.case,a.part,out)
if __name__=='__main__':main()
