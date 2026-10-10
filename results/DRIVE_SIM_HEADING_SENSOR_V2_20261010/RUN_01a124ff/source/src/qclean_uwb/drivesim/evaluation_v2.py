"""Bounded evaluation and raw evidence; synthetic sensors are explicitly labelled."""
from __future__ import annotations
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import numpy as np
from . import sensor_v2 as V, filters as F, experiment as E
from .filter_v2 import run_filter_v2
from .hs_lut import s_model
from .config import build_manifest, file_sha256

class IdealRatio:
    """Analytic synthetic ratio, NOT an FFD/RF-derived LUT or a heading observation."""
    def __call__(self, theta, phi_tx, phi_rx, with_grad=False):
        a=np.radians(phi_rx); h=.6*np.cos(a)
        if not with_grad:return h
        zeros=np.zeros_like(h)
        return h,np.stack([zeros,zeros,-.6*np.sin(a)*np.pi/180],axis=-1)


def mixed_world(dt=.2):
    controls=((2,0,0),(12,.2,0),(8,.1,0),(4,0,.25),(8,.15,-.2),(8,-.15,0),(4,0,-.25),(12,.25,0),(6,0,0))
    ds=[0.];a=[0.]
    for duration,v,w in controls:
        if abs(duration/dt-round(duration/dt))>1e-10: raise ValueError('dt must divide segment durations')
        ds.extend([v*dt]*round(duration/dt));a.extend([w*dt]*round(duration/dt))
    ds,a=np.array(ds),np.array(a);t=np.arange(len(ds))*dt;pose=V.integrate(ds,a)
    rows=[dict(idx=k,t_s=float(t[k]),x=float(pose[k,0]),y=float(pose[k,1]),yaw_body_deg=float(np.degrees(pose[k,2])),
               turn_phase=bool(abs(a[k])>0),drive_g=k,probe_id=-1,phase='drive') for k in range(len(t))]
    return E.World(rows,np.empty((len(t),0,2,2)),np.empty(0),0.,0.,None,route='synthetic-mixed'),ds,a


def directional(truth,est,ds,a,anchor):
    error=est[:,:2]-truth[:,:2];c=np.cos(truth[:,2]);s=np.sin(truth[:,2])
    rho=truth[:,:2]-np.array(anchor[:2]);r=np.linalg.norm(rho,axis=1)
    valid=r>1e-6;unit=np.zeros_like(rho);unit[valid]=rho[valid]/r[valid,None]
    # Body frame exists during stop/reverse; movement-aligned interpretation is masked.
    body=np.column_stack([error[:,0]*c+error[:,1]*s,-error[:,0]*s+error[:,1]*c])
    radial=np.sum(error*unit,axis=1);tangent=-error[:,0]*unit[:,1]+error[:,1]*unit[:,0]
    radial[~valid]=np.nan;tangent[~valid]=np.nan
    estimated_a=np.r_[0.,V.wrap(np.diff(est[:,2]))]
    heading_reintegration=V.integrate(ds,estimated_a,est[0,:3])
    return dict(body_forward_m=body[:,0],body_lateral_m=body[:,1],anchor_radial_m=radial,anchor_tangential_m=tangent,
                anchor_direction_valid=valid,body_motion_valid=np.abs(ds)>1e-12,reverse_mask=ds<0,stop_mask=(ds==0)&(a==0),
                auxiliary_heading_reintegrated_pose=heading_reintegration)


def serialize(obj):
    if isinstance(obj,dict):return {k:serialize(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [serialize(v) for v in obj]
    if isinstance(obj,np.ndarray):return serialize(obj.tolist())
    if isinstance(obj,np.generic):return serialize(obj.item())
    if isinstance(obj,float) and not np.isfinite(obj):return None
    return obj


def plain_output(pose):
    n=len(pose);est=np.zeros((n,6));est[:,:3]=pose
    return dict(est=est,cov3=np.full((n,3,3),np.nan),stats=dict(s_updates=0,s_rejected=0,r_updates=0,r_rejected=0,nis_s=[]))


def evaluate(outdir,seed_start=200,count=48,initials=('exact','legacy-prior'),wheelbases=('matched','unknown'),condition='all',level=1,dt=.2,sensor_config=None,filter_config=None):
    outdir=Path(outdir)
    if outdir.exists() and any(outdir.iterdir()): raise FileExistsError('output directory must be empty')
    outdir.mkdir(parents=True,exist_ok=True);rawdir=outdir/'raw';rawdir.mkdir()
    world,ds,a=mixed_world(dt);t=world.t;truth=world.truth;n=len(t);lut=IdealRatio();records=[];files=[]
    methods=('ideal_increments','wheel_only','wheel_distance_gyro_fixed','wheel_gyro_online','online_range','online_range_s_ideal_ratio')
    for init in initials:
        for wb in wheelbases:
            for seed in range(seed_start,seed_start+count):
                sensor=sensor_config or V.SensorV2Config(level=level,condition=condition)
                inputs,ev=V.generate(t,ds,a,sensor,seed,dict(wheelbase=0. if wb=='matched' else .0075))
                base=filter_config or F.FilterConfig(model_version='sensor-v2',dt=dt,bias_rw_std=0.,use_range=False,use_s=False)
                x0=np.r_[truth[0],0.,0.,0.];P0=np.diag(np.array(base.p0_std)**2)
                if init=='exact': P0[:3,:3]=0
                else: x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.array(base.p0_std[:3])
                draw=V.rng(seed,'observation')
                true_range=np.sqrt(np.sum((truth[:,:2]-np.array(base.anchor_xyz[:2]))**2,axis=1)+(base.anchor_xyz[2]-base.robot_z)**2)
                # No tap quantization, range bias, first-path detector, antenna or RF solver here.
                obs=dict(detected=np.ones(n,bool),range_m=true_range+draw.normal(0,.05,n),
                         s=s_model(lut,base.anchor_xyz,base.robot_z,*truth.T)+draw.normal(0,.09,n),power=np.ones((n,2)))
                flags=dict(turn_phase=world.turn_phase)
                for method in methods:
                    cfg=base
                    if method=='ideal_increments':out=plain_output(V.integrate(ds,a,x0[:3]))
                    elif method=='wheel_only':out=plain_output(V.integrate(inputs['ds_odom'],inputs['dtheta_odom'],x0[:3]))
                    elif method=='wheel_distance_gyro_fixed':out=plain_output(V.integrate(inputs['ds_odom'],inputs['dtheta_gyro'],x0[:3]))
                    else:
                        cfg=replace(base,use_range=method!='wheel_gyro_online',use_s=method=='online_range_s_ideal_ratio')
                        out=run_filter_v2(cfg,lut if cfg.use_s else None,inputs,obs,flags,x0,P0)
                    summary=E.summarize_output(world,out)
                    m=summary['metrics']
                    if 'cov_full' not in out:
                        for key in ('nees_mean','nees_cov95','heading_cov95'):m[key]=None
                        endpoint_nees=None;endpoint_cov=None
                    else:
                        err=out['est'][-1,:3]-truth[-1];err[2]=V.wrap(err[2]);P=out['cov3'][-1]
                        endpoint_nees=float(err@np.linalg.solve(P,err));endpoint_cov=endpoint_nees<=E.CHI2_3_95
                    directions=directional(truth,out['est'],ds,a,base.anchor_xyz)
                    keep=t>=E.EXCLUDE_S
                    for key in ('body_forward_m','body_lateral_m','anchor_radial_m','anchor_tangential_m'):
                        values=directions[key][keep];m[key+'_rmse']=float(np.sqrt(np.nanmean(values**2)))
                    row=dict(seed=seed,initial=init,wheelbase=wb,method=method,condition=sensor.condition,
                             observation='synthetic_range_ratio' if cfg.use_s else ('synthetic_range' if cfg.use_range else 'none'),
                             endpoint_pose_nees=endpoint_nees,endpoint_pose_cov95=endpoint_cov,metrics=m)
                    records.append(row)
                    archive=dict(time_s=t,evaluation_truth_pose=truth,estimate_state=out['est'],initial_state=x0,initial_prior=P0,
                                 evaluation_mask=keep,common_mask=(world.probe_id<0)&(world.drive_g>=E.COMMON_FROM_DRIVE_G),seed=np.array(seed))
                    archive.update({'sensor_'+k:np.asarray(v) for k,v in inputs.items()})
                    archive.update({'evaluation_'+k:np.asarray(v) for k,v in ev.items()})
                    archive.update({'observation_'+k:np.asarray(v) for k,v in obs.items()})
                    archive.update(directions)
                    effective_distance=inputs['ds_odom']
                    archive['auxiliary_distance_reintegrated_pose']=V.integrate(effective_distance,a,x0[:3])
                    # Reintegrations use measured distance/estimated heading separately, never a causal attribution.
                    if 'cov_full' in out:
                        archive['estimate_covariance_full']=out['cov_full'];archive.update(out['observation_trace'])
                    else:archive['covariance_available']=np.array(False)
                    stem=f'{init}_{wb}_{seed}_{method}';p=rawdir/(stem+'.npz')
                    with p.open('xb') as f:np.savez_compressed(f,**archive)
                    files.append(p)
                print(f'completed {init}/{wb}/seed{seed}',flush=True)
    results=outdir/'runs.json';results.write_text(json.dumps(serialize(records),indent=2,allow_nan=False),encoding='utf8');files.append(results)
    aggregated=[]
    for init in initials:
        for wb in wheelbases:
            for method in methods:
                selected=[r for r in records if r['initial']==init and r['wheelbase']==wb and r['method']==method]
                nees=[r['endpoint_pose_nees'] for r in selected if r['endpoint_pose_nees'] is not None]
                rmse=np.array([r['metrics']['pos_rmse_common_m'] for r in selected])
                aggregated.append(dict(initial=init,wheelbase=wb,method=method,n_runs=len(selected),common_pos_rmse_mean_m=float(rmse.mean()),common_pos_rmse_std_m=float(rmse.std(ddof=1)) if count>1 else None,
                                       endpoint_nees_mean=float(np.mean(nees)) if nees else None,
                                       endpoint_coverage95=float(np.mean([r['endpoint_pose_cov95'] for r in selected])) if nees else None,
                                       inference_claim='synthetic bounded diagnostic; no RF/scientific acceptance gate'))
    aggregate=outdir/'aggregate.json';aggregate.write_text(json.dumps(serialize(aggregated),indent=2),encoding='utf8');files.append(aggregate)
    root=Path(__file__).resolve().parents[3]
    source=[root/'src/qclean_uwb/drivesim'/x for x in ('sensor_v2.py','filter_v2.py','evaluation_v2.py','filters.py','experiment.py','sensors.py','hs_lut.py','observation.py')]
    prereg=root/'results/SENSOR_V2_20261008/PREREG_V2.md'
    config=dict(model_version='sensor-v2',sensor=sensor.manifest(),filter=asdict(base),filter_method_overrides={m:dict(use_range=m in ('online_range','online_range_s_ideal_ratio'),use_s=m=='online_range_s_ideal_ratio') for m in methods},dt_s=dt,seed_start=seed_start,n_runs=count,
                initializations=list(initials),wheelbase_conditions=list(wheelbases),methods=methods,
                synthetic_observation='range sigma .05m + analytic ratio .6cos(phi_rx) sigma .09; no RF H/LUT used',
                synthetic_range_filter_R='legacy .05^2 + tap quantization variance + extra .05^2 preserved, intentionally exceeds synthetic generator',
                evaluation_unit='independent seed/run; times are correlated',calibration_data='none, no fitting or tuning',
                truth_field_policy='evaluation_* only; generator/controlled initialization and evaluation use truth; EKF receives measurements only',
                covariance_policy='full covariance only for online EKF; deterministic/fixed baselines do not claim a prior',
                code_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                modified_source_hashes={str(p.relative_to(root)):file_sha256(p) for p in source})
    manifest=build_manifest(config=config,inputs=source+[prereg],outputs=files)
    (outdir/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return aggregated
