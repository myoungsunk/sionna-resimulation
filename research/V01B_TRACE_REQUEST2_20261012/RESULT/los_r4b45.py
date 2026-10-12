import sys,json,hashlib
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
from qclean_uwb.drivesim.rf_store import load_banks,tag_of,h_for_antenna_yaws,load_trace
poses=json.load(open(S/'rf_poses_R4.json'));banks=load_banks();d=S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB'
by={}
for i,p in enumerate(poses):by.setdefault(tag_of(p['x'],p['y']),[]).append(i)
H=np.full((len(poses),257,2,2),np.nan+0j)
for tg,ix in by.items():
    tr=load_trace(d/f'{tg}_trace.npz');i0=int(np.argmin(tr['tau']));one=dict(tr)
    for k,sl in (('jones',lambda a:a[:,i0:i0+1]),('tau',lambda a:a[i0:i0+1]),('ang',lambda a:a[:,i0:i0+1]),('present',lambda a:a[:,i0:i0+1])):one[k]=sl(tr[k])
    hh=h_for_antenna_yaws(one,banks,[poses[i]['yaw_body_deg']+45 for i in ix])
    for i,row in zip(ix,hh):H[poses[i]['pose_id']]=row
np.save(S/'los_gen/H_LoS_R4_aB_m45.npy',H);print('R4_aB_m45 LoS: finite',bool(np.isfinite(H).all()),H.shape)
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C');summ={}
for f in sorted((S/'los_gen').glob('H_LoS_*.npy')):
    case=f.name[7:-4];summ[case]=dict(sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size,stored_reference_exists=(FR/f.name).exists())
json.dump(summ,open(S/'los_gen_summary.json','w'),indent=1)
print('generated for the 5 missing mount-45 cases:',{k:v['sha256'][:12] for k,v in summ.items() if not v['stored_reference_exists']})
