"""G3_v2 path completeness: identity-aware one-to-one matching.
Fixes the *numerical matching defect* of G3_v1 (delay-only nearest neighbour with a fixed 5e-14 s window).
Criteria 1-3 of G3 (LoS & order-1 100 %, order-2/3 >= 99.5 %, max missing/position <= 6) are UNCHANGED.
Criterion 4 (spurious = 0, yaw-independent path set) is unchanged in content; only the matching that decides
'matched' vs 'spurious' is replaced by:
  * geometry sequence k  <->  trace path j feasible iff  |dtau| <= K * ulp32(tau_geo)  AND departure angle <= A AND arrival angle <= A
  * one-to-one assignment (Hungarian, scipy.optimize.linear_sum_assignment) on a gated cost
G3_v1 outputs (g3_all.json, g3_tol.json) are NOT modified.  Tolerances were fixed after seeing the G3_v1 result
(post-hoc, disclosed) and are therefore accompanied by a sensitivity sweep.
"""
import sys,json,itertools,collections,time
import numpy as np
from pathlib import Path
from multiprocessing import Pool
from scipy.optimize import linear_sum_assignment
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
from qclean_uwb.scenarios.corridor import CorridorSetup
from qclean_uwb.features.reflection_attribution import planes,_mirror
C0=299792458.0
T2=S/'tr2/research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012'
SETS=[('R4_aB',S/'trdel/research/V01B_TRACE_REQUEST_20261012/DELIVERY_20261012/traces_R4_aB',10.0),('R4_aA',T2/'R4_aA/traces_R4_aA',4.0),('R2_aA',T2/'R2_aA/traces_R2_aA',4.0),
      ('R2_aB',T2/'R2_aB/traces_R2_aB',10.0),('R5_aA',T2/'R5_aA/traces_R5_aA',4.0),('R5_aB',T2/'R5_aB/traces_R5_aB',10.0)]
# primary tolerances: K = multiple of float32 spacing at tau (delay); A = angular gate in rad.
# A is set from the residual statistics of delay-UNAMBIGUOUS matched paths (ang_residuals.json: departure <= 6.6e-4 rad, arrival <= 1.7e-5 rad)
# and the smallest angular separation of distinct near-delay geometry sequences (>= 9.8e-2 rad): A=1e-2 sits >15x above the former and ~10x below the latter.
# This calibration is POST-HOC (done after the G3_v1 result) and is disclosed; the sweep below shows the verdict is not knife-edge.
K_PRIMARY=16; A_PRIMARY=1e-2
K_SWEEP=[4,8,16,32,64]; A_SWEEP=[1e-4,1e-3,3e-3,1e-2,3e-2,5e-2,1e-1]
def unit(th,ph):return np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
def valid_paths(setup,rx,eps=1e-9):
    """geometry-valid specular sequences with delay, departure unit vector (TX->first point) and arrival unit vector (RX->last point)"""
    L,h,H=setup.length_m,setup.y_half,setup.height_m;pl=planes(L,h,H);lo=np.array([0,-h,0.]);hi=np.array([L,h,H]);tx=np.asarray(setup.anchor_position,float)
    rx=np.asarray(rx,float);n=np.linalg.norm(rx-tx)
    out=[((),n/C0,(rx-tx)/n,(tx-rx)/n)]
    for k in (1,2,3):
        for seq in itertools.product(pl,repeat=k):
            if any(a==b for a,b in zip(seq,seq[1:])):continue
            imgs=[tx]
            for name in seq:imgs.append(_mirror(imgs[-1],pl[name]))
            cur=rx.copy();ok=True;pts=[]
            for i in range(k,0,-1):
                ax,co=pl[seq[i-1]];d=imgs[i]-cur
                if abs(d[ax])<1e-15:ok=False;break
                t=(co-cur[ax])/d[ax]
                if not(eps<t<1-eps):ok=False;break
                P=cur+t*d;o=[a for a in range(3) if a!=ax]
                if np.any(P[o]<lo[o]-1e-9) or np.any(P[o]>hi[o]+1e-9):ok=False;break
                pts.append(P);cur=P
            if ok:
                dep=pts[-1]-tx;arr=pts[0]-rx   # pts[0]=reflection nearest RX, pts[-1]=nearest TX
                out.append((seq,float(np.linalg.norm(rx-imgs[k]))/C0,dep/np.linalg.norm(dep),arr/np.linalg.norm(arr)))
    return out
def ang(u,v):return float(np.arccos(np.clip(u@v,-1,1)))
def match(g,tau,du,au,K,A):
    """g: geometry list; tau,du,au: trace path arrays. returns assignment dict and feasibility."""
    n,m=len(g),len(tau);BIG=1e6;cost=np.full((n,m),BIG);feas=np.zeros((n,m),bool)
    for i,(s,t,d,a) in enumerate(g):
        tolt=K*float(np.spacing(np.float32(t)))
        for j in range(m):
            dt=abs(tau[j]-t)
            if dt<=tolt:
                ad=ang(d,du[j]);aa=ang(a,au[j])
                if ad<=A and aa<=A:cost[i,j]=(dt/tolt)**2+(ad/A)**2+(aa/A)**2;feas[i,j]=True
    ri,ci=linear_sum_assignment(cost);asg={int(i):int(j) for i,j in zip(ri,ci) if feas[i,j]}
    return asg,feas
def one_position(args):
    f,anchor=args;setup=CorridorSetup(anchor_x_m=anchor)
    t=np.load(f);k=t['node_bins'].tolist().index(128);pr=t['present'][k];x,y=float(t['x']),float(t['y'])
    idx=np.where(pr)[0];tau=t['tau'][idx];an=t['ang'][:,idx]
    du=[unit(an[0,j],an[1,j]) for j in range(len(idx))];au=[unit(an[2,j],an[3,j]) for j in range(len(idx))]
    g=valid_paths(setup,setup.robot_position(x,y));res={}
    for K in K_SWEEP:
        for A in A_SWEEP:
            asg,feas=match(g,tau,du,au,K,A);miss=[len(g[i][0]) for i in range(len(g)) if i not in asg]
            res[(K,A)]=dict(miss=miss,spur=len(tau)-len(asg))
    # primary-tolerance diagnostics
    asg,feas=match(g,tau,du,au,K_PRIMARY,A_PRIMARY)
    # (a) delay-only ambiguity: trace paths with >1 geometry sequence in the delay window
    delay_amb=0;full_amb=0;mism=0;max_dt=0.;max_ad=0.
    for j in range(len(tau)):
        cand_d=[i for i,(s,tg,d,a) in enumerate(g) if abs(tau[j]-tg)<=K_PRIMARY*float(np.spacing(np.float32(tg)))]
        cand_f=[i for i in cand_d if ang(g[i][2],du[j])<=A_PRIMARY and ang(g[i][3],au[j])<=A_PRIMARY]
        if len(cand_d)>1:delay_amb+=1
        # fully ambiguous = >1 candidates that are not exact duplicates of each other (delay diff < 1e-15 s and same directions)
        distinct=[]
        for i in cand_f:
            if not any(abs(g[i][1]-g[q][1])<1e-15 and ang(g[i][2],g[q][2])<1e-9 and ang(g[i][3],g[q][3])<1e-9 for q in distinct):distinct.append(i)
        if len(distinct)>1:full_amb+=1
    for i,j in asg.items():
        max_dt=max(max_dt,abs(tau[j]-g[i][1]));max_ad=max(max_ad,ang(g[i][2],du[j]),ang(g[i][3],au[j]))
        jn=int(np.argmin(np.abs(tau-g[i][1])))
        if jn!=j and abs(tau[jn]-g[i][1])<=abs(tau[j]-g[i][1]):mism+=1   # delay-only nearest neighbour would have chosen another trace path
    res['diag']=dict(delay_ambiguous_paths=delay_amb,fully_ambiguous_paths=full_amb,delay_nn_identity_mismatch=mism,max_dtau=max_dt,max_ang=max_ad,
        tag=Path(f).name[:-10],geo=len(g),trace=len(tau),orders=[len(s[0]) for s in g],spur_primary=len(tau)-len(asg),
        miss_primary=[len(g[i][0]) for i in range(len(g)) if i not in asg])
    return res
def summarize(name,rows,K,A):
    tot=collections.Counter();miss=collections.Counter();spur=0;per=[]
    for r in rows:
        m=r[(K,A)];per.append(len(m['miss']));spur+=m['spur']
        for o in m['miss']:miss[o]+=1
    return per,miss,spur
if __name__=='__main__':
    t0=time.time();out={};sweeps={}
    for name,d,anchor in SETS:
        files=sorted(d.glob('*_trace.npz'))
        with Pool(4) as p:rows=p.map(one_position,[(str(f),anchor) for f in files],chunksize=8)
        tot=collections.Counter()
        for r in rows:
            for o in r['diag']['orders']:tot[o]+=1
        per,miss,spur=summarize(name,rows,K_PRIMARY,A_PRIMARY);per=np.array(per)
        o23=tot[2]+tot[3];D=[r['diag'] for r in rows]
        out[name]=dict(positions=len(files),geometry_paths={int(k):v for k,v in tot.items()},missing={int(k):v for k,v in miss.items()},
            order01_complete=bool(miss[0]==0 and miss[1]==0),order23_found_fraction=float(1-(miss[2]+miss[3])/o23),positions_complete=int((per==0).sum()),
            max_missing_per_position=int(per.max()),positions_over6=int((per>6).sum()),spurious=int(spur),
            missing_histogram={int(k):int(v) for k,v in sorted(collections.Counter(per.tolist()).items())},
            ambiguity=dict(positions_with_delay_ambiguous_path=sum(1 for q in D if q['delay_ambiguous_paths']>0),delay_ambiguous_paths=sum(q['delay_ambiguous_paths'] for q in D),
                fully_ambiguous_paths=sum(q['fully_ambiguous_paths'] for q in D),delay_nn_identity_mismatch=sum(q['delay_nn_identity_mismatch'] for q in D),
                max_dtau_matched=max(q['max_dtau'] for q in D),max_ang_matched=max(q['max_ang'] for q in D)))
        sw={}
        for K in K_SWEEP:
            for A in A_SWEEP:
                per2,miss2,spur2=summarize(name,rows,K,A);per2=np.array(per2)
                sw[f'K{K}_A{A:g}']=dict(missing_total=int(sum(miss2.values())),spurious=int(spur2),max_missing=int(per2.max()),order01_missing=int(miss2[0]+miss2[1]),
                    order23_found_fraction=float(1-(miss2[2]+miss2[3])/o23))
        sweeps[name]=sw
        # detail of positions with spurious paths at primary tolerance
        out[name]['spurious_positions']=[dict(tag=q['tag'],spur=q['spur_primary'],miss=q['miss_primary']) for q in D if q['spur_primary']>0]
        print(name,json.dumps({k:v for k,v in out[name].items() if k!='missing_histogram'}),'%.0fs'%(time.time()-t0),flush=True)
    here=Path(__file__).resolve().parent
    json.dump(dict(tolerances=dict(K_ulp32=K_PRIMARY,angle_rad=A_PRIMARY),sets=out),open(here/'g3_v2_all.json','w'),indent=1)
    json.dump(sweeps,open(here/'g3_v2_sweep.json','w'),indent=1)
