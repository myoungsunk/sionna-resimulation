"""Time-based FOGM rerun, leave-one-ROUTE-out fitted time parameters.
Research diagnostic, not an operational candidate. No trained parameter sees held route.
Comparisons: MB_VAR and existing spatial GM03/GM1Y20, fixed BASE gate.
Two covariance allocations:
  KEEP: Rwhite = Rbase and extra FOGM variance (deliberate double-count risk)
  SPLIT: Rwhite_ss = max(0.05 Rbase_ss, Rbase_ss - sigma_b^2)
  SPLIT is a model sensitivity, not guaranteed correct decomposition.
Training residuals use truth offline on training routes ONLY; truth in held route for scoring.
"""
from __future__ import annotations
import os, sys, time, json, math, hashlib, argparse
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT/'mbvar_premodel_diag_20261029'/'code'))
import diag_mbvar as DG
PB=DG.PB
CASES=DG.CASES
BIAS=("B0","L2")
TRAIN_ONLY_WINDOW=30.
LAGS=np.arange(1,9)
STEP=.2

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def moments(D):
    """Autocovariances by original index and time; NEVER bridge non-finite gaps."""
    eps=D['z'][:,1]-D['hg'][:,1]-D['mu']['MB'][:,1]
    ok=np.isfinite(eps)&(D['t']>=TRAIN_ONLY_WINDOW)
    centered=eps.copy(); centered[ok]-=eps[ok].mean()
    gam=[];counts=[];gaps=[]
    for lag in range(9):
        ii=np.flatnonzero(ok[:len(ok)-lag]&ok[lag:])
        if lag:
            delta=D['t'][ii+lag]-D['t'][ii]
            ii=ii[np.abs(delta-STEP*lag)<.04]
        counts.append(len(ii))
        gam.append(float(np.mean(centered[ii]*centered[ii+lag])) if len(ii)>4 else np.nan)
    return np.asarray(gam),counts,float(eps[ok].mean())

def fit(train,held):
    """Positive lags fitted with one exponential covariance law, normalized per case.
    This tests adequacy of AR1/FOGM, not an iid-noise identification claim."""
    corrs=[];vars=[];rows=[]
    for c,D in train.items():
        gam,n,mean=moments(D);rho=gam[1:]/gam[0]
        corrs.append(rho);vars.append(gam[0])
        rows.append(dict(case=c,route=c[:2],n=int(n[0]),mean_eps=mean,
                         gamma0=gam[0],rho1=rho[0],rho2=rho[1],
                         rho4=rho[3],rho8=rho[7],counts_at_lag8=int(n[8])))
    corrs=np.asarray(corrs);vars=np.asarray(vars)
    avg=np.nanmean(corrs,axis=0)
    grid=np.linspace(.1,.995,900)
    # Fit fraction of colored variance times phi^lag, allowing white remainder.
    powers=grid[:,None]**LAGS[None,:]
    amps=np.clip((powers@avg)/(np.sum(powers*powers,axis=1)+1e-15),0.,.98)
    errs=np.mean((powers*amps[:,None]-avg[None,:])**2,axis=1)
    best=int(np.argmin(errs));phi=float(grid[best]);alpha=float(amps[best])
    meanvar=float(np.mean(vars))
    bvar=max(1e-8,alpha*meanvar)
    tau=-STEP/math.log(phi)
    return dict(held_route=held,phi=phi,tau_s=tau,alpha=alpha,
                sigma_b2=bvar,sigma_b=math.sqrt(bvar),
                mean_gamma0=meanvar,fit_rmse_rho=float(math.sqrt(errs[best])),
                train_cases=";".join(train),rho1_mean=float(avg[0]),rho8_mean=float(avg[-1]),
                predicted_rho1=float(alpha*phi),predicted_rho8=float(alpha*phi**8)),rows

def whiten_diagnostic(D,phi):
    """Apply AR1 contrast ONLY for residual-model diagnostic (not an EKF differencing filter)."""
    e=D['z'][:,1]-D['hg'][:,1]-D['mu']['MB'][:,1]
    ok=np.isfinite(e)&(D['t']>=30)
    idx=np.flatnonzero(ok[:-1]&ok[1:]&(np.abs(np.diff(D['t'])-STEP)<.04))
    d=e[idx+1]-phi*e[idx]
    # Adjacent contrast pairs, not across missing samples:
    mask=np.diff(idx)==1
    r1=float(np.corrcoef(d[:-1][mask],d[1:][mask])[0,1]) if mask.sum()>4 else np.nan
    return dict(n=len(idx),eps_lag1=float(moments(D)[0][1]/moments(D)[0][0]),
                eta_lag1=r1,eta_rms=float(np.sqrt(np.mean(d*d))),
                eps_rms=float(np.sqrt(np.mean(e[ok]*e[ok]))))

def replay(D,model,fitval,cov_mode):
    n=len(D['t']);x=np.r_[D['x0'],0.];P=np.zeros((5,5))
    P[:4,:4]=D['P0'];P[4,4]=fitval['sigma_b2']
    X=np.zeros((n,4));PX=np.zeros((n,4,4));B=np.zeros(n)
    residuals=[];used=0;varfloor=0
    for k in range(n):
        if k:
            ds=float(D['ds'][k]);gy=float(D['gy'][k]);dt=float(D['dt'][k])
            phi=math.exp(-max(dt,0.)/fitval['tau_s'])
            q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
            yp,P44,F,_=DG.predict(x[:4],P[:4,:4],ds,gy,dt,q)
            Pn=np.zeros((5,5));Pn[:4,:4]=P44
            Pn[:4,4]=F@P[:4,4]*phi;Pn[4,:4]=Pn[:4,4]
            Pn[4,4]=phi*phi*P[4,4]+fitval['sigma_b2']*(1-phi*phi)
            x=np.r_[yp,phi*x[4]];P=.5*(Pn+Pn.T)
        if D['acc'][k]:
            h,H=model.batch(x[None,:4],D['spec']);h=h[0];H=H[0]
            R=D['R'][k].copy()
            if cov_mode=='SPLIT':
                base=R[1,1];R[1,1]=max(.05*base,base-fitval['sigma_b2'])
                varfloor+=R[1,1]<=.05*base+1e-14
            elif cov_mode!='KEEP':
                raise ValueError(cov_mode)
            Ha=np.c_[H,np.array([0.,1.])]
            v=D['z'][k]-h-D['mu']['MB'][k]-np.array([0.,x[4]])
            S=Ha@P@Ha.T+R;S=.5*(S+S.T)
            K=np.linalg.solve(S,Ha@P).T
            xnew=x+K@v;xnew[2]=DG.wrap(xnew[2])
            A=np.eye(5)-K@Ha;PP=A@P@A.T+K@R@K.T
            x=xnew;P=.5*(PP+PP.T);used+=1
            residuals.append((D['t'][k],v[1]))
        X[k]=x[:4];PX[k]=P[:4,:4];B[k]=x[4]
    score=PB.scores(D,X,PX)
    ix=np.isfinite(D['z']).all(1)&D['acc']
    e=D['z'][:,1]-D['hg'][:,1]-D['mu']['MB'][:,1]
    score.update(bias_corr=float(np.corrcoef(B[ix],e[ix])[0,1]) if ix.sum()>5 else np.nan,
                 b_rmse=float(np.sqrt(np.mean((B[ix]-e[ix])**2))) if ix.sum()>5 else np.nan,
                 n_used=used,white_floor_hits=varfloor,
                 median_Rbase_ss=float(np.median(D['R'][ix,1,1])))
    return score

def score_baseline(D,model,cfg):
    X,P,_,_=PB.run(D,D['mu']['MB'],cfg,model)
    return PB.scores(D,X,P)

def math_tests():
    """Analytic scalar white+colored differencing identities.
    A finite white component becomes MA(1), so naive standard EKF is invalid."""
    phi=.8;Rwhite=.2;Qeta=.1
    # ynoise_k = eta_k + e_k -phi*e_{k-1}
    var_expected=Qeta+(1+phi**2)*Rwhite
    lag1_expected=-phi*Rwhite
    assert np.isclose(var_expected,.428)
    assert np.isclose(lag1_expected,-.16)
    # With only colored b and no white e, differencing recovers eta, but prev state in h* remains uncertain.
    assert var_expected>Qeta and lag1_expected<0
    # covariance block must be PSD for these parameters
    M=np.array([[var_expected,lag1_expected],[lag1_expected,var_expected]])
    assert np.linalg.eigvalsh(M).min()>0
    return dict(phi=phi,R_white=Rwhite,Q_eta=Qeta,diff_noise_variance=var_expected,
                diff_noise_lag1_cov=lag1_expected,mathematical_tests='PASS')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--biases',nargs='+',default=list(BIAS))
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    model=DG.C.base_model()
    dat={c:DG.load(c,'B0',model) for c in CASES}
    fits={};train_rows=[];acf_rows=[];allrows=[];parity=[]
    for route in ('R2','R4','R5'):
        fit,rows=fit_train=fit({c:D for c,D in dat.items() if c[:2]!=route},route)
        fits[route]=fit;train_rows.extend(dict(held_route=route,**rr) for rr in rows)
        print('TRAIN',route,fit,flush=True)
        for c,D in dat.items():
            if c[:2]==route:
                acf_rows.append(dict(case=c,held_route=route,**whiten_diagnostic(D,fit['phi'])))
    for c in CASES:
        route=c[:2]
        for bias in a.biases:
            t0=time.monotonic()
            D=dat[c] if bias=='B0' else DG.load(c,bias,model)
            mb=DG.run(D,'MB','var','fixed',model=model)
            base=PB.run(D,D['mu']['MB'],{'mode':'var'},model)
            pdiff=float(np.max(np.abs(mb[0]-base[0])));cdiff=float(np.max(np.abs(mb[1]-base[1])))
            if pdiff>1e-9 or cdiff>1e-9:raise RuntimeError('MB_VAR_PARITY_FAIL')
            parity.append(dict(case=c,bias=bias,max_state_abs=pdiff,max_cov_abs=cdiff))
            for arm,cfg in [('MB_VAR',{'mode':'var'}),('GM03',{'mode':'gm','L':.3}),('GM1Y20',{'mode':'gm','L':1.,'Psi':20.})]:
                s=score_baseline(D,model,cfg)
                allrows.append(dict(case=c,route=route,bias=bias,arm=arm,**s))
            for mode in ('KEEP','SPLIT'):
                s=replay(D,model,fits[route],mode)
                allrows.append(dict(case=c,route=route,bias=bias,arm='GM_TIME_'+mode,**s))
            pd.DataFrame(allrows).to_csv(out/'FILTER_SCORES.csv',index=False)
            print('DONE',c,bias,'seconds',round(time.monotonic()-t0,1),flush=True)
    pd.DataFrame(fits.values()).to_csv(out/'LORO_TIME_FITS.csv',index=False)
    pd.DataFrame(train_rows).to_csv(out/'TRAIN_ACF.csv',index=False)
    pd.DataFrame(acf_rows).to_csv(out/'HELD_ACF_DIAGNOSTIC.csv',index=False)
    pd.DataFrame(parity).to_csv(out/'PARITY.csv',index=False)
    pd.DataFrame([math_tests()]).to_csv(out/'DIFFERENCING_MATH_TEST.csv',index=False)
    A=pd.DataFrame(allrows);summary=[]
    for (arm,bias),g in A.groupby(['arm','bias']):
        for criterion in ['head_rmse','xy_rmse_cm']:
            ref=A[(A.arm=='MB_VAR')&(A.bias==bias)].set_index('case')
            imp=np.array([getattr(row,criterion)<ref.loc[row.case,criterion] for row in g.itertuples()])
            summary.append(dict(arm=arm,bias=bias,metric=criterion,
                                mean=float(g[criterion].mean()),median=float(g[criterion].median()),
                                beat_MBVAR_n=int(imp.sum()),n=len(g)))
    pd.DataFrame(summary).to_csv(out/'SUMMARY.csv',index=False)
    lock=DG.C.ROOT/'out'/'INPUT_LOCK.sha256'
    man={'stage':'MBVAR_TIME_GM_LORO','utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
         'github_run':os.environ.get('GITHUB_RUN_ID'),'head_sha':os.environ.get('GITHUB_SHA'),
         'method2':'analytic error-noise-correlation validation ONLY; no measurement differencing EKF run',
         'config':{'cases':CASES,'bias':a.biases,'fixed_GATE':True,'t_score_ge_s':30,
             'time_fit':'LORO route gamma(l) normalized l=1..8 phi grid with colored fraction',
             'variance_modes':['KEEP existing Rbase plus colored state','SPLIT subtract stationary b variance with 5% Rbase floor'],
             'held_route_truth_in_parameter_training':False},
         'input_lock_sha256':sha(lock) if lock.exists() else None,
         'source_sha256':{Path(__file__).name:sha(Path(__file__))},
         'outputs_sha256':{p.name:sha(p) for p in out.glob('*.csv')},
         'limitations':['one corridor','route A/B correlated','training truth used on other routes only',
              'no final independent test','base R and b state separation uncertain',
              'AR1 model fit is approximate; residuals may be nonstationary']}
    (out/'MANIFEST.json').write_text(json.dumps(man,ensure_ascii=False,indent=2))
    print('SUMMARY',pd.DataFrame(summary).to_string(index=False),flush=True)
if __name__=='__main__':main()
