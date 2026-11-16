"""Test authenticated +45 G-T1 donor support under the original C7 rules."""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import types

from run_ks_mount45 import DIAG, DIAGNOSTICS, LOCK as KS_LOCK, OUT as KS, ROOT, ROUTES, check, receipt, role_receipt, source
from run_followup_mount45 import LOCK as FOLLOWUP_LOCK, OUT as FOLLOWUP


OUT = ROOT / 'c7'
LOCK = OUT / 'RUN_CONTRACT.json'
TEMPLATE = DIAG / 'continuation_checks_c1_c8/c7/run_c7.py'
TRAINING = ROOT / 'training'


def adapt():
    original = TEMPLATE.read_text(encoding='utf-8')
    changes = {
        'geometry["mount"] != 0': 'geometry["mount"] != 45',
        'KS / "run_03" / "V8.json"': 'KS / "execution" / "V8.json"',
        'f"{route}_B0_Full_10__online.npz"': 'packet_name(route)',
        '            np.testing.assert_allclose(observed, old["measured"], atol=1e-12, rtol=1e-12)':
            '            if observed is None or old["measured"] is None:\n'
            '                assert observed is None and old["measured"] is None\n'
            '            else:\n'
            '                np.testing.assert_allclose(observed, old["measured"], atol=1e-12, rtol=1e-12)',
        'holdout_g_min=float(g.min()), holdout_g_max=float(g.max()),':
            'holdout_g_min=float(g.min()) if len(g) else None, holdout_g_max=float(g.max()) if len(g) else None,',
    }
    for before, after in changes.items():
        assert original.count(before) >= 1, before
        original = original.replace(before, after)
    return original


def freeze():
    previous = role_receipt(FOLLOWUP / 'execution', FOLLOWUP_LOCK)
    c5_path = FOLLOWUP / 'execution/C5.json'
    assert c5_path in previous
    c5 = source.load(c5_path)['disposition']['conservative']['status']
    if c5 == 'PASS':
        raise ValueError('C7 trigger is absent because C5 passed')
    followup_contract = source.load(FOLLOWUP_LOCK)
    ks_contract = source.load(KS_LOCK)
    fit_path = TRAINING / 'FIT_RECEIPT.json'
    fit = source.load(fit_path)
    assert fit['status'] == 'PASS' and source.sha(TRAINING / 'RUN_CONTRACT.json') == fit['contract_sha256']
    anchors = {}
    for label in 'ABC':
        name = f'G-T1_{label}'
        row = fit['case_inputs'][name]
        assert row['mount_deg'] == 45.
        errors = source.checked(TRAINING / f'ERRORS_{name}.npz', row['derived_errors_npz_sha256'])
        samples = source.checked(ROOT / f'guarded_gt1/poses/{name}/SAMPLES.json', row['samples_sha256'])
        anchors[label] = {'geometry': {'case': name, 'anchor': row['anchor_xyz_m'], 'mount': 45, 'poses': row['poses']},
                          'errors': receipt(errors), 'samples': receipt(samples)}
    role_receipt(KS / 'execution', KS_LOCK)
    bound = OUT / 'run_c7_bound.py'
    OUT.mkdir()
    with bound.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(adapt())
    holdout = [source.OUT / f'{source.stem(route)}__online.npz' for route in ROUTES]
    holdout.extend(DIAGNOSTICS / f'{stage}/B_B0_{r}.npz' for stage in ('d2', 'd5') for r in ROUTES)
    source.write(LOCK, {'question': 'G1-INT-001/KS-C7/M45-B-B0', 'role': 'IMPLEMENTER',
        'frozen_utc': source.utc(), 'c5_status': c5, 'source': receipt(bound), 'donors': anchors,
        'holdout': list(map(receipt, holdout)), 'governance': followup_contract['governance'],
        'inputs': list(map(receipt, (Path(__file__), TEMPLATE, fit_path, TRAINING / 'RUN_CONTRACT.json',
                                   KS_LOCK, KS / 'execution/EXECUTION.json', KS / 'execution/V8.json',
                                   FOLLOWUP_LOCK, FOLLOWUP / 'execution/EXECUTION.json', c5_path,
                                   DIAGNOSTICS / 'RUN_CONTRACT.json'))),
        'sources': [r for r in ks_contract['sources'] if Path(r['path']).name == 'ks_fit.py'],
        'scope': 'C7 simulated sweep proxy; frozen old yaw window, station weight and fit support. Same +45 holdout as V8.'})


def run():
    lock = source.load(LOCK)
    for record in [lock['source'], *lock['governance'], *lock['holdout'], *lock['sources'], *lock['inputs']]:
        check(record)
    dest = OUT / 'execution'
    dest.mkdir()
    record = {'started_utc': source.utc(), 'contract_sha256': source.sha(LOCK)}
    try:
        base = types.ModuleType('c7_bound')
        path = check(lock['source'])
        base.__file__ = str(path)
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), vars(base))
        base.ARTIFACTS, base.KS = DIAGNOSTICS, KS
        base.packet_name = lambda route: f'{source.stem(route)}__online.npz'
        data = {}
        geometry = []
        fields = ['x', 'y', 'yaw', 'd', 'g_psi', 'e_s', 's_full', 's_los']
        for a, pin in lock['donors'].items():
            values = source.npz(check(pin['errors']))
            sample_bytes = check(pin['samples']).read_bytes()
            sparse = [s['pose_id'] for s in json.loads(sample_bytes)
                      if s['set'] in base.SETS and s['protocol'] == 'dense49']
            if len(values['mount']) != pin['geometry']['poses'] or any(values['mount'][i] != 45 for i in sparse):
                raise ValueError(f'Unexpected mounted donor rows for {a}')
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['pose_id', *fields])
            for i in range(len(values['mount'])):
                writer.writerow([i, *(values[k][i] for k in fields)])
            data[f'{base.CHAR_OUT}/ERRORS_G-T1_{a}.csv.gz'] = gzip.compress(stream.getvalue().encode())
            data[f'{base.POSES}/G-T1_{a}/SAMPLES.json'] = sample_bytes
            geometry.append(pin['geometry'])
        data[f'{base.CHAR_OUT}/EXTRACT_MANIFEST.json'] = json.dumps({'cases': geometry}).encode()
        donors = base.fetch_donors(data, base.RULES)
        sets = [{(r['station'], r['anchor']) for r in donors if r['role'] == name} for name in base.SETS]
        assert len(donors) == 5292 and sets[0] == sets[1] and len(sets[0]) == 54
        fit = base.summarize_fit(donors, base.RULES)
        support = base.holdout_rows({'frozen_holdout_files': [r['path'] for r in lock['holdout']],
                                    'inherited_sources': {str(i): r for i, r in enumerate(lock['sources'])}}, fit)
        source.write(dest / 'C7_RESULTS.json', {'status': 'SIMULATED_PROXY_DIAGNOSTIC',
            'donor_rows': len(donors), 'fits': fit, 'holdout_rows': support, 'rules': base.RULES})
        with (dest / 'C7_DONOR_ROWS.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(donors[0]))
            writer.writeheader()
            writer.writerows(donors)
        record.update(status='PASS_EXECUTION', exit_code=0)
    except Exception as exc:
        record.update(status='FAIL_EXECUTION', exit_code=1, reason=repr(exc))
        raise
    finally:
        record['finished_utc'] = source.utc()
        record['outputs'] = {p.name: source.sha(p) for p in dest.iterdir() if p.is_file()}
        source.write(dest / 'EXECUTION.json', record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
