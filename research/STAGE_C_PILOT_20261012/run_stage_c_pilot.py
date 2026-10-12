"""Stage C PLUMBING PILOT (not the Stage C validation): scheduled drive -> stop -> physical probe -> resume with the Legacy Method-B on-demand RF backend.
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
ARMS={'SHAM':('off',(0.,10.,20.)),'RANGE3':('range_only',(0.,10.,20.)),'S1':('independent_scalar_diagnostic',(0.,)),'S2':('independent_scalar_diagnostic',(0.,10.)),'S3':('independent_scalar_diagnostic',(0.,10.,20.))}
def one(cond,seed,arm,base):
    anchor,mount,xs=cond;mode,offs=ARMS[arm];cfg=copy.deepcopy(base);CUR.update(anchor=anchor,mount=mount)
    rng=np.random.default_rng([20261012,seed,int(xs*10),int(anchor),int(mount)])
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
    true_end=np.array(orc[-1]['true_pose_xyyaw']);x_end=tr['x_after_RF'][-1];P_end=tr['P_after_RF'][-1]
    e=np.r_[true_end[:2]-x_end[:2],math.atan2(math.sin(true_end[2]-x_end[2]),math.cos(true_end[2]-x_end[2]))]
    nees=float(e@np.linalg.solve(P_end[:3,:3],e))
    ph=tr['phase'];i_probe_end=int(np.where(np.char.startswith(ph.astype(str),'RETURN'))[0][-1]) if (np.char.startswith(ph.astype(str),'RETURN')).any() else -1
    return dict(arm=arm,seed=int(seed),anchor=anchor,mount=mount,x_station=xs,status=res['status'],n_rf=res['n_rf_packets'],t_last=res['t_last_s'],heading_err_deg=float(np.degrees(e[2])),pos_err_m=float(np.linalg.norm(e[:2])),
                nees=nees,P_hdg_sd_deg=float(np.degrees(math.sqrt(P_end[2,2]))),P_pos_sd_m=float(math.sqrt(P_end[0,0]+P_end[1,1])),sec=time.time()-t0,
                rf_range_status=[str(s) for s in tr['range_status'][tr['rf_detected']]] if res['n_rf_packets'] else [],rf_s_status=[str(s) for s in tr['s_status'][tr['rf_detected']]] if res['n_rf_packets'] else [])
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
                rows.append(r);print(json.dumps({k:r[k] for k in r if k in('arm','seed','anchor','mount','x_station','status','n_rf','heading_err_deg','pos_err_m','nees','error','sec')}),flush=True)
                (outdir/'results.json').write_text(json.dumps(rows,indent=1,default=float))
