"""GO-bound C1a runner. Archived priors only; no filter/model/RT replay."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import traceback
import numpy as np
from core import ARMS, update, wrap
from evaluate import score

HERE = Path(__file__).resolve().parent
BOUND = ('core.py', 'evaluate.py', 'test_core.py', 'run.py', 'launch.py',
         'PLAN.json', 'CONTRACT_KO.md', 'INPUT_LOCK.json', 'GOVERNANCE.json')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
stamp = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()


def put(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False)+'\n', encoding='utf8')


def close(name, actual, expected, checks, angular=False):
    difference = wrap(actual-expected) if angular else actual-expected
    maximum = float(np.max(np.abs(difference)))
    checks[name] = max(checks.get(name, 0.), maximum)
    if angular:
        ok = np.all(np.abs(difference) <= 1e-10 + 1e-10*np.abs(expected))
    else:
        ok = np.allclose(actual, expected, atol=1e-10, rtol=1e-10)
    if not ok:
        raise ValueError(f'{name}: max absolute {maximum}')


def covariance_check(name, p, checks):
    sym = np.max(np.abs(p-p.swapaxes(-1, -2)), axis=(1, 2))
    eig = np.linalg.eigvalsh((p+p.swapaxes(-1, -2))*.5)
    scale = np.maximum(1., np.max(np.abs(eig), axis=1))
    key = name+'_minimum_eigenvalue'
    checks[key] = min(checks.get(key, float('inf')), float(eig.min()))
    key = name+'_maximum_symmetry_error'
    checks[key] = max(checks.get(key, 0.), float(sym.max()))
    if np.any(sym > 1e-12*scale) or np.any(eig[:, 0] < -1e-12*scale):
        raise ValueError('covariance '+name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--go', required=True, type=Path)
    args = parser.parse_args()
    plan = json.loads((HERE/'PLAN.json').read_bytes())
    go = json.loads(args.go.read_bytes())
    bindings = {n: sha(HERE/n) for n in BOUND}
    if go.get('schema') != 'C1A_GO_V1' or go.get('decision') != 'GO':
        raise ValueError('independent C1a GO required')
    if go.get('bindings_sha256') != bindings or go.get('authorized') != plan['authorized']:
        raise ValueError('GO code/contract/scope bindings')
    if sys.version_info[:3] != (3, 11, 17) or np.__version__ != '1.26.4':
        raise ValueError('pinned Python/NumPy')
    if any(os.environ.get(n) != '1' for n in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):
        raise ValueError('one thread environment')
    if args.input.resolve() != Path(plan['input_linux']).resolve() or args.out.resolve() != Path(plan['output_linux']).resolve():
        raise ValueError('frozen paths')
    if args.out.exists():
        raise ValueError('preserve existing output')
    args.out.mkdir()
    manifest = dict(question_id='C1A-SAME-PRIOR-001', status='RUNNING',
                    start_utc=stamp(), command=sys.argv, python=sys.version,
                    numpy=np.__version__, platform=platform.platform(),
                    go_sha256=sha(args.go), bindings_sha256=bindings,
                    completed_cells=0, priors=0, posterior_rows=0,
                    new_filter_replays=0, new_RT_calls=0)
    checks = {}
    summaries = []
    failures = args.out/'FAILURES.jsonl'
    failures.touch()
    cell = None
    try:
        lock = json.loads((HERE/'INPUT_LOCK.json').read_bytes())
        for name, entry in lock['sources'].items():
            path = args.input/name
            if path.stat().st_size != entry['size'] or sha(path) != entry['payload_sha256']:
                raise ValueError('input lock '+name)
        registries = {n: json.loads((args.input/n).read_bytes()) for n in
                      ('S1_materialized_registry.json','R2_input_registry.json','R2_native_registry.json')}
        for route in plan['authorized']['routes']:
            for bias in plan['authorized']['biases']:
                for channel in ('Full','Native_LoS'):
                    name = f'{route}_aB_m0_{bias}_{channel}.npz'
                    registry = registries['R2_input_registry.json' if channel == 'Full' else 'R2_native_registry.json']['files'] if route == 'R2' else registries['S1_materialized_registry.json']
                    key = name if route == 'R2' else 'algorithm_input/'+name
                    if registry[key] != sha(args.input/name):
                        raise ValueError('packet source registry')
                truth_name = f'{route}_{bias}_TRUTH.npz'
                registry = registries['R2_input_registry.json']['files'] if route == 'R2' else registries['S1_materialized_registry.json']
                truth_key = f'{route}_aB_m0_{bias}_TRUTH.npz' if route == 'R2' else f'evaluator_truth/{route}_aB_m0_{bias}.npz'
                if registry[truth_key] != sha(args.input/truth_name):
                    raise ValueError('truth source registry')
        manifest['verified_input_files'] = len(lock['sources'])
        (args.out/'cells').mkdir()
        with (args.out/'POSE_EFFECTS.csv').open('x', newline='', encoding='utf8') as table:
            writer = csv.writer(table)
            writer.writerow(('route','bias','seed','pose_id','t_s','arm','xy_m','heading_deg','delta_xy_m','delta_heading_deg'))
            for route in plan['authorized']['routes']:
                for bias in plan['authorized']['biases']:
                    def read(name):
                        with np.load(args.input/name, allow_pickle=False) as f:
                            return dict(f)
                    full = read(f'{route}_aB_m0_{bias}_Full.npz')
                    los = read(f'{route}_aB_m0_{bias}_Native_LoS.npz')
                    for seed in plan['authorized']['seeds']:
                        cell = f'{route}_{bias}_{seed}'
                        tr = read(cell+'_TRACE.npz')
                        for source in (full, los):
                            for key in ('pose_id','t'):
                                if not np.array_equal(source[key], tr[key]):
                                    raise ValueError('exact pose/time join '+cell)
                        if len(np.unique(tr['pose_id'])) != len(tr['pose_id']):
                            raise ValueError('duplicate pose')
                        if len(tr['pose_id']) != plan['route_rows'][route]:
                            raise ValueError('expected route denominator')
                        close('full_mean', tr['mu'], full['muMB'], checks)
                        close('full_innovation', tr['nu'], full['z']-tr['h']-tr['mu'], checks)
                        close('W0_effective_R', tr['Rvar'], tr['Reff'], checks)
                        got = update(tr['prior'], tr['Pprior'], tr['h'], tr['H'],
                                     tr['mu'], tr['Rvar'], tr['mask'], full['z'], los['z'])
                        close('baseline_xy_bias', got['x'][:, 0, [0,1,3]], tr['x'][:, [0,1,3]], checks)
                        close('baseline_heading', got['x'][:, 0, 2], tr['x'][:, 2], checks, True)
                        close('baseline_P', got['P'], tr['P'], checks)
                        close('baseline_K', got['K'], tr['K'], checks)
                        delta = los['z']-full['z']
                        close('range_identity', got['u'][:, 1]-got['u'][:, 0], got['K'][:, :, 0]*delta[:, 0, None], checks)
                        close('s_identity', got['u'][:, 2]-got['u'][:, 0], got['K'][:, :, 1]*delta[:, 1, None], checks)
                        close('interaction_identity', got['u'][:, 3]-got['u'][:, 1]-got['u'][:, 2]+got['u'][:, 0], np.zeros_like(tr['prior']), checks)
                        covariance_check('prior', tr['Pprior'], checks)
                        covariance_check('posterior', got['P'], checks)
                        if not all(np.isfinite(v).all() for v in got.values()):
                            raise ValueError('nonfinite update')
                        np.savez_compressed(args.out/'cells'/(cell+'.npz'),
                            pose_id=tr['pose_id'], t=tr['t'], arms=np.array(ARMS),
                            x=got['x'], u=got['u'], P=got['P'], K=got['K'],
                            prior=tr['prior'], Pprior=tr['Pprior'], H=tr['H'], h=tr['h'],
                            mu=tr['mu'], R=tr['Rvar'], mask=tr['mask'],
                            z_full=full['z'], z_los=los['z'], delta_z=delta)
                        # Scoring labels are opened only after all four arms exist.
                        truth = read(f'{route}_{bias}_TRUTH.npz')
                        for key in ('pose_id','t'):
                            if not np.array_equal(tr[key], truth[key]):
                                raise ValueError('truth key alignment')
                        if not np.isfinite(truth['truth']).all():
                            raise ValueError('nonfinite evaluator truth')
                        rows, summary = score(got, truth['truth'], tr['t'], tr['pose_id'], route, bias, seed)
                        writer.writerows(rows); table.flush(); summaries.extend(summary)
                        manifest['completed_cells'] += 1
                        manifest['priors'] += len(tr['t'])
                        manifest['posterior_rows'] += len(rows)
                        put(args.out/'MANIFEST.json', manifest)
                        print('C1A_CELL', cell, manifest['completed_cells'], flush=True)
        if (manifest['completed_cells'], manifest['priors'], manifest['posterior_rows']) != (120,125440,501760):
            raise ValueError('complete denominators')
        put(args.out/'CELL_SUMMARY.json', summaries)
        manifest['status'] = 'NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
    except BaseException as exc:
        manifest.update(status='STOP', failed_cell=cell, error=repr(exc))
        failures.write_text(json.dumps(dict(cell=cell,error=repr(exc),traceback=traceback.format_exc()))+'\n',encoding='utf8')
        raise
    finally:
        manifest['end_utc'] = stamp()
        put(args.out/'CHECKS.json', checks)
        put(args.out/'MANIFEST.json', manifest)
        put(args.out/'ARTIFACT_HASHES.json', {p.relative_to(args.out).as_posix():sha(p)
            for p in sorted(args.out.rglob('*')) if p.is_file() and p.name != 'ARTIFACT_HASHES.json'})


if __name__ == '__main__':
    main()
