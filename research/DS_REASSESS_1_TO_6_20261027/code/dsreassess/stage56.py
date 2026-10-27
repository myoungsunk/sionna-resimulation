"""5: full-state dynamic observability; 6: geometry-only anchor choices and 5D bias/Q replay."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .io import Context,StageWriter,PRIMARY
from .engine import replay,score,score_window,assert_off_parity,save_replay
from .observability import first_pass_windows,fisher


def stage5(ctx:Context,writer:StageWriter):
    metrics=[]
    for d in ctx.cases():
        for span in first_pass_windows(ctx,d):
            for nominal in ('GT','PRIOR'):
                for channels in ('RANGE_ONLY','RANGE_PLUS_POL'):
                    for bias5 in (False,True):
                        for use_prior in (False,True):
                            r=fisher(ctx,d,span=span,nominal=nominal,
                                     use_pol=channels=='RANGE_PLUS_POL',
                                     use_prior=use_prior,bias5=bias5)
                            metrics.append(dict(channels=channels,**r))
    writer.csv('FULL_STATE_FISHER.csv',metrics)
    df=pd.DataFrame(metrics)
    if df.empty:raise RuntimeError('stage 5: empty windows')
    writer.finish({'interpretation':'data-only rank vs prior-aided condition distinguish geometric identifiability from assumed prior',
                   'scale':'diag(1m,1m,5degree,.1degree/s,[.1m bias])',
                   'assumptions':'locally linear SourceFFD; frozen original A_B; independent RF packets, optimistic information; no new RF simulation',
                   'sigma_inf':'infinite when target tangent projection lies in Fisher nullspace'})


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
