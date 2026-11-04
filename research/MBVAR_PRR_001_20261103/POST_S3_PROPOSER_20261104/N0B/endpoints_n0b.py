"""Offline N0B paired trajectory scoring. Truth never enters the branch runner."""
import math
import numpy as np

def first_dwell(t,good,start):
    since=None
    for i in range(start,len(t)):
        if good[i]:
            if since is None: since=t[i]
            if t[i]-since>=2-1e-9: return float(t[i]-t[0])
        else:
            since=None
    return math.nan

def measure(t,x,P,truth,bg,accurate):
    t,x,P,truth=map(np.asarray,(t,x,P,truth))
    if not len(t) or not np.isfinite(x).all() or not np.isfinite(P).all(): raise ValueError('invalid emitted stream')
    e=x.copy()
    e[:,:3]-=truth
    e[:,2]=np.angle(np.exp(1j*e[:,2]))
    e[:,3]-=bg
    head=abs(np.degrees(e[:,2])); xy=np.linalg.norm(e[:,:2],axis=1)
    good=(head<=1.)&(xy<=.1)
    bad=np.flatnonzero(~good)
    exit_index=int(bad[0]) if accurate and len(bad) else None
    r=dict(available_s=t[-1]-t[0],exit_observed=bool(len(bad)) if accurate else None,
           exit_s=t[exit_index]-t[0] if exit_index is not None else math.nan,
           reentry_s=first_dwell(t,good,exit_index+1) if exit_index is not None else math.nan,
           recovery_s=first_dwell(t,good,0) if not accurate else math.nan)
    r['reentry_duration_s']=r['reentry_s']-r['exit_s']
    for horizon in (10,20):
        select=t<=t[0]+horizon+1e-9
        full=t[-1]>=t[0]+horizon-1e-9
        vals={}
        for name,err in [('head',head),('xy',xy)]:
            v=err[select]
            vals[name+'_int']=np.trapezoid(v,t[select])
            vals[name+'_p95']=np.quantile(v,.95)
            vals[name+'_rmse']=np.sqrt(np.mean(v*v))
        q=P[select]; er=e[select]
        vals['nees4']=np.mean(np.einsum('ij,ij->i',er,np.linalg.solve(q,er[:,:,None])[:,:,0]))
        vals['heading_sigma_deg']=np.mean(np.degrees(np.sqrt(q[:,2,2])))
        vals['xy_ellipse95_m2']=np.mean(np.pi*5.991464547107979*np.sqrt(np.linalg.det(q[:,:2,:2])))
        vals['heading_coverage95']=np.mean(er[:,2]**2/q[:,2,2]<=3.841458820694124)
        for key,value in vals.items():r[f'{key}_{horizon}']=float(value) if full else math.nan
        r[f'full_{horizon}']=bool(full)
    return r
