#!/usr/bin/env python3
"""V02 operating-envelope confirmatory run. See PREREG_ENVELOPE_KO.md (committed before execution).
Usage: run_envelope.py --repo-root <extracted abc-gated-resume tree> --out <dir>
"""
import argparse,hashlib,json,sys,time,platform
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import chi2,binom
ap=argparse.ArgumentParser();ap.add_argument('--repo-root',required=True,type=Path);ap.add_argument('--out',required=True,type=Path);a=ap.parse_args()
sys.path[:0]=[str(a.repo_root/'src')]
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.body_ekf_bridge import V2BodyFilterConfig as Config
DT=.2;N=240;CHECK=(0,60,120,240);SEEDS=range(2000,2512)
LAMBDAS=(0.3,0.4,0.5,0.75,1.0);XY0=0.10;YAW0=np.radians(5.)
CAL={'CAL_SMALL':np.array([.001,.002,.003]),'CAL_LARGE':np.asarray(Config().p0_std,float)[3:]}
NOMINAL=np.array([2.,.5,.2,0.,0.,0.])
def traj():
    ds=np.r_[0.,np.full(N,.04)];ang=np.r_[0.,.012*np.sin(np.arange(N)/17)];ds[181:201]=0.;ang[181:201]=.04;return ds,ang
def cfg():
    return Config(model_version='sensor-v2',kind='ekf',s_mode='direct',use_s=False,use_range=False,anchor_xyz=(4.,0.,2.65),robot_z=.45,
        range_offset=0.,range_sigma=.08,range_extra_sigma=0.,range_quant_var=0.,bias_rw_std=0.,gate=float('inf'))
def trial(std,seed,with_range):
    eps=np.random.default_rng([20261011,seed,2002]).normal(size=6)*std;truth0=NOMINAL+eps
    par=dict(gyro_bias=float(truth0[3]),gyro_sf=float(truth0[4]),wheel_asymmetry=float(truth0[5]),wheelbase=0.,common_scale=0.)
    ds,ang=traj();t=np.arange(N+1)*DT
    inp,ev=V.generate(t,ds,ang,V.SensorV2Config(level=1,condition='all',slip_mode='off'),seed,parameters=par)
    pt=dict(zip([str(s) for s in ev['parameter_names']],ev['true_parameters']));tr=V.integrate(ds,ang,truth0[:3])
    truth=np.c_[tr,ev['true_bias_rad_s'],np.full(N+1,pt['gyro_sf']),np.full(N+1,pt['wheel_asymmetry'])]
    f=F.SensorV2Filter(cfg(),None,NOMINAL.copy(),P0=np.diag(std**2));nr=np.random.default_rng([20261011,seed,8002]).normal(0,.08,N+1)
    E=[];Ps=[]
    for k in range(N+1):
        if k:f.step(float(inp['ds_odom'][k]),float(inp['dtheta_gyro'][k]),float(inp['dtheta_odom'][k]),DT)
        if with_range:f.range_record(float(np.sqrt((truth[k,0]-4.)**2+truth[k,1]**2+2.2**2))+nr[k])
        if k in CHECK:
            x,P=f.mean_cov();e=truth[k]-x;e[2]=V.wrap(e[2]);E.append(e);Ps.append(P.copy())
    return np.array(E),np.array(Ps)
if __name__=='__main__':
    o=a.out;o.mkdir(parents=True,exist_ok=True);rows=[];store={};t0=time.time();FAM=len(LAMBDAS)*len(CAL)*len(CHECK);alpha=.05/FAM
    for calname,cal in CAL.items():
        for lam in LAMBDAS:
            std=np.r_[lam*XY0,lam*XY0,lam*YAW0,cal]
            for wr in (True,False):
                R=[trial(std,s,wr) for s in SEEDS];E=np.stack([r[0] for r in R]);P=np.stack([r[1] for r in R]);n=len(E)
                key=f'{calname}|{lam}|{"RANGE" if wr else "OFF"}';store[key+'|E']=E;store[key+'|P']=P
                for j,k in enumerate(CHECK):
                    e=E[:,j,:3];C=P[:,j,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(C,e[...,None])[...,0])
                    lo,hi=chi2.ppf([alpha/2,1-alpha/2],3*n)/n;cl,ch=binom.ppf([alpha/2,1-alpha/2],n,.95)/n;cov=float(np.mean(nees<=chi2.ppf(.95,3)))
                    rows.append(dict(cal=calname,lam=lam,xy_sigma_m=lam*XY0,yaw_sigma_deg=float(np.degrees(lam*YAW0)),mode='RANGE' if wr else 'OFF',k=k,time_s=k*DT,n=n,
                        mean_NEES=float(nees.mean()),NEES_lo=float(lo),NEES_hi=float(hi),NEES_ok=bool(lo<=nees.mean()<=hi),
                        cov95=cov,cov_lo=float(cl),cov_hi=float(ch),cov_ok=bool(cl<=cov<=ch),
                        hdg_MSE_over_P=float(np.mean(E[:,j,2]**2)/P[:,j,2,2].mean()),pos_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,1))))))
                print(key,'NEES48=%.3f cov=%.3f'%(rows[-1]['mean_NEES'],rows[-1]['cov95']),'elapsed %.0f'%(time.time()-t0),flush=True)
                pd.DataFrame(rows).to_csv(o/'RESULTS_ENVELOPE.csv',index=False)
    d=pd.DataFrame(rows);d['ok']=d.NEES_ok&d.cov_ok;prim=d[d['mode']=='RANGE']
    status={'id':'V02_ENVELOPE','execution':'COMPLETE','seeds':[2000,2511],'n_per_prior':len(SEEDS),'family_tests':FAM,'alpha_per_test':alpha,'envelope':{},'failed_checkpoints':[]}
    for calname in CAL:
        best=None
        for lam in LAMBDAS:
            ok=bool(prim[(prim.cal==calname)&(prim.lam==lam)].ok.all())
            if not ok:break
            best=lam
        status['envelope'][calname]=None if best is None else dict(lam_max=best,xy_sigma_m=best*XY0,yaw_sigma_deg=float(np.degrees(best*YAW0)))
    status['failed_checkpoints']=prim[~prim.ok][['cal','lam','k','mean_NEES','cov95']].to_dict('records')
    status['stage_A_PASS']=False;status['note']='PASS_IN_ENVELOPE only; V02 not promoted to full PASS; outside-envelope failures retained'
    status['versions']=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__)
    status['source_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),a.repo_root/'src/qclean_uwb/drivesim/filter_v2.py',a.repo_root/'src/qclean_uwb/drivesim/sensor_v2.py']}
    (o/'STATUS_ENVELOPE.json').write_text(json.dumps(status,indent=2));np.savez_compressed(o/'TENSORS_ENVELOPE.npz',**store)
    print('ENVELOPE_RESULT',json.dumps({k:status[k] for k in ('envelope','family_tests')}),flush=True)
