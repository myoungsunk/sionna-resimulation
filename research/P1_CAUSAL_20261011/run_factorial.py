#!/usr/bin/env python3
"""P1 causal CHANNEL ablations; no new filter tuning and no field-performance claim.
Truth is used only for oracle measurement controls and final evaluation.
All real inputs are stored noise-free H-derived FP powers and ranges.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np,pandas as pd
from common import ROOT,RUN,B,T,CASES,models,receipt,PoseIndex,sha256
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.body_ekf_bridge import V2BodyFilterConfig
from qclean_uwb.drivesim import hs_lut as HL
CHI=7.814727903251179
RANGE_MODES=('IDEAL','LOS','FULL')
S_MODES=('NONE','MODEL','LOS','FULL')
ARMS=[('NONE','NONE'),('NONE','FULL')]+[(r,s) for r in RANGE_MODES for s in S_MODES]

def config(c,meta):
    return V2BodyFilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_s=True,use_range=True,anchor_xyz=tuple(c['anchor_xyz']),robot_z=float(c['robot_z']),mount_deg=float(c['mount_deg']),bias_rw_std=0.,known_wheelbase_error=0.,range_offset=float(meta['range_bias']['mean_m']))

def inputs(case,safe):
    c=next(x for x in json.loads((B/'CASES.json').read_text()) if x['case']==case)
    samples=json.loads((B/case/'SAMPLES.json').read_text())
    full=pd.read_csv(T/f'timeline_{case[:2]}_T10.csv');no=pd.read_csv(T/f'timeline_{case[:2]}_Tnone.csv')
    _,receipt_full=PoseIndex(samples,len(samples)).timeline(full,case)
    _,receipt_no=PoseIndex(samples,len(samples)).timeline(no,case)
    keep=np.flatnonzero(full.phase!='probe');assert np.array_equal(full.iloc[keep].pose_id,no.pose_id)
    labels=pd.read_csv(RUN/'OUTPUT/02_LABELS_EVAL_ONLY.csv');labels=labels[labels.case==case].set_index('pose_id')
    features=pd.read_csv(RUN/'OUTPUT/01_FEATURES.csv');features=features[features.case==case].set_index('pose_id')
    assert not labels.index.duplicated().any() and not features.index.duplicated().any()
    idlist=full.pose_id.to_numpy(dtype=int)
    lab=labels.loc[idlist];feat=features.loc[idlist]
    truth=full[['x','y','yaw_body_deg']].to_numpy(float);truth[:,2]=np.radians(truth[:,2])
    assert np.max(abs(truth[:,:2]-lab[['true_x','true_y']].to_numpy()))<=5.1e-7
    t=full.t_s.to_numpy(float);ds,dth=V.motion_increments(t,truth,convention='legacy-euler',tolerance=1e-8)
    dist=np.sqrt((truth[:,0]-c['anchor_xyz'][0])**2+(truth[:,1]-c['anchor_xyz'][1])**2+(c['anchor_xyz'][2]-c['robot_z'])**2)
    htrue=safe(c['anchor_xyz'],c['robot_z'],truth[:,0],truth[:,1],truth[:,2],c['mount_deg'])
    data=dict(case=case,c=c,full=full,no=no,keep=keep,t=t,truth=truth,ds=ds,dth=dth,dist=dist,htrue=htrue,
        ranges={'LOS':lab.range_los.to_numpy(float),'FULL':feat.range_m.to_numpy(float)},
        signs={'MODEL':htrue,'LOS':lab.s_los.to_numpy(float),'FULL':feat.s.to_numpy(float)},
        powers=feat[['power1','power2']].to_numpy(float),detected=feat.detected.to_numpy(bool),ids=idlist)
    data['audit']=dict(case=case,n_T10=len(full),n_Tnone=len(no),n_covered_T10=len(receipt_full),n_covered_Tnone=len(receipt_no),all_pose_ids_verified=True)
    return data

def one_sensor(data,cfg,level,seed):
    inp,_=V.generate(data['t'],data['ds'],data['dth'],V.SensorV2Config(level=level,condition='all'),seed)
    x0=np.r_[data['truth'][0].copy(),0.,0.,0.]
    x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.asarray(cfg.p0_std[:3])
    return inp,x0

def range_update(f,data,k,rmode):
    if rmode=='NONE':return None
    z=(float(data['dist'][k])+f.cfg.range_offset if rmode=='IDEAL' else float(data['ranges'][rmode][k]))
    if not np.isfinite(z) or not data['detected'][k]:return None
    return f.range_record(z)

def s_update(f,data,k,smode,safe):
    if smode=='NONE':return None
    z=float(data['signs'][smode][k])
    if not np.isfinite(z) or not data['detected'][k]:return None
    x,P=f.mean_cov();c=data['c'];h,j=safe(c['anchor_xyz'],c['robot_z'],*x[:3],c['mount_deg'],True)
    H=np.zeros(6);H[:3]=j
    R=f._s_R(*data['powers'][k])
    return f.scalar(z,float(h),H,float(R),'s')

def measure(f,truth,anchor):
    x,P=f.mean_cov();err=truth-x[:3];err[2]=V.wrap(err[2]);P3=P[:3,:3]
    ne=float(err@np.linalg.solve(P3,err));hn=float(err[2]**2/P3[2,2])
    pc=P3[:2,:2]-np.outer(P3[:2,2],P3[2,:2])/P3[2,2];ec=err[:2]-P3[:2,2]*err[2]/P3[2,2]
    xn=float(ec@np.linalg.solve(pc,ec));assert abs(ne-hn-xn)<1e-6*max(1,ne)
    r=x[:2]-np.asarray(anchor[:2]);r/=max(np.linalg.norm(r),1e-12);v=np.array([-r[1],r[0]])
    rv=float(r@P3[:2,:2]@r);tv=float(v@P3[:2,:2]@v)
    return dict(ex=float(err[0]),ey=float(err[1]),ep=float(err[2]),nees=ne,heading_nees=hn,xy_cond_nees=xn,
        radial_z2=float((r@err[:2])**2/max(rv,1e-20)),tangent_z2=float((v@err[:2])**2/max(tv,1e-20)),
        heading_var=float(P3[2,2]),radial_sigma=math.sqrt(max(rv,0)),min_xy_cond_sigma=float(np.sqrt(max(np.linalg.eigvalsh(pc)[0],0))))

def fullrun(data,cfg,lut,safe,inp,x0,rm,sm,level,seed):
    f=F.SensorV2Filter(cfg,lut,x0.copy());samples=[];ns=[];nr=[];rejr=rejs=accr=accs=0;snap=[]
    for j,k in enumerate(data['keep']):
        if k:f.step(inp['ds_odom'][k],inp['dtheta_gyro'][k],inp['dtheta_odom'][k],.2)
        for mode,result in [('r',range_update(f,data,k,rm)),('s',s_update(f,data,k,sm,safe))]:
            if result is not None:
                y,R,S,status=result
                if S>0 and np.isfinite(y):
                    if mode=='r':nr.append(y*y/S)
                    else:ns.append(y*y/S)
                if mode=='r':rejr+=status=='rejected';accr+=status=='applied'
                else:rejs+=status=='rejected';accs+=status=='applied'
        if data['no'].t_s.iloc[j]<30.:continue
        m=measure(f,data['truth'][k],data['c']['anchor_xyz']);samples.append(m)
        if level==0 and seed==0 and j%20==0:
            x,P=f.mean_cov();snap.append(dict(case=data['case'],range=rm,s=sm,pose_id=int(data['ids'][k]),progress_s=float(data['no'].t_s.iloc[j]),x6=x.tolist(),P6=P.tolist(),**m))
    a=pd.DataFrame(samples);assert len(a)=={'R2':829,'R4':592,'R5':1265}[data['case'][:2]]
    out=dict(case=data['case'],route=data['case'][:2],mount_deg=data['c']['mount_deg'],level=level,seed=seed,range_mode=rm,s_mode=sm,n_eval=len(a),
        heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(a.ep**2)))),position_rmse_m=float(np.sqrt(np.mean(a.ex**2+a.ey**2))),
        pose_nees=float(a.nees.mean()),pose_nees_median=float(a.nees.median()),heading_nees=float(a.heading_nees.mean()),xy_cond_nees=float(a.xy_cond_nees.mean()),
        pose95coverage=float(np.mean(a.nees<=CHI)),heading95coverage=float(np.mean(a.ep.abs()<=1.95996398454*np.sqrt(a.heading_var))),
        radial_z2=float(a.radial_z2.mean()),tangent_z2=float(a.tangent_z2.mean()),radial_sigma_median=float(a.radial_sigma.median()),min_xy_cond_sigma_median=float(a.min_xy_cond_sigma.median()),
        range_nis_mean=float(np.mean(nr)) if nr else None,s_nis_mean=float(np.mean(ns)) if ns else None,range_applied=accr,range_rejected=rejr,s_applied=accs,s_rejected=rejs)
    return out,snap

def station_controls(data,cfg,lut,safe,inp,x0,level,seed):
    # RF-off prior continues over the SAME original T10 physical timeline.
    # Each stationary packet comparison starts from the same pre-range x6/P6.
    results=[];base=F.SensorV2Filter(cfg,lut,x0.copy());full=data['full'];stations={}
    for g,part in full[full.phase=='probe'].groupby('drive_g'):
        before=full[(full.phase=='drive')&(full.drive_g==g)]
        if len(before)!=1:continue
        i0=int(before.index[0]);part10=part[np.isclose(part.probe_offset_deg,10.)];part20=part[np.isclose(part.probe_offset_deg,20.)]
        if len(part10)==0 or len(part20)==0:continue
        i1=int(part10.index[0]);i2=int(part20.index[0]);stop=int(part.index[-1]);assert i0<i1<i2<=stop
        stations[i0]=(int(g),i1,i2,stop)
    for k in range(len(full)):
        if k:base.step(inp['ds_odom'][k],inp['dtheta_gyro'][k],inp['dtheta_odom'][k],.2)
        if k not in stations:continue
        g,k1,k2,end=stations[k];x,P=base.mean_cov();sample_ids=(k,k1,k2)
        for mode in ('LOS','FULL'):
            for n_s in (0,1,2,3):
                f=F.SensorV2Filter(cfg,lut,x.copy(),P.copy());r_count=s_count=0;ra=sa=0
                for t in range(k,end+1):
                    if t>k:f.step(inp['ds_odom'][t],inp['dtheta_gyro'][t],inp['dtheta_odom'][t],.2)
                    if t in sample_ids:
                        a=range_update(f,data,t,'FULL');r_count+=1;ra+=bool(a and a[3]=='applied')
                    if t in sample_ids[:n_s]:
                        a=s_update(f,data,t,mode,safe);s_count+=1;sa+=bool(a and a[3]=='applied')
                assert r_count==3 and s_count==n_s
                m=measure(f,data['truth'][end],data['c']['anchor_xyz'])
                results.append(dict(case=data['case'],level=level,seed=seed,station_g=g,s_mode=mode,n_s=n_s,n_range=3,range_accepted=ra,s_accepted=sa,elapsed_s=float(data['t'][end]-data['t'][k]),
                    yaw_error_deg=float(np.degrees(m['ep'])),position_error_m=float(math.hypot(m['ex'],m['ey'])),pose_nees=m['nees'],pose95coverage=int(m['nees']<=CHI),
                    initial_pose_id=int(data['ids'][k]),sample_pose_ids=[int(data['ids'][i]) for i in sample_ids],initial_cov_trace=float(np.trace(P))))
    return results

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',required=True,choices=CASES);ap.add_argument('--coeff',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--seeds',type=int,default=4);a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);lut,safe,meta=models(a.coeff);data=inputs(a.case,safe);cfg=config(data['c'],meta)
    receipt(a.out,dict(experiment='P1_RANGE_S_FACTORIAL',input_audit=data['audit'],case=a.case,range_offset=cfg.range_offset,range_R=cfg.range_sigma**2+cfg.range_extra_sigma**2+cfg.range_quant_var,noise='stored RF noiseless; original noisy gyro/wheel',arms=[list(x) for x in ARMS]))
    rows=[];snaps=[];stations=[]
    for level in range(3):
        for seed in range(a.seeds):
            inp,x0=one_sensor(data,cfg,level,seed)
            for rm,sm in ARMS:
                m,z=fullrun(data,cfg,lut,safe,inp,x0,rm,sm,level,seed);rows.append(m);snaps.extend(z)
            # Secondary station subset: all saved sites, but only low/high level and 2 seeds to limit repeated prior weight.
            if level in (0,2) and seed<2:stations.extend(station_controls(data,cfg,lut,safe,inp,x0,level,seed))
            pd.DataFrame(rows).to_csv(a.out/'FACTORIAL_RUNS.csv',index=False)
            print('P1_CASE_PROGRESS',a.case,level,seed,len(rows),flush=True)
    pd.DataFrame(snaps).to_json(a.out/'REPRESENTATIVE_P6.json.gz',orient='records',compression='gzip',double_precision=15)
    pd.DataFrame(stations).to_csv(a.out/'FIXED_3RANGE_S_COUNT_STATIONS.csv',index=False)
    status=dict(execution='COMPLETE',case=a.case,n_fullroute_runs=len(rows),n_station_endpoint_results=len(stations),P0_parent='9604e4c20b694cf29542b4b545f64ebd5414d285',source_family='ORIGINAL7_ONLY',pole_model=safe.model_version,original_Tnone_eval_counts=sorted(set(x['n_eval'] for x in rows)),all_arms_same_timeline_noise=True,secondary_range3_fixed=True,scientific_PASS=False)
    (a.out/'STATUS.json').write_text(json.dumps(status,indent=2));print('P1_FACTORIAL_RESULT',json.dumps(status),flush=True)
if __name__=='__main__':main()
