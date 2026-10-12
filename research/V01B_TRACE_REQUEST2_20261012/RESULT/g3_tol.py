import sys,json,collections
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(S))
import geo_complete as G
import g3_all as A
from qclean_uwb.scenarios.corridor import CorridorSetup
TOLS=[5e-14,1e-13,2e-13,5e-13]
res={}
for name,d,anchor in A.SETS:
    setup=CorridorSetup(anchor_x_m=anchor);G.setup=setup;G.L,G.h,G.H=setup.length_m,setup.y_half,setup.height_m;G.pl=G.planes(G.L,G.h,G.H);G.lo=np.array([0,-G.h,0.]);G.hi=np.array([G.L,G.h,G.H]);G.tx=np.asarray(setup.anchor_position,float)
    miss={t:0 for t in TOLS};spur={t:0 for t in TOLS};mingap=1e9;maxres=0.;n=0;worst_unmatched=[]
    for f in sorted(d.glob('*_trace.npz')):
        t=np.load(f);k=t['node_bins'].tolist().index(128);tl=np.array(sorted(t['tau'][t['present'][k]]));x,y=float(t['x']),float(t['y']);g=sorted(v for _,v in G.valid_paths(setup.robot_position(x,y)));ga=np.array(g)
        gaps=np.diff(ga);nz=gaps[gaps>1e-13];mingap=min(mingap,float(nz.min())) if nz.size else mingap
        for tol in TOLS:
            pool=list(tl);m=0
            for v in g:
                j=int(np.argmin(np.abs(np.array(pool)-v))) if pool else -1
                if j>=0 and abs(pool[j]-v)<=tol:pool.pop(j)
                else:m+=1
            miss[tol]+=m;spur[tol]+=len(pool)
        n+=1
    res[name]=dict(positions=n,missing_by_tol={str(k):v for k,v in miss.items()},spurious_by_tol={str(k):v for k,v in spur.items()},min_gap_between_DISTINCT_valid_delays_s=mingap)
    print(name,json.dumps(res[name]),flush=True)
json.dump(res,open(S/'g3_tol.json','w'),indent=1)
