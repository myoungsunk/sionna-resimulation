import sys,json,collections
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(S))
from geo_complete import valid_paths,setup
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.rf_store import load_banks,tag_of,h_for_antenna_yaws,load_trace
T=S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB'
poses=json.load(open(S/'rf_poses_R4.json'));by={}
for i,p in enumerate(poses):by.setdefault(tag_of(p['x'],p['y']),[]).append(i)
print('== legacy completeness by reflection order (R4_aB, 547 positions, node 128)')
miss=collections.Counter();per=[];tot=collections.Counter()
for t,ix in by.items():
    p=poses[ix[0]];g=valid_paths(setup.robot_position(p['x'],p['y']));tr=np.load(T/f'{t}_trace.npz');k=tr['node_bins'].tolist().index(128);tl=list(tr['tau'][tr['present'][k]])
    m=0
    for seq,tau in g:
        tot[len(seq)]+=1
        j=int(np.argmin(np.abs(np.array(tl)-tau))) if tl else -1
        if j>=0 and abs(tl[j]-tau)<=5e-14:tl.pop(j)
        else:miss[len(seq)]+=1;m+=1
    per.append(m)
per=np.array(per)
print('geometry paths by order:',dict(tot),'| missing in legacy by order:',dict(miss))
print('missing per position: complete %d/547 (%.1f%%), max %d, histogram'%((per==0).sum(),100*(per==0).mean(),per.max()),dict(collections.Counter(per.tolist())))
print('\n== can the missing LoS-only H be rebuilt from the trace? (R4_aB: trace LoS path -> H_LoS, mount 0, vs stored legacy H_LoS_R4_aB_m0)')
banks=load_banks();L0=np.load('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/H_LoS_R4_aB_m0.npy')
out=np.full(L0.shape,np.nan+0j)
for t,ix in by.items():
    tr=load_trace(T/f'{t}_trace.npz');i0=int(np.argmin(tr['tau']))        # LoS = shortest delay
    one=dict(tr);one['jones']=tr['jones'][:,i0:i0+1];one['tau']=tr['tau'][i0:i0+1];one['ang']=tr['ang'][:,i0:i0+1];one['present']=tr['present'][:,i0:i0+1]
    hh=h_for_antenna_yaws(one,banks,[poses[i]['yaw_body_deg']+0.0 for i in ix])
    for i,row in zip(ix,hh):out[poses[i]['pose_id']]=row
rel=np.linalg.norm((out-L0).reshape(len(L0),-1),axis=1)/np.linalg.norm(L0.reshape(len(L0),-1),axis=1)
print('trace-LoS vs stored LoS-H: max rel %.2e, median %.2e, poses<=1e-12: %d/%d'%(rel.max(),np.median(rel),(rel<=1e-12).sum(),len(rel)))
np.save(S/'regen/H_LoS_R4_aB_m0_fromtrace.npy',out)
