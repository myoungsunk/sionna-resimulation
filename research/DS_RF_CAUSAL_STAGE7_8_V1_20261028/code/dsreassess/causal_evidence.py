"""Frozen-RF causal diagnostic 7/8: range slow-error x polarization residual;
first-anchor pass state/covariance x after-pass polarization counterfactual.

No training, no gate recalibration, no mutation of original CaseData/source files.
All interventions using GT are OFFLINE ORACLES, never deployable filters.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import math
import json
import numpy as np
import pandas as pd

from .io import Context, CaseData, StageWriter, sha256, read_json
from .engine import Replay, replay, score, assert_off_parity, save_replay
from .numerics import DEG, wrap, propagate, joint_update

PRIMARY = ('R2_aA_m45', 'R4_aA_m0', 'R4_aB_m0')
CONTRACT_VERSION = 'RF_CAUSAL_7_8_20261028_V1'
PASS_EXPANSION_SECONDS = 10.0
R_SMOOTH_SECONDS = 2.0
S_SMOOTH_SECONDS = 5.0
POST_SECONDS = 60.0
PARITY_TOL = 1e-10
SCORE_FIELDS = ('heading_rmse_deg', 'heading_signed_bias_deg', 'xy_rmse_m',
                'anchor_range_rmse_cm', 'heading_nees')


@dataclass(frozen=True)
class Windows:
    core: np.ndarray
    expanded: np.ndarray
    post: np.ndarray
    post_start_k: int
    exit_k: int
    end_k: int
    next_pass_s: float
    pass_start_s: float
    pass_end_s: float
    clip_reason: str


def get_windows(ctx: Context, d: CaseData) -> Windows:
    """Predefined first GT pass. Post starts after *actual* d<1.5m episode,
    not after ±10s expanded diagnostic. Truncate before next episode.
    """
    p=ctx.first_pass(d.case['id'], d.bias)
    start=float(p['start_s']);end=float(p['end_s'])
    if not (d.t[0] <= start < end <= d.t[-1]):
        raise ValueError(f'bad first GT pass window {d.key}: {start} {end}')
    core=(d.t >= start-1e-8)&(d.t <= end+1e-8)
    expanded=(d.t >= start-PASS_EXPANSION_SECONDS-1e-8)&(d.t <= end+PASS_EXPANSION_SECONDS+1e-8)
    valid=ctx.passes
    sub=valid[(valid.case==d.case['id'])&(valid.bias==d.bias)&(valid.pass_id>1)]
    nextpass=float(sub['start_s'].min()) if len(sub) else np.inf
    stop=min(end+POST_SECONDS,float(d.t[-1]))
    # Next GT pass start must be EXCLUSIVE. Do not add back the same epsilon
    # used for clipping, which would silently include the next-pass packet.
    post=(d.t > end+1e-8)&(d.t <= stop+1e-8)&(d.t < nextpass-1e-8)
    exit_idx=np.flatnonzero(d.t <= end+1e-8)
    post_idx=np.flatnonzero(post)
    if not (core.sum()>0 and expanded.sum()>=10 and len(exit_idx) and len(post_idx)>=10):
        raise RuntimeError(f'FIRST_PASS_OR_POST_NOT_VALID {d.key} npost={post.sum()}')
    exit_k=int(exit_idx[-1]);start_k=int(post_idx[0]);end_k=int(post_idx[-1])
    if start_k!=exit_k+1 or np.any(np.diff(post_idx)!=1):
        raise RuntimeError(f'noncontiguous post window {d.key}')
    reason='NEXT_PASS' if nextpass<=end+POST_SECONDS else ('RECORD_END' if d.t[-1]<end+POST_SECONDS else 'FULL_60_S')
    return Windows(core,expanded,post,start_k,exit_k,end_k,nextpass,start,end,reason)


def gt_observation(ctx:Context,d:CaseData,batch:int=32)->np.ndarray:
    result=np.empty((len(d.t),2),float)
    for k in range(0,len(d.t),batch):
        pred,der=ctx.model.batch(d.truth[k:k+batch],d.case,gradient=False)
        result[k:k+batch]=pred
    if not np.isfinite(result).all():
        raise RuntimeError('nonfinite GT source observation')
    return result


def centered_mean(t, residual, seconds, *, eligibility=None, min_count=3):
    """A deterministic *offline*, centered moving mean (not causal filtering).
    Uses ORIGINAL packet timestamps and a fixed centered width. Does not
    interpolate missing packets. For a pass interval, ignores observations
    outside that interval; returns zeros there and valid sample counts.
    """
    t=np.asarray(t,float);v=np.asarray(residual,float)
    if t.ndim!=1 or v.shape!=t.shape or not np.isfinite(v).all():
        raise ValueError('bad smoother shapes or nonfinite residual')
    if len(t)<min_count or np.any(np.diff(t)<=0) or seconds<=0:
        raise ValueError('bad time grid/width for centered smoother')
    eligible=np.ones(len(t),bool) if eligibility is None else np.asarray(eligibility,bool)
    if eligible.shape!=t.shape or not eligible.any():
        raise ValueError('smoother eligible window empty')
    time=t[eligible];vv=v[eligible]
    # True time windows: for any sample k, take all eligible samples with
    # times |t_j-t_k| <= seconds/2; never confuse array row with clock lag.
    left=np.searchsorted(time,time-seconds/2-1e-10,side='left')
    right=np.searchsorted(time,time+seconds/2+1e-10,side='right')
    count=right-left
    if np.any(count<min_count):
        raise RuntimeError(f'INSUFFICIENT_SMOOTH_SAMPLES width={seconds} minimum={min_count} got {int(count.min())}')
    cumulative=np.r_[0.,np.cumsum(vv,dtype=np.float64)]
    out=np.zeros(len(t));n=np.zeros(len(t),np.int32)
    out[eligible]=(cumulative[right]-cumulative[left])/count
    n[eligible]=count
    if not np.allclose(out[eligible]+(v[eligible]-out[eligible]),v[eligible],rtol=0,atol=1e-12):
        raise RuntimeError('slow+fast != raw residual')
    return out,n


def make_plan(ctx:Context,d:CaseData):
    win=get_windows(ctx,d)
    hgt=gt_observation(ctx,d)
    er_b=d.z[:,0]-hgt[:,0]-d.mu_b
    er_m=d.z[:,0]-hgt[:,0]-d.mu_exds
    es=d.z[:,1]-hgt[:,1]-d.mu_s
    slowr,nr=centered_mean(d.t,er_b,R_SMOOTH_SECONDS,eligibility=win.expanded)
    slows,ns=centered_mean(d.t,es,S_SMOOTH_SECONDS)
    mr_b=np.asarray(d.mu_b,float)
    mr_m=np.asarray(d.mu_exds,float)
    mr_slowremoved=mr_b+slowr
    mr_fastremoved=mr_b+np.where(win.expanded,er_b-slowr,0.)
    mr_range_oracle=mr_b+er_b
    ms_real=np.asarray(d.mu_s,float)
    ms_clean=ms_real+es
    ms_fast=ms_real+slows # remain only high-frequency residual
    ms_slow=ms_real+es-slows # remain only low-frequency residual
    mu_r={'BASE':mr_b,'NO_SLOW_R':mr_slowremoved,'ONLY_SLOW_R':mr_fastremoved,
          'EXDS':mr_m,'R_ORACLE':mr_range_oracle}
    mu_s={'POL_REAL':ms_real,'POL_CLEAN':ms_clean,
          'POL_FAST':ms_fast,'POL_SLOW':ms_slow}
    # GT oracle is an exact observation-mean counterfactual, never fed back
    # into gate or into learned parameters. SourceFFD itself remains unchanged.
    if not np.allclose(d.z[:,1]-hgt[:,1]-ms_clean,0,rtol=0,atol=3e-12):
        raise AssertionError('polarization GT oracle not exact')
    if not np.allclose(d.z[:,0]-hgt[:,0]-mr_range_oracle,0,rtol=0,atol=3e-12):
        raise AssertionError('range GT oracle not exact')
    if not np.allclose(er_b,slowr+(er_b-slowr),rtol=0,atol=3e-12):
        raise AssertionError('range residual decomposition not exact')
    if not np.allclose(es,slows+(es-slows),rtol=0,atol=3e-12):
        raise AssertionError('polarization residual decomposition not exact')
    return dict(windows=win,gt=hgt,er_b=er_b,er_m=er_m,es=es,
                slowr=slowr,slows=slows,nr=nr,ns=ns,mu_r=mu_r,mu_s=mu_s)


def make_intervened_case(d:CaseData,mu_r,mu_s):
    a=np.asarray(mu_r,float);b=np.asarray(mu_s,float)
    if a.shape!=(len(d.t),) or b.shape!=a.shape:
        raise ValueError('wrong intervention mean shape')
    # NOTE: only cloned CaseData changes. z, R, A_B mask, controls, GT and
    # SourceFFD are SHARED (not copied/recalibrated).
    return replace(d,mu_b=a.copy(),mu_s=b.copy())


def replay_with_means(ctx,d,name,mu_r,mu_s):
    clone=make_intervened_case(d,mu_r,mu_s)
    return replay(ctx,clone,name,mu_kind='BASE')


def score_spans(d,arm,win):
    scopes={'scoring':d.t>=30,
            'first_pass_core':win.core,
            'first_pass_extended':win.expanded,
            'first_pass_post60':win.post}
    return [score(d,arm,mask=mask,scope=scope) for scope,mask in scopes.items()]


def run_factorial_case(ctx,d,writer,*,save_traces=True):
    plan=make_plan(ctx,d);win=plan['windows']
    r=plan['mu_r'];s=plan['mu_s']
    # 2x2 Range slow-error removal x Polar exact oracle, plus independent
    # EXDS/full-range-oracle, and a 5s polar low/high residual check.
    combinations=[
        ('BASE__POL_REAL','BASE','POL_REAL'),
        ('BASE__POL_CLEAN','BASE','POL_CLEAN'),
        ('NO_SLOW_R__POL_REAL','NO_SLOW_R','POL_REAL'),
        ('NO_SLOW_R__POL_CLEAN','NO_SLOW_R','POL_CLEAN'),
        ('ONLY_SLOW_R__POL_REAL','ONLY_SLOW_R','POL_REAL'),
        ('EXDS__POL_REAL','EXDS','POL_REAL'),
        ('EXDS__POL_CLEAN','EXDS','POL_CLEAN'),
        ('R_ORACLE__POL_REAL','R_ORACLE','POL_REAL'),
        ('R_ORACLE__POL_CLEAN','R_ORACLE','POL_CLEAN'),
        ('BASE__POL_FAST','BASE','POL_FAST'),
        ('BASE__POL_SLOW','BASE','POL_SLOW'),
        ('EXDS__POL_FAST','EXDS','POL_FAST'),
        ('EXDS__POL_SLOW','EXDS','POL_SLOW'),
    ]
    arms={}
    for label,rkey,skey in combinations:
        arms[label]=replay_with_means(ctx,d,label,r[rkey],s[skey])
    # Pass-clean donors: identical base outside core, true GT r+s inside.
    for prefix,basekey in (('BB','BASE'),('MB','EXDS')):
        mr=r[basekey].copy();ms=s['POL_REAL'].copy()
        mr[win.core]=r['R_ORACLE'][win.core]
        ms[win.core]=s['POL_CLEAN'][win.core]
        label=f'PASS_CLEAN_{prefix}'
        arms[label]=replay_with_means(ctx,d,label,mr,ms)
    assert_off_parity(writer,d,arms['BASE__POL_REAL'],0)
    assert_off_parity(writer,d,arms['EXDS__POL_REAL'],4)
    # New entry must be identical to the untouched public replay module.
    old_b=replay(ctx,d,'FROZEN_BASE',mu_kind='BASE')
    old_m=replay(ctx,d,'FROZEN_EXDS',mu_kind='EXDS')
    for label,old in [('BASE__POL_REAL',old_b),('EXDS__POL_REAL',old_m)]:
        new=arms[label]
        for field in ('x','P','prior','Pprior','K','H','h','nu','mu','R','acc'):
            writer.check(d.key+'_'+label+'_clone_'+field,getattr(new,field),getattr(old,field),PARITY_TOL)
    # In the exact oracle, the measurement error at GT is identically zero;
    # this is NOT an achievable, observed online sensor.
    writer.check(d.key+'_gt_range_oracle',d.z[:,0]-plan['gt'][:,0]-r['R_ORACLE'],np.zeros(len(d.t)),3e-12)
    writer.check(d.key+'_gt_pol_oracle',d.z[:,1]-plan['gt'][:,1]-s['POL_CLEAN'],np.zeros(len(d.t)),3e-12)
    rows=[]
    for name,arm in arms.items():
        rows.extend(score_spans(d,arm,win))
        if save_traces:save_replay(writer,d,arm)
    def differential(a,b,c,e,scope):
        z={k:score(d,arms[k],mask=({'scoring':d.t>=30,'first_pass_post60':win.post}[scope]),scope=scope)
           for k in (a,b,c,e)}
        result=[]
        for metric in SCORE_FIELDS:
            av=z[a][metric];bv=z[b][metric];cv=z[c][metric];dv=z[e][metric]
            result.append({'case':d.case['id'],'bias':d.bias,'scope':scope,
                           'contrast':f'{a}|{b}|{c}|{e}','metric':metric,
                           'Y_A':av,'Y_B':bv,'Y_C':cv,'Y_D':dv,
                           'slow_r_effect_under_real':av-cv,
                           'slow_r_effect_under_clean':bv-dv,
                           'interaction':av-bv-cv+dv,
                           'pol_clean_effect_under_original_range':av-bv,
                           'pol_clean_effect_under_modified_range':cv-dv})
        return result
    contrasts=[]
    for scope in ('scoring','first_pass_post60'):
        contrasts+=differential('BASE__POL_REAL','BASE__POL_CLEAN',
                                'NO_SLOW_R__POL_REAL','NO_SLOW_R__POL_CLEAN',scope)
        contrasts+=differential('BASE__POL_REAL','BASE__POL_CLEAN',
                                'EXDS__POL_REAL','EXDS__POL_CLEAN',scope)
    duration=float(d.t[win.end_k]-d.t[win.post_start_k])+float(d.t[win.post_start_k]-d.t[win.exit_k])
    meta={'case':d.case['id'],'bias':d.bias,'pass_start_s':win.pass_start_s,
          'pass_end_s':win.pass_end_s,'n_pass_core':int(win.core.sum()),
          'n_expanded':int(win.expanded.sum()),'n_post60':int(win.post.sum()),
          'post_exit_duration_s':duration,'post_clip_reason':win.clip_reason,
          'next_pass_start_s':win.next_pass_s if np.isfinite(win.next_pass_s) else None,
          'exit_k':win.exit_k,'post_start_k':win.post_start_k,'end_k':win.end_k,
          'range_smooth_seconds':R_SMOOTH_SECONDS,'pol_smooth_seconds':S_SMOOTH_SECONDS,
          'range_slow_min_count':int(plan['nr'][win.expanded].min()),
          'pol_slow_min_count':int(plan['ns'].min()),
          'post60_r_accepted':int(d.mask[win.post].sum())}
    # Keep small inspectable GT-decomposition table. Never interpret these
    # as online available features.
    diag=pd.DataFrame({'case':d.case['id'],'bias':d.bias,'t_s':d.t,'pose_id':d.ids,
        'accepted':d.mask,'pass_core':win.core,'pass_expanded':win.expanded,'post60':win.post,
        'er_BASE_m':plan['er_b'],'er_EXDS_m':plan['er_m'],'slow_er_BASE_m':plan['slowr'],
        'fast_er_BASE_m':plan['er_b']-plan['slowr'],'es':plan['es'],
        'slow_es':plan['slows'],'fast_es':plan['es']-plan['slows'],
        'mu_r_BASE':d.mu_b,'mu_r_EXDS':d.mu_exds,'mu_s':d.mu_s})
    return rows,contrasts,meta,diag


def stage7(ctx:Context,writer:StageWriter):
    rows=[];contrasts=[];meta=[];diagnostics=[]
    for d in ctx.cases():
        score_rows,int_rows,m,diag=run_factorial_case(ctx,d,writer)
        rows.extend(score_rows);contrasts.extend(int_rows);meta.append(m);diagnostics.append(diag)
        print('[STAGE7]',d.key,'arms=15','checks=',len(writer.checks),flush=True)
    writer.csv('SCORES.csv',rows)
    writer.csv('FACTORIAL_INTERACTIONS.csv',contrasts)
    writer.csv('PASS_WINDOW_CONTRACT.csv',meta)
    pd.concat(diagnostics,ignore_index=True).to_csv(writer.dir/'GT_RESIDUAL_DECOMPOSITION.csv.gz',index=False,compression='gzip',float_format='%.16g')
    if not writer.checks or len(meta)!=len(ctx.cfg.cases)*len(ctx.cfg.biases):
        raise RuntimeError('INCOMPLETE_STAGE7')
    writer.finish({'status_detail':'TECHNICAL_EXECUTION_NOT_CAUSAL_IDENTIFICATION',
                   'scope':'first-GT-pass centered 2s slow range residual; whole-run clean 5s polar diagnostic',
                   'intervention':'fixed A_B; frozen R/Q/odometry/predictions; offline GT mean substitution only',
                   'counterfactuals':'BASE slow-error 2x2 plus EXDS, range oracle and polar fast/slow probes',
                   'limitation':'No performance-based parameter fitting; smoothers use future GT; no natural gate inference'})


def donor_from_stage7(writer,ctx,d,name):
    root=ctx.cfg.output_root/'07_rf_pol_factorial'
    path=root/f'{d.key}_{name}.npz'
    manifest=read_json(root/'OUTPUT_SHA256.json')
    if not path.is_file() or manifest.get(path.name)!=sha256(path):
        raise RuntimeError(f'UNVERIFIED_FACTORIAL_DONOR {path}')
    with np.load(path,allow_pickle=False) as z:
        ar={k:z[k].copy() for k in ('x','P','acc','R','mu','t_s','pose_id')}
    for field,orig in [('acc',d.mask),('t_s',d.t),('pose_id',d.ids)]:
        writer.check(d.key+'_'+name+'_donor_'+field,ar[field],orig,PARITY_TOL)
    writer.check(d.key+'_'+name+'_donor_R',ar['R'],d.R,PARITY_TOL)
    return ar


def post_suffix_replay(ctx,d,exit_k,end_k,x0,P0,mu_r,mu_s):
    """Start immediately AFTER last observed crossing packet. No prior
    measurements are processed twice. Four-state frozen EKF, same Q/R/gate.
    """
    if not (0<=exit_k<end_k<len(d.t)):
        raise ValueError('post suffix indices invalid')
    x=np.asarray(x0,float).copy();P=np.asarray(P0,float).copy()
    if x.shape!=(4,) or P.shape!=(4,4):raise ValueError('bad donor state')
    steps=[]
    for k in range(exit_k+1,end_k+1):
        x,P,_=propagate(x,P,float(d.controls['ds_odom'][k]),
                        float(d.controls['dtheta_gyro'][k]),float(d.controls['dt_s'][k]))
        xprior=x.copy();Pprior=P.copy()
        h,H=ctx.model.batch(x[None,:4],d.case)
        z=d.z[k]
        mu=np.array([mu_r[k],mu_s[k]],float)
        upd=joint_update(x,P,z,h[0],H[0],mu,d.R[k],bool(d.mask[k]))
        x,P=upd.x,upd.P
        kr=upd.K[:,0]*upd.nu[0] if d.mask[k] else np.zeros(4)
        ks=upd.K[:,1]*upd.nu[1] if d.mask[k] else np.zeros(4)
        steps.append((k,x.copy(),P.copy(),kr.copy(),ks.copy(),upd.nu.copy(),upd.K.copy(),
                      xprior,Pprior,np.asarray(h[0]).copy(),np.asarray(H[0]).copy(),
                      mu.copy()))
    return steps


def score_suffix(d,steps,*,arm,scope='post60'):
    if not steps:raise ValueError('empty post suffix')
    k=np.array([a[0] for a in steps],int)
    X=np.stack([a[1] for a in steps]);PP=np.stack([a[2] for a in steps])
    e=X-d.truth[k]
    e[:,2]=wrap(e[:,2]);head=e[:,2]*DEG
    anc=np.asarray(d.case['anchor'])[:2]
    gt=d.truth[k,:2]-anc
    dist=np.linalg.norm(gt,axis=1)
    if np.any(dist<1e-7):raise ValueError('tangent undefined in post suffix')
    ur=gt/dist[:,None];ut=np.c_[-ur[:,1],ur[:,0]]
    he=float(d.case['anchor'][2]-d.case['robot_z_m'])
    truthrange=np.sqrt(dist**2+he**2)
    estdist=np.linalg.norm(X[:,:2]-anc,axis=1)
    est_range=np.sqrt(estdist**2+he**2)
    er=(est_range-truthrange)*100
    er_xy=np.sum(e[:,:2]*ur,axis=1)*100
    et_xy=np.sum(e[:,:2]*ut,axis=1)*100
    rad_rms=float(np.sqrt(np.mean(er_xy**2)))
    tan_rms=float(np.sqrt(np.mean(et_xy**2)))
    xy_rmse=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1))))
    if not np.isclose((rad_rms**2+tan_rms**2)/10000.,xy_rmse**2,rtol=0,atol=1e-10):
        raise AssertionError('radial+tangential RMS not equal XY RMSE squared')
    psi_nees=np.mean((e[:,2]**2)/PP[:,2,2])
    out={'case':d.case['id'],'bias':d.bias,'arm':arm,'scope':scope,
         'n':len(steps),'accepted':int(d.mask[k].sum()),
         't_start_s':float(d.t[k[0]]),'t_end_s':float(d.t[k[-1]]),
         'heading_rmse_deg':float(np.sqrt(np.mean(head**2))),
         'heading_signed_bias_deg':float(np.mean(head)),
         'heading_std_deg':float(np.std(head)),
         'heading_nees':float(psi_nees),'xy_rmse_m':xy_rmse,
         'anchor_range_rmse_cm':float(np.sqrt(np.mean(er**2))),
         'e_rad_signed_cm':float(np.mean(er_xy)),
         'e_tan_signed_cm':float(np.mean(et_xy)),
         'radial_rms_cm':rad_rms,'tangential_rms_cm':tan_rms,
         'rms_krnu_heading_deg':float(np.sqrt(np.mean([ (a[3][2]*DEG)**2 for a in steps]))),
         'rms_ksnu_heading_deg':float(np.sqrt(np.mean([ (a[4][2]*DEG)**2 for a in steps]))),
         'sum_krnu_heading_deg':float(sum(a[3][2]*DEG for a in steps)),
         'sum_ksnu_heading_deg':float(sum(a[4][2]*DEG for a in steps))}
    return out


def check_suffix_parity(writer,d,steps,donor,exit_k,*,label):
    idx=np.array([a[0] for a in steps],int)
    writer.check(d.key+'_'+label+'_post_x_parity',np.stack([a[1] for a in steps]),donor['x'][idx],PARITY_TOL)
    writer.check(d.key+'_'+label+'_post_P_parity',np.stack([a[2] for a in steps]),donor['P'][idx],PARITY_TOL)


def save_suffix_trace(writer:StageWriter,d:CaseData,seq,*,name:str,
                      exit_k:int,exit_x,exit_P,post_range:str,post_pol:str):
    """Save ALL posterior/prior/H/K/P/R/innovation for independent packet audit.
    Non-baseline donor combinations remain explicitly marked as diagnostics.
    """
    idx=np.asarray([a[0] for a in seq],int)
    arrays={
        't_s':d.t[idx], 'pose_id':d.ids[idx],
        'truth_scoring_only':d.truth[idx], 'z':d.z[idx],
        'R':d.R[idx], 'acc':d.mask[idx],
        'x':np.stack([a[1] for a in seq]),
        'P':np.stack([a[2] for a in seq]),
        'krnu':np.stack([a[3] for a in seq]),
        'ksnu':np.stack([a[4] for a in seq]),
        'nu':np.stack([a[5] for a in seq]),
        'K':np.stack([a[6] for a in seq]),
        'prior':np.stack([a[7] for a in seq]),
        'Pprior':np.stack([a[8] for a in seq]),
        'h':np.stack([a[9] for a in seq]),
        'H':np.stack([a[10] for a in seq]),
        'mu':np.stack([a[11] for a in seq]),
        'ds_odom':np.asarray(d.controls['ds_odom'])[idx],
        'dtheta_gyro':np.asarray(d.controls['dtheta_gyro'])[idx],
        'dt_s':np.asarray(d.controls['dt_s'])[idx],
        'exit_k':exit_k, 'exit_x':np.asarray(exit_x,float),
        'exit_P':np.asarray(exit_P,float),
        'donor_arm':name, 'post_range':post_range, 'post_pol':post_pol,
    }
    # Prove each accepted packet has the exact linearized two-channel gain
    # decomposition used by the stored posterior; no hidden update row.
    predicted=arrays['K']*arrays['nu'][:,None,:]
    writer.check(d.key+'_'+name+'_range_increment',arrays['krnu'],
                 np.where(d.mask[idx,None],predicted[:,:,0],0),1e-11)
    writer.check(d.key+'_'+name+'_polar_increment',arrays['ksnu'],
                 np.where(d.mask[idx,None],predicted[:,:,1],0),1e-11)
    writer.npz(f'{d.key}_{name}_POST60.npz',**arrays)


def stage8(ctx:Context,writer:StageWriter):
    scores=[];contrasts=[];prefix=[];trace_records=[]
    for d in ctx.cases():
        win=get_windows(ctx,d)
        model_gt=gt_observation(ctx,d)
        es=d.z[:,1]-model_gt[:,1]-d.mu_s
        sreal=d.mu_s
        sclean=sreal+es
        mr={'BASE':d.mu_b,'EXDS':d.mu_exds}
        donors={'BASE':donor_from_stage7(writer,ctx,d,'BASE__POL_REAL'),
                'EXDS':donor_from_stage7(writer,ctx,d,'EXDS__POL_REAL'),
                'PASS_CLEAN_BB':donor_from_stage7(writer,ctx,d,'PASS_CLEAN_BB'),
                'PASS_CLEAN_MB':donor_from_stage7(writer,ctx,d,'PASS_CLEAN_MB')}
        # Record all exit donor state, gyro bias, P, and GT mismatch explicitly.
        i=win.exit_k
        anc=np.asarray(d.case['anchor'])[:2]
        v=d.truth[i,:2]-anc
        ut=np.r_[-v[1],v[0]]/np.linalg.norm(v)
        for dn,da in donors.items():
            x=da['x'][i];P=da['P'][i];e=x-d.truth[i]
            prefix.append({'case':d.case['id'],'bias':d.bias,'donor':dn,
                           'exit_k':i,'exit_t_s':float(d.t[i]),
                           'e_x_m':float(e[0]),'e_y_m':float(e[1]),
                           'e_tan_cm':float(100*(e[:2]@ut)),
                           'e_psi_deg':float(DEG*wrap(e[2])),
                           'e_bgyro_rad_s':float(e[3]),
                           'Pxx':float(P[0,0]),'Pyy':float(P[1,1]),'Ppsipsi':float(P[2,2]),
                           'Pxy':float(P[0,1]),'Pxpsi':float(P[0,2]),'Pypsi':float(P[1,2])})
        rows={}
        for postrange in ('BASE','EXDS'):
            for pol in ('REAL','CLEAN'):
                # Main 2x2 state-donor x covariance-donor, all future data fixed.
                for xdonor in ('BASE','EXDS'):
                    for pdonor in ('BASE','EXDS'):
                        name=f'X_{xdonor}_P_{pdonor}_R_{postrange}_S_{pol}'
                        seq=post_suffix_replay(ctx,d,i,win.end_k,
                                               donors[xdonor]['x'][i],donors[pdonor]['P'][i],
                                               mr[postrange],sreal if pol=='REAL' else sclean)
                        r=score_suffix(d,seq,arm=name)
                        r.update(x_donor=xdonor,P_donor=pdonor,post_range=postrange,post_pol=pol,
                                 donor_kind='MIXED_BB_MB')
                        rows[(xdonor,pdonor,postrange,pol)]=r
                        scores.append(r)
                        save_suffix_trace(writer,d,seq,name=name,exit_k=i,
                                          exit_x=donors[xdonor]['x'][i],
                                          exit_P=donors[pdonor]['P'][i],
                                          post_range=postrange,post_pol=pol)
                        # Observed baseline has exact continuation; no GT change.
                        if xdonor==pdonor==postrange and pol=='REAL':
                            check_suffix_parity(writer,d,seq,donors[xdonor],i,label=name)
                        # Sufficient packet evidence to independently inspect transfer.
                        for a in seq:
                            trace_records.append({'case':d.case['id'],'bias':d.bias,'arm':name,
                                 'k':int(a[0]),'t_s':float(d.t[a[0]]),'x':float(a[1][0]),
                                 'y':float(a[1][1]),'psi_rad':float(a[1][2]),
                                 'e_psi_deg':float(DEG*wrap(a[1][2]-d.truth[a[0],2])),
                                 'Kr_nur_psi_deg':float(DEG*a[3][2]),
                                 'Ks_nus_psi_deg':float(DEG*a[4][2]),
                                 'accepted':bool(d.mask[a[0]])})
                # Pass-clean donor separately isolates the contribution of the
                # *GT first-pass core intervention* from the otherwise same donor.
                for donor in ('PASS_CLEAN_BB','PASS_CLEAN_MB'):
                    name=f'DONOR_{donor}_R_{postrange}_S_{pol}'
                    seq=post_suffix_replay(ctx,d,i,win.end_k,
                                           donors[donor]['x'][i],donors[donor]['P'][i],
                                           mr[postrange],sreal if pol=='REAL' else sclean)
                    rr=score_suffix(d,seq,arm=name)
                    rr.update(x_donor=donor,P_donor=donor,post_range=postrange,post_pol=pol,
                              donor_kind='CLEAN_PASS_CORE')
                    rows[(donor,donor,postrange,pol)]=rr
                    scores.append(rr)
                    save_suffix_trace(writer,d,seq,name=name,exit_k=i,
                                      exit_x=donors[donor]['x'][i],
                                      exit_P=donors[donor]['P'][i],
                                      post_range=postrange,post_pol=pol)
        for postrange in ('BASE','EXDS'):
            for pol in ('REAL','CLEAN'):
                k=lambda x,p: rows[(x,p,postrange,pol)]
                for metric in ('heading_rmse_deg','heading_signed_bias_deg','xy_rmse_m','e_tan_signed_cm','heading_nees'):
                    ybb=k('BASE','BASE')[metric]; ymb=k('EXDS','BASE')[metric]
                    ybm=k('BASE','EXDS')[metric]; ymm=k('EXDS','EXDS')[metric]
                    contrasts.append({'case':d.case['id'],'bias':d.bias,'post_range':postrange,
                         'post_pol':pol,'metric':metric,
                         'Y_BB':ybb,'Y_MB_stateOnly':ymb,'Y_BM_covOnly':ybm,'Y_MM':ymm,
                         'state_effect_at_P_BB':ymb-ybb,'P_effect_at_state_BB':ybm-ybb,
                         'combined_effect':ymm-ybb,'state_P_interaction':ymm-ymb-ybm+ybb,
                         'pass_clean_effect_from_BB':rows[('PASS_CLEAN_BB','PASS_CLEAN_BB',postrange,pol)][metric]-ybb,
                         'pass_clean_effect_from_MB':rows[('PASS_CLEAN_MB','PASS_CLEAN_MB',postrange,pol)][metric]-ymm})
        print('[STAGE8]',d.key,'post=',int(win.post.sum()),'checks=',len(writer.checks),flush=True)
    writer.csv('POST60_HANDOFF_SCORES.csv',scores)
    writer.csv('HANDOFF_STATE_P_INTERACTIONS.csv',contrasts)
    writer.csv('EXIT_DONOR_STATES.csv',prefix)
    pd.DataFrame(trace_records).to_csv(writer.dir/'POST60_GAIN_LEDGER.csv.gz',index=False,compression='gzip',float_format='%.16g')
    if not writer.checks or len(scores)!=len(ctx.cfg.cases)*len(ctx.cfg.biases)*24:
        raise RuntimeError('INCOMPLETE_HANDOFF_COUNTS')
    writer.finish({'scope':'First GT pass crossing exit to 60s or before next pass; frozen post measurement/mask/Q/R',
                   'intervention':'BB/EXDS state x vs covariance P donor; common BASE or EXDS post-range; real vs GT-clean post-polarization',
                   'pass_core_clean':'GT oracle ONLY within first d<1.5m episode, outside full original background',
                   'limitations':'Mixed donor x/P may be inconsistent; diagnostic only; packet-level gain ledger not total mediated causal effect'})
