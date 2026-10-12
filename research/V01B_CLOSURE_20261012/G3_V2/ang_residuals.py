import sys,numpy as np
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent));sys.path.insert(0,'rfroot/src')
import g3_v2 as M
from qclean_uwb.scenarios.corridor import CorridorSetup
from multiprocessing import Pool
def one(a):
    f,anchor=a;setup=CorridorSetup(anchor_x_m=anchor);t=np.load(f);k=t['node_bins'].tolist().index(128);idx=np.where(t['present'][k])[0]
    g=M.valid_paths(setup,setup.robot_position(float(t['x']),float(t['y'])));taus=np.array([x[1] for x in g]);out=[]
    for j in idx:
        tj=t['tau'][j];c=[i for i in range(len(g)) if abs(tj-taus[i])<=2e-13]
        if len(c)==1:
            i=c[0];out.append((abs(tj-taus[i]),M.ang(g[i][2],M.unit(t['ang'][0,j],t['ang'][1,j])),M.ang(g[i][3],M.unit(t['ang'][2,j],t['ang'][3,j])),len(g[i][0])))
    # separation between distinct (non-duplicate) near-delay geometry sequences
    sep=[]
    for i in range(len(g)):
        for q in range(i+1,len(g)):
            if abs(taus[i]-taus[q])<=2e-13:
                sep.append((abs(taus[i]-taus[q]),max(M.ang(g[i][2],g[q][2]),M.ang(g[i][3],g[q][3]))))
    return out,sep
if __name__=='__main__':
    import glob
    for name,d,anchor in M.SETS:
        fs=sorted(d.glob('*_trace.npz'))
        with Pool(4) as p:r=p.map(one,[(str(f),anchor) for f in fs],chunksize=8)
        A=np.array([x for o,_ in r for x in o]);Sp=np.array([x for _,s in r for x in s])
        for order in (0,1,2,3):
            m=A[A[:,3]==order]
            if len(m):print(name,'order',order,'n',len(m),'dtau max %.2e'%m[:,0].max(),'dep ang p50/p99/max %.1e %.1e %.1e'%tuple(np.percentile(m[:,1],[50,99,100])),'arr %.1e %.1e %.1e'%tuple(np.percentile(m[:,2],[50,99,100])))
        if len(Sp):
            nd=Sp[Sp[:,1]>1e-9]  # non exact duplicates
            print(name,'near-delay (<=2e-13) distinct pairs:',len(Sp),'non-duplicate:',len(nd),'min angular separation of non-duplicates %.2e'%(nd[:,1].min() if len(nd) else float('nan')),flush=True)
