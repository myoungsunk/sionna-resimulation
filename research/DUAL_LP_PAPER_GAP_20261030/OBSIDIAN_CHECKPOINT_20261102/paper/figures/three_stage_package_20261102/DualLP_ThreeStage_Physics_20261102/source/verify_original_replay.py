"""Re-run preserved Full BB/MB B0 with source model to check LoS replay engine parity.
No input/archived result modification, no RT.
"""
from pathlib import Path
import sys,os,io,zipfile,json,numpy as np
ROOT=Path('/mnt/data/_dual_lp_runtime/inputs');os.environ['REFLECT_ROOT']=str(ROOT)
sys.path.insert(0,'/mnt/data/_dual_lp_runtime/legacy/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code');import diag_mbvar as DG
z=zipfile.ZipFile('/mnt/data/DualLP_Physics_Link_Validation_20261101.zip');pre='DualLP_Physics_Link_Validation_20261101/'
model=DG.C.base_model();rows=[]
for case in ['R2_aB_m0','R4_aB_m0','R5_aB_m0']:
 D=DG.load(case,'B0',model)
 for name,bg,mode in [('BB_ORIG','BB','orig'),('MB_VAR','MB','var')]:
  x,p,L=DG.run(D,bg,mode,'self',model=model)
  saved=np.load(io.BytesIO(z.read(pre+f'results/traces/{case}__B0__{name}__self.npz')),allow_pickle=False)
  dx=float(np.max(abs(x-saved['X'])));dp=float(np.max(abs(p-saved['PX'])));wrong=int(np.count_nonzero(L['used']!=saved['used']))
  assert dx<1e-10 and dp<1e-10 and wrong==0,(case,name,dx,dp,wrong)
  rows.append(dict(case=case,arm=name,state_max_abs=dx,P_max_abs=dp,mask_mismatch=wrong,status='PASS'))
  print('FULL_PARITY',case,name,dx,dp,wrong,flush=True)
out=Path('/mnt/data/dual_lp_dramatic_figures_20261102/tables')
import pandas as pd
pd.DataFrame(rows).to_csv(out/'FULL_REPLAY_PARITY_6.csv',index=False)
(out/'FULL_REPLAY_PARITY_QA.json').write_text(json.dumps({'status':'PASS','n':len(rows),'all_max_states':max(x['state_max_abs'] for x in rows),'all_max_P':max(x['P_max_abs'] for x in rows),'full_old_and_new_replayed':True,'original_data_mutated':False},indent=2))
