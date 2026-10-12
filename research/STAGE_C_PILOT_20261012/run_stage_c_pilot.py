"""Stage C PLUMBING PILOT, ENGINEERING_ONLY (not the Stage C validation): scheduled drive -> stop -> physical probe -> resume with the Legacy Method-B on-demand RF backend.
SHAM FIX (v2): every arm with the same number of probe points k uses IDENTICAL physical braking/rotation/wait motion, because the probe controller steers on a shadow
(RF-free) estimate; the RF-corrected estimate is used only for the update bookkeeping and for the post-probe resume heading hold (that is where RF information acts).
Arms: RFOFF3 (no RF), SHAMk (Range at all k points, no s), Sm_Mk (Range at all k points, s at the first m points).
The trigger is a fixed SCHEDULE (DriveStopProbeResume), NOT an RF risk detector. Single-station sensor-v2 EKF (ProbeEKF6); RF modes: off (SHAM-like motion, no RF update),
range_only, independent_scalar_diagnostic (range + s as independent scalars; no joint site/point posterior is implemented).
Run with the Sionna venv python. usage: run_stage_c_pilot.py OUTDIR N_SEEDS [condition filter]"""
import sys,json,copy,time,math,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import legacy_backend as LB
RT=LB.RT
sys.path.insert(0,str(RT/'scripts'/'drive_sim'))
import run_body_probe_v2_native as R
from qclean_uwb.drivesim.body_pose_channel import RFPoseRequest
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
BANKM=RT/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
LUTDIR=S/'g7/lut'
RANGE_OFFSET=json.loads((LUTDIR/'hs_lut_meta.json').read_text())['range_bias']['mean_m']
BACKENDS={}
def backend(anchor,mount):
    k=(anchor,mount)
    if k not in BACKENDS:BACKENDS[k]=LB.LegacyMethodBAtPose(out_dir=S/f'rt_scene_pilot_{anchor}_{mount}',anchor_x_m=anchor,mount_deg=mount)
    return BACKENDS[k]
CUR={}
def factory(**kw):return backend(CUR['anchor'],CUR['mount'])
R.NativeSionnaAtPose=factory                      # same call signature as NativeSionnaAtPose; uses Legacy Method B instead
import dataclasses
from qclean_uwb.drivesim import body_ekf_bridge as BE
from qclean_uwb.drivesim.body_pose_channel import FirstPathReceiver
from qclean_uwb.drivesim.filter_v2 import SensorV2Filter
from qclean_uwb.drivesim.hs_lut import s_model
PROBE_PHASES=('SETTLE','ROTATE','MEASURE','RETURN','SETTLE_RETURN')
class ShadowControlEKF(BE.ProbeEKF6):
    """ProbeEKF6 whose `estimate` (read by the probe controller) is the RF-free shadow estimate during probe phases; RF updates use the true filter state."""
    def __init__(self,config,lut,x0,P0=None,*,rf_mode='range_only'):
        super().__init__(config,lut,x0,P0,rf_mode=rf_mode)
        self.shadow=SensorV2Filter(dataclasses.replace(config,use_range=False,use_s=False),None,np.asarray(x0,float),P0);self._phase='INIT'
    def start_interval(self,m,*,phase,probe_id=-1,command_v_m_s=0.,command_w_rad_s=0.):
        self._phase=str(phase);rec=super().start_interval(m,phase=phase,probe_id=probe_id,command_v_m_s=command_v_m_s,command_w_rad_s=command_w_rad_s)
        self.shadow.step(m.ds_odom,m.dtheta_gyro,m.dtheta_odom,m.dt_s);return rec
    @property
    def true_estimate(self):return BE._state_cov(self.f)[0]
    @property
    def estimate(self):
        return self.shadow.comps[0].x.copy() if self._phase in PROBE_PHASES else self.true_estimate
    def _model_range(self):
        x=self.true_estimate;a=self.cfg.anchor_xyz;delta=np.array([x[0]-a[0],x[1]-a[1],self.cfg.robot_z-a[2]]);d=float(np.linalg.norm(delta))
        if d<=1e-12:raise ValueError('undefined range geometry')
        H=np.zeros(6);H[:2]=delta[:2]/d;return d+self.cfg.range_offset,H
    def _model_s(self):
        x=self.true_estimate
        if np.linalg.norm(x[:2]-np.asarray(self.cfg.anchor_xyz[:2]))<=1e-6:raise ValueError('undefined RF azimuth geometry')
        v,j=s_model(self.lut,self.cfg.anchor_xyz,self.cfg.robot_z,float(x[0]),float(x[1]),float(x[2]),self.cfg.mount_deg,with_jac=True);H=np.zeros(6);H[:3]=j;return float(v),H
class MaskedReceiver(FirstPathReceiver):
    """Same RNG consumption as FirstPathReceiver; s is withheld (NaN) at probe points >= s_points."""
    def __init__(self,*,s_points,**kw):
        super().__init__(**kw);self.s_points=int(s_points)
    def receive(self,channel):
        pkt,orc=super().receive(channel)
        if channel.request.point_index>=self.s_points:pkt=dataclasses.replace(pkt,s=float('nan'))
        return pkt,orc
R.ProbeEKF6=ShadowControlEKF
R.FirstPathReceiver=lambda **kw:MaskedReceiver(s_points=CUR['s_points'],**kw)
# arm -> (RF mode, number of probe points k, number of leading points m that contribute s)
ARMS={'RFOFF3':('off',3,0),'SHAM1':('range_only',1,0),'SHAM2':('range_only',2,0),'SHAM3':('range_only',3,0),
      'S1_M1':('independent_scalar_diagnostic',1,1),'S2_M2':('independent_scalar_diagnostic',2,2),'S3_M3':('independent_scalar_diagnostic',3,3),
      'S1_M3':('independent_scalar_diagnostic',3,1),'S2_M3':('independent_scalar_diagnostic',3,2)}
ALL_OFFS=(0.,10.,20.)
def one(cond,seed,arm,base):
    anchor,mount,xs=cond;mode,k,m=ARMS[arm];offs=ALL_OFFS[:k];cfg=copy.deepcopy(base);CUR.update(anchor=anchor,mount=mount,s_points=m)
    rng=np.random.default_rng([20261012,seed,int(xs*10),int(anchor),int(mount)])
    cfg['initial_filter']['P0_diagonal'][:3]=[0.03**2,0.03**2,math.radians(2.)**2]      # ENGINEERING prior: pose SMALL (V02 SMALL pose), calibration prior as in the config
    P0=np.array(cfg['initial_filter']['P0_diagonal'],float);dxy=rng.normal(size=2)*np.sqrt(P0[:2]);dyaw=rng.normal()*math.sqrt(P0[2])      # truth start differs from the filter's x0 by its own prior
    cfg['physical']['init_true_xyyaw_rad']=[xs+float(dxy[0]),0.1+float(dxy[1]),float(dyaw)];cfg['initial_filter']['x0']=[xs,0.1,0.,0.,0.,0.]
    cfg['initial_filter']['range_offset_m']=RANGE_OFFSET      # frozen Legacy detector offset (LUT meta), as in the sensor-v2 harness
    cfg['sensor']['seed']=int(seed);cfg['probe']['offsets_deg']=list(offs)
    cfg['rf'].update(mode=mode,anchor_x_m=anchor,mount_deg=mount,bank_dir=str(RT),bank_manifest=str(BANKM),lut_npy=str(LUTDIR/'hs_lut_2deg.npy'),lut_meta=str(LUTDIR/'hs_lut_meta.json'),channel_kind='full')
    cfg['route_phases']=dict(mode='scheduled_drive_stop_probe_resume',trigger_after_drive_s=4.,resume_drive_s=4.,stop_timeout_s=5.,stop_hold_s=.4,drive_v_m_s=.2)
    cfg['clock']['max_duration_s']=60.
    rep=R.prerequisite_report(cfg)
    if rep['issues']:return dict(arm=arm,seed=seed,cond=cond,error=str(rep['issues']))
    out=Path('/tmp/stage_c_scratch');out.mkdir(exist_ok=True)
    loop,real,fcfg=R.build_run(cfg,out/f'{arm}_{seed}_{anchor}_{mount}_{xs}')
    t0=time.time();res=loop.run();tr=res['full_P6_trace'];orc=res['physical_oracle_eval_only']
    pose=np.array([o['true_pose_xyyaw'] for o in orc]);ph=np.asarray(tr['phase']).astype(str);pidx=np.where(np.isin(ph,PROBE_PHASES))[0]
    i_end=int(pidx[-1]);i_start=int(pidx[0])
    def err_at(i):
        x=tr['x_after_RF'][i];P=tr['P_after_RF'][i];t=pose[i];e=np.r_[t[:2]-x[:2],math.atan2(math.sin(t[2]-x[2]),math.cos(t[2]-x[2]))]
        return e,float(e@np.linalg.solve(P[:3,:3],e)),P
    e_p,nees_p,P_p=err_at(i_end);e_f,nees_f,P_f=err_at(len(pose)-1)
    t_s=np.asarray(tr['t_s'],float)
    return dict(arm=arm,seed=int(seed),anchor=anchor,mount=mount,x_station=xs,k_points=k,s_points=m,status=res['status'],n_rf=res['n_rf_packets'],t_last=res['t_last_s'],
                probe_duration_s=float(t_s[i_end]-t_s[i_start]),
                motion_fingerprint=hashlib.sha256(np.ascontiguousarray(pose[:i_end+1]).tobytes()).hexdigest()[:16],      # identical across arms with equal k (probe motion decoupled from RF)
                heading_err_probe_end_deg=float(np.degrees(e_p[2])),pos_err_probe_end_m=float(np.linalg.norm(e_p[:2])),nees_probe_end=nees_p,P_hdg_sd_probe_end_deg=float(np.degrees(math.sqrt(P_p[2,2]))),
                heading_err_deg=float(np.degrees(e_f[2])),pos_err_m=float(np.linalg.norm(e_f[:2])),nees=nees_f,P_hdg_sd_deg=float(np.degrees(math.sqrt(P_f[2,2]))),P_pos_sd_m=float(math.sqrt(P_f[0,0]+P_f[1,1])),sec=time.time()-t0,
                rf_range_status=[str(v) for v in tr['range_status'][tr['rf_detected']]] if res['n_rf_packets'] else [],rf_s_status=[str(v) for v in tr['s_status'][tr['rf_detected']]] if res['n_rf_packets'] else [])
if __name__=='__main__':
    outdir=Path(sys.argv[1]);nseeds=int(sys.argv[2]);filt=sys.argv[3] if len(sys.argv)>3 else None
    base=json.loads((RT/'configs/body_probe/ekf_native_noisy_body_v1.json').read_text());rows=[]
    outdir.mkdir(parents=True,exist_ok=True)
    conds=[(a,m,x) for a in (4.,10.) for m in (0.,45.) for x in (5.,7.,9.,12.)]
    if filt:conds=[c for c in conds if filt in f'{c[0]:g}_{c[1]:g}_{c[2]:g}']
    for cond in conds:
        for seed in range(nseeds):
            for arm in ARMS:
                try:r=one(cond,seed,arm,base)
                except Exception as ex:r=dict(arm=arm,seed=seed,cond=cond,error=repr(ex))
                rows.append(r);print(json.dumps({k:r[k] for k in r if k in('arm','seed','anchor','mount','x_station','status','n_rf','probe_duration_s','motion_fingerprint','heading_err_probe_end_deg','heading_err_deg','pos_err_m','nees','error','sec')}),flush=True)
                (outdir/'results.json').write_text(json.dumps(rows,indent=1,default=float))
