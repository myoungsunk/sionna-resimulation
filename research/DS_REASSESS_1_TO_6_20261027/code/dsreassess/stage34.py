"""3: held-route RF R diagnostic and finite difference H audit.
4: factorial CUT_RT with axis, application schedule and evaluation windows separated.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .io import Context,StageWriter
from .engine import replay,score,score_window,geom_series,assert_off_parity,save_replay
from .numerics import maybe_spd,DEG


def _dist_bin(d):
    return 'near' if d<1.5 else ('mid' if d<4 else 'far')


def fit_held_route_cov(df, *, target_route, arm, dist_bin, minimum):
    """Route-heldout B0-only calibration. Do not train on target/B0's L2 duplicate.

    Center within each training route, average the route covariance matrices
    with equal route weights. Means are retained independently for audit.
    """
    tr=df[(df['route']!=target_route)&(df['bias']=='B0')&
          (df['arm']==arm)&(df['sample']=='all')&(df['distance_bin']==dist_bin)]
    status='BIN'
    if len(tr)<minimum or tr.route.nunique()<2:
        tr=df[(df['route']!=target_route)&(df['bias']=='B0')&
              (df['arm']==arm)&(df['sample']=='all')]
        status='WHOLE_HELD_ROUTE_FALLBACK'
    chunks=[];means=[];names=[]
    for route,g in tr.groupby('route'):
        if len(g)<max(5,minimum//3):continue
        dat=g[['er_m','es']].to_numpy(float)
        chunks.append(np.cov(dat,rowvar=False,ddof=1))
        means.append(dat.mean(axis=0))
        names.append(route)
    if len(chunks)<2:
        raise RuntimeError(f'Insufficient 2 independent heldout routes for {target_route}/{arm}/{dist_bin}')
    cov=np.mean(chunks,axis=0)
    eigen=np.linalg.eigvalsh(cov)
    if eigen.min()< -1e-12:raise RuntimeError('held-route sample covariance unexpectedly indefinite')
    if eigen.min()<1e-10:
        cov=cov+np.eye(2)*(1e-10-eigen.min())
    return cov,{'target_route':target_route,'arm':arm,'distance_bin':dist_bin,
                'source':'B0 only','train_routes':','.join(names),
                'n_train':len(tr),'status':status,
                'route_mean_er_m':float(np.mean([m[0] for m in means])),
                'route_mean_es':float(np.mean([m[1] for m in means])),
                'var_r':float(cov[0,0]),'cov_rs':float(cov[0,1]),'var_s':float(cov[1,1])}


def build_R_rule(ctx,d,emp_cov,variant):
    blend=float(ctx.cfg.cov_shrink)
    if variant=='DIAG':
        em={bin_name:np.diag(np.diag(cov)) for bin_name,cov in emp_cov.items()}
    else:
        em={bin_name:np.array(cov,copy=True) for bin_name,cov in emp_cov.items()}
    def r(k,x,R0,h,H):
        dist=np.linalg.norm(x[:2]-np.asarray(d.case['anchor'])[:2])
        cov=em[_dist_bin(dist)]
        R=blend*R0+(1-blend)*cov
        if variant=='TAP':
            _,_,diag=ctx.model.batch(x[None,:4],d.case,gradient=False,return_diagnostics=True)
            if float(diag['fp_margin'][0])<0.02:
                scale=np.diag([1.,2.])
                R=scale@R@scale
        return maybe_spd(R)
    return r


def finite_difference_H(ctx,d,*,stride):
    """Numerical derivative of the FULL nonlinear SourceFFD incl tap detector.

    Analytic H is valid within the *current* detected FP tap and interpolation
    cell; a changed active branch is flagged and not treated as a coding bug.
    """
    model=ctx.model
    samples=[]
    indices=list(range(0,len(d.t),stride))
    if indices[-1]!=len(d.t)-1:indices.append(len(d.t)-1)
    steps=(0.001,0.001,1e-4)  # m, m, rad
    for k in indices:
        x=np.asarray(d.ref['prior'][k,0],float)
        h,H,diag=model.batch(x[None],d.case,gradient=True,return_diagnostics=True)
        h=h[0];H=H[0]
        tap=int(diag['tap'][0]);cell=np.asarray(diag['cells'][0]);margin=float(diag['fp_margin'][0])
        for idx,delta in enumerate(steps):
            p=x.copy();q=x.copy();p[idx]+=delta;q[idx]-=delta
            hp,_,dp=model.batch(p[None],d.case,gradient=False,return_diagnostics=True)
            hm,_,dm=model.batch(q[None],d.case,gradient=False,return_diagnostics=True)
            fd=(hp[0]-hm[0])/(2*delta)
            same_tap=bool(int(dp['tap'][0])==tap==int(dm['tap'][0]))
            same_cell=bool(np.array_equal(dp['cells'][0],cell) and np.array_equal(dm['cells'][0],cell))
            samples.append({'case':d.case['id'],'bias':d.bias,'t_s':d.t[k],
                            'state_axis':['x_m','y_m','psi_rad'][idx],
                            'tap':tap,'fp_margin':margin,'tap_stable':same_tap,
                            'cell_stable':same_cell,
                            'h_s':float(h[1]),'H_s_analytic':float(H[1,idx]),
                            'H_s_finite_diff':float(fd[1]),'difference':float(fd[1]-H[1,idx]),
                            'H_r_analytic':float(H[0,idx]),'H_r_fd':float(fd[0]),
                            'large_stable_disagreement':bool(same_tap and same_cell and
                                                             abs(fd[1]-H[1,idx])>0.02)})
    return samples


def stage3(ctx:Context,writer:StageWriter):
    inputs=ctx.cfg.output_root/'02_residuals/RESIDUALS.csv.gz'
    if not inputs.is_file():
        raise FileNotFoundError('Run stage 2 first: '+str(inputs))
    from .io import read_json,sha256
    manifest=read_json(ctx.cfg.output_root/'02_residuals/OUTPUT_SHA256.json')
    if sha256(inputs)!=manifest.get(inputs.name):
        raise RuntimeError('STAGE2_RESIDUALS_SHA_MISMATCH: do not reuse altered calibration inputs')
    df=pd.read_csv(inputs,compression='gzip')
    expected={'case','route','bias','arm','sample','distance_bin','er_m','es'}
    if miss:=expected-set(df.columns):raise RuntimeError(f'stage2 residual columns missing {miss}')
    scores=[];cal=[];finite=[]
    for d in ctx.cases():
        fitted={}
        for arm in ('BASE','EXDS'):
            fitted[arm]={}
            for bin_name in ('near','mid','far'):
                fitted[arm][bin_name],record=fit_held_route_cov(df,target_route=d.case['route'],
                                                                 arm=arm,dist_bin=bin_name,
                                                                 minimum=ctx.cfg.min_train_n)
                cal.append(dict(case=d.case['id'],bias=d.bias,**record))
        arms={}
        for prefix,mu in (('BB','BASE'),('MB','EXDS')):
            arms[prefix+'_OFF']=replay(ctx,d,prefix+'_OFF',mu_kind=mu)
            # DIAG/ FULL condition R on prior estimated d; GT used only for
            # heldout training stats, never for online selection.
            for variant in ('DIAG','FULL','TAP'):
                # TAP builds from held-route full covariance, adds fp-margin inflation.
                rr_kind='FULL' if variant=='TAP' else variant
                rr=build_R_rule(ctx,d,fitted[mu],rr_kind)
                if variant=='TAP':
                    def rr_tap(k,x,R0,h,H, rr=rr):
                        R=rr(k,x,R0,h,H)
                        _,_,diag=ctx.model.batch(x[None,:4],d.case,gradient=False,return_diagnostics=True)
                        if float(diag['fp_margin'][0])<0.02:
                            scale=np.diag([1.,2.])
                            R=scale@R@scale
                        return maybe_spd(R)
                    rr=rr_tap
                arms[prefix+'_'+variant]=replay(ctx,d,prefix+'_'+variant,mu_kind=mu,R_rule=rr)
        assert_off_parity(writer,d,arms['BB_OFF'],0)
        assert_off_parity(writer,d,arms['MB_OFF'],4)
        for arm in arms.values():
            scores.extend([score(d,arm),score_window(d,arm,ctx)])
            save_replay(writer,d,arm)
        finite.extend(finite_difference_H(ctx,d,stride=ctx.cfg.fd_stride))
    writer.csv('SCORES.csv',scores)
    writer.csv('LORO_COVARIANCE.csv',cal)
    writer.csv('FFD_FINITE_DIFFERENCE.csv',finite)
    writer.finish({'note':'Held-route empirical covariance is an exploratory R model; stable-H discrepancy is a diagnostic, not auto-corrected.',
                   'safety':'R switched by prior estimated distance. TAP is modeled as extra inflation, not a repaired Gaussian likelihood.',
                   'covariance_shrink_toward_R_POWER':ctx.cfg.cov_shrink})


def axis_gt_or_est(ctx,d,*,axis,window):
    """First-pass application schedule is the SAME GT interval in all PASS arms;
    the chosen axis is the only second experimental factor.
    """
    pp=ctx.first_pass(d.case['id'],d.bias)
    lo=round(float(pp['window_start_s']),8)
    hi=round(float(pp['window_end_s']),8)
    anc=np.asarray(d.case['anchor'])[:2]
    def cut(k,prior,data):
        active=(window=='ALL' or (lo<=round(float(data.t[k]),8)<=hi))
        if not active:return None
        xy=(data.truth[k,:2] if axis=='GT' else prior[:2])
        radius=xy-anc
        r=np.linalg.norm(radius)
        if r<1e-7:
            raise ValueError(f'undefined {axis} horizontal tangent axis {data.key} k={k}')
        return np.array([-radius[1],radius[0]])/r
    return cut


def _gap_rows(d,outputs,ctx):
    out=[]
    # Important: never compare percentages from different evaluation windows.
    p=ctx.first_pass(d.case['id'],d.bias)
    masks={
      't_ge_30':d.t>=30,
      'first_pass_window':(np.round(d.t,8)>=round(float(p['window_start_s']),8)) &
                          (np.round(d.t,8)<=round(float(p['window_end_s']),8)),
      'first_pass_post':(np.round(d.t,8)>=round(float(p['post_start_s']),8)) &
                         (np.round(d.t,8)<=round(float(p['post_end_s']),8))}
    g={nm:geom_series(d,r) for nm,r in outputs.items()}
    for name,mask in masks.items():
        base=g['BB_OFF'];mu=g['MB_OFF']
        for field in ('e_tan_cm','e_beta_deg','e_psi_deg'):
            gap=float((mu[field][mask]-base[field][mask]).mean())
            if abs(gap)<1e-10:continue
            for variant in ('PRIOR_PASS','PRIOR_ALL','GT_PASS','GT_ALL'):
                a=g['BB_'+variant];b=g['MB_'+variant]
                new=float((b[field][mask]-a[field][mask]).mean())
                out.append({'case':d.case['id'],'bias':d.bias,'scope':name,
                            'metric':field,'variant':variant,'baseline_gap':gap,
                            'new_gap':new,'f_magnitude':1-abs(new)/abs(gap),
                            'f_signed':1-new/gap,'sign_reversal':bool(gap*new<0)})
    return out


def stage4(ctx:Context,writer:StageWriter):
    scores=[];gaps=[];traces=[]
    for d in ctx.cases():
        runs={}
        for prefix,mu in (('BB','BASE'),('MB','EXDS')):
            runs[prefix+'_OFF']=replay(ctx,d,prefix+'_OFF',mu_kind=mu)
            for axis in ('PRIOR','GT'):
                for win in ('PASS','ALL'):
                    key=prefix+'_'+axis+'_'+win
                    runs[key]=replay(ctx,d,key,mu_kind=mu,
                                     cut_rule=axis_gt_or_est(ctx,d,axis=axis,window=win))
        assert_off_parity(writer,d,runs['BB_OFF'],0)
        assert_off_parity(writer,d,runs['MB_OFF'],4)
        gaps.extend(_gap_rows(d,runs,ctx))
        for a in runs.values():
            scores.extend([score(d,a),score_window(d,a,ctx)])
            save_replay(writer,d,a)
            traces.append(geom_series(d,a))
    writer.csv('SCORES.csv',scores)
    writer.csv('SAME_WINDOW_GAP_REDUCTIONS.csv',gaps)
    pd.concat(traces,ignore_index=True).to_csv(writer.dir/'GEOMETRY_SERIES.csv.gz',index=False,compression='gzip')
    writer.finish({'factor_1':'tangent projection axis = prior-estimated or GT (GT oracle)',
                   'factor_2':'cut applies in SAME GT-defined first-pass interval or all samples',
                   'evaluation':'both common t>=30 and common first-pass post interval; signed and magnitude gap separate'})
