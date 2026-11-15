from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import json
import re

import numpy as np
import run_tb3_model003_s3 as runner


def replay(task):
    original_file = Path(task)
    original = json.loads(original_file.read_text())
    case, path, arm = (original[key] for key in ('case', 'path', 'arm'))
    expected = int(re.search(r'packet (\d+)', original['reason'])[1])
    source = Path('/frozen')
    args = SimpleNamespace(
        case=case, path=path, arm=arm, level='B0', snr=30,
        results_root=Path('/results'), model_source=Path('/model'), banks_dir=Path('/banks'),
        timeline=source/'TIMELINE_PACKETS.csv', timeline_sha256=original['timeline_sha256'],
        s2=source/'CHARACTERIZATION_003.json', s2_sha256=original['s2_sha256'],
        selection=source/'RANGING_RULE_SELECTION.json', selection_sha256=original['s1_sha256'],
        parity=source/'PARITY.json', parity_sha256=original['parity_sha256'],
        dr=original_file.parent/f'{case}_{path}_B0_DR.json', out=Path('/tmp/unused.json'))
    measure, update, fit = runner.m1r_batch, runner.update_rf, runner.fit_path
    write, replace = runner.write, Path.replace
    track, captured, params = [], {}, {}

    def inspect_meas(model, obs, banks, mean, cov, anchor, rx_z, rule, **steps):
        xy = mean[:, :2] - anchor[:2]
        dz = rx_z - anchor[2]
        d = np.sqrt(np.sum(xy**2, axis=1) + dz**2)
        jac = xy / d[:, None]
        variance = np.einsum('...i,...ij,...j->...', jac, cov[:, :2, :2], jac)
        sigma = np.sqrt(np.maximum(variance, 0))
        offsets = np.eye(2) * steps['step_xy_m']
        near = np.min(np.stack([d] + [np.sqrt(np.sum((xy + off)**2, axis=1) + dz**2)
                                     for off in [*offsets, *(-offsets)]]), axis=0)
        with np.errstate(invalid='raise'):
            nodes = near - np.sqrt(2) * 2.0201828704560856 * sigma
        track.append(dict(d=d, dmin=near, sigma=sigma, nodes=nodes, cov=cov.copy()))
        return measure(model, obs, banks, mean, cov, anchor, rx_z, rule, **steps)

    def inspect_update(mean, cov, *args, **options):
        updated = update(mean, cov, *args, **options)
        track[-1].update(accepted=updated[2]['accepted'].copy(), postcov=updated[1].copy())
        return updated

    def inspect_fit(*args, **options):
        params['k_var'] = args[-1]
        return fit(*args, **options)

    runner.m1r_batch, runner.update_rf, runner.fit_path = inspect_meas, inspect_update, inspect_fit
    runner.write = lambda _, report: captured.update(report)
    Path.replace = lambda *_: None
    try:
        runner.run_fold(args)
    finally:
        runner.m1r_batch, runner.update_rf, runner.fit_path = measure, update, fit
        runner.write, Path.replace = write, replace

    for key in ('status', 'reason', 'source_file_sha256', 'timeline_sha256',
                'paired_dr_sha256', 'source_sha256', 'banks_sha256'):
        assert captured[key] == original[key], (case, path, arm, key, captured[key])
    assert len(track) == expected + 1 and all(np.min(t['nodes']) > 0 for t in track[:-1])
    first = track[-1]
    invalid = np.flatnonzero(first['nodes'] <= 0)
    assert len(invalid) > 0
    worst = int(np.argmin(first['nodes']))
    low = int(invalid[0])

    def row(t, j):
        vals = dict(d=float(t['d'][j]), d_min=float(t['dmin'][j]), sigma=float(t['sigma'][j]),
                    node_min=float(t['nodes'][j]), prior_diag=np.diag(t['cov'][j]).tolist())
        if 'postcov' in t:
            vals.update(accepted=bool(t['accepted'][j]), post_diag=np.diag(t['postcov'][j]).tolist())
        return vals

    out = dict(case=case, path=path, arm=arm, packet=expected, invalid_count=len(invalid), worst_seed=worst,
               lowest_seed=low, num_accepted=int(sum(t['accepted'][worst] for t in track[:-1])),
               first=row(first, worst), lowest=row(first, low), k_variance=params['k_var'])
    if case == 'G-T1_A' and path == 'P-B':
        out['trajectory_worst'] = [row(t, worst) for t in track]
    return out


jobs = sorted(Path('/output/folds/30').glob('*_B0_J-CI*.json'))
jobs.sort(key=lambda p: ('G-T1_A_P-B' not in p.name, p.name))
print('starting', len(jobs), flush=True)
with ProcessPoolExecutor(max_workers=8) as pool:
    for out in pool.map(replay, map(str, jobs)):
        print(json.dumps(out), flush=True)
