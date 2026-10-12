import sys,json,collections
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.rf_store import load_banks,tag_of
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION,rot_z,CorridorSetup
from qclean_uwb.features.reflection_attribution import image_delays
T=S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB'
poses=json.load(open(S/'rf_poses_R4.json'));banks=load_banks()
z=np.load(S/'native5_paths/NATIVE_FULL__R4_aB_m45__PATHS_CENTER_BIN.npz');aN=z['a'].astype(complex);tauN=z['tau'].astype(float);valid=z['valid']
setup=CorridorSetup(anchor_x_m=10.0);tx=setup.anchor_position;TIE=1e-13
def classes(table):
    seqs=list(table);d=np.array([table[s] for s in seqs]);order=np.argsort(d,kind='stable');cd=[];cn=[];cnt=[]
    for i in order:
        if cd and d[i]-cd[-1]<=TIE:
            cnt[-1]+=1
            if (len(seqs[i]),seqs[i])<cn[-1]:cn[-1]=(len(seqs[i]),seqs[i])
        else:cd.append(d[i]);cn.append((len(seqs[i]),seqs[i]));cnt.append(1)
    return np.array(cd),['LOS' if not n[1] else '>'.join(n[1]) for n in cn],np.array(cnt)
BIN=128;tx_f=[P.field_world(b,ANCHOR_ROTATION,0,0) for b in banks[:0]]  # placeholder (angles are per-trace)
by={}
for i,p in enumerate(poses):by.setdefault(tag_of(p['x'],p['y']),[]).append(i)
rows=[];cnt_equal=0;tot=0;tau_max=0.;cls_rows=[]
for tag,ix in by.items():
    t=np.load(T/f'{tag}_trace.npz');nb=t['node_bins'].tolist();k=nb.index(BIN);pres=t['present'][k];sel=np.flatnonzero(pres)
    tauL=t['tau'][sel];ang=t['ang'][:,sel];J=t['jones'][k][sel]                      # [n,3,3] at node 128
    tx_f=np.stack([P.field_world(b,ANCHOR_ROTATION,ang[0],ang[1],bins=[BIN]) for b in banks])   # [port,1,n,3]
    rx=setup.robot_position(poses[ix[0]]['x'],poses[ix[0]]['y']);cd,names,mult=classes(image_delays(tx,rx,setup.length_m,setup.y_half,setup.height_m))
    def cls_of(tau):
        r=np.abs(tau[:,None]-cd[None,:]);pk=r.argmin(1);return np.where(r[np.arange(len(tau)),pk]<=5e-14,pk,-1)
    cL=cls_of(tauL)
    for i in ix:
        yaw=poses[i]['yaw_body_deg']+45.0
        rx_f=np.stack([P.field_world(b,rot_z(float(yaw)),ang[2],ang[3],bins=[BIN]) for b in banks])
        aL=np.einsum('rbni,bnij,tbnj->brtn',rx_f,J[None],tx_f)[0]                    # [rx,tx,n]
        v=valid[i];vi=np.flatnonzero(v);tN=tauN[i,vi];cN=cls_of(tN);aNp=aN[i][:,:,vi]
        tot+=1;cnt_equal+=int(len(sel)==len(vi))
        if len(sel)==len(vi):tau_max=max(tau_max,float(np.abs(np.sort(tauL)-np.sort(tN)).max()))
        for c in set(cL.tolist())|set(cN.tolist()):
            if c<0:continue
            mL=cL==c;mN=cN==c;sL=aL[:,:,mL].sum(2);sN=aNp[:,:,mN].sum(2)
            nL,nN=int(mL.sum()),int(mN.sum());eL=float(np.linalg.norm(sL));eN=float(np.linalg.norm(sN))
            cls_rows.append((i,names[c],int(mult[c]),nL,nN,eL,eN,float(np.linalg.norm(sN-sL))))
import pandas as pd
d=pd.DataFrame(cls_rows,columns=['pose','cls','mult','nL','nN','eL','eN','diff']);d.to_csv(S/'trace_class_compare.csv',index=False)
print('poses compared',tot,'| raw path count at bin128 equal (legacy trace vs Native):',cnt_equal,'/',tot,'| max |sorted tau diff| when counts equal: %.2e s'%tau_max)
