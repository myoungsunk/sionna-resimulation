"""Build Native-LoS packets using a Full-parity-verified R2 model."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
out=Path(__file__).resolve().parent
pkg=out.parents[2]
sys.path.insert(0,str(pkg/'S1'))
import parity as p
b=p.b
case='R2_aB_m0'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert json.loads((out/'FULL_GATE.json').read_text())['passed']
lock=json.loads((out/'NATIVE_LOCK.json').read_text())
native=out/(case+'_Native_LoS.csv')
assert digest(native)==lock[native.name]
means=pd.read_csv(native,float_precision='round_trip').set_index('pose_id',verify_integrity=True)
base=b.orig/'p2'
manifest=json.loads((base/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_bytes())
meta=next(q for q in manifest['cases'] if q['id']==case)
src=base/meta['los_path']; samples=base/meta['samples_path']
training=json.loads((out/'TRAINING_LOCK.json').read_text())
assert all(digest(base/meta[q])==training['source_hash'][meta[q]] for q in ['los_path','samples_path'])
H=np.load(src,mmap_mode='r')
poses=[r['pose_id'] for r in json.loads(samples.read_bytes())]
assert len(poses)==len(set(poses))==len(H)
import subprocess
raw=subprocess.check_output(['git','-C',str(b.repo),'show',training['source']+':research/PJ_DS_GATED_20261021/series_dump.py'])
nodes=[n for n in ast.parse(raw).body if (isinstance(n,ast.FunctionDef) and n.name=='taps') or (isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='OFFS')]
ns={'np':np}
exec(compile(ast.Module(nodes,type_ignores=[]),'original_taps','exec'),ns)
chunks=[ns['taps'](H[i:i+128,:,:,0]) for i in range(0,len(H),128)]
taps=pd.DataFrame({k:np.concatenate([c[k] for c in chunks]) for k in ('ds_+1','s_fp_chk')},index=poses)
featfile=b.orig/'p2_artifacts/prepared/OBSERVATION_FEATURES_LABELS.csv.gz'
assert digest(featfile)==training['features_sha256']
ft=pd.read_csv(featfile)
ft=ft[(ft.case==case)&(ft.channel=='los')].set_index('pose_id',verify_integrity=True)
assert np.max(abs(ft.loc[poses,'s_fp']-taps.s_fp_chk))<1e-9
receipt={}
for bias in ['B0','L2']:
    full=b.cache/'research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL'/(case+'_'+bias+'.npz')
    nativepath=next((b.orig/'p2_artifacts').rglob(case+'_los_'+bias+'_TRACE.npz'))
    with np.load(full) as c,np.load(nativepath) as n:
        jb=c['names'].tolist().index('OFF_BB')
        j=n['arms'].tolist().index('POWER_DIAG')
        ids=c['pose_id']; t=c['t_s']; gt=c['truth_scoring_only'][:,:3]
        assert np.array_equal(ids,n['pose_id']) and np.array_equal(t,n['t_s']) and np.array_equal(ids,means.index)
        bb=n['mu'][:,j]; mb=bb.copy();mb[:,0]=means.loc[ids,'MU_R_EXDS_m']
        R=n['R'][:,j];z=ft.loc[ids,['range_m','s_fp']].to_numpy()
        P0=c['Pprior'][0,jb];D=taps.loc[ids,'ds_+1'].abs().to_numpy()
        assert np.isfinite(D).all()
        packet=dict(t=t,pose_id=ids,z=z,muMB=mb,muBASE=bb,R=R,P0=P0,D=D)
        ds,gy,dt,x0=b.pb.build_controls(t,gt,bias,0)
        mask=b.pb.gated_mask(z,bb,R,ds,gy,dt,np.r_[x0,0.],P0,p.spec,b.model)
        assert np.array_equal(mask,n['accepted'][:,j])
        data=dict(t=t,z=z,mu=dict(MB=mb),R=R,R0=R,ds=ds,gy=gy,dt=dt,x0=np.r_[x0,0.],P0=P0,anchor=np.array([10.,0.]),spec=p.spec,acc=mask,fin=np.isfinite(z).all(1))
        X,P,_,_=b.pb.run(data,mb,dict(mode='var'),b.model)
        tr=p.online.replay(packet,dict(ds=ds,gy=gy,dt=dt,x0=x0),'W0',b.core,b.model,p.spec)
        assert np.array_equal(tr['mask'],mask) and np.allclose(X,tr['x'],atol=1e-10,rtol=1e-10) and np.allclose(P,tr['P'],atol=1e-10,rtol=1e-10)
        target=out/(case+'_'+bias+'_Native_LoS.npz')
        np.savez_compressed(target,**packet)
        receipt[bias]=dict(n=len(ids),packet_sha256=digest(target),control_sha256=digest(full),historical_trace_sha256=digest(nativepath),max_dx=float(np.max(abs(X-tr['x']))),max_dP=float(np.max(abs(P-tr['P']))),gate_differences=0)
(out/'PACKETS.json').write_text(json.dumps(receipt,indent=2))
files={f'R2_aB_m0_{bias}_Native_LoS.npz':item['packet_sha256'] for bias,item in receipt.items()}
(out/'INPUT_LOCK.json').write_text(json.dumps(dict(channel='Native_LoS',files=files),indent=2))
