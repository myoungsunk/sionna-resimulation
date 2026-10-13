"""R2-2: A_DR (RF off) consistency decomposition. Criteria and configurations: R22_ADR_PREREG_KO.md (frozen before this script ran).
Uses the frozen sensor-v2 generator and EKF (RUN_01a124ff source); ensemble NEES over N seeds per (route, drift) cell.
usage: r22_adr_decomposition.py OUT_DIR [--n 300] [--procs 4]"""
import argparse,json,math,sys,time
from multiprocessing import Pool
from pathlib import Path
import numpy as np
from scipy.stats import chi2
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS
ROUTES=('R2','R4','R5');LEVELS=(0,1,2);SEED0=6000
MOT={r:dict(np.load(HERE/f'inputs_R2/MOTION_{r}_legacy-euler.npz')) for r in ROUTES}
CONFIGS={'B0':dict(),
 'G_none':dict(cond='none'),'G_gyro_bias':dict(cond='gyro_bias'),'G_gyro_sf':dict(cond='gyro_sf'),'G_wheel_asym':dict(cond='wheel_asymmetry'),'G_wheelbase':dict(cond='wheelbase'),
 'G_wheel_noise':dict(cond='wheel_noise'),'G_gyro_noise':dict(cond='gyro_noise'),'G_slip':dict(cond='slip'),
 'F1_known_eb':dict(known=True),'F2_prior_matched':dict(prior=True),'F1F2':dict(known=True,prior=True),'D_Qx2':dict(q=2.0),'D_Qx4':dict(q=4.0)}
def one(task):
    name,route,level,seed=task;c=CONFIGS[name];m=MOT[route];t=m['t'];truth=m['pose']
    inputs,ev=V.generate(t,m['ds'],m['dtheta'],V.SensorV2Config(level=level,condition=c.get('cond','all')),seed)
    known=float(ev['true_parameters'][3]) if c.get('known') else 0.
    p0=[0.03,0.03,math.radians(2.),math.radians(0.12),0.0104,0.0064]
    if c.get('prior'):
        L=DRIFT_LEVELS[level];p0[3]=math.radians(L.gyro_bias_dps);p0[4]=L.gyro_sf;p0[5]=L.wheel_ratio
    q=c.get('q',1.0)
    cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=False,use_s=False,anchor_xyz=(4.0,0.0,2.65),mount_deg=0.,robot_z=0.45,bias_rw_std=0.,known_wheelbase_error=known,p0_std=tuple(p0),
        k_s=2e-5*q,k_theta=1e-4*q,k_stheta=1e-5*q,gyro_N_rad_sqrt_s=math.radians(.015)*math.sqrt(q))
    x0=np.r_[truth[0],0.,0.,0.];x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.array(p0[:3])
    f=F.SensorV2Filter(cfg,None,x0);n=len(t);nees=np.full(n,np.nan);err=np.zeros((n,3))
    for k in range(n):
        if k:f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
        est,cov=f.mean_cov();e=truth[k]-est[:3];e[2]=V.wrap(e[2]);err[k]=e;P=cov[:3,:3]
        if np.linalg.eigvalsh(P).min()>0:nees[k]=e@np.linalg.solve(P,e)
    return task,nees.astype(np.float32),np.hypot(err[:,0],err[:,1]).astype(np.float32),err[:,2].astype(np.float32)
def metrics(N,nees,t):
    keep=t>=30;A=np.nanmean(nees[:,keep],axis=0);cut=int(0.75*keep.sum());lo,hi=chi2.ppf([.025,.975],3*N)/N
    cov=float(np.nanmean(nees[:,keep]<=chi2.ppf(.95,3)));per_run=np.nanmean(nees[:,keep],axis=1)
    return dict(anees=float(np.nanmean(A)),anees_late25=float(np.nanmean(A[cut:])),coverage95=cov,frac_k_inside_chi2_interval=float(np.mean((A>=lo)&(A<=hi))),per_run_mean_nees_median=float(np.median(per_run)),per_run_mean_nees_mean=float(np.mean(per_run)),
        consistent=bool(2.4<=np.nanmean(A)<=3.6 and 0.92<=cov<=0.98 and 2.4<=np.nanmean(A[cut:])<=3.6),
        direction='OVERCONFIDENT' if np.nanmean(A)>3.6 else ('CONSERVATIVE' if np.nanmean(A)<2.4 else 'IN_BAND'))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('out');ap.add_argument('--n',type=int,default=300);ap.add_argument('--procs',type=int,default=4);a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    tasks=[(nm,r,l,SEED0+s) for nm in CONFIGS for r in ROUTES for l in LEVELS for s in range(a.n)];t0=time.time();res={}
    with Pool(a.procs) as pool:
        for i,(task,nees,pe,he) in enumerate(pool.imap_unordered(one,tasks,chunksize=20)):
            res[task]=(nees,pe,he)
            if i%2000==0:print(i,len(tasks),'%.0fs'%(time.time()-t0),flush=True)
    summary={};cellrows=[]
    for nm in CONFIGS:
        cells={}
        for r in ROUTES:
            for l in LEVELS:
                arr=np.stack([res[(nm,r,l,SEED0+s)][0] for s in range(a.n)]);pe=np.stack([res[(nm,r,l,SEED0+s)][1] for s in range(a.n)]);keep=MOT[r]['t']>=30
                mt=metrics(a.n,arr.astype(float),MOT[r]['t']);mt['pos_rmse_m']=float(np.sqrt(np.mean(pe[:,keep].astype(float)**2)));mt['heading_rmse_deg']=float(np.degrees(np.sqrt(np.mean(np.stack([res[(nm,r,l,SEED0+s)][2] for s in range(a.n)])[:,keep].astype(float)**2))))
                cells[f'{r}_d{l}']=mt;cellrows.append(dict(config=nm,cell=f'{r}_d{l}',**mt))
        summary[nm]=dict(all_cells_consistent=all(c['consistent'] for c in cells.values()),n_consistent=int(sum(c['consistent'] for c in cells.values())),n_overconfident=int(sum(c['direction']=='OVERCONFIDENT' for c in cells.values())),n_conservative=int(sum(c['direction']=='CONSERVATIVE' for c in cells.values())),
            anees_median_over_cells=float(np.median([c['anees'] for c in cells.values()])),cells=cells)
    legit=['B0','F2_prior_matched','F1_known_eb','F1F2'];first=next((k for k in legit if summary[k]['all_cells_consistent']),None)
    verdict=('DR_BASELINE_FOUND:'+first) if first else 'DR_MODEL_MISMATCH_UNRESOLVED'
    doc=dict(n_seeds=a.n,seed0=SEED0,verdict=verdict,legit_order=legit,configs=summary,seconds=time.time()-t0)
    (out/'R22_ADR_DECOMPOSITION.json').write_text(json.dumps(doc,indent=1))
    import csv
    with open(out/'R22_ADR_CELLS.csv','w',newline='') as fh:
        w=csv.DictWriter(fh,fieldnames=list(cellrows[0]));w.writeheader();w.writerows(cellrows)
    for k,v in summary.items():print(f"{k:18s} consistent {v['n_consistent']}/9 over {v['n_overconfident']} cons {v['n_conservative']} medianANEES {v['anees_median_over_cells']:.2f}")
    print(verdict)
