"""Diagnostic-only correlation ablation; production never exposes partial C modes."""
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import filters as F, sensor_v2 as V, filter_v2 as K, experiment as E
from qclean_uwb.drivesim.evaluation_v2 import mixed_world, serialize
from qclean_uwb.drivesim.config import build_manifest
Original=K.SensorV2Filter

class DiagnosticFilter(Original):
    mode='none'
    def step(self,d,g,o,dt):
        c=self.comps[0];cfg=self.cfg;xp=c.x.copy();b=cfg.wheel_base/(1+cfg.known_wheelbase_error)
        c.x,Fj,G=K.transition(xp,d,g,dt,b)
        Q=np.diag([cfg.k_s*abs(d),cfg.gyro_N_rad_sqrt_s**2*dt,cfg.k_theta*abs(o)+cfg.k_stheta*abs(d)])
        c.P=Fj@c.P@Fj.T+G@Q@G.T
        h,H,B=K.odometry_model(xp,d,g,dt,cfg.wheel_base,cfg.known_wheelbase_error)
        C=np.zeros(6) if self.mode=='none' else -G[:,1]*Q[1,1]*B[1]
        R=float(B@Q@B);y=o-h;S=float(H@c.P@H+R+2*H@C)
        status='zero_variance'
        if S>1e-20:
            if y*y/S>F.CHI2_1_999:status='rejected';self.stats['o_rejected']+=1
            else:c.x,c.P,_=K.correlated_update(c.x,c.P,H,y,R,C);status='applied';self.stats['o_updates']+=1
        c.P[3,3]+=cfg.bias_rw_std**2*dt
        return dict(innovation=y,R=R,S=S,status=status,H=H,C=C,Q=Q,F=Fj,G=G)

if __name__=='__main__':
    out=ROOT/'results/SENSOR_V2_20261008/CORRELATION_ABLATION'
    if out.exists():raise FileExistsError(out)
    out.mkdir();(out/'raw').mkdir();world,ds,a=mixed_world();rows=[];files=[]
    for seed in range(200,248):
        inputs,ev=V.generate(world.t,ds,a,V.SensorV2Config(condition='noise_pair'),seed)
        cfg=F.FilterConfig(model_version='sensor-v2',use_range=False,use_s=False,bias_rw_std=0.)
        x0=np.r_[world.truth[0],0.,0.,0.];P0=np.diag(np.array(cfg.p0_std)**2);P0[:3,:3]=0
        for mode in ('full','gyro-only','none'):
            try:
                K.SensorV2Filter=Original if mode=='full' else DiagnosticFilter;DiagnosticFilter.mode=mode
                filtered=K.run_filter_v2(cfg,None,inputs,{},dict(turn_phase=world.turn_phase),x0,P0)
            finally:K.SensorV2Filter=Original
            summary=E.summarize_output(world,filtered)['metrics'];err=filtered['est'][-1,:3]-world.truth[-1];err[2]=V.wrap(err[2])
            nees=float(err@np.linalg.solve(filtered['cov3'][-1],err))
            rows.append(dict(seed=seed,mode=mode,metrics=summary,endpoint_nees=nees,endpoint_coverage95=nees<=E.CHI2_3_95))
            p=out/'raw'/f'{seed}_{mode}.npz'
            archive=dict(time_s=world.t,evaluation_truth_pose=world.truth,estimate_state=filtered['est'],estimate_covariance_full=filtered['cov_full'],initial_state=x0,initial_prior=P0,seed=np.array(seed),evaluation_mask=world.t>=30)
            archive.update(filtered['observation_trace']);archive.update({'sensor_'+k:np.asarray(v) for k,v in inputs.items()});archive.update({'evaluation_'+k:np.asarray(v) for k,v in ev.items()})
            with p.open('xb') as f:np.savez_compressed(f,**archive)
            files.append(p)
    aggregate=[dict(mode=mode,n_runs=48,common_pos_rmse_mean_m=float(np.mean([r['metrics']['pos_rmse_common_m'] for r in rows if r['mode']==mode])),endpoint_nees_mean=float(np.mean([r['endpoint_nees'] for r in rows if r['mode']==mode])),endpoint_coverage95=float(np.mean([r['endpoint_coverage95'] for r in rows if r['mode']==mode]))) for mode in ('full','gyro-only','none')]
    for name,obj in (('runs.json',rows),('aggregate.json',aggregate)):
        p=out/name;p.write_text(json.dumps(serialize(obj),indent=2,allow_nan=False),encoding='utf8');files.append(p)
    source=[Path(__file__),ROOT/'src/qclean_uwb/drivesim/filter_v2.py',ROOT/'src/qclean_uwb/drivesim/sensor_v2.py',ROOT/'src/qclean_uwb/drivesim/evaluation_v2.py',ROOT/'results/SENSOR_V2_20261008/PREREG_V2.md']
    man=build_manifest(config=dict(model_version='sensor-v2 diagnostic',seeds=list(range(200,248)),condition='noise_pair',correlation_modes=['full','gyro-only','none'],inference='measurements only; zero generated drift, not oracle calibration',claim='diagnostic; no production acceptance gate'),inputs=source,outputs=files)
    (out/'manifest.json').write_text(json.dumps(man,indent=2),encoding='utf8');print(aggregate)
