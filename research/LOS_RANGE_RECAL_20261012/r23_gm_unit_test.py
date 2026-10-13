"""Unit test: GMEKF with sigma_b2 -> 0 must equal the frozen 6-state SensorV2Filter (range update, same R). Pass = max |est diff| <= 1e-9 (state) and <= 1e-9 (pose cov)."""
import json,math,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import gm_ekf as G
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
res={}
for route in ('R2','R5'):
    m=dict(np.load(HERE/f'inputs_R2/MOTION_{route}_legacy-euler.npz'));t=m['t'];truth=m['pose'];inputs,ev=V.generate(t,m['ds'],m['dtheta'],V.SensorV2Config(level=1,condition='all'),6500)
    R=0.09**2;off=-0.5315983906250129
    cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=True,use_s=False,anchor_xyz=(4.0,0.0,2.65),robot_z=0.45,bias_rw_std=0.,p0_std=(0.03,0.03,math.radians(2.),math.radians(0.12),0.0104,0.0064),range_sigma=math.sqrt(R),range_quant_var=0.,range_extra_sigma=0.,range_offset=off)
    x0=np.r_[truth[0],0.,0.,0.];f6=F.SensorV2Filter(cfg,None,x0);g7=G.GMEKF(cfg,x0,1e-16,0.9,R,off)
    rng=np.random.default_rng(1);dmax=0.;cmax=0.;a=cfg.anchor_xyz
    for k in range(len(t)):
        if k:
            f6.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k]);g7.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
        d=math.sqrt((truth[k,0]-a[0])**2+(truth[k,1]-a[1])**2+(a[2]-0.45)**2);z=d+off+0.3*math.sin(k/20)+rng.normal()*0.09
        if k%2==0:f6.range_record(z);g7.range_update(z)
        e6,c6=f6.mean_cov();e7,c7=g7.mean_cov();dmax=max(dmax,float(np.abs(e6-e7).max()));cmax=max(cmax,float(np.abs(c6-c7).max()))
    res[route]=dict(max_state_diff=dmax,max_cov_diff=cmax,pass_=bool(dmax<=1e-9 and cmax<=1e-9),r_updates=(f6.stats['r_updates'],g7.stats['r_updates']))
res['all_pass']=all(v['pass_'] for v in res.values() if isinstance(v,dict));print(json.dumps(res,indent=1));Path(sys.argv[1]).write_text(json.dumps(res,indent=1))
