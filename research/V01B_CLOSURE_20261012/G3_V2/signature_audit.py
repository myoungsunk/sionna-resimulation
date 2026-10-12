"""G3_v2 audit item: does the matched trace slot carry the SAME reflection-order signature as the geometry sequence?
Matching is the primary G3_v2 matching (K=16 ulp32, A=1e-2 rad, Hungarian). Mismatches are split into
(a) degenerate-class swaps: another geometry sequence with identical delay (<1e-15 s) and directions (<1e-9 rad) has the trace's signature, and
(b) true identity mismatches."""
import sys,json,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from multiprocessing import Pool
import g3_v2 as M
from qclean_uwb.scenarios.corridor import CorridorSetup
def seqname(s):return 'LOS' if not s else '>'.join(s)
def one(a):
    f,anchor=a;setup=CorridorSetup(anchor_x_m=anchor);t=np.load(f);k=t['node_bins'].tolist().index(128);idx=np.where(t['present'][k])[0]
    if t['signature'].shape[0]!=t['tau'].shape[0]:return 0,0,0,0,1   # signature array length != tau length: slot alignment unknown
    tau=t['tau'][idx];an=t['ang'][:,idx];sig=[str(t['signature'][j]) for j in idx]
    du=[M.unit(an[0,j],an[1,j]) for j in range(len(idx))];au=[M.unit(an[2,j],an[3,j]) for j in range(len(idx))]
    g=M.valid_paths(setup,setup.robot_position(float(t['x']),float(t['y'])));asg,_=M.match(g,tau,du,au,M.K_PRIMARY,M.A_PRIMARY)
    ok=swap=bad=0
    for i,j in asg.items():
        if seqname(g[i][0])==sig[j]:ok+=1;continue
        twin=[q for q in range(len(g)) if q!=i and abs(g[q][1]-g[i][1])<1e-15 and M.ang(g[q][2],g[i][2])<1e-9 and M.ang(g[q][3],g[i][3])<1e-9 and seqname(g[q][0])==sig[j]]
        if twin:swap+=1
        else:bad+=1
    return ok,swap,bad,len(asg),0
if __name__=='__main__':
    out={}
    for name,d,anchor in M.SETS:
        files=sorted(d.glob('*_trace.npz'))
        with Pool(2) as p:r=p.map(one,[(str(f),anchor) for f in files],chunksize=8)
        ok,swap,bad,n,skipped=[sum(x[i] for x in r) for i in range(5)]
        out[name]=dict(assigned=n,signature_equal=ok,degenerate_class_swap=swap,true_identity_mismatch=bad,positions_skipped_signature_length_mismatch=skipped);print(name,out[name],flush=True)
    json.dump(out,open(Path(__file__).resolve().parent/'signature_audit.json','w'),indent=1)
