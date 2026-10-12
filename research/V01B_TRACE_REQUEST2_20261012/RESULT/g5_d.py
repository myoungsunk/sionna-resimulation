import sys,json,hashlib,subprocess,time,importlib.util
import numpy as np
from pathlib import Path
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');R=S/'rfroot'
sys.path.insert(0,str(R/'src'))
from qclean_uwb.drivesim.rf_store import load_banks,tag_of,h_for_antenna_yaws,load_trace
T2=S/'tr2/research/V01B_TRACE_REQUEST2_20261012/DELIVERY_TRACES_20261012'
FR=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C');DA=S/'deliv/research/V01B_DATA_REQUEST_20261011/DELIVERY_A_20261012'
M={c['case']:c for c in json.load(open(S/'matrix.json'))}
FQ=np.load(FR/'freqs_hz.npy')
def sp(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
obs=sp('obs_frozen',str(S/'obs_frozen.py'))
sets=[('R4_aA','R4'),('R2_aA','R2'),('R2_aB','R2'),('R5_aA','R5'),('R5_aB','R5')]
banks=load_banks();out={}
def stored_full(case):
    for p in (FR/'FULL_RF'/f'H_{case}.npy',DA/f'H_{case}.npy'):
        if p.exists():return np.load(p)
for name,r in sets:
    t0=time.time();poses=json.load(open(S/f'rf_poses_{r}.json'));d=T2/name/f'traces_{name}'
    for mount in (0,45):
        case=f'{name}_m{mount}';h=S/f'regen2/H_{case}.npy'
        subprocess.run([sys.executable,'-I',str(R/'scripts/drive_sim/rf_b_apply.py'),'--poses',str(S/f'rf_poses_{r}.json'),'--traces',str(d),'--mount',str(mount),'--out',str(h)],check=True,capture_output=True)
        a=np.load(h);b=stored_full(case);rel=np.linalg.norm((a-b).reshape(len(a),-1),axis=1)/np.linalg.norm(b.reshape(len(b),-1),axis=1)
        sha_ok=hashlib.sha256(h.read_bytes()).hexdigest()==M[case]['full_sha256']
        out[case]=dict(G5_rel_max=float(rel.max()),G5_rel_median=float(np.median(rel)),G5_bitexact=bool(sha_ok),G5_pass_1e12=bool(rel.max()<=1e-12),n_poses=len(a))
        print(case,json.dumps(out[case]),'| %.0fs'%(time.time()-t0),flush=True)
    # LoS H from the trace's shortest-delay path, both mounts
    by={}
    for i,p in enumerate(poses):by.setdefault(tag_of(p['x'],p['y']),[]).append(i)
    for mount in (0,45):
        case=f'{name}_m{mount}';H=np.full((len(poses),257,2,2),np.nan+0j)
        for tg,ix in by.items():
            tr=load_trace(d/f'{tg}_trace.npz');i0=int(np.argmin(tr['tau']));one=dict(tr)
            for k,sl in (('jones',lambda a:a[:,i0:i0+1]),('tau',lambda a:a[i0:i0+1]),('ang',lambda a:a[:,i0:i0+1]),('present',lambda a:a[:,i0:i0+1])):one[k]=sl(tr[k])
            hh=h_for_antenna_yaws(one,banks,[poses[i]['yaw_body_deg']+mount for i in ix])
            for i,row in zip(ix,hh):H[poses[i]['pose_id']]=row
        np.save(S/f'los_gen/H_LoS_{case}.npy',H);ex=FR/f'H_LoS_{case}.npy'
        if ex.exists():
            L=np.load(ex);rel=np.linalg.norm((H-L).reshape(len(H),-1),axis=1)/np.linalg.norm(L.reshape(len(L),-1),axis=1)
            idx=np.unique(np.linspace(0,len(H)-1,len(H)).astype(int));oa=obs.observe(np.asarray(H),FQ,None,None,tx=0);ob=obs.observe(np.asarray(L),FQ,None,None,tx=0)
            det=np.asarray(oa['detected'])&np.asarray(ob['detected']);ds=np.abs(np.asarray(oa['s'])-np.asarray(ob['s']))[det]
            out[case]['LoS_parity']=dict(rel_max=float(rel.max()),rel_median=float(np.median(rel)),ds_max=float(np.nanmax(ds)),tap_equal=bool(np.array_equal(oa['index'],ob['index'])),pass_=bool(rel.max()<=1e-3 and np.nanmax(ds)<=.01))
            print('  LoS parity',case,json.dumps(out[case]['LoS_parity']),flush=True)
        else:
            out[case]['LoS_generated']=hashlib.sha256((S/f'los_gen/H_LoS_{case}.npy').read_bytes()).hexdigest();print('  LoS generated (no stored reference)',case,out[case]['LoS_generated'][:16],flush=True)
    json.dump(out,open(S/'g5_d.json','w'),indent=1)
