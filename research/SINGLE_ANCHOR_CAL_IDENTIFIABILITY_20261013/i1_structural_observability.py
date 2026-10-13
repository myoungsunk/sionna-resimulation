"""I1 local structural/mean-information audit. No estimator or seed campaign."""
from pathlib import Path
import sys,json,csv,hashlib,datetime,platform
import numpy as np
import pandas as pd
from i1_model import forward,build_whitener,whiten,rank,effective,augment_prior
from replay import ROOT

HERE=Path(__file__).resolve().parent
def write(p,data):p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def datasets(spec):
    motion=ROOT/'research/LOS_RANGE_RECAL_20261012/inputs_R2'
    expected={line.split()[1]:line.split()[0] for line in (motion/'SHA256SUMS_CSV.txt').read_text().splitlines() if line.strip()}
    result={}
    for route in ['R2','R4','R5']:
        path=motion/f'MOTION_{route}.csv';assert sha(path)==expected[path.name]
        d=pd.read_csv(path,float_precision='round_trip');t=d.t.to_numpy()
        result[route]=dict(t=t,dt=np.r_[0,np.diff(t)],d=d.ds.to_numpy(),g=d.dtheta.to_numpy(),o=d.dtheta.to_numpy(),theta=np.r_[d[['x','y','theta']].iloc[0].to_numpy(),0.,0.,0.])
    cfg=spec['synthetic'];t=np.linspace(0,cfg['duration_s'],round(cfg['duration_s']/cfg['dt_s'])+1);dt=np.r_[0,np.diff(t)]
    v=np.full(len(t),cfg['speed_m_s']);mid=t-dt/2
    for name in spec['routes'][3:]:
        vv=v*(1+cfg['variation_fraction']*np.sin(2*np.pi*mid/cfg['duration_s'])) if name=='RADIAL_VARIABLE' else v
        ds=vv*dt;angle=np.zeros(len(t));theta=np.r_[cfg['initial_pose'],0.,0.,0.]
        if name in ('TANGENTIAL_STRAIGHT','CIRCULAR_TANGENT'):theta[2]=np.pi/2
        if name=='CIRCULAR_TANGENT':angle=ds/cfg['radius_m']
        result[name]=dict(t=t,dt=dt,d=ds,g=angle,o=angle,theta=theta)
    return result

def gauge_tests(inputs,anchor,spec):
    theta=inputs['theta'];v,_=forward(theta,inputs,anchor,True)
    errs=[]
    for angle in [.3,1.1,-1.7]:
        R=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
        other=theta.copy();other[:2]=anchor[:2]+R@(theta[:2]-anchor[:2]);other[2]+=angle
        w,_=forward(other,inputs,anchor,True);errs.append(float(np.max(abs(v-w))))
    return dict(max_observation_change=max(errs),pass_rotation=max(errs)<spec['gauge_observation_atol'])

def nonlinear_families(data,spec):
    inp=data['RADIAL_CONSTANT'];anchor=np.array(spec['anchors']['A']);base=inp['theta']
    pairs=[]
    for eps in [.003,.006,.012]:
        a=base.copy();a[5]=eps;a[3]=eps*.1/(.287*(1-eps**2/4))
        b=a.copy();b[3]*=-1;b[5]*=-1
        va,_=forward(a,inp,anchor,True);vb,_=forward(b,inp,anchor,True);v0,_=forward(base,inp,anchor,True)
        pairs.append(dict(eps=eps,bg_rad_s=float(a[3]),DR_observation_difference=float(np.max(abs(va[:,0]-v0[:,0]))),mirror_range_difference=float(np.max(abs(va[:,1]-vb[:,1]))),range_difference_from_zero_cal=float(np.max(abs(va[:,1]-v0[:,1])))))
    return dict(condition='constant speed straight nominal controls, radial anchor A, fixed initial pose',family='bg=eps*v*(1+SFg)/(b*(1-eps^2/4)), SFg=0 here',pairs=pairs,claim='DR admits a continuous calibration family; range admits reflected +/- calibration pairs, NOT a continuous family through zero inferred from rank alone')

def run(out):
    spec=json.loads((HERE/'I1_SPEC.json').read_text());out.mkdir(parents=True,exist_ok=False)
    write(out/'FROZEN_SPEC.json',spec)
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();data=datasets(spec);scale=np.array(spec['scales'])
    rows=[];times=[];gauges={}
    for name,inp in data.items():
        np.savez_compressed(out/(name+'_design.npz'),**inp)
        for aid,coords in spec['anchors'].items():
            anchor=np.array(coords);gauges[name+':'+aid]=gauge_tests(inp,anchor,spec)
            for arm in spec['arms']:
                if arm=='A_DR' and aid=='B':continue
                use=arm!='A_DR';ops,values,J=build_whitener(inp['theta'],inp,anchor,spec,use)
                raw=np.array([J[k,j] for k,j,*_ in ops])*scale
                weighted=whiten(J,ops)*scale
                prefix=f'{name}:{arm}:{aid}'
                np.savez_compressed(out/(prefix.replace(':','_')+'_sensitivity.npz'),raw_scaled_J=raw,whitened_scaled_J=weighted,nominal_observations=values)
                for pose_case in spec['pose_cases']:
                    for kind in ['DATA_ONLY','POSE_PRIOR','POSTERIOR']:
                        mat=augment_prior(weighted,pose_case,kind,spec)
                        info=effective(mat,spec['primary_svd_rtol'])
                        stability=[effective(mat,tol)['rank'] for tol in spec['svd_relative_tolerances']]
                        row=dict(case=prefix,pose_case=pose_case,information=kind,structural_rank=rank(raw,spec['primary_svd_rtol']),cal_rank=info['rank'],lambda_min=info['eigenvalues'][0],lambda_max=info['eigenvalues'][1],condition=info['condition'],cal_information_00=info['matrix'][0][0],cal_information_01=info['matrix'][0][1],cal_information_11=info['matrix'][1][1],nuisance_rank=info['nuisance_rank'],rank_stable=len(set(stability))==1,rank_sweep='/'.join(map(str,stability)))
                        rows.append(row)
                        for fraction in [.1,.25,.5,.75,1.]:
                            k=min(len(inp['t'])-1,int(fraction*(len(inp['t'])-1)))
                            count=sum(op[0]<=k for op in ops)
                            inf=effective(augment_prior(weighted[:count],pose_case,kind,spec),spec['primary_svd_rtol'])
                            times.append(dict(case=prefix,pose_case=pose_case,information=kind,time_s=float(inp['t'][k]),cal_rank=inf['rank'],lambda_min=inf['eigenvalues'][0],lambda_max=inf['eigenvalues'][1],condition=inf['condition']))
                print(prefix,'complete',flush=True)
    for filename,records in [('STRUCTURAL_RANK.csv',rows),('CAL_FIM_TIMESERIES.csv',times)]:
        with (out/filename).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    write(out/'NONLINEAR_INVARIANCES.json',dict(gauge=gauges,calibration=nonlinear_families(data,spec)))
    write(out/'I1_IDENTIFIABILITY.json',dict(status='LOCAL_ANALYSIS_COMPLETE',scope=spec['scope'],rows=rows,F0=spec['F0_status'],I2='NOT_RUN',L1='NOT_RUN: independent confirmation not performed',warnings=['Local rank is not practical precision','Tangent mean information omits parameter-dependent covariance information','S0 gauge does not imply calibration nonidentifiability','Nonlinear profiles are fixed-covariance diagnostics, not exact posteriors']))
    sources=[HERE/n for n in ['I1_SPEC.json','i1_model.py','i1_structural_observability.py']]
    sources+=list((ROOT/'research/LOS_RANGE_RECAL_20261012/inputs_R2').glob('MOTION_R*.csv'))
    write(out/'I1_MANIFEST.json',dict(start=start,end=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,python=sys.version,numpy=np.__version__,platform=platform.platform(),sources={str(p.relative_to(ROOT)):sha(p) for p in sources},outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()}))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
