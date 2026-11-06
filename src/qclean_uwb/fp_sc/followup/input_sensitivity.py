"""Counterfactual raw-score diagnostics ONLY; no provider or decision API.

Inputs are fixed C scores and hypothetical intervals, never VALID/trusted state.
The result cannot authorize production detection or replace a tap.
"""
import numpy as np
from .contracts import STEP_M, Policy

MODES = ('C', 'P', 'M', 'PM')
BUILT, HOLD_SIGNAL, HOLD_PRIOR, HOLD_HISTORY = range(4)

def raw_score_grid(raw_tap, c_score, p_bounds, m_bounds, policy: Policy):
    """Return scores/flags/status [scenario,mode]. -1 flag means unavailable.

Replicates the frozen raw-row score, not best-candidate selection. Array math
is checked against prepare_candidate_set in tests and real-row preflight.
"""
    p = np.asarray(p_bounds, dtype=float); m = np.asarray(m_bounds, dtype=float)
    if p.ndim != 2 or p.shape[1] != 2 or p.shape != m.shape:
        raise ValueError('EXPECTED_MATCHING_SCENARIO_INTERVALS')
    for a in (p,m):
        finite=np.isfinite(a).all(axis=1)
        if np.any(a[finite,0]>a[finite,1]): raise ValueError('REVERSED_INTERVAL')
    scores=np.full((len(p),4),np.nan);status=np.full((len(p),4),HOLD_SIGNAL,dtype=np.int8)
    flags=np.full((len(p),4),-1,dtype=np.int8)
    if raw_tap is None or c_score is None: return scores,flags,status
    if not np.isfinite(c_score): raise ValueError('NONFINITE_C_SCORE')
    r=raw_tap*STEP_M
    good_p=np.isfinite(p).all(axis=1)&((p[:,1]-p[:,0])<=policy.max_prior_width_m)
    good_m=np.isfinite(m).all(axis=1)
    pr=np.maximum(np.maximum(p[:,0]-r,r-p[:,1]),0)/policy.mapping_slack_m
    mr=np.maximum(np.maximum(m[:,0]-r,r-m[:,1]),0)/policy.mapping_slack_m
    scores[:,0]=c_score;status[:,0]=BUILT
    for i,ok,res in ((1,good_p,pr),(2,good_m,mr),(3,good_p&good_m,np.maximum(pr,mr))):
        status[:,i]=HOLD_PRIOR if i==1 else HOLD_HISTORY
        if i==3:status[~good_p,i]=HOLD_PRIOR
        status[ok,i]=BUILT
        scores[ok,i]=c_score+policy.prior_weight*res[ok]**2
    ready=status==BUILT;flags[ready]=(scores[ready]>=policy.wrong_cut).astype(np.int8)
    return scores,flags,status

def scenario_grid():
    base=dict(p_shift_taps=0.,p_width_scale=1.,profile='constant',history_lag_s=0.,
              m_fp_shift_taps=0.,m_offset_shift_taps=0.,m_motion_scale=1.,event='none',legacy=None)
    result=[]
    def add(name,**kw): result.append(dict(base,id=name,**kw))
    add('NOMINAL')
    for profile in ('constant','jump','drift'):
        for shift in (-2.,-1.,-.5,.5,1.,2.):
            add(f'P_CENTER_{profile}_{shift}',p_shift_taps=shift,profile=profile)
    for scale in (.25,.5,2.,4.): add(f'P_WIDTH_{scale}',p_width_scale=scale)
    for shift in (-2.,-1.,1.,2.):
        for scale in (.5,2.):add(f'P_CENTER_WIDTH_{shift}_{scale}',p_shift_taps=shift,p_width_scale=scale)
        add(f'M_FP_{shift}',m_fp_shift_taps=shift)
        add(f'M_OFFSET_{shift}',m_offset_shift_taps=shift)
        add(f'PM_SAME_{shift}',p_shift_taps=shift,m_fp_shift_taps=shift)
        add(f'PM_OPPOSED_{shift}',p_shift_taps=shift,m_fp_shift_taps=-shift)
    for scale in (.5,2.):add(f'M_MOTION_{scale}',m_motion_scale=scale)
    for lag in (.2,1.,2.,2.2):add(f'M_LAG_{lag}',history_lag_s=lag)
    for event in ('missing_1s','missing_2s','missing_5s','reinitialize'):add(event,event=event)
    for legacy in ('COV_001','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS','YAW_PLUS','YAW_MINUS'):
        add(f'LEGACY_{legacy}',legacy=legacy)
    assert len({r['id'] for r in result})==len(result)
    return result

def build_intervals(k,t,ds,raw_taps,nominal_low,nominal_high,offset,legacy_rows,grid,policy):
    """Only previous raw taps enter M; current nominal mapping is premeasurement.

No observation/decision feeds back. Events remove history availability only;
all original current RF rows are still evaluated.
"""
    n=len(t);mid=n//2;now=float(t[k]);cum=np.cumsum(abs(ds))
    ps=np.full((len(grid),2),np.nan);ms=ps.copy()
    history_j=np.full(len(grid),-1,dtype=np.int32);ages=np.full(len(grid),np.nan)
    for s,g in enumerate(grid):
        amplitude=1.
        if g['profile']=='jump':amplitude=float(k>=mid)
        if g['profile']=='drift':amplitude=float(np.clip((now-t[mid])/10.,0.,1.))
        center=(nominal_low[k]+nominal_high[k])/2+g['p_shift_taps']*STEP_M*amplitude
        radius=(nominal_high[k]-nominal_low[k])/2*g['p_width_scale']
        ps[s]=[center-radius,center+radius]
        if g['id']=='NOMINAL':ps[s]=[nominal_low[k],nominal_high[k]]
        if g['legacy']:
            r=legacy_rows[(k,g['legacy'])];ps[s]=[float(r['low']),float(r['high'])]
        candidates=np.arange(k)
        if g['history_lag_s']:
            candidates=candidates[t[:k]<=now-g['history_lag_s']+1e-10]
        if g['event'].startswith('missing_'):
            duration=float(g['event'].split('_')[1][:-1])
            candidates=candidates[(t[candidates]<t[mid])|(t[candidates]>=t[mid]+duration)]
        if g['event']=='reinitialize' and k>=mid:candidates=candidates[candidates>=mid]
        if not len(candidates):continue
        j=int(candidates[-1]);age=now-float(t[j]);history_j[s]=j;ages[s]=age
        if age<=0 or age>policy.history_max_age_s or raw_taps[j]<0:continue
        # Preserve actual distance during missing observations; no lost-motion fiction.
        distance=float(cum[k]-cum[j])
        motion=max(policy.vmax_mps*age,distance)*g['m_motion_scale']
        radius=motion+policy.motion_slack_m+policy.mapping_slack_m
        center=(raw_taps[j]+g['m_fp_shift_taps'])*STEP_M+offset[k]-offset[j]+g['m_offset_shift_taps']*STEP_M
        ms[s]=[center-radius,center+radius]
    return ps,ms,history_j,ages
