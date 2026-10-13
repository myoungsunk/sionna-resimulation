"""I2 development: public-input static-calibration PF and truth-only scoring."""
from pathlib import Path
import sys, json, hashlib, datetime, platform
from dataclasses import asdict
import numpy as np
import pandas as pd
from i2_batch import batch_posterior

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write(p, obj):
    def default(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    Path(p).write_text(json.dumps(obj, indent=2, default=default, allow_nan=False), encoding='utf-8')

def quantile(x, w, q):
    ix = np.argsort(x)
    return np.interp(q, np.cumsum(w[ix]), x[ix])

def summarize(x, w):
    c = x[:, [3,5]]
    mean = w @ c
    delta = c-mean
    cov = (delta*w[:,None]).T @ delta
    sd = np.sqrt(np.diag(cov))
    lo = np.array([quantile(c[:,j],w,.025) for j in range(2)])
    hi = np.array([quantile(c[:,j],w,.975) for j in range(2)])
    valid = bool(np.all(sd > 0) and np.linalg.det(cov) > 0)
    radius = None
    corr = None
    if valid:
        radius = float(quantile(np.einsum('ij,ji->i',delta,np.linalg.solve(cov,delta.T)),w,.95))
        corr = float(cov[0,1]/np.prod(sd))
    return dict(mean=mean,cov=cov,sd=sd,lo=lo,hi=hi,joint_radius=radius,corr=corr,joint_valid=valid)

def pf(public, cfg, arm, n, seed, checkpoints):
    """No truth access; Matheron conditional proposal, static parameters, no jitter."""
    rng = np.random.default_rng(seed)
    x = public['x0'] + np.asarray(cfg['p0_std'])*rng.normal(size=(n,6))
    w = np.full(n,1/n); ancestors = np.arange(n)
    snapshots = []; raw = {}; min_ess = float(n); resamples = 0
    b = cfg['wheel_base']
    for k in range(len(public['t_s'])):
        logw = np.log(w, where=w>0, out=np.full(n,-np.inf))
        if k:
            d,g,o,dt = [public[key][k] for key in ('ds_odom','dtheta_gyro','dtheta_odom','dt_s')]
            bg,sf,eps = x[:,3:].T
            den=1+sf; level=1-eps**2/4
            if np.any(den<=0) or np.any(level<=0): raise ValueError('invalid calibration support')
            qd=cfg['k_s']*abs(d); qg=cfg['gyro_N_rad_sqrt_s']**2*dt
            qo=cfg['k_theta']*abs(o)+cfg['k_stheta']*abs(d)
            b1=-eps/b; b2=-level/den
            s=b1*b1*qd+b2*b2*qg+qo
            if np.any(s<=0): raise ValueError('nonpositive innovation variance')
            y=o-(level*(g-bg*dt)/den+eps*d/b)
            noise=rng.normal(size=(3,n))*np.sqrt([qd,qg,qo])[:,None]
            correction=(y-b1*noise[0]-b2*noise[1]-noise[2])/s
            nd=noise[0]+qd*b1*correction; ng=noise[1]+qg*b2*correction
            a=(g-ng-bg*dt)/den; u=d-nd-eps*b*a/4
            step=u*np.sinc(a/(2*np.pi)); mid=x[:,2]+a/2
            x[:,0]+=step*np.cos(mid); x[:,1]+=step*np.sin(mid)
            x[:,2]=(x[:,2]+a+np.pi)%(2*np.pi)-np.pi
            logw+=-.5*(np.log(2*np.pi*s)+y*y/s)
        if arm != 'DR' and public['range_mask'][k]:
            anchor=np.asarray(cfg['anchor_xyz'])
            r=np.sqrt(np.sum((x[:,:2]-anchor[:2])**2,axis=1)+(cfg['robot_z']-anchor[2])**2)
            logw+=-.5*((public['range_m'][k]-r)**2/cfg['range_sigma']**2+np.log(2*np.pi*cfg['range_sigma']**2))
        w=np.exp(logw-np.max(logw)); w/=w.sum()
        if not np.all(np.isfinite(w)): raise ValueError('invalid weights')
        ess=1/np.sum(w*w); min_ess=min(min_ess,ess)
        if k in checkpoints:
            summary=summarize(x,w)
            summary.update(k=k,t_s=float(public['t_s'][k]),ess=float(ess),ancestors=int(len(np.unique(ancestors))),resamples=resamples,min_ess=float(min_ess))
            snapshots.append(summary)
            raw[f'cal_{k}']=x[:,3:].copy(); raw[f'weights_{k}']=w.copy()
        if ess < n/2 and k+1<len(public['t_s']):
            cdf=np.cumsum(w); cdf[-1]=1
            idx=np.searchsorted(cdf,(rng.random()+np.arange(n))/n)
            x=x[idx].copy(); ancestors=ancestors[idx]; w.fill(1/n); resamples+=1
    return snapshots,raw

def score(summary, truth):
    c=truth[[3,5]]; e=summary['mean']-c
    joint=None
    if summary['joint_valid']:
        joint=bool(e@np.linalg.solve(summary['cov'],e)<=summary['joint_radius'])
    return dict(bg_mean_dps=float(np.rad2deg(summary['mean'][0])),eps_mean=float(summary['mean'][1]),
        bg_error_dps=float(np.rad2deg(e[0])),eps_error=float(e[1]),
        bg_sd_dps=float(np.rad2deg(summary['sd'][0])),eps_sd=float(summary['sd'][1]),
        bg_coverage=bool(summary['lo'][0]<=c[0]<=summary['hi'][0]),eps_coverage=bool(summary['lo'][1]<=c[1]<=summary['hi'][1]),
        joint_coverage=joint,bg_eps_corr=summary['corr'],ess=summary.get('ess'),ancestors=summary.get('ancestors'))

def run(out):
    # Generation import stays outside pf()/batch_posterior(); these consume public dictionaries only.
    sys.path.insert(0,str(ROOT/'research/DR_EKF_DIAGNOSIS_20261013'))
    import dr_harness as H
    design_path=HERE/'out/I2_DESIGN.json'
    design=json.loads(design_path.read_text())
    out.mkdir(parents=True,exist_ok=False)
    write(out/'I2_DESIGN.json',design)
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows=[]; references=[]
    for route_idx,route in enumerate(design['routes']):
      for world in design['worlds']:
       for seed in design['seeds']:
        episode=f'{world}_{route}_d2_s{seed}'; dest=out/episode; dest.mkdir()
        inputs,ev,params,truth=H.make_world(H.ARMS[world],route,2,seed)
        cfg=asdict(H.make_cfg(H.ARMS[world],2,params))
        public={k:np.array(inputs[k],copy=True) for k in ('t_s','dt_s','ds_odom','dtheta_gyro','dtheta_odom')}
        public['x0']=H.initial_state(H.ARMS[world],route,seed,params,cfg['p0_std'])
        z=np.random.default_rng([20261013,2202,route_idx,seed]).normal(size=len(truth))
        anchor=np.asarray(design['anchor_xyz']); cfg.update(anchor_xyz=anchor.tolist(),robot_z=design['robot_z'])
        distance=np.sqrt(np.sum((truth[:,:2]-anchor[:2])**2,axis=1)+(cfg['robot_z']-anchor[2])**2)
        np.savez_compressed(dest/'truth.npz',truth6=truth)
        write(dest/'config.json',cfg)
        checkpoints=sorted(set(int(round(f*(len(truth)-1))) for f in design['snapshots_fraction']))
        arms=[('DR',.05,5)]+[(f'RANGE_{s}_{r}',s,r) for s in design['sigma_m'] for r in design['rates_hz']]
        for arm_idx,(arm,sigma,rate) in enumerate(arms):
            cfg['range_sigma']=sigma
            public['range_m']=distance+sigma*z
            public['range_mask']=np.ones(len(truth),bool) if rate==5 else np.isclose((public['t_s']-public['t_s'][0])%1,0,atol=1e-8)
            # Treat timestamps just below integer seconds symmetrically.
            if rate==1: public['range_mask']=np.isclose(public['t_s']-public['t_s'][0],np.round(public['t_s']-public['t_s'][0]),atol=1e-8)
            if arm=='DR': public['range_mask'][:]=False
            np.savez_compressed(dest/f'{arm}_public.npz',**public)
            write(dest/f'{arm}_config.json',cfg)
            summaries,raw=pf(public,cfg,arm,design['primary_particles'],[20261013,2203,route_idx,seed,arm_idx,0],checkpoints)
            np.savez_compressed(dest/f'{arm}_pf.npz',**raw)
            write(dest/f'{arm}_posterior.json',summaries)
            for summary in summaries:
                rows.append(dict(episode=episode,route=route,world=world,seed=seed,arm=arm,sigma_m=sigma,rate_hz=rate,k=summary['k'],t_s=summary['t_s'],**score(summary,truth[summary['k']])))
            if world=='A2_3_GAUSS_LEVEL' and seed==8000 and arm in design['pf_validation']['arms']:
                high=[]
                for repeat in range(2):
                    s,r=pf(public,cfg,arm,16384,[20261013,2203,route_idx,seed,arm_idx,repeat+1],checkpoints)
                    np.savez_compressed(dest/f'{arm}_pf_high_{repeat}.npz',**r)
                    write(dest/f'{arm}_pf_high_{repeat}.json',s); high.append(s[-1])
                batch=batch_posterior(public,cfg,[len(truth)-1],'DR' if arm=='DR' else 'RANGE',seed+100*route_idx,design['batch'])
                np.savez_compressed(dest/f'{arm}_batch.npz',samples=batch.pop('samples'),pose_samples=batch.pop('pose_samples'),calibration_samples=batch.pop('calibration_samples'))
                write(dest/f'{arm}_batch.json',batch)
                references.append(dict(episode=episode,arm=arm,batch=batch['diagnostics'],status='REFERENCE_NOT_VALIDATED',primary_ancestors=summaries[-1]['ancestors'],high_ancestors=[s['ancestors'] for s in high]))
            print(episode,arm,'completed',flush=True)
    pd.DataFrame(rows).to_csv(out/'I2_CALIBRATION_POSTERIOR.csv',index=False)
    write(out/'I2_REFERENCE_VALIDATION.json',dict(status='REFERENCE_NOT_VALIDATED',cases=references,reason='Qualification requires independent terminal posterior agreement and convergence review.'))
    write(out/'I2_GATE.json',dict(execution='PASS',overall='INCONCLUSIVE',practical_sufficiency='INCONCLUSIVE',S0='NOT_RUN',I3='NOT_RUN',I7='NOT_RUN',reason=['Operational error budget absent by user clarification','S0 gauge/domain pending','Reference qualification pending diagnostics; no gold posterior assumption']))
    sources=[Path(__file__),HERE/'i2_batch.py',design_path,Path(H.__file__)]+list(H.FROZEN_SRC.rglob('*.py'))+[H.MOTION_DIR/f'MOTION_{r}.csv' for r in design['routes']]
    write(out/'I2_RUN_MANIFEST.json',dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,executable=sys.executable,python=platform.python_version(),numpy=np.__version__,platform=platform.platform(),exit_code=0,input_code_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},outputs_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
