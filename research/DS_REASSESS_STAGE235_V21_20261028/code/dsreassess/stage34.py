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


def fit_held_route_cov(df, *, target_route, arm, dist_bin, minimum,
                       sample_condition):
    """Held-route R from exactly one stated observation population.

    All conditions use B0 only and EXCLUDE the target route. An insufficient
    accepted-only distance bin may fall back to the accepted-only whole
    sequence on other routes; it can NEVER borrow rejected packets.
    """
    if sample_condition not in ('all','accepted_A_B'):
        raise ValueError('invalid covariance training population')
    if dist_bin not in ('near','mid','far'):
        raise ValueError('invalid covariance distance bin')
    primary=df[(df['route']!=target_route)&(df['bias']=='B0') &
               (df['arm']==arm)&(df['sample']==sample_condition)]
    tr=primary[primary['distance_bin']==dist_bin]
    # Preserve exactly the legacy ALL-population fallback criterion so the
    # original DIAG/FULL results can be compared at 1e-10. For accepted_A_B
    # this same rule is applied WITHIN the accepted population only.
    if len(tr)<minimum or tr.route.nunique()<2:
        tr=primary
        status='WHOLE_SAME_POPULATION_FALLBACK'
    else:
        status='BIN_SAME_POPULATION'
    if len(tr)<minimum or tr.route.nunique()<2:
        counts=tr.groupby('route').size().to_dict()
        raise RuntimeError(f'INSUFFICIENT_HELD_ROUTE_{sample_condition}: '
                           f'{target_route}/{arm}/{dist_bin} train counts={counts}')
    chunks=[];means=[];names=[];counts=[]
    for route,g in tr.groupby('route'):
        if route==target_route:raise AssertionError('training/test route leakage')
        dat=g[['er_m','es']].to_numpy(float)
        if len(dat)<max(5,minimum//3):
            raise RuntimeError('population-specific held-route count is insufficient')
        chunks.append(np.cov(dat,rowvar=False,ddof=1))
        means.append(dat.mean(axis=0))
        names.append(route);counts.append(len(g))
    if len(chunks)<2:
        raise RuntimeError(f'Insufficient heldout-route populations {target_route}/{arm}/{dist_bin}/{sample_condition}')
    cov=np.mean(chunks,axis=0) # Equal route weight; NOT packet-weighted pooling.
    eigen=np.linalg.eigvalsh(cov)
    if eigen.min()<-1e-12:raise RuntimeError('held-route sample covariance indefinite')
    if eigen.min()<1e-10:cov=cov+np.eye(2)*(1e-10-eigen.min())
    return cov,{'target_route':target_route,'arm':arm,'distance_bin':dist_bin,
                'sample_condition':sample_condition,
                'source':'B0 only','train_routes':','.join(names),
                'train_route_sizes':';'.join(str(v) for v in counts),
                'n_train':int(sum(counts)),'status':status,
                'route_mean_er_m':float(np.mean([m[0] for m in means])),
                'route_mean_es':float(np.mean([m[1] for m in means])),
                'var_r':float(cov[0,0]),'cov_rs':float(cov[0,1]),
                'var_s':float(cov[1,1])}


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
    """All-vs-accepted covariance population × DIAG-vs-FULL structure.

    The old population-all arms keep their exact legacy names (`BB_DIAG`,
    `BB_FULL`, `MB_DIAG`, `MB_FULL`). New `*_ACC_*` arms differ ONLY in
    the training population. TAP remains an old exploratory arm; it is
    deliberately NOT swept in this confounder-isolation experiment.
    """
    inputs=ctx.cfg.output_root/'02_residuals/RESIDUALS.csv.gz'
    if not inputs.is_file():
        raise FileNotFoundError('Run amended Stage 2 first: '+str(inputs))
    from .io import read_json,sha256
    manifest=read_json(ctx.cfg.output_root/'02_residuals/OUTPUT_SHA256.json')
    if sha256(inputs)!=manifest.get(inputs.name):
        raise RuntimeError('STAGE2_RESIDUALS_SHA_MISMATCH')
    df=pd.read_csv(inputs,compression='gzip')
    expected={'case','route','bias','arm','sample','distance_bin',
              'er_m','es','packet_index','raw_sample_index'}
    if miss:=expected-set(df.columns):
        raise RuntimeError(f'patched Stage 2 residual columns missing {miss}')
    scores=[];cal=[];finite=[];contrast=[]
    for d in ctx.cases():
        fitted={}
        for arm in ('BASE','EXDS'):
            fitted[arm]={}
            for population in ('all','accepted_A_B'):
                fitted[arm][population]={}
                for bin_name in ('near','mid','far'):
                    cov,record=fit_held_route_cov(
                        df,target_route=d.case['route'],arm=arm,
                        dist_bin=bin_name,minimum=ctx.cfg.min_train_n,
                        sample_condition=population)
                    fitted[arm][population][bin_name]=cov
                    cal.append(dict(case=d.case['id'],bias=d.bias,**record))
        arms={}
        for prefix,mu in (('BB','BASE'),('MB','EXDS')):
            arms[prefix+'_OFF']=replay(ctx,d,prefix+'_OFF',mu_kind=mu)
            for population,marker in (('all',''),('accepted_A_B','ACC_')):
                for structure in ('DIAG','FULL'):
                    name=prefix+'_'+marker+structure
                    rule=build_R_rule(ctx,d,fitted[mu][population],structure)
                    arms[name]=replay(ctx,d,name,mu_kind=mu,R_rule=rule)
        assert_off_parity(writer,d,arms['BB_OFF'],0)
        assert_off_parity(writer,d,arms['MB_OFF'],4)
        for arm in arms.values():
            scores.extend([score(d,arm),score_window(d,arm,ctx)])
            save_replay(writer,d,arm)
        # Make the isolated population contrast explicit at fixed shrink and R shape.
        for prefix in ('BB','MB'):
            for structure in ('DIAG','FULL'):
                a=score(d,arms[prefix+'_'+structure])
                b=score(d,arms[prefix+'_ACC_'+structure])
                off=score(d,arms[prefix+'_OFF'])
                contrast.append({'case':d.case['id'],'bias':d.bias,'mean_model':prefix,
                                 'structure':structure,'cov_shrink':ctx.cfg.cov_shrink,
                                 'all_arm':prefix+'_'+structure,
                                 'accepted_arm':prefix+'_ACC_'+structure,
                                 **{key+'_all':a[key] for key in (
                                    'heading_rmse_deg','xy_rmse_m','anchor_range_rmse_cm','heading_nees')},
                                 **{key+'_accepted':b[key] for key in (
                                    'heading_rmse_deg','xy_rmse_m','anchor_range_rmse_cm','heading_nees')},
                                 **{key+'_off':off[key] for key in (
                                    'heading_rmse_deg','xy_rmse_m','anchor_range_rmse_cm','heading_nees')},
                                 'delta_heading_accepted_minus_all_deg':
                                    b['heading_rmse_deg']-a['heading_rmse_deg']})
        finite.extend(finite_difference_H(ctx,d,stride=ctx.cfg.fd_stride))
    if hasattr(ctx.cfg,'repo_root'):
        # Hard gate: the pre-existing all-population DIAG/FULL and OFF arms must
        # remain byte-numerically equal to the previous published scientific data.
        from .io import sha256,read_json
        old_root=(ctx.cfg.repo_root/'research/DS_REASSESS_1_TO_6_20261027/results/03_RF_R_H')
        old_scores=old_root/'SCORES.csv'
        old_manifest=read_json(old_root/'OUTPUT_SHA256.json')
        if not old_scores.is_file() or sha256(old_scores)!=old_manifest.get('SCORES.csv'):
            raise RuntimeError('ORIGINAL_STAGE3_SCORES_NOT_VERIFIED')
        ref=pd.read_csv(old_scores)
        current=pd.DataFrame(scores)
        retained={'BB_OFF','BB_DIAG','BB_FULL','MB_OFF','MB_DIAG','MB_FULL'}
        index=['case','bias','arm','scope']
        old=ref[ref.arm.isin(retained)].set_index(index).sort_index()
        new=current[current.arm.isin(retained)].set_index(index).sort_index()
        if old.index.has_duplicates or new.index.has_duplicates or not old.index.equals(new.index):
            raise RuntimeError('STAGE3_LEGACY_ARM_COVERAGE_MISMATCH')
        metric_cols=['heading_rmse_deg','heading_signed_bias_deg','heading_nees',
                     'xy_rmse_m','anchor_range_rmse_cm']
        max_diff=float(np.max(np.abs(old[metric_cols].to_numpy(float)-new[metric_cols].to_numpy(float))))
        if not np.isfinite(max_diff) or max_diff>1e-10:
            raise RuntimeError(f'STAGE3_ALL_POPULATION_PARITY_FAILED max_diff={max_diff}')
        writer.json('LEGACY_ALL_PARITY.json',{'status':'PASS','comparisons':int(len(old)),
                    'metrics':metric_cols,'max_abs_diff':max_diff,
                    'baseline_SHA256':sha256(old_scores)})
    else:
        # Synthetic FakeCtx has no remote baseline and cannot claim that QA.
        writer.json('LEGACY_ALL_PARITY.json',{'status':'SYNTHETIC_NOT_REAL_EVIDENCE'})
    writer.csv('SCORES.csv',scores)
    writer.csv('LORO_COVARIANCE.csv',cal)
    writer.csv('R_SAMPLE_CONTRASTS.csv',contrast)
    writer.csv('FFD_FINITE_DIFFERENCE.csv',finite)
    writer.finish({'comparison_axes':'BASE/EXDS x all/accepted_A_B x DIAG/FULL; fixed 0.5 POWER shrink',
                   'training':'B0 on other routes only, equal route weight; fallback stays in same sample_condition',
                   'legacy_parity':'old DIAG/FULL outputs unchanged as the all-sample reference; OFF E1 mandatory',
                   'scope':'TAP held for future experiment, not part of this isolation sweep',
                   'interpretation':'centered covariance does not remove residual mean, true conditional noise or selection bias'})


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
