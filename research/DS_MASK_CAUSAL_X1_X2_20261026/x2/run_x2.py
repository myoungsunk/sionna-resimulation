from pathlib import Path
import os,sys,json,hashlib,datetime,traceback
R=Path(__file__).resolve().parent
OLD=R.parent/'DS_MASK_CAUSAL_X0A_X1_20261026_01a1775b'
PARENT=R.parent/'OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849'
SRC=PARENT/'p2'
sys.dont_write_bytecode=True
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
os.environ.update(PJ_SOURCE_ROOT=str(SRC),PJ_ART=str(PARENT/'p2_artifacts'),PJ_OUT=str(R/'runtime'))
import numpy as np
import pandas as pd
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,data):
    (R/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def event(stage,**kw):
    d=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage=stage,**kw)
    with (R/'events.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(d)+'\n')
    print(json.dumps(d),flush=True)
def stop():
    f=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if f and Path(f).exists():raise RuntimeError('MANAGED_STOP_REQUESTED')
def err(a,b):
    d=np.asarray(a)-np.asarray(b);d=d.copy();d[...,2]=(d[...,2]+np.pi)%(2*np.pi)-np.pi;return d
checks=[]
def check(name,a,b,tol=1e-9):
    a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(name,a.shape,b.shape)
    delta=float(np.max(np.abs(a-b)));assert np.isfinite(delta) and delta<=tol,(name,delta,tol)
    checks.append(dict(name=name,max_abs_difference=delta,atol=tol))
def main():
    assert json.loads((OLD/'EXECUTION_RESULT.json').read_text())['status']=='TECHNICAL_PASS'
    previous=json.loads((OLD/'INPUT_LOCK.json').read_text())
    locked=previous['files'].copy()
    oldhash={x['path']:x['sha256'] for x in json.loads((OLD/'OUTPUT_SHA256.json').read_text())['files']}
    inputs=list((OLD/'x1').glob('*.npz'))+[OLD/'EXECUTION_RESULT.json',OLD/'INPUT_LOCK.json']
    assert len(inputs)==16
    for p in inputs:
        h=sha(p);assert h==oldhash[p.relative_to(OLD).as_posix()]
        locked.append(dict(path=str(p),sha256=h))
    for rec in locked:assert sha(rec['path'])==rec['sha256'],rec['path']
    write('INPUT_LOCK.json',dict(files=locked,protocol_sha256=sha(R/'PROTOCOL.md'),script_sha256=sha(__file__),command=sys.argv,python=sys.version))
    event('INPUT_FREEZE_PASS',files=len(locked))
    sys.path.insert(0,str(SRC/'research/PJ_DS_GATED_20261021'))
    import v_replay as V
    from core import transition
    model=V.SourceFFD();gates=[];packetrows=[];crossrows=[]
    outdir=R/'linear';outdir.mkdir(exist_ok=True)
    for case in V.MANIFEST['cases']:
        for bias in ['B0','L2']:
            cid=case['id'];event('LINEAR_START',case=cid,bias=bias);stop()
            with np.load(OLD/'x1'/f'{cid}_{bias}.npz',allow_pickle=False) as data:d={k:data[k] for k in data.files}
            t=d['t_s'];truth=np.column_stack([d['truth_scoring_only'],np.full(len(t),np.radians(V.BIAS_LEVELS[bias]))])
            controls,x0=V.build_positive_bias_controls(t,d['truth_scoring_only'],bias)
            check(cid+bias+'_initial',err(d['prior'][0,0],np.r_[x0,0]),np.zeros(4))
            ht=np.concatenate([model.batch(truth[k:k+64],case)[0] for k in range(0,len(t),64)])
            for arm in ['BB','MM']:
                j=list(d['names']).index(arm);n=len(t);actual=err(d['x'][:,j],truth);ep=err(d['prior'][:,j],truth)
                K=d['K'][:,j]*d['acc'][:,j,None,None];H=d['H'][:,j]
                u=d['z']-ht-d['mu'][:,j];A=np.eye(4)[None]-K@H
                T=np.empty((n,4,4));motion=np.zeros((n,4));remainder=np.zeros((n,4));linear=np.zeros((n,4));closure=np.zeros((n,4));components=np.zeros((n,3,4))
                initial=ep[0].copy()
                for k in range(n):
                    if k%128==0:stop()
                    F=np.eye(4);w=np.zeros(4);df=np.zeros(4)
                    if k:
                        args=[float(controls[key][k]) for key in ['ds_odom','dtheta_gyro','dt_s']]
                        predicted,F,_=transition(d['x'][k-1,j],*args)
                        check(f'{cid}{bias}{arm}_prior_{k}',err(predicted,d['prior'][k,j]),np.zeros(4),1e-11)
                        fp,_,_=transition(truth[k-1],*args);w=err(fp,truth[k])
                        df=ep[k]-F@actual[k-1]-w
                    dh=d['h'][k,j]-ht[k]-H[k]@ep[k]
                    T[k]=A[k]@F;motion[k]=A[k]@w;remainder[k]=A[k]@df-K[k]@dh
                    prev=linear[k-1] if k else initial
                    linear[k]=T[k]@prev+motion[k]+K[k]@u[k]
                    prevc=closure[k-1] if k else initial
                    closure[k]=T[k]@prevc+motion[k]+K[k]@u[k]+remainder[k]
                    components[k,0]=T[k]@(components[k-1,0] if k else initial)+motion[k]
                    components[k,1]=T[k]@(components[k-1,1] if k else np.zeros(4))+K[k,:,0]*u[k,0]
                    components[k,2]=T[k]@(components[k-1,2] if k else np.zeros(4))+K[k,:,1]*u[k,1]
                check(f'{cid}{bias}{arm}_nonlinear_closure',closure,actual)
                check(f'{cid}{bias}{arm}_component_sum',components.sum(axis=1),linear)
                for window,mask in [('all',np.ones(n,bool)),('t_ge_30',t>=30)]:
                    a=np.degrees(actual[mask,2]);b=np.degrees(linear[mask,2]);ra=float(np.sqrt(np.mean(a*a)));rb=float(np.sqrt(np.mean(b*b)))
                    corr=float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else None
                    rel=abs(rb/ra-1) if ra>0 else None;passed=corr is not None and rel is not None and corr>=.9 and rel<=.05
                    gates.append(dict(case=cid,bias=bias,arm=arm,window=window,correlation=corr,actual_rmse_deg=ra,linear_rmse_deg=rb,relative_rmse_difference=rel,series_error_rmse_deg=float(np.sqrt(np.mean((a-b)**2))),gate_pass=passed))
                np.savez_compressed(outdir/f'{cid}_{bias}_{arm}.npz',t_s=t,pose_id=d['pose_id'],actual_error=actual,linear_error=linear,closure_error=closure,components=components,T=T,K=K,u=u,motion=motion,remainder=remainder,accepted=d['acc'][:,j],base_accept=d['acc'][:,0],mur_accept=d['acc'][:,3])
            pd.DataFrame(gates).to_csv(R/'LINEAR_GATE.csv',index=False)
            event('LINEAR_CASE_DONE',case=cid,bias=bias,passed=all(x['gate_pass'] for x in gates[-4:]))
    passed=all(x['gate_pass'] for x in gates)
    write('LINEAR_GATE.json',dict(status='PASS' if passed else 'FAIL',condition_arms=28,window_checks=56,passed_window_checks=sum(x['gate_pass'] for x in gates),thresholds=dict(min_correlation=.9,max_relative_rmse_difference=.05),nonlinear_closure='PASS',attribution_authorized_by_gate=passed))
    if passed:
        for f in sorted(outdir.glob('*.npz')):
            d=dict(np.load(f,allow_pickle=False));stem=f.stem;case,bias,arm=stem.rsplit('_',2);n=len(d['t_s']);mask=d['t_s']>=30
            states=np.zeros((n,2,4));contrib=np.zeros((n,n,2))
            for k in range(n):
                if k%128==0:stop()
                states[:k]=np.einsum('ij,ncj->nci',d['T'][k],states[:k])
                states[k]=d['K'][k].T*d['u'][k,:,None]
                contrib[k,:k+1]=np.degrees(states[:k+1,:,2])
            total=contrib.sum(axis=1);check(stem+'_packet_sum',total,np.degrees(d['components'][:,1:,2]),1e-8)
            cross=2*total[mask,0]*total[mask,1]
            crossrows.append(dict(case=case,bias=bias,arm=arm,cross_sum_deg2=float(cross.sum()),cross_mean_deg2=float(cross.mean())))
            for k in range(n):
                group='both' if d['base_accept'][k] and d['mur_accept'][k] else 'new' if d['mur_accept'][k] else 'lost' if d['base_accept'][k] else 'neither'
                for ch,channel in enumerate(['range','pol']):
                    vals=contrib[mask,k,ch];packetrows.append(dict(case=case,bias=bias,arm=arm,pose_id=int(d['pose_id'][k]),packet_time=float(d['t_s'][k]),channel=channel,group=group,signed_sum_deg=float(vals.sum()),positive_times=int((vals>0).sum()),negative_times=int((vals<0).sum())))
            np.savez_compressed(R/(stem+'_contributions.npz'),c_deg=contrib,t_s=d['t_s'],pose_id=d['pose_id'])
        pd.DataFrame(crossrows).to_csv(R/'CROSS_TERMS.csv',index=False);pd.DataFrame(packetrows).to_csv(R/'PACKET_CONTRIBUTIONS.csv.gz',index=False)
    for rec in locked:assert sha(rec['path'])==rec['sha256']
    write('CHECKS.json',checks)
    write('EXECUTION_RESULT.json',dict(status='X2_ATTRIBUTION_COMPLETE' if passed else 'STOP_LINEAR_GATE',linear_gate='PASS' if passed else 'FAIL',attribution_executed=passed,inputs_preserved=True,checks=len(checks),claim='Local frozen linear bookkeeping only' if passed else 'Linear approximation failed preregistered fidelity; no channel attribution conclusion'))
    event('COMPLETE',status='X2_ATTRIBUTION_COMPLETE' if passed else 'STOP_LINEAR_GATE')
if __name__=='__main__':
    try:main()
    except BaseException as e:
        write('FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
