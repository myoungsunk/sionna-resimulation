#!/usr/bin/env python3
"""Offline Δs latent-polarization-bias conditional-information audit.

This is intentionally NOT an EKF correction algorithm: no posterior updates are fed
back, no GT is used at online estimation time.  Ground truth is used only as an
OFFLINE label to score how much the newly observed CIR shape can constrain the
unobserved polarization bias.  Baseline P^- is frozen E1 EXDS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from collections import Counter

import numpy as np
import pandas as pd

ROOT_COMMIT = '16eb9521e19f04fd75bdeb02abd4cc687debb944'
CASE_IDS = ('R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')
STEP = (0.002,0.002,math.radians(0.10))
OFFSETS = (1, 2, 4)


def jdump(obj,path):
    path=Path(path)
    def conv(z):
        if isinstance(z,(np.integer,)):return int(z)
        if isinstance(z,(np.floating,)):return float(z)
        if isinstance(z,(np.bool_,)):return bool(z)
        if isinstance(z,Path):return str(z)
        if isinstance(z,np.ndarray):return z.tolist()
        raise TypeError(type(z).__name__)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=conv,allow_nan=False)+'\n',encoding='utf-8')


def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def source_path(root,p):
    path=(Path(root)/p).resolve()
    if not path.is_file():raise FileNotFoundError('FROZEN_RF_INPUT_MISSING: '+str(path))
    if path.open('rb').read(120).startswith(b'version https://git-lfs.github.com'):
        raise RuntimeError('GIT_LFS_POINTER_NOT_REAL_RF: '+str(path))
    return path


def spectrum_to_shape(h,window,offsets=OFFSETS,tap_lock=None):
    """Original 30%-leading-edge, stronger-peak-port, Hann+4x-FFT.
    h has [packet, freq, two_rx]; no input from GT or model is assumed.
    tap_lock (for FD only) fixes the reference tap, never the rf detector.
    """
    h=np.asarray(h,np.complex128)
    if h.ndim!=3 or h.shape[2]!=2 or h.shape[1]!=len(window):
        raise ValueError('Expected [N,257,2] complex channels')
    n,nf,_=h.shape
    cir=np.fft.ifft(h*window[None,:,None],n=4*nf,axis=1)*nf
    amps=np.abs(cir)
    ii=np.arange(n)
    p=amps.max(axis=1).argmax(axis=1)
    strong=amps[ii,:,p]
    detected=(strong>=.30*strong.max(axis=1)[:,None]).argmax(axis=1)
    tap=detected if tap_lock is None else np.asarray(tap_lock,int)
    if np.any(tap<0) or np.any(tap+max(offsets)>=4*nf):
        raise RuntimeError('TAP_INDEX_OUT_OF_BOUNDS')
    def scat(offset):
        pow=np.abs(cir[ii,tap+offset,:])**2
        den=pow.sum(axis=1)
        if np.any(den<=0):raise RuntimeError('NO_POWER_AT_TAP')
        return (pow[:,0]-pow[:,1])/den
    s0=scat(0)
    return s0,np.column_stack([scat(o)-s0 for o in offsets]),detected


def centered_time_mean(t,v,window_s=5.0):
    t=np.asarray(t,float);v=np.asarray(v,float)
    if len(t)!=len(v) or np.any(np.diff(t)<=0):raise ValueError('non-monotonic time/shape')
    left=np.searchsorted(t,t-window_s/2-1e-10,side='left')
    right=np.searchsorted(t,t+window_s/2+1e-10,side='right')
    sums=np.r_[0,np.cumsum(v)]
    return (sums[right]-sums[left])/(right-left)


def route_case_weights(case_ids,routes):
    """Equal route weight; within each route equal case and each case equal packet weight."""
    cid=np.asarray(case_ids);routes=np.asarray(routes)
    rset=np.unique(routes)
    w=np.zeros(len(cid))
    for r in rset:
        cset=np.unique(cid[routes==r])
        for c in cset:
            flag=(cid==c)&(routes==r)
            w[flag]=1/(len(rset)*len(cset)*flag.sum())
    assert abs(w.sum()-1)<1e-10
    return w


def wavg(x,w):return float(np.sum(np.asarray(x)*w)/np.sum(w))


def wcov(x,w):
    """Population covariance under weights (case/route balanced), not a formal CI."""
    x=np.asarray(x,float)
    w=np.asarray(w,float)/np.sum(w)
    means=np.sum(x*w[:,None],axis=0)
    z=x-means
    return (z*w[:,None]).T@z, means


def stabilize_cov(cov,diag_rel_floor=1e-6,offdiag_scale=0.85):
    """Retain signed cross-covariance; prevent singular single-scene empirical R."""
    c=np.array(cov,float)
    if c.shape!=(3,3):raise ValueError('3x3 expected')
    c=(c+c.T)*0.5
    floor=max(float(np.max(np.diag(c))),1e-12)*diag_rel_floor
    c[np.diag_indices(3)]=np.maximum(np.diag(c),floor)
    c[np.triu_indices(3,1)]*=offdiag_scale
    c[np.tril_indices(3,-1)]*=offdiag_scale
    lam=np.linalg.eigvalsh(c)
    if lam[0]<=floor:
        c+=np.eye(3)*(floor-lam[0]+1e-15)
    if not np.all(np.linalg.eigvalsh(c)>0):raise RuntimeError('SPD_COVARIANCE_FAILURE')
    return c


@dataclass
class Fold:
    route:str
    intercept:float
    slope:float
    sigma_bias2:float
    cov:np.ndarray
    n:int
    training_cases:list
    slope_ols_inverted:float
    mean_bias:float
    mean_delta:float
    cov_bias_delta:float
    var_delta:float


def fit_fold(df,held,feature='delta1',allow_lt30=False):
    rows=df[(df.route!=held)&(df.accepted)].copy()
    if len(rows)<30 or len(rows.route.unique())!=2:
        raise RuntimeError('LORO_REQUIRED_2_TRAIN_ROUTES: '+held)
    w=route_case_weights(rows.case.to_numpy(),rows.route.to_numpy())
    b=rows.bias_slow.to_numpy(float)
    delta=rows[feature].to_numpy(float)
    bc,mm=wcov(np.column_stack([b,delta]),w)
    sigma_b2=max(float(bc[0,0]),1e-9)
    slope=float(bc[0,1]/sigma_b2)
    intercept=float(mm[1]-slope*mm[0])
    eps_s=rows.e_s.to_numpy(float)-b
    eps_d=delta-(intercept+slope*b)
    residuals=np.column_stack([rows.e_r.to_numpy(float),eps_s,eps_d])
    rc,rm=wcov(residuals,w)
    R=stabilize_cov(rc)
    return Fold(held,intercept,slope,sigma_b2,R,len(rows),sorted(rows.case.unique().tolist()),
                float(bc[0,1]/max(bc[1,1],1e-9)),float(mm[0]),float(mm[1]),float(bc[0,1]),float(bc[1,1]))


def info_update(P,H,R):
    P=(np.asarray(P,float)+np.asarray(P,float).T)*0.5
    H=np.asarray(H,float);R=np.asarray(R,float)
    S=H@P@H.T+R
    try:K=np.linalg.solve(S,H@P).T
    except np.linalg.LinAlgError as e:raise RuntimeError('INNOVATION_NOT_SPD') from e
    A=np.eye(len(P))-K@H
    pp=A@P@A.T+K@R@K.T
    pp=(pp+pp.T)*0.5
    return pp


def conditional_info(P,H2,H3,R3):
    """Full 5D P prior contains XY, heading, gyro-bias, latent s-bias.
    2-channel [range,s] R2 is the principal submatrix of same empirical R3.
    All comparisons use an IDENTICAL prior and all off-diagonal covariances.
    """
    R3=np.asarray(R3,float)
    p2=info_update(P,H2,R3[:2,:2]);p3=info_update(P,H3,R3)
    v2=float(p2[2,2]);v3=float(p3[2,2])
    if min(v2,v3)<=0:raise RuntimeError('NONPOSITIVE_POSTERIOR_VAR')
    if v3>v2+1e-8*max(v2,v3):
        raise RuntimeError(f'INFORMATION_MONOTONICITY_FAIL: {v3}>{v2}')
    return {'sigma2_deg':float(np.degrees(np.sqrt(v2))),
            'sigma3_deg':float(np.degrees(np.sqrt(v3))),
            'psi_info_gain_abs_rad2':float(1/v3-1/v2),
            'psi_info_gain_fraction':float(1-v3/v2),
            'relative_precision_gain':float(v2/v3-1)}


def true_case(ctx,d,derivative=True):
    """Extract native Full first path and SourceFFD LoS shape; align on pose_id.
    GT is used exclusively to label bias, not to choose the frozen prior.
    """
    source=ctx.cfg.source_root
    raw_file=source_path(source,d.case['full_path'])
    ids_file=source_path(source,d.case['samples_path'])
    raw_ids=pd.DataFrame(json.loads(ids_file.read_text()))['pose_id'].to_numpy()
    ix=pd.Index(raw_ids).get_indexer(d.ids)
    if np.any(ix<0) or len(np.unique(ix))!=len(ix):raise RuntimeError('ORIGINAL_POSE_ID_ALIGNMENT_FAIL')
    rf=np.load(raw_file,mmap_mode='r',allow_pickle=False)
    if rf.ndim!=4 or rf.shape[2:]!=(2,2) or rf.shape[1]!=257 or len(raw_ids)!=rf.shape[0]:
        raise RuntimeError(f'ORIGINAL_FULL_RF_SHAPE_WRONG {rf.shape}')
    model=ctx.model
    nf=len(model.freqs)
    if nf!=257 or nf!=rf.shape[1]:raise RuntimeError('SOURCE_BANK_FREQ_MISMATCH')
    win=np.asarray(model.window,float)
    total=len(d.t)
    full=np.empty((total,3),float)
    los=np.empty((total,3),float)
    hgt=np.empty((total,2),float)
    for start in range(0,total,32):
        end=min(total,start+32)
        H=np.asarray(rf[ix[start:end],:,:,0],np.complex128)
        s0,ds,tap=spectrum_to_shape(H,win)
        full[start:end]=ds
        if np.max(np.abs(s0-d.z[start:end,1]))>1e-9:
            raise RuntimeError(f'NATIVE_FP_S_VS_E1_PARITY_FAIL_{d.key}')
        states=d.truth[start:end]
        a,_,_,_,_,_=model.spectrum(states,d.case,gradient=False)
        ms0,md,_=spectrum_to_shape(a,win)
        los[start:end]=md
        predict,_=model.batch(states,d.case,gradient=False)
        hgt[start:end]=predict
        if np.max(np.abs(predict[:,1]-ms0))>1e-8:
            raise RuntimeError(f'SOURCE_FFD_LOS_S_PARITY_FAIL_{d.key}')
    residual=full-los
    er=d.z[:,0]-hgt[:,0]-d.mu_exds
    es=d.z[:,1]-hgt[:,1]-d.mu_s
    bs=centered_time_mean(d.t,es,5.0)
    out=pd.DataFrame({'case':d.case['id'],'route':d.case['route'],'bias':'B0','t_s':d.t,
        'pose_id':d.ids,'accepted':d.mask,'e_r':er,'e_s':es,'bias_slow':bs,
        'delta1':residual[:,0],'delta2':residual[:,1],'delta4':residual[:,2],
        'raw_delta1':full[:,0],'los_delta1':los[:,0]})
    return out, hgt, full, los, {'full_rf':sha(raw_file),'pose_ids':sha(ids_file)}


def jacobians_at_prior(ctx,d):
    """Frozen EXDS E1 prior; Δs differentiates LoS shape at the SAME fixed tap.
    Detect nearby tap changes separately, avoid falsely smoothing transitions.
    """
    model=ctx.model
    states=np.asarray(d.ref['prior'][:,4,:],float)
    h,H=model.batch(states,d.case,gradient=True)
    if H.shape!=(len(d.t),2,4):raise RuntimeError('H_JAC_SHAPE')
    n=len(states)
    D=np.empty((n,3,3),float)
    unsafe=np.zeros(n,bool)
    for a in range(0,n,32):
        b=min(n,a+32)
        xx=states[a:b]
        base,_,_,_,_,_=model.spectrum(xx,d.case,gradient=False)
        _,_,tap=spectrum_to_shape(base,model.window)
        for col,dx in enumerate(STEP):
            plus=xx.copy();minus=xx.copy()
            plus[:,col]+=dx;minus[:,col]-=dx
            hp,_,_,_,_,_=model.spectrum(plus,d.case,gradient=False)
            hm,_,_,_,_,_=model.spectrum(minus,d.case,gradient=False)
            _,dp,tp=spectrum_to_shape(hp,model.window,tap_lock=tap)
            _,dm,tm=spectrum_to_shape(hm,model.window,tap_lock=tap)
            D[a:b,:,col]=(dp-dm)/(2*dx)
            unsafe[a:b]|=(tp!=tap)|(tm!=tap)
    assert np.isfinite(D).all()
    return H,D,unsafe


def evaluate_information(df,folds,h_jac,delta_jac,prior_cov,unstable):
    """Full-state local conditional-information diagnostic. GT used only in
    training labels & evaluation, not in prior state/Jacobians.
    """
    out=[]
    for c,fc in folds.items():
        part=df[df.case==c].reset_index(drop=True)
        H=h_jac[c];D=delta_jac[c];P4=prior_cov[c]
        if len(part)!=len(H):raise RuntimeError('ROW_MISALIGNMENT')
        for k,row in part.iterrows():
            if not row.accepted:continue
            if unstable[c][k]:continue
            P=np.zeros((5,5),float);P[:4,:4]=P4[k];P[4,4]=fc.sigma_bias2
            H2=np.zeros((2,5));H2[:,:4]=H[k];H2[1,4]=1.
            H3=np.vstack([H2,np.r_[D[k,0],0.,fc.slope]])
            vals=conditional_info(P,H2,H3,fc.cov)
            out.append({'case':c,'route':row.route,'t_s':row.t_s,'pose_id':int(row.pose_id),
                        'accepted':True,'slope':fc.slope,'sigma_b':math.sqrt(fc.sigma_bias2),
                        'eps_delta':row.delta1-fc.intercept-fc.slope*row.bias_slow,
                        's_bias_gt':row.bias_slow,**vals})
    return pd.DataFrame(out)



def var_failure_traces(ctx,d):
    """Replay the EXACT frozen MB and MB_VAR under the same fixed A_B mask.
    Also compute same-prior single-update counterfactuals to separate the
    immediate R-only gain effect from accumulated recursive prior divergence.
    Not a unique causal mediation decomposition of the full trajectory.
    """
    from dsreassess.engine import replay, score
    from dsreassess.numerics import wrap
    def infl(k,x,R,h,H):
        anc=np.asarray(d.case['anchor'],float)[:2]
        rho=float(np.linalg.norm(x[:2]-anc))
        sigma=float(np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]))
        out=np.array(R,float,copy=True)
        out[1,1]+=sigma*sigma
        return out
    off=replay(ctx,d,'MB_ORIG',mu_kind='EXDS')
    alt=replay(ctx,d,'MB_VAR',mu_kind='EXDS',R_rule=infl)
    for k,field in [('x','x'),('P','P'),('h','h'),('H','H'),('K','K'),('mu','mu'),('nu','nu'),('R','R')]:
        x=np.asarray(getattr(off,field))
        target=np.asarray(d.ref[field][:,4])
        error=float(np.max(np.abs(x-target)))
        if error>1e-10:raise AssertionError(f'ORIG_E1_PARITY_{d.key}_{field}: {error}')
    if not np.array_equal(off.acc,alt.acc) or not np.array_equal(alt.acc,d.mask):
        raise RuntimeError('VAR_MASK_CHANGED')
    if not np.allclose(alt.R[:,0,0],d.R[:,0,0],atol=1e-15,rtol=0):
        raise RuntimeError('VAR_RANGE_R_CHANGED')
    if not np.allclose(alt.R[:,1,1]-d.R[:,1,1],
            np.maximum(alt.R[:,1,1]-d.R[:,1,1],0),atol=1e-12,rtol=0):
        raise RuntimeError('VAR_S_R_NEGATIVE')
    rows=[]
    anc=np.asarray(d.case['anchor'],float)[:2]
    dist=np.linalg.norm(d.truth[:,:2]-anc,axis=1)
    for k in range(len(d.t)):
        if not d.mask[k]:continue
        xprior=off.prior[k];P=off.Pprior[k];H=off.H[k];v=off.nu[k]
        def getK(R):
            S=H@P@H.T+R
            return np.linalg.solve(S,H@P).T
        k0=getK(off.R[k]);k1=getK(alt.R[k])
        # Same-prior, same-innovation, same-accepted-packet arm comparison.
        ep=float(wrap(xprior[2]-d.truth[k,2]))
        u0=k0[2]@v;u1=k1[2]@v
        e0=float(wrap(ep+u0));e1=float(wrap(ep+u1))
        # Within-arm decomposition of *this one update*, not total future effect.
        r0=float(k0[2,0]*v[0]);s0=float(k0[2,1]*v[1])
        r1=float(k1[2,0]*v[0]);s1=float(k1[2,1]*v[1])
        gain_s_benefit_orig=float(wrap(ep+r0+s0)**2-wrap(ep+r0)**2)
        gain_s_benefit_var=float(wrap(ep+r1+s1)**2-wrap(ep+r1)**2)
        # Dynamic difference: each arm's own prior and Q/R recursion.
        psi_dyn=float(np.degrees(wrap(alt.x[k,2]-off.x[k,2])))
        xydyn=float(np.linalg.norm(alt.x[k,:2]-d.truth[k,:2])-
                    np.linalg.norm(off.x[k,:2]-d.truth[k,:2]))
        rr=float(dist[k]); zone='near' if rr<1.5 else ('mid' if rr<3 else 'far')
        rows.append({'case':d.case['id'],'bias':d.bias,'k':k,'t_s':d.t[k],
            'pose_id':int(d.ids[k]),'zone_gt':zone,'dist_gt_m':rr,
            'sigma_b_added':math.sqrt(alt.R[k,1,1]-off.R[k,1,1]),
            'nu_r_off':float(v[0]),'nu_s_off':float(v[1]),
            'H_s_psi_off':float(H[1,2]),
            'K_s_psi_orig':float(k0[2,1]),'K_s_psi_var_sameprior':float(k1[2,1]),
            'K_r_psi_orig':float(k0[2,0]),'K_r_psi_var_sameprior':float(k1[2,0]),
            'psi_prior_error_off_deg':math.degrees(ep),
            'sameprior_update_heading_error_orig_deg':math.degrees(e0),
            'sameprior_update_heading_error_var_deg':math.degrees(e1),
            'sameprior_delta_head_mse_deg2':math.degrees(1)**2*(e1*e1-e0*e0),
            'orig_s_contribution_head_mse_deg2':math.degrees(1)**2*gain_s_benefit_orig,
            'var_s_contribution_head_mse_deg2':math.degrees(1)**2*gain_s_benefit_var,
            'full_recursive_heading_gap_deg':psi_dyn,
            'full_recursive_XY_error_delta_m':xydyn})
    frame=pd.DataFrame(rows)
    original_score=score(d,off)
    var_score=score(d,alt)
    return frame,{'case':d.case['id'],'bias':d.bias,
        'n_accepted':len(frame),
        'original_heading_rmse':original_score['heading_rmse_deg'],
        'VAR_heading_rmse':var_score['heading_rmse_deg'],
        'original_XY_rmse_m':original_score['xy_rmse_m'],
        'VAR_XY_rmse_m':var_score['xy_rmse_m'],
        'n_harmful_sameprior':int((frame.sameprior_delta_head_mse_deg2>0).sum()),
        'n_helpful_sameprior':int((frame.sameprior_delta_head_mse_deg2<0).sum()),
        'sum_delta_heading_mse_sameprior_deg2':float(frame.sameprior_delta_head_mse_deg2.sum()),
        'sum_gain_s_orig_mse_deg2':float(frame.orig_s_contribution_head_mse_deg2.sum()),
        'sum_gain_s_var_mse_deg2':float(frame.var_s_contribution_head_mse_deg2.sum()),
        'n_scoring':int((d.t>=30).sum())}


def combine_case_frames(frames):
    df=pd.concat(frames,ignore_index=True)
    if len(df.case.unique())!=len(CASE_IDS):raise RuntimeError('MISSING_CASES')
    return df


def analyze_real(args):
    import importlib
    code_path=args.code_root.resolve()
    if not (code_path/'dsreassess/io.py').is_file():raise FileNotFoundError(f'BASELINE_CODE_NOT_FOUND {code_path}')
    # All implementation stays outside the original checkout.
    if str(code_path) not in sys.path:sys.path.insert(0,str(code_path))
    from dsreassess.io import Config,Context
    root=args.repo_root.resolve();out=args.output_root.resolve()
    if out.exists():raise FileExistsError(f'OUTPUT_ROOT_ALREADY_EXISTS: {out}')
    for parent in (root,args.source_root.resolve(),args.artifacts_root.resolve()):
        if out==parent or parent in out.parents:raise ValueError('OUTPUT_ROOT_MUST_BE_EXTERNAL')
    head=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',ROOT_COMMIT,head],check=True)
    out.mkdir(parents=True)
    cfg=Config(root,args.source_root.resolve(),args.artifacts_root.resolve(),out, cases=CASE_IDS,biases=('B0',),strict_source=True)
    try:
        ctx=Context(cfg)
        frames=[];var_rows=[];J={};D={};P4={};Unsafe={};digest={}
        for d in ctx.cases():
            print('[RAW]',d.key,flush=True)
            table,hgt,full,los,checksum=true_case(ctx,d)
            jac,djac,unstable=jacobians_at_prior(ctx,d)
            frames.append(table)
            var_frame,var_metrics=var_failure_traces(ctx,d)
            var_frame.to_csv(out/f'VAR_GAIN_TRACE_{d.case["id"]}_B0.csv.gz',index=False,compression='gzip',float_format='%.16g')
            var_rows.append(var_metrics)
            J[d.case['id']]=jac;D[d.case['id']]=djac
            P4[d.case['id']]=np.asarray(d.ref['Pprior'][:,4],float)
            Unsafe[d.case['id']]=unstable
            digest[d.case['id']]=checksum
            print('[PARITY]',d.key,'n',len(table),'unstable_J',int(unstable.sum()),flush=True)
        df=combine_case_frames(frames)
        # B0 only, not fake independent L0/L1/L2 RF copies.
        folds={route:fit_fold(df,route) for route in ('R2','R4','R5')}
        casefold={case:folds[case.split('_')[0]] for case in CASE_IDS}
        outtrain=[];held=[]
        for route,fold in folds.items():
            candidates=df[(df.route==route)&df.accepted]
            pred=fold.mean_bias+fold.slope_ols_inverted*(candidates.delta1.to_numpy()-fold.mean_delta)
            actual=candidates.bias_slow.to_numpy()
            for c in candidates.case.unique():
                m=candidates.case.to_numpy()==c
                bias=actual[m];pv=pred[m]
                var=float(np.mean((bias-bias.mean())**2));mse=float(np.mean((bias-pv)**2))
                held.append({'case':c,'held_route':route,'n':int(m.sum()),
                    'r2_bias_from_delta1':float(1-mse/max(var,1e-12)),
                    'rmse_bias_from_delta1':math.sqrt(mse),'rms_bias':math.sqrt(np.mean(bias*bias)),
                    'corr_bias_delta':float(np.corrcoef(bias,candidates.loc[m,'delta1'])[0,1])})
            outtrain.append({'held_route':route,'train_cases':','.join(fold.training_cases),'n_train':fold.n,
                'intercept_d':fold.intercept,'slope_d_per_bias':fold.slope,
                'sigma_bias':math.sqrt(fold.sigma_bias2),
                'rho_rs':float(fold.cov[0,1]/math.sqrt(fold.cov[0,0]*fold.cov[1,1])),
                'rho_rdelta':float(fold.cov[0,2]/math.sqrt(fold.cov[0,0]*fold.cov[2,2])),
                'rho_sdelta':float(fold.cov[1,2]/math.sqrt(fold.cov[1,1]*fold.cov[2,2])),
                'cov_R_rr':fold.cov[0,0],'cov_R_ss':fold.cov[1,1],
                'cov_R_dd':fold.cov[2,2],
                'cov_R_rs':fold.cov[0,1],'cov_R_rdelta':fold.cov[0,2],
                'cov_R_sdelta':fold.cov[1,2]})
        # Check the calibrated error model on the *unseen route* before
        # interpreting the mathematically nonnegative information increment.
        calibration=[]
        for route,F in folds.items():
            test=df[(df.route==route)&df.accepted].copy()
            noise=np.column_stack([test.e_r.to_numpy(float),
                 test.e_s.to_numpy(float)-test.bias_slow.to_numpy(float),
                 test.delta1.to_numpy(float)-(F.intercept+F.slope*test.bias_slow.to_numpy(float))])
            predicted=np.asarray(F.cov,float)
            whitened=np.einsum('ni,ij,nj->n',noise,np.linalg.inv(predicted),noise)
            for c in test.case.unique():
                m=test.case.to_numpy()==c
                cc=np.cov(noise[m].T)
                calibration.append({'case':c,'held_route':route,'n':int(m.sum()),
                    'empirical_joint_chisq_mean_3d':float(np.mean(whitened[m])),
                    'fraction_joint_chisq_lt_7p815':float(np.mean(whitened[m]<=7.8147)),
                    'variance_ratio_r':float(cc[0,0]/predicted[0,0]),
                    'variance_ratio_s':float(cc[1,1]/predicted[1,1]),
                    'variance_ratio_delta':float(cc[2,2]/predicted[2,2])})
        info=evaluate_information(df,casefold,J,D,P4,Unsafe)
        summaries=[]
        for c,g in info.groupby('case',sort=False):
            fullrows=df[df.case==c]
            summaries.append({'case':c,'route':c.split('_')[0],
                'n_info':len(g),'n_accepted':int(fullrows.accepted.sum()),
                'n_nonsmooth_excluded':int((Unsafe[c]&fullrows.accepted.to_numpy()).sum()),
                'median_relative_precision_gain':float(g.relative_precision_gain.median()),
                'p10_relative_precision_gain':float(g.relative_precision_gain.quantile(0.1)),
                'median_post_sigma2_deg':float(g.sigma2_deg.median()),
                'median_post_sigma3_deg':float(g.sigma3_deg.median()),
                'fraction_gain_at_least_10pct':float((g.relative_precision_gain>=.1).mean()),
                'max_negative_numeric_gain':float(min(0,g.relative_precision_gain.min()))})
        s=pd.DataFrame(summaries);r=pd.DataFrame(held);train=pd.DataFrame(outtrain)
        df.to_csv(out/'INPUT_GT_DECOMPOSITION.csv.gz',index=False,compression='gzip',float_format='%.16g')
        info.to_csv(out/'FROZEN_PRIOR_INFORMATION.csv.gz',index=False,compression='gzip',float_format='%.16g')
        s.to_csv(out/'INFORMATION_SUMMARY.csv',index=False)
        pd.DataFrame(var_rows).to_csv(out/'VAR_FAILURE_SUMMARY.csv',index=False)
        r.to_csv(out/'HELD_ROUTE_BIAS_PREDICTION.csv',index=False)
        train.to_csv(out/'TRAINED_COVARIANCES.csv',index=False)
        pd.DataFrame(calibration).to_csv(out/'HELD_ROUTE_COV_CALIBRATION.csv',index=False)
        jdump({'status':'MEASUREMENT_INFORMATION_AUDIT_NOT_RECURSIVE_PROOF',
            'scope':'7 real Full RF cases, original B0 native packet alignment, 3 held routes',
            'base_repo_head':head,'base_commit_ancestor':ROOT_COMMIT,
            'feature':'delta1=Full s(fp+1)-s(fp) minus SourceFFD LoS same feature',
            'label':'centered 5s original-time-window of z_s-h_s(GT)-mu_s; offline only',
            'fit':'2 other routes, equal route+case weights, finite positive 3x3 covariance, signed cross-cov',
            'information':'frozen E1 EXDS prior P4, augmented bias prior independent and trained, R3 empirical; incremental information nonnegative by algebra, calibration must pass',
            'limitations':'GT labels, full covariance from single scene, no online EKF replay, no sensor-noise realism; P_xb=0 assumed',
            'input_sha256':digest,'inputs':ctx.evidence_metadata(),
            'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
            ,out/'INFORMATION_AUDIT_STATUS.json')
        print('[DONE] '+str(out),flush=True)
        print(s.to_string(index=False),flush=True)
        return 0
    except BaseException as e:
        jdump({'status':'FAILED_NO_CLAIM','error_type':type(e).__name__,'message':str(e)},out/'FAILED.json')
        raise


def synthetic_smoke(output_root):
    """Test only: known stochastic toy data; deliberately NOT called real RF."""
    rng=np.random.default_rng(20261028)
    case=[]
    for route in ('R2','R4','R5'):
        for part in (0,1):
            n=400
            b=rng.normal(0,.08,n)
            delta=.28*b+rng.normal(0,.016,n)
            e_s=b+rng.normal(0,.025,n)
            e_r=rng.normal(0,.035,n)
            case.append(pd.DataFrame({'case':f'{route}_case{part}', 'route':route,
                'accepted':True,'bias_slow':b,'delta1':delta,'e_s':e_s,'e_r':e_r}))
    df=pd.concat(case,ignore_index=True)
    rows=[]
    for held in ('R2','R4','R5'):
        F=fit_fold(df,held)
        P=np.diag([.025,.025,math.radians(3)**2,.0001,F.sigma_bias2])
        H2=np.zeros((2,5));H2[0,0]=1.;H2[1,2]=3.5;H2[1,4]=1
        H3=np.vstack([H2,np.array([0,0,.04,0,F.slope])])
        vals=conditional_info(P,H2,H3,F.cov)
        assert vals['sigma3_deg']<=vals['sigma2_deg']
        rows.append({'route':held,'train_slope':F.slope,'rho_s_delta':F.cov[1,2]/math.sqrt(F.cov[1,1]*F.cov[2,2]),**vals})
    output_root=Path(output_root)
    if output_root.exists():raise FileExistsError('Synthetic output dir must be new')
    output_root.mkdir(parents=True)
    pd.DataFrame(rows).to_csv(output_root/'SYNTHETIC_INFORMATION.csv',index=False)
    jdump({'status':'SYNTHETIC_TEST_ONLY_NO_RF_CLAIM','n_routes':3,'seed':20261028,
           'meaning':'Verifies code and known independent toy observation only',
           'results':rows},output_root/'SYNTHETIC_RECEIPT.json')
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


def main(argv=None):
    p=argparse.ArgumentParser(description='Offline LORO latent polarization-bias Δs information audit')
    p.add_argument('--mode',choices=('synthetic','real'),required=True)
    p.add_argument('--output-root',required=True,type=Path)
    p.add_argument('--repo-root',type=Path)
    p.add_argument('--source-root',type=Path)
    p.add_argument('--artifacts-root',type=Path)
    p.add_argument('--code-root',type=Path)
    a=p.parse_args(argv)
    if a.mode=='synthetic':return synthetic_smoke(a.output_root)
    for key in ('repo_root','source_root','artifacts_root','code_root'):
        if getattr(a,key) is None:p.error(f'--{key.replace("_","-")} is required for real')
    return analyze_real(a)

if __name__=='__main__':raise SystemExit(main())

