"""Additive short-range Monte Carlo precision and reflection exploration checks."""
import numpy as np
from scipy.stats import t as student_t, qmc
from scipy.special import logsumexp
from repair_short_range import *

def reflected(model,x,target=None):
    """Exact involution delta'=-delta-a; determinant magnitude one.

    a depends on all other variables but not delta. Range depends only on
    cos(delta+a/2), so likelihood and uniform-heading prior are invariant.
    """
    if len(model.p['range_m'])!=2:raise ValueError('reflection kernel supports exactly one transition')
    y=np.asarray(x).copy();t=target if target is not None else S0BatchTarget(model.p,model.c,'RANGE')
    for row in y:
        state=np.r_[row[0],0.,row[1],t.std*row[2:5]]
        md,mg,ld,lgd,lgg,_=t.conditional(state)
        ng=float(mg[0]+lgd[0]*row[5]+lgg[0]*row[6])
        bg,sf,eps=t.std*row[2:5]
        a=(float(model.p['dtheta_gyro'][1])-ng-bg*float(model.p['dt_s'][1]))/(1+sf)
        row[1]=(-row[1]-a+np.pi)%(2*np.pi)-np.pi
    return y

def joint_mh_v2(t,model,seed,burn=4000,retained=32000,nchains=16):
    chains=[];accept=[];reflection_error=0.;crossings=[];attempts=[];applied=[]
    for j in range(nchains):
        rng=np.random.default_rng(np.random.SeedSequence([seed,5421,j]));x=draw_proposal(t,rng,1)[0]
        # Four separated initial headings; no extra prior information.
        x[1]=-np.pi+(j+.5)*2*np.pi/nchains;lp=production_full(t,x)
        keep=[];counts=np.zeros(3);cross=0;attempted=0
        for it in range(burn+retained):
            if it%1000==0:check_budget()
            block=int(rng.random()>=.5)
            if block==0:
                y=draw_proposal(t,rng,1)[0];ly=production_full(t,y)
                lr=mh_log_ratio(ly,lp,proposal_log(t,x),proposal_log(t,y))
            else:
                q=x.copy();q[0]=np.log(x[0]);v=q+np.array([.01,.8,.6,.6,.6,.6,.6])*rng.normal(size=7)
                v[1]=(v[1]+np.pi)%(2*np.pi)-np.pi;y=v.copy();y[0]=np.exp(v[0]);ly=production_full(t,y)
                lr=mh_log_ratio(ly+v[0],lp+q[0])
            if np.log(rng.random())<lr:x,lp=y,ly;counts[block]+=1
            # Random exact reflection is MH-corrected; not a doubled sample.
            if rng.random()<.5:
                attempted+=1
                y=reflected(model,x[None],t)[0];ly=production_full(t,y)
                reflection_error=max(reflection_error,abs(ly-lp))
                if np.log(rng.random())<ly-lp:
                    cross+=int(reflection_branch(model,x[None])[0]!=reflection_branch(model,y[None])[0])
                    x,lp=y,ly;counts[2]+=1
            if it>=burn:keep.append(x.copy())
        chains.append(keep);accept.append((counts/(burn+retained)).tolist());crossings.append(cross);attempts.append(attempted);applied.append(int(counts[2]))
        if retained>=32000:print('BATCH chain',j,'END',flush=True)
    return np.array(chains),dict(acceptance=accept,max_reflection_logdensity_error=reflection_error,reflection_branch_crossings=crossings,reflection_attempted=attempts,reflection_applied=applied)

def compare_v2(refs,others):
    nr,no=len(refs),len(others)
    sd=np.sqrt((np.mean([np.square(s['sd']) for s in refs],0)+np.mean([np.square(s['sd']) for s in others],0))/2)
    def error(key):
        a=np.array([s[key] for s in refs]);b=np.array([s[key] for s in others]);bv=b.var(0,ddof=1)/no
        if 'mcse' in others[0]:bv=np.maximum(bv,np.sum(np.square([s['mcse'][key] for s in others]),0)/no**2)
        return abs(a.mean(0)-b.mean(0)),np.sqrt(a.var(0,ddof=1)/nr+bv)
    d,e=error('mean');mu=(d+1.96*e)/sd
    a=np.array([np.log(s['sd']) for s in refs]);b=np.array([np.log(s['sd']) for s in others]);bv=b.var(0,ddof=1)/no
    if 'mcse' in others[0]:bv=np.maximum(bv,np.sum([np.square(np.array(s['mcse']['sd'])/s['sd']) for s in others],0)/no**2)
    ratio=np.exp(abs(a.mean(0)-b.mean(0))+1.96*np.sqrt(a.var(0,ddof=1)/nr+bv))
    d,e=error('quantiles');quant=(d+1.96*e)/sd[:,None]
    d,e=error('sector_mass');sector=d+student_t.ppf(1-.05/24,min(nr,no)-1)*e
    return dict(mean_upper_sd=mu.tolist(),sd_ratio_upper=ratio.tolist(),quantile_upper_sd=quant.tolist(),sector_simultaneous_upper=sector.tolist(),moment_pass=bool(max(mu)<=.25 and max(ratio)<=1.25 and np.max(quant)<=.1),sector_pass=bool(max(sector)<=.05),replicate_counts=[nr,no],MC_method='unchanged independent replicate + within-chain block SE; Bonferroni t df=min(nr,no)-1')

def features(x):return np.column_stack((x[:,0],np.sin(x[:,1]),np.cos(x[:,1]),x[:,2:]))

def measures(model,x,w,grid,threshold):
    vals=[]
    for j,col in enumerate(features(x).T):
        order=np.argsort(col);cw=np.r_[0.,np.cumsum(w[order])]
        vals.extend(cw[np.searchsorted(col[order],grid[j],side='right')])
    ld=model.full(x);return np.r_[vals,[w[ld>=q].sum() for q in threshold]]

def simultaneous(ref,other,within=None):
    nr,no=len(ref),len(other);bv=other.var(0,ddof=1)/no
    if within is not None:bv=np.maximum(bv,np.sum(within,0)/no**2)
    raw=abs(ref.mean(0)-other.mean(0));se=np.sqrt(ref.var(0,ddof=1)/nr+bv)
    crit=student_t.ppf(1-.05/(2*len(raw)),min(nr,no)-1);upper=raw+crit*se
    return dict(cdf_upper=float(max(upper[:-3])),hpd_upper=upper[-3:].tolist(),raw_cdf_difference=float(max(raw[:-3])),raw_hpd_difference=raw[-3:].tolist(),critical_value=float(crit),df=min(nr,no)-1,method='heldout Bonferroni t; same family and thresholds, actual replicate count',passes=bool(max(upper)<=.05))

def heading_integration(model,n,power=14,reps=4):
    """Independent periodic midpoint quadrature heading, Sobol other6 dims.

    Conditional marginal can expose heading basins; cannot exclude modes
    separated solely in other state directions.
    """
    heading=-np.pi+(np.arange(n)+.5)*2*np.pi/n;logs=[]
    for rep in range(reps):
        u=qmc.Sobol(6,scramble=True,seed=880001+rep).random_base2(power)
        u7=np.column_stack([u[:,0],np.full(len(u),.5),u[:,1:]])
        x=model.prior_draw(u7);ll=[]
        correction=model.radial_logpdf(x[:,0])-radial_proposal_log(model.inverse_grid,model.inverse_cdf,x[:,0])
        for de in heading:
            check_budget();x[:,1]=de;ll.append(logsumexp(model.likelihood(x)+correction)-np.log(len(x)))
        logs.append(ll)
    logs=np.array(logs);density=np.exp(logs-logsumexp(logs,axis=1)[:,None])
    return heading,density

def basin_definition(heading,density):
    d=density.mean(0);minima=np.where((d<np.roll(d,1))&(d<=np.roll(d,-1)))[0]
    maxima=np.where((d>np.roll(d,1))&(d>=np.roll(d,-1)))[0]
    # Preserve all detected extrema; do not prune shallow basins by result.
    edges=heading[minima]
    return dict(edges=edges.tolist(),maxima=heading[maxima].tolist(),claim='heading marginal only; no full7D unvisited-mode exclusion')

def basin_mass(x,w,edges):
    if not edges:return np.array([w.sum()])
    idx=np.searchsorted(edges,x[:,1],side='right')%len(edges)
    return np.bincount(idx,weights=w,minlength=len(edges))

def reflection_branch(model,x):
    bg,sf,eps=(x[:,2:5]*model.std).T;p,c=model.p,model.c
    dt,d,g,o=[float(p[k][1]) for k in ['dt_s','ds_odom','dtheta_gyro','dtheta_odom']]
    den=1+sf;level=1-eps**2/4;qd=c['k_s']*abs(d);qg=c['gyro_N_rad_sqrt_s']**2*dt;qo=c['k_theta']*abs(o)+c['k_stheta']*abs(d)
    v0=-eps/c['wheel_base'];v1=-level/den;S=qo+v0*v0*qd+v1*v1*qg;y=o-level*(g-bg*dt)/den-eps*d/c['wheel_base']
    cov00=qd-qd*qd*v0*v0/S;cov01=-qd*qg*v0*v1/S;cov11=qg-qg*qg*v1*v1/S;l0=np.sqrt(cov00);l10=cov01/l0;l1=np.sqrt(cov11-l10*l10)
    ng=qg*v1*y/S+l10*x[:,5]+l1*x[:,6];a=(g-ng-bg*dt)/den
    return (np.sin(x[:,1]+a/2)>0).astype(int)

def mass_agreement(ref,other,within=None):
    nr,no=len(ref),len(other);bv=other.var(0,ddof=1)/no
    if within is not None:bv=np.maximum(bv,np.sum(within,0)/no**2)
    se=np.sqrt(ref.var(0,ddof=1)/nr+bv)
    upper=abs(ref.mean(0)-other.mean(0))+student_t.ppf(1-.05/(2*ref.shape[1]),min(nr,no)-1)*se
    return dict(upper=upper.tolist(),passes=bool(max(upper)<=.05),df=min(nr,no)-1)
