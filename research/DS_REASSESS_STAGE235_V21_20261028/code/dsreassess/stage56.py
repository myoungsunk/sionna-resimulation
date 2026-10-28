"""5: full-state dynamic observability; 6: geometry-only anchor choices and 5D bias/Q replay."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .io import Context,StageWriter,PRIMARY
from .engine import replay,score,score_window,assert_off_parity,save_replay
from .observability import first_pass_windows,fisher
from .fisher_independent import independent_nominal, independent_fisher, fd_chain_samples


def stage5(ctx:Context,writer:StageWriter):
    """Real-input independent observability audit of all 4/5-state scenarios.

    The *reference* nominal path/analytic Phi and W are captured from existing
    fisher(), while independent path/Phi come from centered numerical motion
    differentiation and the W/SVD/rank/sigma use a separate matrix codepath.
    No Stage 1, Stage 4 or Stage 6 replay is touched.
    """
    metrics=[];audit=[];fd_rows=[];rank_sensitivity=[]
    for d in ctx.cases():
        for span in first_pass_windows(ctx,d):
            for nominal in ('GT','PRIOR'):
                cap={}
                independent_X,independent_Phi=independent_nominal(d,span,nominal)
                blocks={}
                # The original frozen physics is the one common SourceFFD model.
                # Its local H is checked by separate *initial-state perturbation*
                # of the complete observer chain below.
                H_ind=np.empty((len(independent_X),2,4))
                for a in range(0,len(independent_X),32):
                    b=min(len(independent_X),a+32)
                    _,h=ctx.model.batch(independent_X[a:b],d.case)
                    H_ind[a:b]=h
                for channels in ('RANGE_ONLY','RANGE_PLUS_POL'):
                    for bias5 in (False,True):
                        for use_prior in (False,True):
                            pol=channels=='RANGE_PLUS_POL'
                            captured_this_scenario={}
                            reference=fisher(ctx,d,span=span,nominal=nominal,
                                             use_pol=pol,use_prior=use_prior,
                                             bias5=bias5,diagnostics=captured_this_scenario)
                            if not cap:cap=captured_this_scenario
                            metrics.append(dict(channels=channels,**reference))
                            indep,Wscaled,B,rows_k=independent_fisher(
                                d,span,independent_X,independent_Phi,H_ind,
                                pol=pol,prior=use_prior,bias5=bias5,
                                bias_prior_var=ctx.cfg.augmented_br_prior_std_m**2)
                            if not cap:raise RuntimeError('failed to capture reference Fisher inputs')
                            # Independent rank from SVD and normal-matrix spectrum.
                            if indep['rank']!=int(reference['rank']):
                                raise RuntimeError(f'Fisher rank mismatch: {d.key} {span[0]} {nominal} '
                                                   f'{channels}/{bias5}/{use_prior}: {indep["rank"]} '
                                                   f'vs {reference["rank"]}')
                            n=5 if bias5 else 4
                            q=np.array([1.,1.,np.radians(5.),np.radians(.1)]+([.1] if bias5 else []))
                            # Compare with THIS scenario's original Fisher matrix.
                            W_ref=q[:,None]*captured_this_scenario['W']*q[None,:]
                            error=float(np.max(np.abs(W_ref-Wscaled)))
                            atol=max(2e-5,1e-5*max(1.,float(np.max(np.abs(W_ref)))))
                            writer.check(f'{d.key}_{span[0]}_{nominal}_{channels}_{bias5}_{use_prior}_W',
                                         Wscaled,W_ref,atol)
                            sigma0=float(reference['sigma_terminal_tan_cm'])
                            sigma1=float(indep['sigma_terminal_tan_cm'])
                            if np.isinf(sigma0)!=np.isinf(sigma1):
                                raise RuntimeError('independent Fisher sigma null/finite mismatch')
                            if np.isfinite(sigma0):
                                writer.check(f'{d.key}_{span[0]}_{nominal}_{channels}_{bias5}_{use_prior}_sigma',
                                             np.array([sigma1]),np.array([sigma0]),
                                             max(.02,.005*max(1.,sigma0)))
                            null0=float(reference['null_target_fraction'])
                            if abs(null0-indep['null_target_fraction'])>1e-3:
                                raise RuntimeError('Fisher null projection discrepancy')
                            # Single-anchor Range ONLY must preserve rotational gauge.
                            if not pol and not use_prior:
                                if indep['rank']>=n or indep['gauge_rayleigh_over_lambda_max']>1e-7:
                                    raise RuntimeError('single-anchor range-only rotational gauge violated')
                            key=dict(case=d.case['id'],bias=d.bias,window=span[0],
                                     nominal=nominal,channels=channels,
                                     bias5=bias5,use_prior=use_prior)
                            audit.append(dict(**key,rank_ref=int(reference['rank']),
                                              rank_independent=indep['rank'],rank_svd=indep['rank_svd'],
                                              reference_sigma_cm=sigma0,
                                              independent_sigma_cm=sigma1,
                                              W_abs_max_diff=error,W_tolerance=atol,
                                              min_psd_eigen=indep['min_psd_eigenvalue'],
                                              null_fraction_ref=null0,
                                              null_fraction_independent=indep['null_target_fraction'],
                                              gauge_rayleigh_normalized=indep['gauge_rayleigh_over_lambda_max'],
                                              status='PASS'))
                            rank_sensitivity.append(dict(**key,**indep['sensitivity'],
                                                         nominal_rank=indep['rank'],
                                                         sensitive=any(v!=indep['rank'] for v in indep['sensitivity'].values())))
                            blocks[f'Wref_{channels}_{bias5}_{use_prior}']=W_ref
                            blocks[f'Wind_{channels}_{bias5}_{use_prior}']=Wscaled
                # Capture one reference source-path trace per (case,bias,window,nominal).
                for field,a,b,tol in (
                    ('X',independent_X,cap['X'],2e-8),
                    ('Phi',independent_Phi,cap['Phi'],3e-4),
                    ('H',H_ind,cap['H4'],3e-4)):
                    writer.check(f'{d.key}_{span[0]}_{nominal}_{field}_independent',a,b,tol)
                fd_rows.extend(fd_chain_samples(ctx,d,span,nominal,independent_X,
                                                independent_Phi,H_ind,points=5))
                writer.npz(f'{d.key}_{span[0]}_{nominal}_FISHER_AUDIT.npz',
                           reference_X=cap['X'],reference_Phi=cap['Phi'],
                           reference_H4=cap['H4'],independent_X=independent_X,
                           independent_Phi=independent_Phi,independent_H4=H_ind,
                           R=cap['R'],accepted_mask=cap['mask'],
                           t_s=d.t[span[1]:span[2]],pose_id=d.ids[span[1]:span[2]],
                           anchor_xyz=np.asarray(d.case['anchor'],float),
                           prior_P4=d.ref['Pprior'][span[1],0],
                           **blocks)
    writer.csv('FULL_STATE_FISHER.csv',metrics)
    writer.csv('FISHER_INDEPENDENT_AUDIT.csv',audit)
    writer.csv('H_PHI_FD_CHAIN_AUDIT.csv',fd_rows)
    writer.csv('FISHER_RANK_SENSITIVITY.csv',rank_sensitivity)
    df=pd.DataFrame(metrics);qa=pd.DataFrame(audit)
    if df.empty or qa.empty or not writer.checks:
        raise RuntimeError('Stage 5 must produce nonempty real-input independent checks')
    if not set(qa.status)=={'PASS'}:
        raise RuntimeError('some Fisher independent audits did not pass')
    writer.finish({'interpretation':'Data-only rank vs prior-aided; single-range gauge, full SourceFFD local observability',
                   'independent_checks':len(writer.checks),
                   'independent_math':'numeric F products, whitened B SVD, independent eigen, gauge and target-null projections',
                   'fd_chain':'selected full nonlinear SourceFFD tap/cell-stable H(Phi) vs perturbed initial motion',
                   'sensitivity':'0.1x/10x eigen cutoffs and 0.5x/2x angle state scales; change flagged, not tuned',
                   'uncertainty':'temporally independent RF likelihood only; reported sigmas are not empirical RMSE',
                   'stage6_note':'if Stage 5 original Fisher changes, quarantine old Stage 6 layout Fisher until revalidated'})


def geometry_layouts(case):
    a=np.asarray(case['anchor'],float)
    layouts=[('ORIGINAL_RANGE',[a],False),('ORIGINAL_RANGE_AND_S',[a],True)]
    # For relocation-only, compare using RANGE ONLY. Original s does not apply.
    for y in (-2.,-1.,-.5,.5,1.,2.):
        b=a.copy();b[1]+=y
        layouts.append((f'RELOCATE_Y_{y:+g}',[b],False))
    for dx in (-6.,-3.,3.,6.):
        for dy in (-1.,0.,1.):
            b=a.copy();b[0]+=dx;b[1]+=dy
            layouts.append((f'ADD_X_{dx:+g}_Y_{dy:+g}',[a,b],False))
            layouts.append((f'ADD_X_{dx:+g}_Y_{dy:+g}_OLD_S',[a,b],True))
    return layouts


def _compare_layout_data(ctx,d):
    out=[]
    for span in first_pass_windows(ctx,d):
        for name,anchors,has_pol in geometry_layouts(d.case):
            f=fisher(ctx,d,span=span,nominal='GT',anchors=anchors,use_pol=has_pol,
                     use_prior=False,bias5=False)
            out.append(dict(layout=name,anchors_xyz=';'.join(','.join(f'{w:.4g}' for w in a) for a in anchors),**f))
    return out


def stage6(ctx:Context,writer:StageWriter):
    """Two strictly distinct experiments. No imaginary RF measurement generation.

    6A: Fisher-only range geometry sweep, old s included ONLY if original
        anchor remains. All candidate new-anchor measurements are hypothetical.
    6B: same original recorded RF, no anchor changes. Compare 4-state and 5-state
        residual range bias state, optionally add post-exit tangent process Q.
    """
    geo=[];scores=[];transitions=[]
    for d in ctx.cases():
        geo.extend(_compare_layout_data(ctx,d))
        variants={}
        for prefix,mu in (('BB','BASE'),('MB','EXDS')):
            name=prefix+'_4OFF'
            variants[name]=replay(ctx,d,name,mu_kind=mu)
            for suffix,kwargs in (
               ('5BIAS',dict(bias_state=True)),
               ('5BIAS_QT',dict(bias_state=True,
                               tangent_q_std=ctx.cfg.tangent_q_std_m_per_sqrt_s,
                               q_after_exit_s=ctx.cfg.post_exit_seconds,
                               range_bias_q_std=ctx.cfg.augmented_br_q_std_m_per_sqrt_s))):
                key=prefix+'_'+suffix
                variants[key]=replay(ctx,d,key,mu_kind=mu,**kwargs)
        assert_off_parity(writer,d,variants['BB_4OFF'],0)
        assert_off_parity(writer,d,variants['MB_4OFF'],4)
        for a in variants.values():
            scores.extend([score(d,a),score_window(d,a,ctx)])
            save_replay(writer,d,a)
            if a.x.shape[1]==5:
                transitions.append({'case':d.case['id'],'bias':d.bias,'arm':a.name,
                                    'accepted_postQ':int((a.q_active&a.acc).sum()),
                                    'mean_b_r_m_scoring':float(np.mean(a.x[d.t>=30,4])),
                                    'std_b_r_m_scoring':float(np.std(a.x[d.t>=30,4])),
                                    'last_b_r_m':float(a.x[-1,4])})
    writer.csv('LAYOUT_GEOMETRY_ONLY_FISHER.csv',geo)
    writer.csv('SCORES.csv',scores)
    writer.csv('BIAS_STATE_Q_TRIGGER.csv',transitions)
    writer.finish({'safety':'Hypothetical relocated/new anchor results are local Fisher only. NEVER insert historical RF z_s into a moved-anchor SourceFFD.',
                   'augmented_state':'[x,y,psi,b_g,b_r]; b_r is additive residual range offset after fixed mu',
                   'post_exit_trigger':'prior-estimated horizontal crossing near<=1.5m to far>1.5m; no GT timing',
                   'process_Q_t':'world-frame tangent at estimated prior following a near-zone exit; sigma units m/sqrt(s)',
                   'new_anchor_noise_assumption':'independent additional range with frozen old Rrr, not validated by RF simulation'})
