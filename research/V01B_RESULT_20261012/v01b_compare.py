import sys,json,hashlib
from pathlib import Path
import numpy as np
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad')
sys.path.insert(0,str(S/'abc_src/src'))
from qclean_uwb.drivesim import observation as O
f=np.load('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
D=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
CASES=['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']
rows=[];detail={}
for c in CASES:
    L=np.load(D/f'H_{c}.npy');N=np.load(S/f'native5/H_{c}_native.npy')
    assert L.shape==N.shape,(c,L.shape,N.shape)
    num=np.linalg.norm((N-L).reshape(len(L),-1),axis=1);den=np.linalg.norm(L.reshape(len(L),-1),axis=1)
    rel=num/np.maximum(den,1e-300)
    oL=O.observe(L,f,None,None,tx=0);oN=O.observe(N,f,None,None,tx=0)
    det=np.asarray(oL['detected'])&np.asarray(oN['detected']);ds=np.abs(np.asarray(oL['s'])-np.asarray(oN['s']))
    tapeq=np.asarray(oL['index'])==np.asarray(oN['index'])
    dtap=np.asarray(oN['index'])-np.asarray(oL['index'])
    row=dict(case=c,n_poses=len(L),rel_max=float(rel.max()),rel_median=float(np.median(rel)),rel_p99=float(np.quantile(rel,.99)),
        frac_rel_le_1e3=float(np.mean(rel<=1e-3)),s_abs_max=float(np.nanmax(ds[det])) if det.any() else float('nan'),
        s_abs_median=float(np.nanmedian(ds[det])),frac_s_le_0p01=float(np.mean(ds[det]<=.01)),tap_match_frac=float(tapeq.mean()),
        n_det_L=int(np.sum(oL['detected'])),n_det_N=int(np.sum(oN['detected'])),n_tap_mismatch=int((~tapeq).sum()),
        max_abs_dtap=int(np.abs(dtap).max()),mean_dtap=float(dtap.mean()),
        norm_ratio_median=float(np.median(np.linalg.norm(N.reshape(len(N),-1),axis=1)/den)))
    row['PASS_all_three']=bool(row['rel_max']<=1e-3 and row['s_abs_max']<=.01 and row['n_tap_mismatch']==0)
    rows.append(row);np.savez_compressed(S/f'v01b_{c}_perpose.npz',rel=rel,ds=ds,tap_L=oL['index'],tap_N=oN['index'])
import pandas as pd;pd.set_option('display.width',250);pd.set_option('display.max_columns',30)
d=pd.DataFrame(rows);d.to_csv(S/'v01b_compare.csv',index=False);print(d.T.to_string())
