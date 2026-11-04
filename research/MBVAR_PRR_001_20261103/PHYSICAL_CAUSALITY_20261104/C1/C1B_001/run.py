"""GO-bound same-prior BASE gate diagnostic, DEV then unrepeated remainder."""
import argparse
import csv
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import numpy as np
from threadpoolctl import threadpool_info
from conditional import ARMS, observations, joint_gate, update
from legacy import load
from score import evaluate

HERE = Path(__file__).resolve().parent
BOUND = ('conditional.py','legacy.py','score.py','run.py','launch.py','test_conditional.py',
         'PLAN.json','INPUT_LOCK.json','CONTRACT_KO.md','GOVERNANCE.json','../C1A_001/core.py')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
stamp = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()


def put(path, data):
    path.write_bytes((json.dumps(data,indent=2,allow_nan=False)+'\n').encode('utf8'))


def close(checks, name, actual, expected, angular=False):
    delta = actual-expected
    if angular:
        delta = (delta+np.pi) % (2*np.pi)-np.pi
    checks[name] = max(checks.get(name,0.),float(np.max(np.abs(delta))))
    if not np.all(np.abs(delta) <= 1e-10+1e-10*np.abs(expected)):
        raise ValueError(name+' parity '+str(checks[name]))


def cov(checks, name, matrix):
    matrices = matrix.reshape(-1,4,4)
    symmetry = np.max(np.abs(matrices-matrices.swapaxes(-1,-2)),axis=(1,2))
    eig = np.linalg.eigvalsh((matrices+matrices.swapaxes(-1,-2))*.5)
    scale = np.maximum(1.,np.max(np.abs(eig),axis=1))
    key = name+'_minimum_eigenvalue';checks[key] = min(checks.get(key,float('inf')),float(eig.min()))
    key = name+'_maximum_symmetry_error';checks[key] = max(checks.get(key,0.),float(symmetry.max()))
    if np.any(symmetry > 1e-12*scale) or np.any(eig[:,0] < -1e-12*scale):
        raise ValueError('covariance '+name)


def read(path):
    with np.load(path,allow_pickle=False) as data:
        return dict(data)


def authorization(plan, phase):
    return dict(stage='C1b_only',phase=phase,routes=plan['routes'],biases=plan['biases'],
                seeds=plan['phases'][phase]['seeds'],output=plan['phases'][phase]['output'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase',choices=('dev','remaining'))
    args = parser.parse_args()
    plan = json.loads((HERE/'PLAN.json').read_bytes())
    phase = plan['phases'][args.phase]
    go_path = HERE/phase['go']
    go = json.loads(go_path.read_bytes())
    bindings = {n:sha(HERE/n) for n in BOUND}
    if go.get('schema') != 'C1B_GO_V1' or go.get('decision') != 'GO' or go.get('authorized') != authorization(plan,args.phase) or go.get('bindings_sha256') != bindings:
        raise ValueError('independent phase-specific exact-code GO required')
    if args.phase == 'remaining':
        prior_audit = HERE/'audit/C1B_DEV_RESULT_AUDIT_RESULT.json'
        if sha(prior_audit) != go.get('prerequisite_sha256') or json.loads(prior_audit.read_bytes()).get('decision') != 'ACCEPT':
            raise ValueError('DEV independent acceptance prerequisite')
    out = HERE/phase['output']
    if out.exists():
        raise ValueError('preserve existing scientific output')
    out.mkdir()
    manifest = dict(question_id='C1B-BASE-GATE-001',phase=args.phase,status='RUNNING',
                    start_utc=stamp(),command=sys.argv,bindings_sha256=bindings,
                    go_sha256=sha(go_path),completed_cells=0,priors=0,posterior_rows=0,
                    BASE_shadow_reconstructions=0,FFD_states_completed=0,
                    new_MBVAR_baseline_replays=0,new_training_runs=0,new_RT_calls=0)
    checks, summaries, context = {}, [], {}
    failures = out/'FAILURES.jsonl';failures.touch()
    cell = None
    try:
        if sha(Path(sys.executable)) != plan['python_executable_sha256']:
            raise ValueError('original interpreter executable hash')
        expected = json.loads((Path(plan['cache'])/'provenance/ENV_LOCK.json').read_bytes())
        versions = {name:importlib.metadata.version(name) for name in expected['packages']}
        if sys.version != expected['python'] or versions != expected['packages'] or platform.platform() != expected['os']:
            raise ValueError('original Windows runtime versions')
        if any(os.environ.get(name) != '1' for name in expected['threads']):
            raise ValueError('one-thread environment before NumPy import')
        pools = threadpool_info()
        if not pools or any(p['num_threads'] != 1 for p in pools):
            raise ValueError('actual BLAS threads')
        manifest['runtime'] = dict(python=sys.version,platform=platform.platform(),packages=versions,threadpools=pools)
        lock = json.loads((HERE/'INPUT_LOCK.json').read_bytes())
        cache = Path(plan['cache']);parent = HERE.parent/'C1A_001';inputs = Path(plan['c1a_cache'])
        if sha(parent/'INPUT_LOCK.json') != lock['c1a_input_lock_sha256'] or sha(parent/'audit/C1A_RESULT_AUDIT_RESULT.json') != lock['c1a_result_audit_sha256']:
            raise ValueError('accepted C1a prerequisites')
        parent_audit = json.loads((parent/'audit/C1A_RESULT_AUDIT_RESULT.json').read_bytes())
        parent_index = parent/'RESULTS_001/ARTIFACT_HASHES.json'
        if sha(parent_index) != parent_audit['artifact_hashes_sha256']:
            raise ValueError('accepted C1a artifact index')
        parent_artifacts = json.loads(parent_index.read_bytes())
        parent_lock = json.loads((parent/'INPUT_LOCK.json').read_bytes())
        for name, entry in parent_lock['sources'].items():
            path = inputs/name
            if path.stat().st_size != entry['size'] or sha(path) != entry['payload_sha256']:
                raise ValueError('C1a input '+name)
        for name, entry in lock['sources'].items():
            path = cache/name
            if path.stat().st_size != entry['size'] or sha(path) != entry['sha256']:
                raise ValueError('control/source lock '+name)
        for name, entry in lock['banks'].items():
            path = Path(entry['path'])
            if path.stat().st_size != entry['size'] or sha(path) != entry['sha256']:
                raise ValueError('bank '+name)
        core, online, model = load(cache,lock['banks'])
        spec = dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
        (out/'cells').mkdir()
        with (out/'POSE_EFFECTS.csv').open('x',newline='',encoding='utf8') as table:
            writer = csv.writer(table)
            writer.writerow(('route','bias','seed','pose_id','t_s','arm','accepted','FF_accepted','xy_m','heading_deg','delta_xy_vs_FF','delta_heading_vs_FF','delta_xy_vs_C1a','delta_heading_vs_C1a'))
            for route in plan['routes']:
                for bias in plan['biases']:
                    full = read(inputs/f'{route}_aB_m0_{bias}_Full.npz')
                    los = read(inputs/f'{route}_aB_m0_{bias}_Native_LoS.npz')
                    for seed in phase['seeds']:
                        cell = f'{route}_{bias}_{seed}'
                        context = dict(cell=cell)
                        tr = read(inputs/(cell+'_TRACE.npz'))
                        ctl = read(cache/'controls'/f'{route}_aB_m0_{bias}_{seed}.npz')
                        c1a_path = parent/'RESULTS_001/cells'/(cell+'.npz')
                        if sha(c1a_path) != parent_artifacts['cells/'+cell+'.npz']:
                            raise ValueError('accepted C1a comparison cell '+cell)
                        c1a = read(c1a_path)
                        n = len(tr['t'])
                        if n != plan['route_rows'][route] or len(np.unique(tr['pose_id'])) != n:
                            raise ValueError('denominator/duplicate pose')
                        for data in (full,los,c1a):
                            if not all(np.array_equal(data[key],tr[key]) for key in ('pose_id','t')):
                                raise ValueError('exact pose/time join')
                        # A separate observer-only check, not regeneration of MB_VAR states.
                        if args.phase == 'dev':
                            for start in range(0,n,32):
                                h,H = model.batch(tr['prior'][start:start+32],spec)
                                manifest['FFD_states_completed'] += len(h)
                                close(checks,'source_h_at_MBprior',h,tr['h'][start:start+32])
                                close(checks,'source_H_at_MBprior',H,tr['H'][start:start+32])
                        sx = np.r_[ctl['x0'],0.];sp = full['P0'].copy()
                        dims = dict(prior=(4,),Pprior=(4,4),x=(4,),P=(4,4),h=(2,),H=(2,4),S=(2,2),nis=(4,))
                        base = {key:np.empty((n,*shape)) for key,shape in dims.items()}
                        gates = np.empty((n,4),dtype=bool)
                        for k in range(n):
                            context = dict(cell=cell,index=k,pose_id=int(tr['pose_id'][k]),
                                           t=float(tr['t'][k]),stage='BASE prediction/observation')
                            sx,sp = online.predict(core,sx,sp,k,ctl)
                            hB,HB = model.batch(sx[None],spec);hB,HB = hB[0],HB[0]
                            manifest['FFD_states_completed'] += 1
                            z = observations(full['z'][k],los['z'][k])
                            accepted,nis,S = joint_gate(z,hB,HB,sp,full['muBASE'][k],full['R'][k])
                            context = dict(cell=cell,index=k,pose_id=int(tr['pose_id'][k]),t=float(tr['t'][k]),
                                expected_FF_mask=bool(tr['mask'][k]),calculated_FF_mask=bool(accepted[0]),
                                BASE_prior=sx.tolist(),BASE_Pprior=sp.tolist(),BASE_h=hB.tolist(),BASE_H=HB.tolist(),NIS=nis.tolist())
                            if bool(accepted[0]) != bool(tr['mask'][k]):
                                raise ValueError('original Full BASE mask mismatch')
                            for key,value in [('prior',sx),('Pprior',sp),('h',hB),('H',HB),('S',S),('nis',nis)]:
                                base[key][k] = value
                            gates[k] = accepted
                            # Advance exactly the original Full shadow, never a hybrid history.
                            if accepted[0]:
                                gain = np.linalg.solve(S,HB @ sp).T
                                sx = sx+gain @ (full['z'][k]-hB-full['muBASE'][k]);sx[2] = core.wrap(sx[2])
                                a = np.eye(4)-gain @ HB
                                sp = a @ sp @ a.T+gain @ full['R'][k] @ gain.T;sp = (sp+sp.T)*.5
                            base['x'][k] = sx;base['P'][k] = sp
                        close(checks,'full_mean',tr['mu'],full['muMB'])
                        close(checks,'full_innovation',tr['nu'],full['z']-tr['h']-tr['mu'])
                        close(checks,'W0_R',tr['Rvar'],tr['Reff'])
                        result = update(tr['prior'],tr['Pprior'],tr['h'],tr['H'],tr['mu'],tr['Rvar'],gates,full['z'],los['z'])
                        close(checks,'FF_x_nonangular',result['x'][:,0,[0,1,3]],tr['x'][:,[0,1,3]])
                        close(checks,'FF_heading',result['x'][:,0,2],tr['x'][:,2],True)
                        close(checks,'FF_P',result['P'][:,0],tr['P'])
                        close(checks,'FF_K',result['K'][:,0],tr['K'])
                        close(checks,'C1a_FF_nonangular',result['x'][:,0,[0,1,3]],c1a['x'][:,0,[0,1,3]])
                        close(checks,'C1a_FF_heading',result['x'][:,0,2],c1a['x'][:,0,2],True)
                        close(checks,'C1a_FF_P',result['P'][:,0],c1a['P'])
                        for key,value in result.items():
                            if not np.isfinite(value).all():raise ValueError('nonfinite result '+key)
                        for key,value in base.items():
                            if not np.isfinite(value).all():raise ValueError('nonfinite BASE '+key)
                        for key in ('Pprior','P'):cov(checks,'BASE_'+key,base[key])
                        cov(checks,'MB_prior',tr['Pprior']);cov(checks,'MB_posterior',result['P'])
                        np.savez_compressed(out/'cells'/(cell+'.npz'),pose_id=tr['pose_id'],t=tr['t'],arms=np.array(ARMS),
                            mask=gates,**result,**{'BASE_'+key:value for key,value in base.items()},
                            BASE_mean=full['muBASE'],BASE_R=full['R'],prior=tr['prior'],Pprior=tr['Pprior'],h=tr['h'],H=tr['H'],mu=tr['mu'],R=tr['Rvar'],z_full=full['z'],z_los=los['z'])
                        truth = read(inputs/f'{route}_{bias}_TRUTH.npz')
                        if not all(np.array_equal(tr[key],truth[key]) for key in ('pose_id','t')) or not np.isfinite(truth['truth']).all():
                            raise ValueError('truth keys/nonfinite')
                        rows, summary = evaluate(result,c1a,truth['truth'],tr['t'],tr['pose_id'],gates,route,bias,seed)
                        writer.writerows(rows);table.flush();summaries.extend(summary)
                        manifest['completed_cells'] += 1;manifest['priors'] += n;manifest['posterior_rows'] += len(rows)
                        manifest['BASE_shadow_reconstructions'] += 1
                        put(out/'MANIFEST.json',manifest)
                        print('C1B_CELL',args.phase,cell,manifest['completed_cells'],flush=True)
        if (manifest['completed_cells'],manifest['priors'],manifest['posterior_rows']) != (phase['cells'],phase['priors'],phase['priors']*4):
            raise ValueError('complete phase denominators')
        put(out/'CELL_SUMMARY.json',summaries)
        manifest['status'] = 'NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
    except BaseException as exc:
        manifest.update(status='STOP',failed_cell=cell,error=repr(exc))
        put(out/'FAILED_STATE.json',context)
        failures.write_bytes((json.dumps(dict(cell=cell,error=repr(exc),traceback=traceback.format_exc()))+'\n').encode())
        raise
    finally:
        manifest['end_utc'] = stamp();put(out/'CHECKS.json',checks);put(out/'MANIFEST.json',manifest)
        put(out/'ARTIFACT_HASHES.json',{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'ARTIFACT_HASHES.json'})


if __name__ == '__main__':
    main()
