"""Exploratory saved LoS-H EKF counterfactual, not an archived original score.
Two policies: ZERO_DIRECT_MEAN (matched clean direct) and FROZEN_FULL_MEAN (only channel changes).
Original prior/R/motion/joint NIS retained. No RT.
"""
import io,os,sys,time,gzip,zipfile,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
P=Path('/mnt/data/dual_lp_dramatic_figures_20261102');T=P/'tables';T.mkdir(exist_ok=True)
ROOT=Path('/mnt/data/_dual_lp_runtime/inputs');os.environ['REFLECT_ROOT']=str(ROOT)
sys.path.insert(0,str(ROOT/'repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
sys.path.insert(0,'/mnt/data/_dual_lp_runtime/legacy/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code')
import diag_mbvar as DG
from qclean_uwb.drivesim.observation import observe
z=zipfile.ZipFile('/mnt/data/DualLP_Physics_Link_Validation_20261101.zip');prefix='DualLP_Physics_Link_Validation_20261101/'
ledger=pd.read_csv(io.BytesIO(gzip.decompress(z.read(prefix+'results/PHYSICS_PACKET_LEDGER.csv.gz'))))
freq=6250400000+1950000*np.arange(257)
print('START_MODEL',flush=True);model=DG.C.base_model();print('MODEL_READY',flush=True)
rows=[];parities=[];sources=[]
for case in ['R2_aB_m0','R4_aB_m0','R5_aB_m0']:
  D0=DG.load(case,'B0',model);n=len(D0['t']);g=ledger.query('case == @case').sort_values('pose_id')
  assert len(g)==n and (g.pose_id.to_numpy()==np.arange(n)).all()
  file=ROOT/'rf'/f'H_LoS_{case}.npy';H=np.load(file,mmap_mode='r',allow_pickle=False)
  obs=[observe(np.asarray(H[start:min(start+64,n)]),freq,None,None,tx=0) for start in range(0,n,64)]
  Z=np.column_stack([np.concatenate([a['range_m'] for a in obs]),np.concatenate([a['s'] for a in obs])])
  dr=float(np.max(abs(Z[:,0]-g.LoS_r_m.to_numpy())));ds=float(np.max(abs(Z[:,1]-g.LoS_s.to_numpy())))
  assert dr<1e-10 and ds<1e-12
  parities.append({'case':case,'n':n,'range_max_diff_m':dr,'s_max_diff':ds});sources.append({'case':case,'H_LoS_sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
  print('VALIDATE',case,'parity',dr,ds,flush=True)
  for bias in ['B0','L0','L1','L2']:
    D=D0.copy()
    if bias!='B0':
      td,tg,tt,x0=DG.PB.build_controls(D['t'],D['gt'][:,:3],bias)
      D.update(ds=td,gy=tg,dt=tt,x0=np.r_[x0,0.])
    D['z']=Z.copy()
    for label,mean in [('LOS_ZERO_MEAN',np.zeros_like(D0['mu']['BB'])),('LOS_FROZEN_FULL_BB_MEAN',D0['mu']['BB'])]:
      D['mu']={'BB':mean.copy()}
      st=time.perf_counter();X,PC,L=DG.run(D,'BB','orig','self',model=model);score=DG.scores(D,X,PC)
      row={'case':case,'bias':bias,'arm':label,'gate':'self','n':n,'n_used':int(L['used'].sum()),'run_sec':round(time.perf_counter()-st,3),**score}
      rows.append(row)
      np.savez_compressed(T/f'{case}_{bias}_{label}.npz',X=X,PX=PC,used=L['used'],nis=L['nis'],t=D['t'],gt=D['gt'],z_los=Z)
      print('FINISHED',case,bias,label,'head',round(score['head_rmse'],5),'xy',round(score['xy_rmse_cm'],5),flush=True)
pd.DataFrame(rows).to_csv(T/'LOS_COUNTERFACTUAL_24.csv',index=False)
pd.DataFrame(parities).to_csv(T/'LOS_PARITY.csv',index=False)
(P/'source/LOS_INPUT_SHA.json').write_text(json.dumps(sources,indent=2))
(T/'LOS_QA.json').write_text(json.dumps({'status':'EXPLORATORY_SOURCE_LOCKED_LOS_REPLAY','n':len(rows),'no_new_RT':True,'R_reused_from_BB_Full':True,'mean_variants':['ZERO_DIRECT','FROZEN_FULL_BB'],'source_model_unchanged':True,'is_archived_original':False,'source_h_parity':parities},indent=2))
print('DONE',len(rows),flush=True)
