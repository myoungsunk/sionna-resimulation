"""GO-bound C2 execution: immutable Full prefix and independent recursive arms."""
import argparse
import csv
import datetime
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import numpy as np
from threadpoolctl import threadpool_info
from authority import HERE,check,sha,committed_revision
from engine import run as recurse,RecursionFailure
from evaluate import baseline_score,window_score


def put(path,value):path.write_bytes((json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf8'))
def read(path):
    with np.load(path,allow_pickle=False) as data:return dict(data)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def close(checks,name,actual,expected,angular=False):
    difference=actual-expected
    if angular:difference=(difference+np.pi)%(2*np.pi)-np.pi
    checks[name]=max(checks.get(name,0.),float(np.max(np.abs(difference))))
    if not np.all(np.abs(difference)<=1e-10+1e-10*np.abs(expected)):
        raise ValueError(name+' parity '+str(checks[name]))


def validate_inputs(plan):
    lock=json.loads((HERE/'INPUT_LOCK.json').read_bytes())
    for name,entry in lock['accepted_prerequisites'].items():
        p=Path(name)
        if p.stat().st_size!=entry['size'] or sha(p)!=entry['sha256']:raise ValueError('accepted prerequisite '+name)
    source=Path(lock['C0A_csv']['path'])
    if sha(source)!=lock['C0A_csv']['sha256'] or source.stat().st_size!=lock['C0A_csv']['size']:raise ValueError('C0A source lock')
    parent=Path(plan['c1a_phase']);other=Path(plan['c1b_phase'])
    a=json.loads((parent/'INPUT_LOCK.json').read_bytes());b=json.loads((other/'INPUT_LOCK.json').read_bytes())
    for registry,folder,key in ((a['sources'],Path(plan['c1a_cache']),'payload_sha256'),(b['sources'],Path(plan['cache']),'sha256')):
        for name,entry in registry.items():
            p=folder/name
            if p.stat().st_size!=entry['size'] or sha(p)!=entry[key]:raise ValueError('immutable source '+name)
    for name,entry in b['banks'].items():
        p=Path(entry['path'])
        if p.stat().st_size!=entry['size'] or sha(p)!=entry['sha256']:raise ValueError('bank '+name)
    acceptance=json.loads((other/'audit/C1B_RESULT_AUDIT_RESULT.json').read_bytes())
    if acceptance['decision']!='ACCEPT' or acceptance['counts']['cells']!=120:raise ValueError('C1b full acceptance')
    indexes={}
    for phase in ('DEV_001','REMAINING_001'):
        name=phase+'/ARTIFACT_HASHES.json';p=other/name
        if sha(p)!=acceptance['phase_artifact_and_report_sha256'][name]:raise ValueError('C1b accepted artifact index')
        indexes[phase]=json.loads(p.read_bytes())
    return lock,b,indexes


def runtime(plan):
    expected=json.loads((Path(plan['cache'])/'provenance/ENV_LOCK.json').read_bytes())
    versions={name:importlib.metadata.version(name) for name in expected['packages']}
    if sys.version!=expected['python'] or platform.platform()!=expected['os'] or versions!=expected['packages'] or sha(Path(sys.executable))!=plan['python_executable_sha256']:
        raise ValueError('original Windows runtime identity')
    if any(os.environ.get(name)!='1' for name in expected['threads']):raise ValueError('one-thread environment')
    pools=threadpool_info()
    if not pools or any(p['num_threads']!=1 for p in pools):raise ValueError('actual BLAS threads')
    return dict(python=sys.version,platform=platform.platform(),packages=versions,threadpools=pools,
                loaded_BLAS_sha256={p['filepath']:sha(Path(p['filepath'])) for p in pools})


def source_module(path):
    spec=importlib.util.spec_from_file_location('c2_frozen_legacy_loader',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def truth_reference(model,spec,truth,physical):
    n=len(truth['t']);h=[];H=[];taps=[];cells=[];margins=[]
    for k in range(0,n,32):
        pred,jac,diag=model.batch(truth['truth'][k:k+32],spec,return_diagnostics=True)
        h.append(pred);H.append(jac);taps.append(diag['tap']);cells.append(diag['cells']);margins.append(diag['fp_margin'])
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(truth['truth'][:,:2],axis=0),axis=1))]
    rows=[physical[int(i)] for i in truth['pose_id']]
    if not np.all(np.abs(np.array([float(r['t_s']) for r in rows])-truth['t'])<=1e-9):raise ValueError('C0A truth time join')
    return dict(t=truth['t'],pose_id=truth['pose_id'],h=np.concatenate(h),H=np.concatenate(H),
        source_tap=np.concatenate(taps),source_cells=np.concatenate(cells),source_fp_margin=np.concatenate(margins),
        physical_delta=np.array([[float(r['delta_range_m']),float(r['physical_e_mp'])] for r in rows]),
        physical_delta_tap=np.array([int(r['delta_tap']) for r in rows]),
        time_bin=np.floor((truth['t']+1e-9)/1.).astype(np.int64),distance_m=distance,
        distance_bin=np.floor((distance+1e-12)/.2).astype(np.int64))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('dev','remaining'));args=parser.parse_args()
    plan,phase,go,bindings=check(args.phase)
    revision=committed_revision(args.phase)
    out=HERE/phase['output']
    if out.exists():raise ValueError('preserve scientific output')
    out.mkdir()
    manifest=dict(question_id='C2-RECURSIVE-001',phase=args.phase,status='RUNNING',start_utc=stamp(),
        command=sys.argv,code_revision=revision,published_bound_files_match=True,bindings_sha256=bindings,
        go_sha256=sha(HERE/phase['go']),source_cells_completed=0,window_cells_completed=0,trajectories=0,posterior_rows=0,
        FFD_states_filter=0,FFD_states_FF_verification=0,FFD_states_truth_reference=0,
        FF_source_verification_replays=0,new_MBVAR_baseline_experiments=0,new_training_runs=0,new_RT_calls=0,
        prefix_checkpoint_windows=0,model_initialization_attempts=0,model_initializations=0)
    (out/'FAILURES.jsonl').touch();checks={};context={};summaries=[];blocks=[];diagnostics=[]
    try:
        manifest['runtime']=runtime(plan)
        lock,b_lock,indexes=validate_inputs(plan)
        cache=Path(plan['c1a_cache']);controls=Path(plan['cache']);other=Path(plan['c1b_phase'])
        all_windows=json.loads((HERE/'WINDOWS.json').read_bytes())['windows']
        rf={r:{} for r in plan['routes']}
        for row in csv.DictReader(Path(lock['C0A_csv']['path']).open(encoding='utf8')):
            route=row['route'];pid=int(row['pose_id'])
            if pid in rf[route]:raise ValueError('duplicate C0A pose')
            rf[route][pid]=row
        dev_index=None
        if args.phase=='remaining':
            dev_audit=json.loads((HERE/'audit/C2_DEV_RESULT_AUDIT_RESULT.json').read_bytes())
            p=HERE/'DEV_001/ARTIFACT_HASHES.json'
            if sha(p)!=dev_audit['artifact_hashes_sha256']:raise ValueError('accepted C2 DEV artifact index')
            dev_index=json.loads(p.read_bytes())
        for folder in ('filter','metrics','baselines','evaluation_refs','verification','partial'): (out/folder).mkdir()
        stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
        def progress(info):
            context.update(info)
            if stop and Path(stop).exists():raise RuntimeError('managed stop requested')
            if info['index']%100==0:print('C2_PROGRESS',args.phase,context.get('cell'),info['index'],flush=True)
        loader=source_module(other/'legacy.py')
        manifest['model_initialization_attempts']+=1
        core,online,model=loader.load(Path(plan['cache']),b_lock['banks']);manifest['model_initializations']=1
        spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
        for route in plan['routes']:
            windows=[w for w in all_windows if w['route']==route]
            for bias in plan['biases']:
                full=read(cache/f'{route}_aB_m0_{bias}_Full.npz');los=read(cache/f'{route}_aB_m0_{bias}_Native_LoS.npz')
                for seed in phase['seeds']:
                    cell=f'{route}_{bias}_{seed}';context=dict(cell=cell,stage='input join')
                    tr=read(cache/(cell+'_TRACE.npz'));ctl=read(controls/'controls'/f'{route}_aB_m0_{bias}_{seed}.npz')
                    n=len(tr['t']);which='DEV_001' if seed==10 else 'REMAINING_001'
                    p=other/which/'cells'/(cell+'.npz')
                    if sha(p)!=indexes[which]['cells/'+cell+'.npz']:raise ValueError('accepted BASE checkpoint payload')
                    base=read(p)
                    if n!=plan['route_rows'][route] or len(np.unique(tr['pose_id']))!=n or not np.all(np.abs(np.diff(tr['t'])-.2)<=1e-9):raise ValueError('unique complete 5Hz grid')
                    for data in (full,los,base):
                        if not all(np.array_equal(tr[key],data[key]) for key in ('t','pose_id')):raise ValueError('exact pose/time join')
                    if any(len(ctl[key])!=n for key in ('ds','gy','dt')):raise ValueError('controls length')
                    for window in windows:
                        if abs(tr['t'][window['first_index']]-window['start_s'])>1e-9 or abs(tr['t'][window['last_index']]-window['end_s'])>1e-9:raise ValueError('frozen window grid')
                    if args.phase=='dev':
                        verified,stat=recurse(core,online,model,spec,full,los,ctl,tr,base,[],verify_ff=True,progress=progress)
                        data=verified['FF_VERIFY']
                        if not np.array_equal(data['mask'][:,0],tr['mask']):raise ValueError('FF original mask parity')
                        for name in ('P','prior','Pprior','h','H','K','nu','S'):
                            close(checks,'FF_'+name,data[name][:,0],tr[name])
                        close(checks,'FF_R',data['R'][:,0],tr['Rvar'])
                        close(checks,'FF_x_nonangular',data['x'][:,0,[0,1,3]],tr['x'][:,[0,1,3]])
                        close(checks,'FF_heading',data['x'][:,0,2],tr['x'][:,2],True)
                        for name in ('x','P','prior','Pprior','h','H','S'):
                            if name=='x':
                                close(checks,'Full_BASE_x_nonangular',data['BASE_x'][:,0,[0,1,3]],base['BASE_x'][:,[0,1,3]])
                                close(checks,'Full_BASE_heading',data['BASE_x'][:,0,2],base['BASE_x'][:,2],True)
                            else:close(checks,'Full_BASE_'+name,data['BASE_'+name][:,0],base['BASE_'+name])
                        np.savez_compressed(out/'verification'/(cell+'.npz'),**data)
                        manifest['FF_source_verification_replays']+=1;manifest['FFD_states_FF_verification']+=stat['FFD_states']
                    records,stat=recurse(core,online,model,spec,full,los,ctl,tr,base,windows,progress=progress)
                    manifest['FFD_states_filter']+=stat['FFD_states']
                    checks['minimum_covariance_eigenvalue']=min(checks.get('minimum_covariance_eigenvalue',float('inf')),stat['minimum_eigenvalue'])
                    checks['maximum_covariance_symmetry_error']=max(checks.get('maximum_covariance_symmetry_error',0.),stat['maximum_symmetry_error'])
                    # No GT/error/NEES inputs were passed to either recursion above.
                    truth=read(cache/f'{route}_{bias}_TRUTH.npz')
                    if not all(np.array_equal(tr[key],truth[key]) for key in ('t','pose_id')) or not np.isfinite(truth['truth']).all():raise ValueError('truth exact join/finite')
                    name=f'{route}_{bias}.npz'
                    if args.phase=='dev':
                        reference=truth_reference(model,spec,truth,rf[route]);reference['truth_sha256']=np.array(sha(cache/f'{route}_{bias}_TRUTH.npz'))
                        np.savez_compressed(out/'evaluation_refs'/name,**reference)
                        manifest['FFD_states_truth_reference']+=n
                    else:
                        p=HERE/'DEV_001/evaluation_refs'/name
                        if sha(p)!=dev_index['evaluation_refs/'+name]:raise ValueError('accepted truth-observer reference')
                        reference=read(p)
                        if str(reference['truth_sha256'])!=sha(cache/f'{route}_{bias}_TRUTH.npz'):raise ValueError('reference truth binding')
                    if not all(np.array_equal(reference[key],tr[key]) for key in ('t','pose_id')):raise ValueError('evaluation reference exact join')
                    baseline=baseline_score(tr,truth)
                    np.savez_compressed(out/'baselines'/(cell+'.npz'),t=tr['t'],pose_id=tr['pose_id'],**baseline)
                    for window in windows:
                        context.update(window=window['id'],stage='post-recursion evaluation')
                        data=records[window['id']];stem=cell+'_'+window['id']
                        np.savez_compressed(out/'filter'/(stem+'.npz'),**data)
                        metrics,rows,block,diag=window_score(data,tr,baseline,truth,reference,window,route,bias,seed)
                        np.savez_compressed(out/'metrics'/(stem+'.npz'),**metrics)
                        summaries.extend(rows);blocks.extend(block);diagnostics.extend(diag)
                        manifest['window_cells_completed']+=1;manifest['trajectories']+=6;manifest['posterior_rows']+=len(data['t'])*6
                        manifest['prefix_checkpoint_windows']+=int(window['first_index']>0)
                    manifest['source_cells_completed']+=1;put(out/'MANIFEST.json',manifest)
                    print('C2_CELL',args.phase,cell,manifest['source_cells_completed'],manifest['window_cells_completed'],flush=True)
        for actual,expected in (('source_cells_completed','source_cells'),('window_cells_completed','window_cells'),('trajectories','trajectories'),('posterior_rows','posterior_rows')):
            if manifest[actual]!=phase[expected]:raise ValueError('complete denominators '+actual)
        keys=[(r['route'],r['bias'],r['seed'],r['window'],r['mode'],r['arm']) for r in summaries]
        if len(keys)!=len(set(keys)) or len(keys)!=phase['trajectories']:raise ValueError('summary completeness/duplicates')
        put(out/'TRAJECTORY_SUMMARY.json',summaries);put(out/'AUTOCORRELATION.json',diagnostics)
        for filename,rows in (('TRAJECTORY_SUMMARY.csv',summaries),('DIAGNOSTIC_BLOCKS.csv',blocks)):
            with (out/filename).open('x',encoding='utf8',newline='') as table:
                writer=csv.DictWriter(table,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        manifest['status']='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
    except BaseException as error:
        manifest.update(status='STOP',error=repr(error))
        if isinstance(error,RecursionFailure):
            context.update(error.context)
            for name,data in error.partial.items():np.savez_compressed(out/'partial'/(str(context.get('cell','unknown'))+'_'+name+'.npz'),**data)
        put(out/'FAILED_STATE.json',context)
        (out/'FAILURES.jsonl').write_bytes((json.dumps(dict(context=context,error=repr(error),traceback=traceback.format_exc()))+'\n').encode('utf8'))
        raise
    finally:
        manifest['end_utc']=stamp();put(out/'CHECKS.json',checks);put(out/'MANIFEST.json',manifest)
        put(out/'ARTIFACT_HASHES.json',{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'})


if __name__=='__main__':main()
