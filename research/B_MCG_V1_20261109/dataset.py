"""Evidence loading is separate from online allowlist and monitor inference."""
from pathlib import Path
import sys,json,os
import numpy as np
from numerics import OnlineSeries,extract_B,SPEC,sha,save,dump,metrics
ROUTES=('R2','R4','R5')

def load(repo,assets,out):
    repo=Path(repo);assets=Path(assets);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    src=repo/'research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources'
    records=json.loads((repo/'research/FP_NATIVE_B_CAUSAL_ABLATION_20261108/RELEASE_INPUT_LOCK.json').read_text())['files']
    receipt=[]
    for r in records:
        p=assets/r['asset_name']
        if p.stat().st_size!=r['size'] or sha(p)!=r['sha256']:raise ValueError(('INPUT_SHA',p.name))
        receipt.append(dict(name=p.name,sha256=sha(p),bytes=p.stat().st_size))
        if p.name.startswith('LP_'):
            dest=src/p.name
            if not dest.exists():os.link(p,dest)
            if sha(dest)!=r['sha256']:raise ValueError('BANK_STAGE_MISMATCH')
    sys.path[:0]=[str(src/'src'),str(src/'research/FFD_P0P3_20261016'),str(src/'research/EKF4_RANGE_S_STAGED_20261014')]
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from qclean_uwb.drivesim import observation
    core,online,model,hashes=load_original_model(src)
    data={}
    for route in ROUTES:
        on=dict(np.load(assets/f'{route}_B0_Full_10__online.npz',allow_pickle=False))
        ev=dict(np.load(assets/f'{route}_B0_Full_10__evaluator.npz',allow_pickle=False))
        assert np.array_equal(on['t'],ev['t']) and np.array_equal(on['pose_id'],ev['pose_id'])
        B,z,features=extract_B(on['Hrf'],observation)
        native=observation.first_path_batch(observation.cir_batch(on['Hrf']),1950000.)
        assert np.max(abs(on['z']-np.column_stack([native['range_m'],native['s']])))<1e-10
        data[route]=dict(on=on,ev=ev,B=B,z=z,features=features)
    dump(out/'INPUT_LOCK.json',dict(files=receipt,n=sum(len(v['z']) for v in data.values()),source_hashes=hashes))
    return core,online,model,data,hashes

def series(d,fit=None):
    on=d['on'];mu=on['muMB'].copy();mub=on['muBASE'].copy();R=on['R'].copy()
    if fit is not None:mu+=fit['delta_mu'];mub+=fit['delta_mu'];R+=fit['R_add_diag']
    return OnlineSeries(on['t'],on['ds'],on['gy'],on['dt'],d['z'],mu,R,on['x0'],on['P0'],mub)

def train_stats(model,data):
    stats={}
    for route,d in data.items():
        truth=d['ev']['truth'];hs=[]
        for j in range(0,len(truth),32):
            q=np.c_[truth[j:j+32],np.zeros(len(truth[j:j+32]))];hs.append(model.batch(q,SPEC)[0])
        h=np.concatenate(hs);rN=d['on']['z']-h-d['on']['muMB'];rB=d['z']-h-d['on']['muMB']
        stats[route]=dict(diff=d['z']-d['on']['z'],covN=np.cov(rN.T,ddof=0),covB=np.cov(rB.T,ddof=0),htrue=h,rB=rB)
    return stats

def calibration(stats,test):
    train=[r for r in ROUTES if r!=test]
    mu=np.mean([stats[r]['diff'].mean(0) for r in train],axis=0)
    cd=np.mean([stats[r]['covB']-stats[r]['covN'] for r in train],axis=0)
    return dict(delta_mu=mu,R_add_diag=np.diag(np.maximum(np.diag(cd),0)),training_routes=train)

def baselines(core,online,model,data,repo,out):
    out=Path(out);traces={};checks={}
    for route,d in data.items():
        s=series(d);on=d['on'];controls=s.controls()
        native=online.replay(s.packet()|{'z':on['z']},controls,'W0',core,model,SPEC)
        errors={}
        for key in ['prior','Pprior','h','H','Reff','K','mask']:
            actual=native[key];expected=on['trace_'+key]
            errors['NN_'+key]=float(np.max(abs(actual.astype(float)-expected.astype(float))/np.maximum(1,abs(expected))))
        tr=online.replay(s.packet(),controls,'W0',core,model,SPEC)
        oldpath=Path(repo)/'research/FP_SC_RECOVERY_R0_R5_20261107/R45_RUN_001'/f'{route}_TRACE.npz'
        with np.load(oldpath,allow_pickle=False) as old:
            for key,orig in [('x','x'),('P','P'),('prior','prior'),('Pprior','Pprior'),('H','H'),('h','h'),('K','K'),('Reff','R'),('mask','accepted')]:
                expected=old[orig][:,0];actual=tr[key]
                errors['B_'+key]=float(np.max(abs(actual.astype(float)-expected.astype(float))/np.maximum(1,abs(expected))))
        if max(errors.values())>1e-10:raise ValueError(('BASELINE_PARITY',route,errors))
        checks[route]=errors;traces[route]=tr
        save(out/f'{route}_B.npz',**tr,t=s.t,z=s.z,features=d['features'])
        dump(out/'P0_BASELINE.json',dict(status='PASS',routes=checks,max_error=max(max(v.values()) for v in checks.values())))
        print('P0_PASS',route,max(errors.values()),flush=True)
    return traces
