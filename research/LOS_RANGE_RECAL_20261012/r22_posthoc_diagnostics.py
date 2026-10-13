"""R2-2 POST-HOC diagnostics (labelled exploratory, run AFTER the pre-registered decomposition returned DR_MODEL_MISMATCH_UNRESOLVED).
Question: why is A_DR over-confident (ANEES 13-26 with wheel noise alone)? Tests: (1) odom innovation calibration, (2) eigen-direction z-variance of the pose covariance over time,
(3) convention mismatch of the motion integrator, (4) sweep of the calibration-state prior with the wheel-noise-only generator (small heading uncertainty -> EKF linearisation regime).
usage: r22_posthoc_diagnostics.py OUT_JSON [--seeds 150]"""
import json,math,sys
from pathlib import Path
import numpy as np
from scipy.stats import chi2
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import r22_adr_decomposition as R
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
SEEDS=int(sys.argv[3]) if len(sys.argv)>3 and sys.argv[2]=='--seeds' else 150;out={}
def mkfilter(cal,odom=True):
    p0=[0.03,0.03,math.radians(2.)]+list(cal);return p0,FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=False,use_s=False,bias_rw_std=0.,p0_std=tuple(p0),use_odom_heading=odom)
D=math.radians;DEF=(D(.12),.0104,.0064)
# (3) convention mismatch: exact sensors + exact init
out['convention_mismatch_max_pos_err_m']={}
for route in R.ROUTES:
    m=R.MOT[route];inputs,ev=V.generate(m['t'],m['ds'],m['dtheta'],V.SensorV2Config(level=1,condition='none'),6000);p0,cfg=mkfilter(DEF,odom=False);f=F.SensorV2Filter(cfg,None,np.r_[m['pose'][0],0,0,0.]);mx=0.
    for k in range(len(m['t'])):
        if k:f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
        mx=max(mx,float(np.hypot(*(m['pose'][k,:2]-f.mean_cov()[0][:2]))))
    out['convention_mismatch_max_pos_err_m'][route]=mx
# (1)(2) R2, wheel-noise only, default prior
m=R.MOT['R2'];t=m['t'];truth=m['pose'];ks=[int(np.searchsorted(t,x)) for x in (30,60,100,150,195)];Zs={k:[] for k in ks};zi=[]
for s in range(SEEDS):
    inputs,ev=V.generate(t,m['ds'],m['dtheta'],V.SensorV2Config(level=1,condition='wheel_noise'),6000+s);p0,cfg=mkfilter(DEF)
    x0=np.r_[truth[0],0.,0.,0.];x0[:3]+=V.rng(6000+s,'initial').normal(size=3)*np.array(p0[:3]);f=F.SensorV2Filter(cfg,None,x0)
    for k in range(len(t)):
        if k:r=f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k]);zi.append(r['innovation']/math.sqrt(r['S']))
        if k in ks:
            est,cov=f.mean_cov();e=truth[k]-est[:3];e[2]=V.wrap(e[2]);w,Vv=np.linalg.eigh(cov[:3,:3]);Zs[k].append((Vv.T@e)/np.sqrt(w))
zi=np.array(zi);out['odom_innovation_normalised']=dict(var=float(zi.var()),mean=float(zi.mean()),lag1=float(np.corrcoef(zi[:-1],zi[1:])[0,1]))
out['eigen_direction_z_variance_R2_wheel_noise']={f't={t[k]:.0f}s':[float(v) for v in np.array(Zs[k]).var(axis=0)] for k in ks}
# (4) calibration-prior sweep, wheel-noise-only generator, level 1
def anees(route,cal):
    m=R.MOT[route];t=m['t'];truth=m['pose'];keep=t>=30;N=[];hP=[]
    for s in range(SEEDS):
        inputs,ev=V.generate(t,m['ds'],m['dtheta'],V.SensorV2Config(level=1,condition='wheel_noise'),6000+s);p0,cfg=mkfilter(cal)
        x0=np.r_[truth[0],0.,0.,0.];x0[:3]+=V.rng(6000+s,'initial').normal(size=3)*np.array(p0[:3]);f=F.SensorV2Filter(cfg,None,x0);n=np.full(len(t),np.nan)
        for k in range(len(t)):
            if k:f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
            est,cov=f.mean_cov();e=truth[k]-est[:3];e[2]=V.wrap(e[2]);n[k]=e@np.linalg.solve(cov[:3,:3],e)
        N.append(n);hP.append(math.degrees(math.sqrt(cov[2,2])))
    N=np.array(N)[:,keep];return dict(anees=float(np.nanmean(np.nanmean(N,axis=0))),coverage95=float(np.nanmean(N<=chi2.ppf(.95,3))),end_heading_P_sigma_deg=float(np.mean(hP)))
out['cal_prior_sweep_wheel_noise_only']={f'{r}|{lab}':anees(r,tuple(c*sc for c in DEF)) for r in R.ROUTES for lab,sc in (('default',1.0),('div10',0.1),('div100',0.01))}
out['note']='post-hoc, exploratory; supports (does not prove) that A_DR inconsistency tracks heading uncertainty (EKF linearisation), not Q/F/G mismatch in the small-uncertainty regime'
Path(sys.argv[1]).write_text(json.dumps(out,indent=1));print(json.dumps(out,indent=1))
