import sys,json,itertools,collections
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
from qclean_uwb.scenarios.corridor import CorridorSetup
from qclean_uwb.features.reflection_attribution import planes,_mirror
C0=299792458.0
setup=CorridorSetup(anchor_x_m=10.0);L,h,H=setup.length_m,setup.y_half,setup.height_m;pl=planes(L,h,H);lo=np.array([0,-h,0.]);hi=np.array([L,h,H]);tx=np.asarray(setup.anchor_position,float)
def valid_paths(rx,eps=1e-9):
    rx=np.asarray(rx,float);out=[((),float(np.linalg.norm(rx-tx))/C0)]
    for k in (1,2,3):
        for seq in itertools.product(pl,repeat=k):
            if any(a==b for a,b in zip(seq,seq[1:])):continue
            imgs=[tx]
            for name in seq:imgs.append(_mirror(imgs[-1],pl[name]))
            cur=rx.copy();ok=True
            for i in range(k,0,-1):
                ax,co=pl[seq[i-1]];d=imgs[i]-cur
                if abs(d[ax])<1e-15:ok=False;break
                t=(co-cur[ax])/d[ax]
                if not(eps<t<1-eps):ok=False;break
                P=cur+t*d;o=[a for a in range(3) if a!=ax]
                if np.any(P[o]<lo[o]-1e-9) or np.any(P[o]>hi[o]+1e-9):ok=False;break
                cur=P
            if ok:out.append((seq,float(np.linalg.norm(rx-imgs[k]))/C0))
    return out
if __name__=='__main__':
    poses=json.load(open(S/'rf_poses_R4.json'));T=S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB'
    z=np.load(S/'native5_paths/NATIVE_FULL__R4_aB_m45__PATHS_CENTER_BIN.npz');tauN=z['tau'].astype(float);valid=z['valid']
    tag=lambda x,y:f"x{x:.4f}_y{y:.4f}";seen={};rows=[]
    for i,p in enumerate(poses):
        t=tag(p['x'],p['y'])
        if t in seen:continue
        seen[t]=i
        g=valid_paths(setup.robot_position(p['x'],p['y']));tg=np.sort([x[1] for x in g])
        tr=np.load(T/f'{t}_trace.npz');k=tr['node_bins'].tolist().index(128);tl=np.sort(tr['tau'][tr['present'][k]]);tn=np.sort(tauN[i][valid[i]])
        def match(a,b,tol=5e-14):   # multiset comparison: how many of a are matched one-to-one in b
            b=list(b);m=0
            for x in a:
                j=int(np.argmin(np.abs(np.array(b)-x))) if b else -1
                if j>=0 and abs(b[j]-x)<=tol:m+=1;b.pop(j)
            return m
        rows.append(dict(tag=t,geo=len(tg),legacy=len(tl),native=len(tn),legacy_in_geo=match(tl,tg),native_in_geo=match(tn,tg),geo_in_legacy=match(tg,tl),geo_in_native=match(tg,tn)))
    import pandas as pd;d=pd.DataFrame(rows);d.to_csv(S/'geo_complete.csv',index=False)
    print('positions',len(d));print(d[['geo','legacy','native','legacy_in_geo','native_in_geo','geo_in_legacy','geo_in_native']].describe().loc[['min','50%','max']].round(1).to_string())
    print('\nexact: geometry-valid set == legacy set at bin 128 in %d/%d positions; == Native set in %d/%d'%(int(((d.geo==d.legacy)&(d.geo_in_legacy==d.geo)).sum()),len(d),int(((d.geo==d.native)&(d.geo_in_native==d.geo)).sum()),len(d)))
    print('legacy paths NOT in geometry-valid set (total over positions):',int((d.legacy-d.legacy_in_geo).sum()),'| Native paths not in geometry set:',int((d.native-d.native_in_geo).sum()))
    print('geometry-valid paths missing from legacy:',int((d.geo-d.geo_in_legacy).sum()),'| missing from Native:',int((d.geo-d.geo_in_native).sum()))
