"""I2 S0 public-only PF and separated experiment/scoring driver."""
from pathlib import Path
import json,sys,hashlib,datetime,platform
import numpy as np
import pandas as pd
from i2_ideal_range_calibration import write, quantile
from i2_s0_batch import radial_table, batch_s0

HERE=Path(__file__).resolve().parent
PUBLIC_KEYS=('t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom','range_m','range_mask')

def summary(cal,w):
    c=cal[:,[0,2]]; mean=w@c; delta=c-mean
    cov=(delta*w[:,None]).T@delta; sd=np.sqrt(np.diag(cov))
    lo=np.array([quantile(c[:,j],w,.025) for j in range(2)])
    hi=np.array([quantile(c[:,j],w,.975) for j in range(2)])
    unique=len(np.unique(c,axis=0)); valid=False; corr=None; radius=None
    # Numeric rank is checked in scaled coordinates; no repair or artificial width.
    if unique>=3 and np.all(sd>0):
        corrmat=cov/np.outer(sd,sd)
        if np.linalg.matrix_rank(corrmat)==2 and np.all(np.linalg.eigvalsh(corrmat)>0):
            valid=True; corr=float(corrmat[0,1])
            q=np.einsum('ij,ji->i',delta/sd,np.linalg.solve(corrmat,(delta/sd).T))
            radius=float(quantile(q,w,.95))
    return dict(mean=mean,cov=cov,sd=sd,lo=lo,hi=hi,joint_valid=valid,joint_radius=radius,corr=corr,unique_cal_pairs=unique)

def pf_s0(public,cfg,arm,n,seed,checkpoints,prior='area',cutoff_sigma=None):
    """First range enters via radial initialization only; no external initial pose."""
    if set(public)!=set(PUBLIC_KEYS): raise ValueError('Only approved S0 observation keys permitted')
    rng=np.random.default_rng(seed); x=np.zeros((n,6))
    x[:,3:]=rng.normal(size=(n,3))*np.asarray(cfg['p0_std'])[3:]
    radial=None
    if arm!='DR':
        if not public['range_mask'][0]: raise ValueError('First range observation required')
        radial=radial_table(float(public['range_m'][0]),cfg['range_sigma'],cfg['robot_z']-cfg['anchor_xyz'][2],prior,cutoff_sigma)
        x[:,0]=radial.sample(rng,n); x[:,2]=rng.uniform(-np.pi,np.pi,n)
    initial=x[:,:3].copy(); ancestry=np.arange(n); w=np.full(n,1/n)
    snapshots=[]; raw={}; resamples=0; miness=float(n); updates=0
    for k in range(len(public['t_s'])):
        logw=np.log(w,where=w>0,out=np.full(n,-np.inf))
        if k:
            d,g,o,dt=(public[key][k] for key in ('ds_odom','dtheta_gyro','dtheta_odom','dt_s'))
            bg,sf,eps=x[:,3:].T; den=1+sf; level=1-eps**2/4; b=cfg['wheel_base']
            if np.any(den<=0) or np.any(level<=0): raise ValueError('invalid calibration support')
            qd=cfg['k_s']*abs(d); qg=cfg['gyro_N_rad_sqrt_s']**2*dt
            qo=cfg['k_theta']*abs(o)+cfg['k_stheta']*abs(d)
            b1=-eps/b; b2=-level/den; variance=b1*b1*qd+b2*b2*qg+qo
            if np.any(variance<=0): raise ValueError('nonpositive odometry variance')
            innovation=o-(level*(g-bg*dt)/den+eps*d/b)
            noise=rng.normal(size=(3,n))*np.sqrt([qd,qg,qo])[:,None]
            correction=(innovation-b1*noise[0]-b2*noise[1]-noise[2])/variance
            nd=noise[0]+qd*b1*correction; ng=noise[1]+qg*b2*correction
            a=(g-ng-bg*dt)/den; u=d-nd-eps*b*a/4
            step=u*np.sinc(a/(2*np.pi)); mid=x[:,2]+a/2
            x[:,0]+=step*np.cos(mid); x[:,1]+=step*np.sin(mid)
            x[:,2]=(x[:,2]+a+np.pi)%(2*np.pi)-np.pi
            logw+=-.5*(np.log(2*np.pi*variance)+innovation**2/variance)
            if arm!='DR' and public['range_mask'][k]:
                r=np.sqrt(np.sum(x[:,:2]**2,axis=1)+(cfg['robot_z']-cfg['anchor_xyz'][2])**2)
                logw+=-.5*((public['range_m'][k]-r)**2/cfg['range_sigma']**2+np.log(2*np.pi*cfg['range_sigma']**2))
                updates+=1
        w=np.exp(logw-np.max(logw)); w/=w.sum()
        if not np.all(np.isfinite(w)): raise ValueError('invalid PF weights')
        ess=1/np.sum(w*w); miness=min(miness,ess)
        if k in checkpoints:
            s=summary(x[:,3:],w); ini=initial[ancestry]
            delta_hist=np.histogram(ini[:,2],bins=np.linspace(-np.pi,np.pi,25),weights=w)[0]
            s.update(k=k,t_s=float(public['t_s'][k]),ess=float(ess),min_ess=float(miness),ancestors=int(len(np.unique(ancestry))),resamples=resamples,range_updates_after_initialization=updates,
                initial_rho_quantiles=[float(quantile(ini[:,0],w,q)) for q in [.025,.5,.975]],initial_delta_hist=delta_hist,
                initial_delta_resultant=float(abs(w@np.exp(1j*ini[:,2]))),reference_status='REFERENCE_NOT_VALIDATED')
            snapshots.append(s); raw[f'cal_{k}']=x[:,3:].copy();raw[f'weights_{k}']=w.copy()
            raw[f'initial_rho_delta_{k}']=ini[:,[0,2]].copy()
        if ess<n/2 and k+1<len(public['t_s']):
            cdf=np.cumsum(w);cdf[-1]=1
            ix=np.searchsorted(cdf,(rng.random()+np.arange(n))/n)
            x=x[ix].copy();ancestry=ancestry[ix];w.fill(1/n);resamples+=1
    return snapshots,raw,radial.diagnostics if radial is not None else {'initial_range_used':False}

def score(s,truth):
    c=truth[[3,5]]; error=s['mean']-c; joint=None
    if s['joint_valid']:
        z=error/s['sd']; correlation=s['cov']/np.outer(s['sd'],s['sd'])
        joint=bool(z@np.linalg.solve(correlation,z)<=s['joint_radius'])
    return dict(bg_error_dps=float(np.rad2deg(error[0])),eps_error=float(error[1]),bg_sd_dps=float(np.rad2deg(s['sd'][0])),eps_sd=float(s['sd'][1]),bg_coverage=bool(s['lo'][0]<=c[0]<=s['hi'][0]),eps_coverage=bool(s['lo'][1]<=c[1]<=s['hi'][1]),joint_coverage=joint,corr=s['corr'],ancestors=s['ancestors'],ess=s['ess'])

def run(out):
    design=json.loads((HERE/'I2_S0_DESIGN.json').read_text());out.mkdir(parents=True,exist_ok=False)
    write(out/'I2_S0_DESIGN.json',design)
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();rows=[];radials=[];inputs_hashes={}
    for ri,route in enumerate(design['routes']):
      for world in design['worlds']:
       for seed in design['seeds']:
        ep=f'{world}_{route}_d2_s{seed}';src=HERE/design['input_root']/ep;dest=out/ep;dest.mkdir()
        # Truth is loaded only for score(), never provided to pf_s0 or batch_s0.
        truth=np.load(src/'truth.npz')['truth6']
        inputs_hashes[str((src/'truth.npz').relative_to(HERE))]=hashlib.sha256((src/'truth.npz').read_bytes()).hexdigest()
        arms=[('DR',.05,5)]+[(f'RANGE_{s}_{r}',s,r) for s in design['sigma_m'] for r in design['rates_hz']]
        for ai,(arm,sigma,rate) in enumerate(arms):
            path=src/f'{arm}_public.npz';config_path=src/f'{arm}_config.json'
            for p in [path,config_path]:inputs_hashes[str(p.relative_to(HERE))]=hashlib.sha256(p.read_bytes()).hexdigest()
            with np.load(path) as z:public={k:z[k].copy() for k in PUBLIC_KEYS}
            cfg=json.loads(config_path.read_text());cfg['anchor_xyz']=[0,0,cfg['anchor_xyz'][2]]
            # Pose stds are not used; calibration entries remain frozen.
            cfg['p0_std'][:3]=[0,0,0]
            np.savez_compressed(dest/f'{arm}_public.npz',**public);write(dest/f'{arm}_config.json',cfg)
            checkpoints=sorted(set(round(f*(len(public['t_s'])-1)) for f in design['snapshots_fraction']))
            variants=[('area',None)]
            if world=='A2_3_GAUSS_LEVEL' and seed in [8000,8001] and arm!='DR' and rate==5:
                variants += [(p,None) for p in design['prior_sensitivity']['priors']]
            if world=='A2_3_GAUSS_LEVEL' and seed==8000 and arm=='RANGE_0.2_5':
                variants += [('area',c) for c in design['domain_sensitivity']['upper_range_cutoff_sigma']]
            for prior,cutoff in variants:
                label=f'{arm}_{prior}'+(f'_cut{cutoff}' if cutoff is not None else '')
                s,raw,rad=pf_s0(public,cfg,arm,8192,[20261013,2301,ri,seed,ai,0],checkpoints,prior,cutoff)
                write(dest/f'{label}_posterior.json',s);np.savez_compressed(dest/f'{label}_pf.npz',**raw)
                radials.append(dict(episode=ep,arm=arm,prior=prior,cutoff=cutoff,diagnostics=rad))
                for snap in s:rows.append(dict(episode=ep,world=world,route=route,seed=seed,arm=arm,prior=prior,cutoff=cutoff,label=label,k=snap['k'],t_s=snap['t_s'],**score(snap,truth[snap['k']])))
            focus=world=='A2_3_GAUSS_LEVEL' and seed==8000 and arm in design['pf_reference']['arms']
            if focus:
                for n in design['pf_reference']['particle_counts']:
                    for repeat in range(2):
                        s,raw,_=pf_s0(public,cfg,arm,n,[20261013,2301,ri,seed,ai,n,repeat+1],checkpoints)
                        label=f'{arm}_area_N{n}_rep{repeat}'
                        write(dest/f'{label}_posterior.json',s);np.savez_compressed(dest/f'{label}_pf.npz',**raw)
                for prior in ['area'] if arm=='DR' else design['batch']['range_priors']:
                    b=batch_s0(public,cfg,'DR' if arm=='DR' else 'RANGE',seed+ri*100,design['batch'],prior)
                    arrays={k:b.pop(k) for k in list(b) if isinstance(b[k],np.ndarray)}
                    np.savez_compressed(dest/f'{arm}_{prior}_batch.npz',**arrays)
                    write(dest/f'{arm}_{prior}_batch.json',b)
            print(ep,arm,'done',flush=True)
    pd.DataFrame(rows).to_csv(out/'I2_S0_CALIBRATION_POSTERIOR.csv',index=False)
    write(out/'I2_S0_RADIAL_INITIALIZATION.json',radials)
    sources=[HERE/n for n in ['I2_S0_DESIGN.json','S0_CONTRACT_KO.md','i2_s0.py','i2_s0_batch.py','i2_batch.py','i2_ideal_range_calibration.py']]
    write(out/'I2_S0_RUN_MANIFEST.json',dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,executable=sys.executable,python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),exit_code=0,code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},input_sha256=inputs_hashes,output_sha256={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
