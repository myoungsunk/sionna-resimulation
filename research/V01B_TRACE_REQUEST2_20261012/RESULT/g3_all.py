"""G3 path completeness for all 6 trace sets, thresholds exactly as frozen in CLOSURE_MANIFEST.json (commit 6cca770). No tuning."""
import sys,json,collections,time
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(S))
import geo_complete as G
from qclean_uwb.scenarios.corridor import CorridorSetup
T2=S/'tr2/research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012'
SETS=[('R4_aB',S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB',10.0),('R4_aA',T2/'R4_aA/traces_R4_aA',4.0),('R2_aA',T2/'R2_aA/traces_R2_aA',4.0),
      ('R2_aB',T2/'R2_aB/traces_R2_aB',10.0),('R5_aA',T2/'R5_aA/traces_R5_aA',4.0),('R5_aB',T2/'R5_aB/traces_R5_aB',10.0)]
def run(name,d,anchor):
    setup=CorridorSetup(anchor_x_m=anchor)
    G.setup=setup;G.L,G.h,G.H=setup.length_m,setup.y_half,setup.height_m;G.pl=G.planes(G.L,G.h,G.H);G.lo=np.array([0,-G.h,0.]);G.hi=np.array([G.L,G.h,G.H]);G.tx=np.asarray(setup.anchor_position,float)
    tot=collections.Counter();miss=collections.Counter();spur=0;per=[];files=sorted(d.glob('*_trace.npz'));tf=0
    for f in files:
        t=np.load(f);k=t['node_bins'].tolist().index(128);tl=list(t['tau'][t['present'][k]]);x,y=float(t['x']),float(t['y'])
        g=G.valid_paths(setup.robot_position(x,y));m=0
        for seq,tau in g:
            tot[len(seq)]+=1
            j=int(np.argmin(np.abs(np.array(tl)-tau))) if tl else -1
            if j>=0 and abs(tl[j]-tau)<=5e-14:tl.pop(j)
            else:miss[len(seq)]+=1;m+=1
        spur+=len(tl);per.append(m)   # legacy paths left unmatched = not in the geometry-valid set
    per=np.array(per);o23=tot[2]+tot[3];f23=1-(miss[2]+miss[3])/o23
    return dict(set=name,positions=len(files),geometry_paths=dict(tot),missing=dict(miss),order01_complete=bool(miss[0]==0 and miss[1]==0),order23_found_fraction=float(f23),
        positions_complete=int((per==0).sum()),max_missing_per_position=int(per.max()),positions_over6=int((per>6).sum()),spurious=int(spur),missing_histogram={int(k):int(v) for k,v in sorted(collections.Counter(per.tolist()).items())})
if __name__=='__main__':
    out=[];t0=time.time()
    for name,d,a in SETS:
        r=run(name,d,a);out.append(r);print(json.dumps(r),flush=True);print('  elapsed %.0fs'%(time.time()-t0),flush=True)
        json.dump(out,open(S/'g3_all.json','w'),indent=1)
