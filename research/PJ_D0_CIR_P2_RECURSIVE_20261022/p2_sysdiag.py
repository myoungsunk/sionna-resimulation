#!/usr/bin/env python3
"""System-level verification, stage 1 (16_SYSTEM_VERIFICATION_PLAN_KO.md). Offline on the v3 arrays, diagnostic only.

V1   kernel representation: W(t,k) ~ sum_j B_j(age)[alpha_j g_k/R_k + beta_j g_k S_k/R_k] (g-modulated) against the
     same basis without g (unmodulated); predictors of the pol heading component c(t) = sum_k W eps_k; band shares of
     eps through W and of u = g eps / R through the fitted modulated kernel.
V2   pol-only GLS with the true positions: eps_k = g_k dpsi_t + g_k S_k db + n_k, Cov(n) = Gamma (fitted AR + GM + const
     + white, cross-fitted on the other routes) + gyro random walk; GLS / WLS / EKF realized and expected errors.
V2'  correlated-noise filter counterfactual: the realized inputs of v3 pushed through a linear filter whose gains come
     from an augmented model (AR / GM / constant nuisance states for pol and/or range, estimated or considered).
     'base' (no nuisance) must reproduce the saved gains and the saved state error.
V4   excitation of g (true-state slope) and information retention eta = g'Gamma^-1 g / g'diag(R)^-1 g by window.
V6'  same route and anchor, mount 0 vs 45 deg (R2_aA): multipath bias e = s_F - s_LoS at the same poses.
V7   revisit pairs (|dp| < 5 cm, |dpsi| < 5 deg, |dt| > 20 s) and the correlation of eps at those pairs.
GT is used throughout for the decomposition; nothing here is an operational candidate.
"""
from __future__ import annotations
import argparse, glob, json, math, sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.linalg import cho_factor, cho_solve
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))

ARMS=['BASE','CIR','WIDE_NOES','PWIDE_NOES','ORACLE']
DEG=180/math.pi
AGE_EDGES=np.array([0,2,5,10,20,30,45,60,90,120,180,1e9])
Q_ODOM=2e-5;Q_GYRO=math.radians(.015)**2
INIT_STD=np.array([.1,.1,math.radians(5.)]);BIAS_STD=math.radians(.1)
V2_WINDOWS=[30.,60.,120.,240.];WLS_WINDOWS=[10.,30.,60.,120.]
BANDS=['const','slow_gt30s','mid_3_30s','fast_lt3s']

# ----------------------------------------------------------------------------- helpers
def stem_parts(f):
    stem=Path(f).name.replace('_EB3_ARRAYS.npz','');case,_,bias=stem.rsplit('_',2);return case,bias

def ma(x,t,win):
    dt=float(np.median(np.diff(t)));w=max(1,int(round(win/dt)))
    return pd.Series(x).rolling(w,center=True,min_periods=1).mean().to_numpy()

def bands(x,t):
    c=np.full_like(x,x.mean());s30=ma(x,t,30.);s3=ma(x,t,3.)
    return {'const':c,'slow_gt30s':s30-c,'mid_3_30s':s3-s30,'fast_lt3s':x-s3}

def kernels(F,K,H,ev):
    """Heading kernels for the pol and range rows at evaluation indices ev (float64, vectorized backward)."""
    n=len(F);E=len(ev);L=np.zeros((E,4));Wp=np.zeros((E,n));Wr=np.zeros((E,n));start={}
    for e,k in enumerate(ev):start.setdefault(int(k),[]).append(e)
    for k in range(n-1,-1,-1):
        for e in start.get(k,()):L[e]=0.;L[e,2]=1.
        Wk=L@K[k];Wp[:,k]=Wk[:,1];Wr[:,k]=Wk[:,0]
        if k>0:L=L@((np.eye(4)-K[k]@H[k])@F[k])
    return Wp,Wr

def bias_lever(F,ti):
    """S_k = -sum_{j=k+1}^{ti} F_j[2,3]: dpsi_k = dpsi_t + S_k db for k <= ti (from the saved transitions)."""
    f=F[1:ti+1,2,3]                      # f[k] = F_{k+1}[2,3], k = 0..ti-1
    return -np.r_[np.cumsum(f[::-1])[::-1],0.]

def autocov(x,maxlag):
    x=np.asarray(x,float);n=len(x);L=min(maxlag,n-2)
    return np.array([np.dot(x[:n-l],x[l:])/(n-l) for l in range(L+1)])   # uncentered (mean kept as a component)

def fit_gamma(gam,dt):
    """gamma(tau) = sw2 [tau=0] + sa2 rho^(tau/dt) + sb2 exp(-tau/taub) + s02, fitted on lags >= 1 (log parameters)."""
    L=len(gam)-1;lags=np.unique(np.round(np.geomspace(1,L,80)).astype(int));tau=lags*dt;g0=max(float(gam[0]),1e-30)
    y=gam[lags]/g0
    def model(p):
        sa2,rho,sb2,tb,s02=np.exp(p[0]),1/(1+np.exp(-p[1])),np.exp(p[2]),np.exp(p[3]),np.exp(p[4])
        return sa2*rho**(tau/dt)+sb2*np.exp(-tau/tb)+s02
    best=None
    for tb0 in (5.,20.,60.):
        p0=np.r_[math.log(.3),0.,math.log(.2),math.log(tb0),math.log(max(y[-1],1e-4))]
        r=least_squares(lambda p:model(p)-y,p0,bounds=(np.r_[-20,-8,-20,math.log(dt),-20],np.r_[2,8,2,math.log(2000.),2]))
        if best is None or r.cost<best.cost:best=r
    p=best.x;sa2,rho,sb2,tb,s02=np.exp(p[0])*g0,1/(1+np.exp(-p[1])),np.exp(p[2])*g0,np.exp(p[3]),np.exp(p[4])*g0
    sw2=max(g0-(sa2+sb2+s02),1e-3*g0)          # white floor keeps the augmented filters numerically regular
    return {'sw2':float(sw2),'sa2':float(sa2),'rho':float(rho),'sb2':float(sb2),'tau_b':float(tb),'s02':float(s02),
            'gamma0':g0,'fit_rmse_rel':float(np.sqrt(2*best.cost/len(y))),'dt':float(dt)}

def gamma_matrix(par,tk,Rk,Rmean):
    d=np.abs(tk[:,None]-tk[None,:])
    G=par['sa2']*par['rho']**(d/par['dt'])+par['sb2']*np.exp(-d/par['tau_b'])+par['s02']
    G[np.diag_indices_from(G)]+=par['sw2']*Rk/Rmean
    return G

def gamma_empirical(par,tk):
    """Toeplitz Gamma from the pooled cross-fit autocovariance (Bartlett taper), projected to PSD by eigenvalue clipping."""
    g=np.asarray(par['emp'],float);L=len(g);lag=np.rint(np.abs(tk[:,None]-tk[None,:])/par['dt']).astype(int)
    taper=np.clip(1-lag/L,0,None);G=np.where(lag<L,g[np.minimum(lag,L-1)],0.)*taper
    w,U=np.linalg.eigh(.5*(G+G.T));w=np.maximum(w,1e-6*max(float(w.max()),1e-30));return (U*w)@U.T

def shared_shape_ef(items,iters=8):
    """One kernel shape w (age bins x 2 regressors) shared by all evaluation times, one scale per time:
    y_e ~ s_e X_e w. Alternating least squares; returns the pooled explained energy."""
    if not items:return np.nan
    w=np.zeros(items[0][0].shape[1])
    for X,y,_ in items:
        c,*_=np.linalg.lstsq(X,y,rcond=None);nr=np.linalg.norm(c)
        if nr>0:w+=c/nr*np.sign(c@w if w.any() else 1.)
    for _ in range(iters):
        sc=[float((X@w)@y)/max(float((X@w)@(X@w)),1e-300) for X,y,_ in items]
        A=np.vstack([s_*X for (X,_,_),s_ in zip(items,sc)]);b=np.concatenate([y for _,y,_ in items]);w,*_=np.linalg.lstsq(A,b,rcond=None)
    sc=[float((X@w)@y)/max(float((X@w)@(X@w)),1e-300) for X,y,_ in items]
    ssr=sum(float(np.sum((y-s_*(X@w))**2)) for (X,y,_),s_ in zip(items,sc));tot=sum(d for _,_,d in items)
    return 1-ssr/tot if tot>0 else np.nan

def chol(G):
    G=.5*(G+G.T);j=1e-12*float(np.trace(G))/len(G);return cho_factor(G+j*np.eye(len(G)),lower=True)

def gls(A,cf,y,prior_info=None):
    """cf = Cholesky factor of Gamma (or a 1-D array = diagonal Gamma). Returns covariance, estimate, weights."""
    GiA=A/cf[:,None] if isinstance(cf,np.ndarray) and cf.ndim==1 else cho_solve(cf,A)
    I=A.T@GiA
    if prior_info is not None:I=I+prior_info
    C=np.linalg.inv(I);w=GiA@C          # estimate = w' y
    return C,w.T@y,w

# ----------------------------------------------------------------------------- per-case analysis
def analyse_case(job):
    f,par_x,par_in,gt,anc=job['file'],job['par_cross'],job['par_in'],job['gt'],job['anchor']
    has_kappa=bool(job.get('kappa'))
    case,bias=stem_parts(f);Z=np.load(f);t=Z['t'];truth=Z['truth'];n=len(t);ev_all=Z['ev']
    ev=ev_all[t[ev_all]>=60.];ev2=ev[::5]
    g_gt=gt['g'];out={k:[] for k in ('V1KER','V1PRED','V1BAND','V2','V2P','V4','QA')}
    ur=np.c_[truth[:,0]-anc[0],truth[:,1]-anc[1]];ur/=np.linalg.norm(ur,axis=1,keepdims=True);ut=np.c_[-ur[:,1],ur[:,0]]
    base0={'case':case,'route':case[:2],'bias':bias,'uses_gt':True}
    for arm in ARMS:
        g_=lambda k:Z[f'{arm}__{k}']
        F,G,K,H,R,acc=g_('F'),g_('G'),g_('K'),g_('H'),g_('R'),g_('acc').astype(bool)
        eps=g_('eps');es=eps[:,1];er=eps[:,0];g=H[:,1,2];Rs=R[:,1,1];dp=g_('dp')
        Wp,Wr=kernels(F,K,H,ev);row0={**base0,'arm':arm}
        # QA against the saved float32 kernels
        sel=np.searchsorted(ev_all,ev);qa=float(np.max(np.abs(Wp-Z[f'{arm}__Wpol'][sel].astype(float))))
        out['QA'].append({**row0,'check':'kernel_vs_saved_float32','value':qa})
        c=Wp@es                                                    # pol heading component at ev
        ti=int(ev[len(ev)//2]);Sq=bias_lever(F,ti);errs=[]
        for k0 in (0,ti//2,ti-1):
            x=np.array([1e-3,1e-5])
            for j in range(k0+1,ti+1):x=F[j][2:4,2:4]@x
            errs.append(abs(x[0]-(1e-3-Sq[k0]*1e-5)))
        out['QA'].append({**row0,'check':'bias_lever_vs_propagation','value':float(max(errs))})
        # ---------------- V1 kernel representation
        ef_mod=[];ef_unm=[];cfit=np.zeros(len(ev));a_all=[];store=[]
        for e,ti in enumerate(ev):
            k=np.arange(ti+1);ok=acc[:ti+1]&(np.abs(g[:ti+1])>1e-9);age=t[ti]-t[k];S=bias_lever(F,ti)
            bi=np.searchsorted(AGE_EDGES[1:-1],age,side='right');B=np.zeros((ti+1,len(AGE_EDGES)-1));B[k,bi]=1.
            Xm=np.c_[B*(g[k]/Rs[k])[:,None],B*(g[k]*S/Rs[k])[:,None]];Xu=np.c_[B/Rs[k][:,None],B*(S/Rs[k])[:,None]]
            y=Wp[e,:ti+1];den=float(y@y)
            cm,*_=np.linalg.lstsq(Xm[ok],y[ok],rcond=None);cu,*_=np.linalg.lstsq(Xu[ok],y[ok],rcond=None)
            yhm=np.where(ok,Xm@cm,0.);yhu=np.where(ok,Xu@cu,0.)
            ef_mod.append(1-float((y-yhm)@(y-yhm))/den if den>0 else np.nan);ef_unm.append(1-float((y-yhu)@(y-yhu))/den if den>0 else np.nan)
            cfit[e]=float(yhm@es[:ti+1]);store.append((Xm[ok],Xu[ok],y[ok],den))
            nb=B.shape[1];a=np.where(ok,B@cm[:nb]+(B@cm[nb:])*S,0.);a_all.append(a)   # W ~ a * g/R
        efs={}
        for nm,ix in (('modulated',0),('unmodulated',1)):
            efs[nm]=shared_shape_ef([(st[ix],st[2],st[3]) for st in store])
        out['V1KER'].append({**row0,'n_ev':len(ev),'EF_shared_shape_modulated':efs['modulated'],'EF_shared_shape_unmodulated':efs['unmodulated'],'EF_modulated_median':float(np.nanmedian(ef_mod)),'EF_unmodulated_median':float(np.nanmedian(ef_unm)),
                             'EF_modulated_p10':float(np.nanquantile(ef_mod,.1)),'EF_unmodulated_p10':float(np.nanquantile(ef_unm,.1)),
                             'n_params_each':2*(len(AGE_EDGES)-1)})
        def r2(y,x):
            if np.std(x)==0 or np.std(y)==0:return np.nan,np.nan
            b=np.polyfit(x,y,1);res=y-np.polyval(b,x);return float(1-np.var(res)/np.var(y)),float(b[0])
        pr={**row0,'c_rms_deg':DEG*float(np.sqrt(np.mean(c**2))),'sum_abs_Wpol_median':float(np.median(np.abs(Wp).sum(1))),
            'sum_abs_Wrng_median':float(np.median(np.abs(Wr).sum(1)))}
        pr['R2_fitted_modulated_kernel'],_=r2(c,cfit)
        for T in WLS_WINDOWS:
            bp=np.zeros(len(ev))
            for e,ti in enumerate(ev):
                mk=acc[:ti+1]&(t[:ti+1]>t[ti]-T);den=float(np.sum(g[:ti+1][mk]**2/Rs[:ti+1][mk]))
                bp[e]=float(np.sum(g[:ti+1][mk]*es[:ti+1][mk]/Rs[:ti+1][mk]))/den if den>0 else 0.
            pr[f'R2_bpsi_{int(T)}s'],pr[f'slope_bpsi_{int(T)}s']=r2(c,bp)
        Be=bands(es,t);u=np.where(acc,g*es/Rs,0.);Bu=bands(u,t);tot=float(np.mean(c**2));totf=float(np.mean(cfit**2))
        for bn in BANDS:
            ce=Wp@Be[bn];cu=np.array([float(a_all[e]@Bu[bn][:ti+1]) for e,ti in enumerate(ev)])
            out['V1BAND'].append({**row0,'band':bn,'share_eps_through_W':float(np.mean(ce*c)/tot) if tot>0 else np.nan,
                                  'share_u_through_fitted_a':float(np.mean(cu*cfit)/totf) if totf>0 else np.nan})
        out['V1PRED'].append(pr)
        # ---------------- V2 pol-only GLS (true positions, true slope) and the EKF pol component
        if arm!='ORACLE':
            Rmean=float(np.mean(Rs[acc]))
            qcum=np.cumsum((Q_GYRO*np.r_[np.diff(t),0.])[::-1])[::-1]        # qcum[k] = sum_{j>=k+1} q_j
            for src,par in (('crossfit',par_x[arm]['pol']),('insample',par_in[arm]['pol']),('crossfit_empirical',par_x[arm]['pol'])):
                for T in (V2_WINDOWS if src!='crossfit_empirical' else [w for w in V2_WINDOWS if w<=120.]):
                    rec={k:[] for k in ('gls','gls_const','wls','ekf')};exp={k:[] for k in ('white','gls','gls_const','ekf')}
                    for ti in ev2:
                        mk=acc[:ti+1]&(t[:ti+1]>t[ti]-T);k=np.where(mk)[0]
                        if len(k)<10:continue
                        S=bias_lever(F,ti)[k];gk=g_gt[k];A=np.c_[gk,gk*S]
                        Ge=gamma_empirical(par,t[k]) if src=='crossfit_empirical' else gamma_matrix(par,t[k],Rs[k],Rmean)
                        qk=qcum[k]-qcum[ti];Gg=np.outer(gk,gk)*np.minimum.outer(qk,qk)   # gyro random walk between t_k and t
                        pri=np.diag([0.,1/BIAS_STD**2]);y=es[k];cf=chol(Ge+Gg)
                        C,xh,_=gls(A,cf,y,pri);rec['gls'].append(xh[0]);exp['gls'].append(C[0,0])
                        Ac=np.c_[A,np.ones(len(k))];Cc,xc,_=gls(Ac,cf,y,np.diag([0.,1/BIAS_STD**2,0.]));rec['gls_const'].append(xc[0]);exp['gls_const'].append(Cc[0,0])
                        Cw,xw,_=gls(A,Rs[k].copy(),y,pri);rec['wls'].append(xw[0]);exp['white'].append(Cw[0,0])
                        kk=np.where(acc[:ti+1])[0];e_=int(np.where(ev==ti)[0][0]);w=Wp[e_,kk]
                        rec['ekf'].append(c[e_]);exp['ekf'].append(float(w@gamma_matrix(par,t[kk],Rs[kk],Rmean)@w))
                    if not rec['gls']:continue
                    row={**row0,'gamma_source':src,'window_s':T,'n_ev':len(rec['gls'])}
                    for kname,v in rec.items():row[f'realized_rmse_{kname}_deg']=DEG*float(np.sqrt(np.mean(np.square(v))))
                    for kname,v in exp.items():row[f'expected_sd_{kname}_deg']=DEG*float(np.sqrt(np.mean(v)))
                    # NOT a headroom: the EKF pol component is shaped by range/odom too; the comparable counterfactual is V2'
                    row['ekf_pol_part_over_polonly_gls']=row['realized_rmse_ekf_deg']/max(row['realized_rmse_gls_deg'],1e-12)
                    out['V2'].append(row)
        # ---------------- V2' correlated-noise filter counterfactual
        kap=(job['kappa'].get(arm) if arm in ('WIDE_NOES','PWIDE_NOES') else np.ones(n)) if has_kappa else None
        for variant in V2P_VARIANTS:
            if arm=='ORACLE' and variant['pol']:continue
            if variant.get('eff') and kap is None:continue
            for src,pars in (('crossfit',par_x[arm]),('insample',par_in[arm])):
                if (variant['name']=='base' or variant.get('eff')) and src=='insample':continue
                res=aug_filter(Z,arm,variant,pars,kap)
                if variant.get('eff')=='phys_gain':
                    out['QA'].append({**row0,'check':'x2_physgain_state_vs_saved_maxabs_rad','value':float(np.max(np.abs(res['d'][:,2]-dp[:,2])))})
                if variant['name']=='base':
                    out['QA'].append({**row0,'check':'v2p_base_gain_maxabs','value':res['gain_err']})
                    out['QA'].append({**row0,'check':'v2p_base_state_maxabs','value':float(np.max(np.abs(res['d'][:,:4]-dp)))})
                m=t>=30;eh=res['d'][m,2];ep=res['d'][m,:2]
                rt=np.sum(ep*ut[m],1);rr=np.sum(ep*ur[m],1)
                out['V2P'].append({**row0,'variant':variant['name'],'gamma_source':src,'heading_rmse_deg':DEG*float(np.sqrt(np.mean(eh**2))),
                    'heading_bias_deg':DEG*float(eh.mean()),'heading_nees':float(np.mean(eh**2/res['Ppsi'][m])),
                    'tangential_rmse_cm':100*float(np.sqrt(np.mean(rt**2))),'radial_rmse_cm':100*float(np.sqrt(np.mean(rr**2))),
                    'saved_heading_rmse_deg':DEG*float(np.sqrt(np.mean(dp[m,2]**2)))})
        # ---------------- V4 excitation
        if arm!='ORACLE':
            par=par_x[arm]['pol'];Rmean=float(np.mean(Rs[acc]))
            for e0 in range(0,n,max(1,int(round(10/float(np.median(np.diff(t))))))):
                mk=(t>=t[e0])&(t<t[e0]+60.)&acc;k=np.where(mk)[0]
                if len(k)<30 or t[e0]+60.>t[-1]:continue
                gk=g_gt[k];Ge=gamma_matrix(par,t[k],Rs[k],Rmean);iw=float(np.sum(gk**2/Rs[k]));ic=float(gk@cho_solve(chol(Ge),gk))
                sg=np.sign(gk);out['V4'].append({**row0,'t0':float(t[e0]),'g_mean':float(gk.mean()),'g_sd':float(gk.std()),
                    'g_abs_median':float(np.median(np.abs(gk))),'g_sign_changes':int(np.sum(sg[1:]*sg[:-1]<0)),
                    'eta_info_retention':ic/iw if iw>0 else np.nan,'corr_slow_eps_vs_g':float(np.corrcoef(ma(es,t,30.)[k],gk)[0,1]) if gk.std()>0 else np.nan})
    return out

# ----------------------------------------------------------------------------- V2' augmented linear filter
V2P_VARIANTS=[
    {'name':'base','pol':(),'rng':(),'consider':False},
    {'name':'pol_ar','pol':('a',),'rng':(),'consider':False},
    {'name':'pol_slow','pol':('b','c'),'rng':(),'consider':False},
    {'name':'pol_full','pol':('a','b','c'),'rng':(),'consider':False},
    {'name':'pol_full_consider','pol':('a','b','c'),'rng':(),'consider':True},
    {'name':'rng_full','pol':(),'rng':('a','b','c'),'consider':False},
    {'name':'both_full','pol':('a','b','c'),'rng':('a','b','c'),'consider':False},
    {'name':'both_full_consider','pol':('a','b','c'),'rng':('a','b','c'),'consider':True},
    {'name':'both_full_xcorr','pol':('a','b','c'),'rng':('a','b','c'),'consider':False,'xcorr':True},
    # X2: d0 feedback as an effective slope kappa*H_s (kappa from the P4 innovation curves), c2 removed from the input
    {'name':'x2_eff_physgain','pol':(),'rng':(),'consider':False,'eff':'phys_gain'},
    {'name':'x2_eff_effgain','pol':(),'rng':(),'consider':False,'eff':'eff_gain'},
]

def aug_filter(Z,arm,variant,pars,kappa=None):
    """Linear filter on the saved linearization (F, G, H, accept mask) with nuisance states; realized inputs from v3.
    Error recursion: d- = Phi d+ + [G w + r_pred; 0];  nu = eps + r_meas - H dx- - D n-;  d+ = d- + K nu (accepted only)."""
    g_=lambda k:Z[f'{arm}__{k}'];t=Z['t']
    F,G,K0,H,R0,acc=g_('F'),g_('G'),g_('K'),g_('H'),g_('R'),g_('acc').astype(bool)
    eps,w,rp,rm,dm=g_('eps'),g_('w'),g_('r_pred'),g_('r_meas'),g_('dm');n=len(t)
    eff=variant.get('eff')
    if eff:
        assert kappa is not None and len(kappa)==n
        eps=eps.copy();eps[:,1]=g_('c1')                  # c2 = ehat_gt - ehat ~ beta H d-: modelled through kappa instead
    nu_names=[('pol',s) for s in variant['pol']]+[('rng',s) for s in variant['rng']];m=len(nu_names);N=4+m
    chan={'rng':0,'pol':1};phi=np.ones(m);qn=np.zeros(m);p0=np.zeros(m);D=np.zeros((2,m))
    for i,(ch,s) in enumerate(nu_names):
        p=pars[ch];D[chan[ch],i]=1.
        if s=='a':p0[i]=p['sa2']
        elif s=='b':p0[i]=p['sb2']
        else:p0[i]=p['s02']
    white={}
    for ch in ('rng','pol'):
        idx=chan[ch];Rm=float(np.mean(R0[acc,idx,idx]))
        white[ch]=(pars[ch]['sw2']/Rm) if (ch=='pol' and variant['pol']) or (ch=='rng' and variant['rng']) else None
    P=np.zeros((N,N));P[:4,:4]=np.diag(np.r_[INIT_STD**2,BIAS_STD**2]);P[4:,4:]=np.diag(p0)
    pairs=[]
    if variant.get('xcorr'):
        rho=float(np.clip(pars['pol'].get('xcorr_slow',0.),-.95,.95))
        for i,(ch,s_) in enumerate(nu_names):
            if ch=='pol' and s_ in ('b','c'):
                j=nu_names.index(('rng',s_));pairs.append((i,j,rho));P[4+i,4+j]=P[4+j,4+i]=rho*math.sqrt(p0[i]*p0[j])
    d=np.zeros(N);out=np.zeros((n,N));Ppsi=np.zeros(n);gerr=0.;cons=variant['consider']
    for k in range(n):
        if k==0:
            dmk=np.zeros(N);dmk[:4]=dm[0]
        else:
            dt=-float(F[k][2,3]);Phi=np.eye(N);Phi[:4,:4]=F[k]
            for i,(ch,s) in enumerate(nu_names):
                p=pars[ch]
                if s=='a':phi[i]=p['rho']**(dt/p['dt']);qn[i]=p['sa2']*(1-phi[i]**2)
                elif s=='b':phi[i]=math.exp(-dt/p['tau_b']);qn[i]=p['sb2']*(1-phi[i]**2)
                else:phi[i]=1.;qn[i]=0.
                Phi[4+i,4+i]=phi[i]
            ds=float(np.linalg.norm(F[k][:2,2]))/max(float(np.linalg.norm(G[k][:2,0])),1e-300)
            Q=np.zeros((N,N));Q[:4,:4]=G[k]@np.diag([Q_ODOM*abs(ds),Q_GYRO*dt,0.])@G[k].T;Q[4:,4:]=np.diag(qn)
            for i,j,rho in pairs:Q[4+i,4+j]=Q[4+j,4+i]=rho*math.sqrt(qn[i]*qn[j])
            P=Phi@P@Phi.T+Q;P=.5*(P+P.T)
            dmk=Phi@d;dmk[:4]+=G[k][:,0]*w[k,0]+G[k][:,1]*w[k,1]+rp[k]
        Ht=np.c_[H[k],D];Rk=R0[k].copy();Htrue=Ht
        if eff:
            Htrue=Ht.copy();Htrue[1,:4]*=kappa[k]
            if eff=='eff_gain':Ht=Htrue
        for ch in ('rng','pol'):
            if white[ch] is not None:i=chan[ch];Rk[i,i]=white[ch]*R0[k,i,i]
        if acc[k]:
            S=Ht@P@Ht.T+Rk;S=.5*(S+S.T);Kt=np.linalg.solve(S,Ht@P).T
            if cons and m:Kt[4:]=0.
            if not m and not eff:gerr=max(gerr,float(np.max(np.abs(Kt-K0[k]))))
            A=np.eye(N)-Kt@Ht;P=A@P@A.T+Kt@Rk@Kt.T;P=.5*(P+P.T)
            nu=eps[k]+rm[k]-Htrue[:,:4]@dmk[:4]-D@dmk[4:];d=dmk+Kt@nu
        else:
            d=dmk
            if not m:gerr=max(gerr,float(np.max(np.abs(K0[k]))))        # saved K is 0 for rejected packets
        out[k]=d;Ppsi[k]=P[2,2]
    return {'d':out,'Ppsi':Ppsi,'gain_err':gerr}

# ----------------------------------------------------------------------------- driver
def write_manifest(path,args,inputs,outputs):
    import hashlib, datetime, subprocess
    try:commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,cwd=HERE).stdout.strip()
    except Exception:commit=''
    sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
    Path(path).write_text(json.dumps({'script':Path(__file__).name,'script_sha256':sha(__file__),'git_commit':commit,'argv':sys.argv,'args':args,
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':[{'path':str(f),'sha256':sha(f)} for f in inputs],'outputs':outputs},indent=2,default=str))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--workers',type=int,default=4);ap.add_argument('--kappa',default=None,help='dir with *_D0FB_CURVE_ARRAYS.npz (P4) for X2');ap.add_argument('--no-ffd',action='store_true',help='test mode: g_gt = saved prior slope')
    a=ap.parse_args();fs=sorted(glob.glob(str(Path(a.input)/'**'/'*_EB3_ARRAYS.npz'),recursive=True));assert len(fs)==14,len(fs)
    dst=Path(a.out);dst.mkdir(parents=True,exist_ok=True)
    if not a.no_ffd:
        from p2_replay import V
        model=V.SourceFFD();cases={c['id']:c for c in V.MANIFEST['cases']}
    # pass 1: true slopes, autocovariances
    GT={};ACF={};meta={};XC={}
    for f in fs:
        case,bias=stem_parts(f);Z=np.load(f);t=Z['t'];truth=Z['truth'];dt=float(np.median(np.diff(t)))
        meta[(case,bias)]={'dt':dt,'dt_spread':float(np.max(np.abs(np.diff(t)-dt))),'n':len(t)}
        if a.no_ffd:
            GT[(case,bias)]={'g':Z['BASE__H'][:,1,2].copy(),'h_err':0.};anc=np.r_[0.,0.,2.]
        else:
            hr=[model.batch(np.c_[truth[i:i+32,:3],np.zeros(len(truth[i:i+32]))],cases[case],gradient=True) for i in range(0,len(t),32)]
            hg=np.concatenate([r[0] for r in hr]);Hg=np.concatenate([r[1] for r in hr])
            GT[(case,bias)]={'g':Hg[:,1,2],'h_err':float(np.max(np.abs(hg-Z['hgt'])))}
        maxlag=int(round(150/dt))
        for arm in ARMS:
            e=Z[f'{arm}__eps'];a1=ma(e[:,0],t,30.);a2=ma(e[:,1],t,30.)
            XC[(case,bias,arm)]=float(np.corrcoef(a1,a2)[0,1]) if a1.std()>0 and a2.std()>0 else 0.
            for ch,i in (('rng',0),('pol',1)):ACF[(case,bias,arm,ch)]=(autocov(e[:,i],maxlag),dt,len(t))
    anchors={c:(np.asarray(cases[c]['anchor'],float) if not a.no_ffd else np.r_[0.,0.,2.]) for c in {stem_parts(f)[0] for f in fs}}
    # parameter fits: in-sample per case, cross-fit pooled over the other routes (B0 only, n-weighted)
    PAR_IN={};PAR_X={};prow=[]
    for f in fs:
        case,bias=stem_parts(f);rt=case[:2];PAR_IN[(case,bias)]={};PAR_X[(case,bias)]={}
        for arm in ARMS:
            PAR_IN[(case,bias)][arm]={};PAR_X[(case,bias)][arm]={}
            for ch in ('rng','pol'):
                g0,dt,_=ACF[(case,bias,arm,ch)];pin=fit_gamma(g0,dt)
                others=[k for k in ACF if k[2]==arm and k[3]==ch and k[1]=='B0' and k[0][:2]!=rt]
                assert others and all(k[0][:2]!=rt for k in others),('CROSSFIT_LEAK',case,arm,ch)
                L=min(len(ACF[k][0]) for k in others);wts=np.array([ACF[k][2] for k in others],float)
                gp=np.sum([ACF[k][0][:L]*wv for k,wv in zip(others,wts)],0)/wts.sum();px=fit_gamma(gp,dt)
                px['fit_routes']=sorted({k[0][:2] for k in others});pin['fit_routes']=[rt];px['emp']=gp;pin['emp']=g0
                px['xcorr_slow']=float(np.average([XC[(k[0],k[1],arm)] for k in others],weights=wts));pin['xcorr_slow']=XC[(case,bias,arm)]
                PAR_IN[(case,bias)][arm][ch]=pin;PAR_X[(case,bias)][arm][ch]=px
                for src,p in (('insample',pin),('crossfit',px)):prow.append({'case':case,'bias':bias,'arm':arm,'channel':ch,'source':src,**{k:v for k,v in p.items() if k not in ('fit_routes','emp')},'fit_routes':'+'.join(p['fit_routes'])})
    pd.DataFrame(prow).to_csv(dst/'SYS_GAMMA_PARAMS.csv',index=False)
    KAP={}
    if a.kappa:
        for f in fs:
            case,bias=stem_parts(f);cf=sorted(Path(a.kappa).rglob(f'{case}_D0FB_CURVE_ARRAYS.npz'))
            if not cf:continue
            C=np.load(cf[0]);gr=C['heading__grid'];ip=int(np.where(gr==1.)[0][0]);im=int(np.where(gr==-1.)[0][0]);tt=np.load(f)['t']
            dd=C['heading__d0'][:,ip]-C['heading__d0'][:,im];KAP[(case,bias)]={}
            for arm,key in (('PWIDE_NOES','heading__eP'),('WIDE_NOES','heading__eW')):
                de=C[key][:,ip]-C[key][:,im];kap=np.where(np.abs(dd)>1e-6,1-de/np.where(np.abs(dd)>1e-6,dd,1.),1.)
                KAP[(case,bias)][arm]=np.interp(tt,C['t'],kap)
    jobs=[{'file':f,'par_cross':PAR_X[stem_parts(f)],'par_in':PAR_IN[stem_parts(f)],'gt':GT[stem_parts(f)],'anchor':anchors[stem_parts(f)[0]],
           'kappa':KAP.get(stem_parts(f),{})} for f in fs]
    T={}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for o in ex.map(analyse_case,jobs):
            for k,v in o.items():T.setdefault(k,[]).extend(v)
    # V6' mount comparison (R2_aA_m0 vs R2_aA_m45, B0) and V7 revisits
    v6=[];v7=[]
    byk={stem_parts(f):f for f in fs}
    if ('R2_aA_m0','B0') in byk and ('R2_aA_m45','B0') in byk:
        A0=np.load(byk[('R2_aA_m0','B0')]);A4=np.load(byk[('R2_aA_m45','B0')])
        same=bool(A0['truth'].shape==A4['truth'].shape and np.max(np.abs(A0['truth'][:,:2]-A4['truth'][:,:2]))<1e-9)
        if same:
            t=A0['t'];e0=A0['ORACLE__ehat'];e4=A4['ORACLE__ehat'];g0=GT[('R2_aA_m0','B0')]['g'];g4=GT[('R2_aA_m45','B0')]['g']
            for nm,x0,x4 in (('e_raw',e0,e4),('e_slow30',ma(e0,t,30.),ma(e4,t,30.)),('e_fast3',e0-ma(e0,t,3.),e4-ma(e4,t,3.)),('g_true',g0,g4)):
                v6.append({'pair':'R2_aA_m0 vs R2_aA_m45','quantity':nm,'corr':float(np.corrcoef(x0,x4)[0,1]),'rms_m0':float(np.sqrt(np.mean(x0**2))),
                           'rms_m45':float(np.sqrt(np.mean(x4**2))),'mean_m0':float(x0.mean()),'mean_m45':float(x4.mean())})
        else:v6.append({'pair':'R2_aA_m0 vs R2_aA_m45','quantity':'SKIPPED_TRUTH_DIFFERS'})
    for f in fs:
        case,bias=stem_parts(f)
        if bias!='B0':continue
        Z=np.load(f);t=Z['t'];tr=Z['truth'];tree=cKDTree(tr[:,:2]);allp=np.array(sorted(tree.query_pairs(0.05)),dtype=int).reshape(-1,2)
        dpsi=np.abs(np.angle(np.exp(1j*(tr[allp[:,0],2]-tr[allp[:,1],2]))));dtt=np.abs(t[allp[:,0]]-t[allp[:,1]])
        keep=(dpsi<math.radians(5))&(dtt>20);pairs=allp[keep];dtt=dtt[keep]
        for arm in ARMS:
            x=Z['ORACLE__ehat'] if arm=='ORACLE' else Z[f'{arm}__eps'][:,1];lab='e_raw' if arm=='ORACLE' else 'eps_pol'
            if not len(pairs):v7.append({'case':case,'arm':arm,'signal':lab,'dt_bin':'all','n_pairs':0});continue
            for lo,hi in ((20,60),(60,120),(120,1e9),(20,1e9)):
                mk=(dtt>=lo)&(dtt<hi);p=pairs[mk]
                v7.append({'case':case,'arm':arm,'signal':lab,'dt_bin':f'{lo}-{hi if hi<1e9 else "inf"}','n_pairs':int(len(p)),
                           'corr':float(np.corrcoef(x[p[:,0]],x[p[:,1]])[0,1]) if len(p)>5 else np.nan})
    T['V6']=v6;T['V7']=v7
    for k,v in T.items():pd.DataFrame(v).to_csv(dst/f'SYS_{k}.csv',index=False)
    qa={'n_files':len(fs),'kernel_vs_saved_max':max([r['value'] for r in T['QA'] if r['check']=='kernel_vs_saved_float32'],default=np.nan),
        'v2p_base_gain_max':max([r['value'] for r in T['QA'] if r['check']=='v2p_base_gain_maxabs'],default=np.nan),
        'v2p_base_state_max':max([r['value'] for r in T['QA'] if r['check']=='v2p_base_state_maxabs'],default=np.nan),
        'h_gt_vs_saved_max':max(v['h_err'] for v in GT.values()),'dt_spread_max':max(v['dt_spread'] for v in meta.values())}
    (dst/'SYS_QA.json').write_text(json.dumps(qa,indent=2,default=float))
    write_manifest(dst/'SYS_STAGE1_MANIFEST.json',vars(a),fs+sorted(str(x) for x in Path(a.kappa).rglob('*_D0FB_CURVE_ARRAYS.npz')) if a.kappa else fs,sorted(str(x) for x in dst.glob('SYS_*')))
    assert qa['v2p_base_state_max']<1e-8,('V2P_BASE_CLOSURE_FAIL',qa)
    print('SYSDIAG_PASS '+json.dumps(qa,default=float),flush=True)

if __name__=='__main__':main()
