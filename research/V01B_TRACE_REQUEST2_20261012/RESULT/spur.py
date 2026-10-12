import sys,json
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(S))
import geo_complete as G
from qclean_uwb.scenarios.corridor import CorridorSetup
from qclean_uwb.features.reflection_attribution import image_delays,planes,_mirror
d=S/'tr2/research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012/R2_aA/traces_R2_aA'
setup=CorridorSetup(anchor_x_m=4.0)
G.setup=setup;G.L,G.h,G.H=setup.length_m,setup.y_half,setup.height_m;G.pl=G.planes(G.L,G.h,G.H);G.lo=np.array([0,-G.h,0.]);G.hi=np.array([G.L,G.h,G.H]);G.tx=np.asarray(setup.anchor_position,float)
C=299792458.0
for f in sorted(d.glob('*_trace.npz')):
    t=np.load(f);k=t['node_bins'].tolist().index(128);tl=list(t['tau'][t['present'][k]]);x,y=float(t['x']),float(t['y']);rx=setup.robot_position(x,y)
    g=G.valid_paths(rx)
    for seq,tau in g:
        j=int(np.argmin(np.abs(np.array(tl)-tau))) if tl else -1
        if j>=0 and abs(tl[j]-tau)<=5e-14:tl.pop(j)
    if tl:
        print('position',f.name[:-10],'x=%.6f y=%.6f z_rx=%.3f'%(x,y,rx[2]),'| unmatched legacy tau:',tl,'| n paths in legacy trace at node128 =',int(t['present'][k].sum()),'geometry-valid =',len(g))
        tab=image_delays(setup.anchor_position,rx,setup.length_m,setup.y_half,setup.height_m);valid_seq={s for s,_ in g}
        cand=sorted(((abs(v-tl[0]),s) for s,v in tab.items()),key=lambda z:z[0])[:3]
        for r,s in cand:print('   nearest image sequence:',s or 'LOS','| delay residual %.2e s (%.2e m)'%(r,r*C),'| in my valid set:',s in valid_seq)
        # why was it rejected? reproduce the image-method walk for the nearest sequence
        s=cand[0][1];pl=planes(setup.length_m,setup.y_half,setup.height_m);imgs=[np.asarray(setup.anchor_position,float)]
        for n in s:imgs.append(_mirror(imgs[-1],pl[n]))
        cur=np.asarray(rx,float);lo=np.array([0,-setup.y_half,0.]);hi=np.array([setup.length_m,setup.y_half,setup.height_m])
        for i in range(len(s),0,-1):
            ax,co=pl[s[i-1]];dd=imgs[i]-cur;tt=(co-cur[ax])/dd[ax];P=cur+tt*dd;o=[a for a in range(3) if a!=ax]
            print('   step',i,s[i-1],'t=%.12f'%tt,'point',np.round(P,6),'inside face bounds:',bool(np.all(P[o]>=lo[o]-1e-9) and np.all(P[o]<=hi[o]+1e-9)),'| margin to bounds (m):',np.round(np.minimum(P[o]-lo[o],hi[o]-P[o]),9).tolist());cur=P
