#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import hs_lut as HL,pattern_apply as PA,observation as O,sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from pole_safe_model import PoleSafeModel
from rf_pose_index import sha256,PoseIndex
RUN=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff'
B=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
T=ROOT/'results/DRIVE_SIM_20261007/S1/routes'
BANK_SHA=['b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9']


def load():
    banks=[]
    for name,expected in zip(['LP_plus45_bank.npz','LP_minus45_bank.npz'],BANK_SHA):
        p=ROOT/name
        if not p.exists() or p.stat().st_size<1000:raise RuntimeError('ORIGINAL_FFD_LFS_NOT_MATERIALIZED')
        assert sha256(p)==expected,'FFD hash mismatch'
        banks.append(PA.Bank(np.load(p)))
    meta=json.loads((RUN/'LUT/hs_lut_meta.json').read_text());m=meta['meta']
    old=HL.HsLut(dict(theta_deg=m['theta_deg'],phi_deg=np.arange(m['phi_deg'][0],m['phi_deg'][1]+.01,m['phi_deg'][2]),s=np.load(RUN/'LUT/hs_lut_2deg.npy')))
    return banks,old,meta


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--seeds',type=int,default=8);a=ap.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
    banks,old,meta=load();safe=PoleSafeModel(old,banks)
    coeffpath=out/'CARTESIAN_POLE_FIELD_V1.npz'
    np.savez_compressed(coeffpath,coeff=safe.field.coeff,origin=safe.field.origin,terms=np.asarray(safe.field.terms),freq=safe.field.freq,scale=safe.field.scale)
    cases={c['case']:c for c in json.loads((B/'CASES.json').read_text())}
    labels=pd.read_csv(RUN/'OUTPUT/02_LABELS_EVAL_ONLY.csv');features=pd.read_csv(RUN/'OUTPUT/01_FEATURES.csv')
    rec=[]
    for case,g in labels.groupby('case'):
        c=cases[case];anchor=c['anchor_xyz'];psi=np.radians(g.true_yaw_deg)
        pred=safe(anchor,c['robot_z'],g.true_x.to_numpy(),g.true_y.to_numpy(),psi,c['mount_deg'])
        for i,(_,r) in enumerate(g.iterrows()):
            rho=math.hypot(r.true_x-anchor[0],r.true_y-anchor[1]);th=math.degrees(math.atan2(rho,anchor[2]-c['robot_z']))
            rec.append(dict(case=case,pose_id=int(r.pose_id),rho_m=rho,theta_deg=th,s_los=r.s_los,
                old_s=r.s_lut_truth,new_s=float(pred[i]),old_error=r.s_los-r.s_lut_truth,new_error=r.s_los-pred[i]))
    regression=pd.DataFrame(rec);regression.to_csv(out/'ALL_9519_NATIVE_LOS_REGRESSION.csv.gz',index=False)
    assert len(regression)==9519
    outer=regression[regression.theta_deg>=3.]
    assert np.max(abs(outer.old_s-outer.new_s))<1e-10,'Unrelated LUT region changed'
    # New approach points reference direct original FFD contraction, not a new PathSolver run.
    ring=[];jacrows=[];seams=[]
    anchor=np.array([4.,0.,2.65]);z=.45
    for mount in [0.,45.]:
        for yawdeg in [-180.,-179.,0.,45.,90.,179.,180.]:
            psi=math.radians(yawdeg)
            for rho in [0.,1e-5,1e-4,1e-3,.01,.03,.05,.10,.25,.5]:
                for bearing in range(0,360,45):
                    p=anchor.copy();p[2]=z;p[0]+=rho*math.cos(math.radians(bearing));p[1]+=rho*math.sin(math.radians(bearing))
                    val,J=safe(anchor,z,p[0],p[1],psi,mount,True)
                    d=p-anchor;d/=np.linalg.norm(d)
                    h=HL.los_h(banks,d,yawdeg+mount,10.)
                    direct=float(O.observe(h[None],banks[0].freqs_hz,None,None)['s'][0])
                    ring.append(dict(mount=mount,yaw=yawdeg,rho=rho,bearing=bearing,new_s=val,direct_ffd_s=direct,error=val-direct,Jxy=float(np.linalg.norm(J[:2]))))
                    if rho<=.05 and yawdeg in [0.,45.,179.]:
                        fd=[]
                        for j in range(3):
                            pp=[p[0],p[1],psi];mm=list(pp);pp[j]+=1e-6;mm[j]-=1e-6
                            fd.append((safe(anchor,z,*pp,mount)-safe(anchor,z,*mm,mount))/2e-6)
                        jacrows.append(dict(mount=mount,yaw=yawdeg,rho=rho,bearing=bearing,max_abs_gradient_error=float(np.max(abs(J-np.array(fd))))))
            for theta in [1.,3.]:
                rho=2.2*math.tan(math.radians(theta));u=rho*math.cos(.37);v=rho*math.sin(.37)
                left=safe(anchor,z,4+u*(1-1e-7),v*(1-1e-7),psi,mount,True)
                right=safe(anchor,z,4+u*(1+1e-7),v*(1+1e-7),psi,mount,True)
                seams.append(dict(mount=mount,yaw=yawdeg,theta=theta,value_jump=float(abs(left[0]-right[0])),gradient_jump=float(np.max(abs(left[1]-right[1])))))
    ring=pd.DataFrame(ring);jacrows=pd.DataFrame(jacrows);seams=pd.DataFrame(seams)
    ring.to_csv(out/'NEW_POINT_DIRECT_FFD_RING.csv',index=False);jacrows.to_csv(out/'POLE_H_J_PARITY.csv',index=False);seams.to_csv(out/'C0_C1_BLEND_BOUNDARIES.csv',index=False)
    print('V03_FIELD_REGRESSION_DONE',len(ring),len(regression),flush=True)
    # Isolate h/H change only: preserve legacy receiver noise constants/offset for all four arms.
    metrics=[];tails=[];routes={}
    for route in ['R2','R4','R5']:
        full=pd.read_csv(T/f'timeline_{route}_T10.csv');no=pd.read_csv(T/f'timeline_{route}_Tnone.csv')
        kkeep=np.flatnonzero(full.phase!='probe');assert np.array_equal(full.iloc[kkeep].pose_id,no.pose_id)
        t=full.t_s.to_numpy();pose=full[['x','y','yaw_body_deg']].to_numpy(float);pose[:,2]=np.radians(pose[:,2])
        ds,dt=V.motion_increments(t,pose,convention='legacy-euler',tolerance=1e-8)
        routes[route]=(full,no,kkeep,t,pose,ds,dt)
    for case,g in labels.groupby('case'):
        c=cases[case];full,no,kkeep,t,truth,ds,dth=routes[case[:2]];obs=features[features.case==case].set_index('pose_id')
        for level in [0,1,2]:
            for seed in range(a.seeds):
                inp,_=V.generate(t,ds,dth,V.SensorV2Config(level=level,condition='all'),seed)
                for arm in ['ORIGINAL','EST_RHO_GUARD','THETA2_CLAMP','CARTESIAN_CANDIDATE']:
                    cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=True,use_s=True,
                        anchor_xyz=tuple(c['anchor_xyz']),robot_z=c['robot_z'],mount_deg=c['mount_deg'],bias_rw_std=0.,
                        range_offset=float(meta['range_bias']['mean_m']))
                    x0=np.r_[truth[0],0.,0.,0.];x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.asarray(cfg.p0_std[:3])
                    f=F.SensorV2Filter(cfg,old,x0);errs=[];skipped=0
                    for j,k in enumerate(kkeep):
                        if k:f.step(inp['ds_odom'][k],inp['dtheta_gyro'][k],inp['dtheta_odom'][k],.2)
                        o=obs.loc[int(no.pose_id.iloc[j])]
                        if bool(o.detected):
                            f.range_record(float(o.range_m));x,P=f.mean_cov();rho=float(np.linalg.norm(x[:2]-c['anchor_xyz'][:2]))
                            if arm=='ORIGINAL':f.s_record(float(o.s),(float(o.power1),float(o.power2)))
                            elif arm=='EST_RHO_GUARD' and rho<.1:skipped+=1
                            elif arm=='EST_RHO_GUARD':f.s_record(float(o.s),(float(o.power1),float(o.power2)))
                            else:
                                if arm=='CARTESIAN_CANDIDATE':h,J=safe(c['anchor_xyz'],c['robot_z'],*x[:3],c['mount_deg'],True)
                                else:
                                    # Clamp remains explicitly diagnostic; finite-difference the CLAMPED observation.
                                    def hc(xx):
                                        aa=np.asarray(c['anchor_xyz']);delta=xx[:2]-aa[:2];rr=np.linalg.norm(delta)
                                        if rr<2.2*np.tan(np.radians(2.)) and rr>1e-12:
                                            xy=aa[:2]+delta*(2.2*np.tan(np.radians(2.))/rr)
                                        else:xy=xx[:2]
                                        return float(HL.s_model(old,c['anchor_xyz'],c['robot_z'],*xy,xx[2],c['mount_deg']))
                                    h=hc(x);J=np.zeros(3)
                                    for d in range(3):
                                        xp=x.copy();xm=x.copy();xp[d]+=1e-6;xm[d]-=1e-6;J[d]=(hc(xp)-hc(xm))/2e-6
                                H=np.zeros(6);H[:3]=J;f.scalar(float(o.s),h,H,f._s_R(float(o.power1),float(o.power2)),'s')
                        x,P=f.mean_cov();e=truth[k]-x[:3];e[2]=V.wrap(e[2])
                        if no.t_s.iloc[j]>=30.:
                            ne=float(e@np.linalg.solve(P[:3,:3],e));errs.append([*e,ne])
                            if ne>1000 and seed==0 and level==0:
                                tails.append(dict(case=case,arm=arm,pose_id=int(no.pose_id.iloc[j]),progress_s=float(no.t_s.iloc[j]),NEES=ne,
                                    estimated_rho=float(np.linalg.norm(x[:2]-c['anchor_xyz'][:2])),true_rho=float(np.linalg.norm(truth[k,:2]-c['anchor_xyz'][:2]))))
                    e=np.array(errs);metrics.append(dict(case=case,level=level,seed=seed,arm=arm,n_eval=len(e),
                        heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:,2]**2)))),position_rmse_m=float(np.sqrt(np.mean(e[:,0]**2+e[:,1]**2))),
                        pose_NEES=float(e[:,3].mean()),pose95coverage=float(np.mean(e[:,3]<=7.814727903251179)),guard_skips=skipped))
        print('V03_FILTER_CASE_DONE',case,flush=True)
    metrics=pd.DataFrame(metrics);metrics.to_csv(out/'MATCHED_POLE_FILTER_REPLAY.csv',index=False)
    pd.DataFrame(tails).to_csv(out/'NEES_TAIL_POSE_JOIN.csv',index=False)
    stats=metrics.groupby('arm')[['heading_rmse_deg','position_rmse_m','pose_NEES','pose95coverage']].mean();stats.to_csv(out/'POLE_FILTER_SUMMARY.csv')
    near=regression.rho_m<.1
    status={'id':'V03','execution':'COMPLETE','model_version':safe.model_version,
       'model_coeff_sha256':sha256(coeffpath),'original_lut_sha256':sha256(RUN/'LUT/hs_lut_2deg.npy'),
       'bank_sha256':BANK_SHA,'fit_receipts':safe.field.fit_receipts,'native_LoS_regression_n':len(regression),
       'new_direct_FFD_points':len(ring),'fresh_native_PathSolver_points':0,
       'near9_old_s_RMS':float(np.sqrt(np.mean(regression.loc[near,'old_error']**2))),
       'near9_new_s_RMS':float(np.sqrt(np.mean(regression.loc[near,'new_error']**2))),
       'new_direct_FFD_max_error':float(ring.error.abs().max()),
       'analytic_gradient_vs_FD_max_error':float(jacrows.max_abs_gradient_error.max()),
       'blend_value_jump':float(seams.value_jump.max()),'blend_gradient_jump':float(seams.gradient_jump.max()),
       'outside3deg_regression':'PASS_UNCHANGED','paired_filter_runs':len(metrics),
       'fresh_native_near_pole_validation':'NOT_RUN','scientific_PASS':False,
       'filter_summary':stats.reset_index().to_dict('records')}
    (out/'NEW_LUT_VERSION_SHA.json').write_text(json.dumps(status,indent=2));(out/'STATUS.json').write_text(json.dumps(status,indent=2))
    for name in ['pole_safe_model.py','run_v03_pole_recovery.py']:(out/name).write_bytes(Path(__file__).with_name(name).read_bytes())
    print('V03_RESULT',json.dumps(status),flush=True)

if __name__=='__main__':main()
