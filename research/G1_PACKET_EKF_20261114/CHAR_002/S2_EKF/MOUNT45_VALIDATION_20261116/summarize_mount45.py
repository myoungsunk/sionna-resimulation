"""Tabulate matched route scores and within-condition reference changes."""

import argparse
import csv
from pathlib import Path

from run_compare_mount45 import ARMS, ORIGINAL, ROOT, mount


FIELDS = ('pose95_coverage', 'heading95_coverage', 'xy95_coverage',
          'heading_rmse_deg', 'xy_rmse_cm', 'mean_nees3')
HISTORICAL_STRUCTURE = ROOT.parent / 'G1_INT_DIAG_001_20261115/structure_sc_ki/run_01/RESULTS.json'


def comparison(old, new, baseline):
    for route in ('R2', 'R4', 'R5', 'pooled'):
        for arm, metrics in new[route].items():
            if arm not in old[route]:
                continue
            for field in FIELDS:
                v0, v45, ref = old[route][arm][field], metrics[field], new[route][baseline][field]
                multiplier, units = (100., 'percent / pp') if field.endswith('_coverage') else (1., 'raw')
                yield {'route': route, 'arm': arm, 'metric': field, 'units': units,
                       'mount0': multiplier * v0, 'mount45': multiplier * v45,
                       'delta45_minus_0': multiplier * (v45 - v0), 'reference_m45': baseline,
                       'm45_delta_vs_reference': multiplier * (v45 - ref)}


def run(kind):
    if kind in ('s2', 'l2'):
        stage, path = ('2a', ROOT) if kind == 's2' else ('2b', ROOT / 'l2')
        old_path = ORIGINAL / f'run_20261115_a/{stage}/RESULTS.json'
        new_path = path / 'comparison/execution/RESULTS.json'
        raw_old, raw_new = [mount.load(p) for p in (old_path, new_path)]
        old = raw_old['by_case'] | {'pooled': raw_old['pooled']}
        new = raw_new['by_case'] | {'pooled': raw_new['pooled']}
        assert set(ARMS) <= set(old['R2']) and raw_new['by_case']['R2']['E0']['n'] == raw_old['by_case']['R2']['E0']['n']
        baseline = 'E0'
    else:
        old_path, new_path = HISTORICAL_STRUCTURE, ROOT / 'structure/execution/RESULTS.json'
        old_metrics, new_metrics = [mount.load(p)['metrics'] for p in (old_path, new_path)]
        old = old_metrics['routes'] | {'pooled': old_metrics['pooled']}
        new = new_metrics['routes'] | {'pooled': new_metrics['pooled']}
        baseline = 'LORO'
    output = ROOT / f'MOUNT_0_VS_45_{kind.upper()}.csv'
    rows = list(comparison(old, new, baseline))
    with output.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    mount.write(output.with_suffix('.json'), {
        'status': 'CONDITIONAL_DESCRIPTIVE_COMPARISON', 'rows': len(rows),
        'source_sha256': {str(p): mount.sha(p) for p in (Path(__file__), old_path, new_path)},
        'output_sha256': mount.sha(output), 'reference': baseline,
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('s2', 'l2', 'structure'))
    run(parser.parse_args().kind)
