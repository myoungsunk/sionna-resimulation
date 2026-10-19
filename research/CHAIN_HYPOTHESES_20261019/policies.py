"""No GT in policy decisions. All switches use pre-fit parameters and RF features."""
import numpy as np
from colored_math import error_map
R0=np.diag([.0068578637,.0081])
ARMS=['JOINT4','POWER1','MEAN_ONLY','COV_ONLY','NO_CRS','STATIC_RICH','MEM_WHITE','MEM_RS','MEM_R','MEM_S','MEM_SHORT','MEM_LONG','MEM_NO_CROSS','POWER_IEKF','POWER_SR4','POWER_COMMON_GATE','MEM_COMMON_GATE','POWER_NO_GATE','POWER_RECOVERY','POWER_FREEZE_BG','P4_HARD_BOTH','P4_HARD_MEAN','P4_HARD_COV','P4_SOFT','P4_UTILITY','LOCAL_MEM_KEEP','LOCAL_MEM_DROP','LOCAL_RICH','LOCAL_PLACEBO']

def event_intervals(data,config):
    q=data['feature_detector_s_span'];t=data['t'];flag=q>=config['event_q90']
    n=len(t);start=n;end=n
    for i in range(1,n):
        if t[i]>=30 and flag[i] and flag[i-1]:start=i;break
    if start<n:
        end=n;clear=0
        for i in range(start+1,n):
            clear=clear+1 if not flag[i] else 0
            if clear>=3:end=i+1;break
    length=end-start;ps=n;pe=n
    if length>0:
        for i in range(end,n-length+1):
            if not np.any(flag[i:i+length]):ps=i;pe=i+length;break
    return {'start':start,'end':end,'placebo_start':ps,'placebo_end':pe,'n':n,'threshold':config['event_q90'],'selection':'First two consecutive above training detector-span q90 after warmup; ends after three clear packets; placebo is a later equally long all-low span. No GT used.'}

def parameters(arm,k,data,cfg,event,dt):
    mu=data['mu'][k].copy();C=data['R'][k].copy();f=0.;a=0.;which='none';active=False
    if arm=='JOINT4':mu[:]=0;C=R0.copy()
    elif arm=='MEAN_ONLY':C=R0.copy()
    elif arm=='COV_ONLY':mu[:]=0
    elif arm=='NO_CRS':C[0,1]=C[1,0]=0
    elif arm=='STATIC_RICH':mu=data['mu_rich'][k].copy();C=data['R_rich'][k].copy()
    elif arm.startswith('P4_'):
        p=float(data['risk'][k]);on=p>=.5
        if arm=='P4_UTILITY':on=float(data['utility'][k])>=.5
        if arm in ['P4_HARD_BOTH','P4_UTILITY'] and not on:mu[:]=0;C=R0.copy()
        elif arm=='P4_HARD_MEAN' and not on:mu[:]=0
        elif arm=='P4_HARD_COV' and not on:C=R0.copy()
        elif arm=='P4_SOFT':C=(1-p)*R0+p*C+p*(1-p)*np.outer(mu,mu);mu=p*mu
    ismem=arm.startswith('MEM_')
    if arm=='LOCAL_MEM_KEEP':ismem=k>=event['start']
    elif arm=='LOCAL_MEM_DROP':ismem=event['start']<=k<event['end']
    elif arm=='LOCAL_PLACEBO':ismem=event['placebo_start']<=k<event['placebo_end']
    elif arm=='LOCAL_RICH' and event['start']<=k<event['end']:mu=data['mu_rich'][k].copy();C=data['R_rich'][k].copy()
    if ismem:
        tp=cfg['temporal'];f=tp['f'];a=tp['a_ref']**(dt/tp['dt_ref']);which='both';active=True
        if arm=='MEM_WHITE':a=0.
        elif arm=='MEM_R':which='r'
        elif arm=='MEM_S':which='s'
        elif arm=='MEM_SHORT':a=a*a
        elif arm=='MEM_LONG':a=np.sqrt(a)
    B,E=error_map(C,f,which)
    return mu,C,B,E,float(a),active
