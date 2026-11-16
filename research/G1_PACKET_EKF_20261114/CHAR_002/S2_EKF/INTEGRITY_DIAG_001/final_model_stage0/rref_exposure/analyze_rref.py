"""Stage0: arithmetic on archived traces; never imports or calls an EKF replay."""
from pathlib import Path
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
M6 = Path('D:/SLAM_bot/artifacts/G1_GM_THETA_M6_20261116')
PYTHON = sys.executable


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def csv_write(path, rows):
    with path.open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def calc_kernel(t, arc, yaw, mask, g, r):
    """Two independently computed Icell formulas and full pairwise N_eff."""
    accepted = np.flatnonzero(mask)
    hazard = arc + yaw / np.deg2rad(10.)
    precision = g * g / r
    result = {k: np.empty(t.size) for k in
              ('N', 'N_w', 'N_eff', 'g2_rms', 'I_cell', 'g2_Neff', 'g2_Nw',
               'I_effective', 'I_cell_hazard')}
    for i in range(t.size):
        past = accepted[(accepted < i) & (t[accepted] >= t[i] - 10.)][-100:]
        idx = np.r_[past, i]
        dw = np.abs(arc[idx, None] - arc[idx][None, :])
        yw = np.abs(yaw[idx, None] - yaw[idx][None, :])
        rho = np.exp(-dw - yw / np.deg2rad(10.))
        n, nw = idx.size, rho[-1].sum()
        neff = n * n / rho.sum()
        g2 = np.mean(g[idx] ** 2)
        info = rho[-1] @ precision[idx]
        hazard_info = precision[i] + np.exp(hazard[past] - hazard[i]) @ precision[past]
        vals = (n, nw, neff, g2, info, g2 * neff, g2 * nw,
                precision[idx].sum() * neff / n, hazard_info)
        for key, value in zip(result, vals, strict=True):
            result[key][i] = value
    return result


def main():
    contract_path = ROOT / 'RUN_CONTRACT.json'
    root = json.loads(contract_path.read_text(encoding='utf-8'))
    before = {b['path']: sha(b['path']) for b in root['bindings']}
    assert all(before[b['path']] == b['sha256'] for b in root['bindings'])
    lane = {'question_id': root['question_id'], 'lane': 'rref_exposure',
            'frozen_utc': datetime.now(timezone.utc).isoformat(),
            'root_contract_sha256': sha(contract_path),
            'implementation_sha256': sha(__file__),
            'definitions': root['rref'],
            'population': 'accepted AND D3-supported; raw-only accepted population additionally reported',
            'distance_geometry': 'G0 prior horizontal rho_before',
            'motion': 'arc=cumsum(abs(ds)), yaw=cumsum(abs(wrap(gy-previous G0 b_g*dt)))',
            'kernel_history': 'all accepted history regardless of current distance bin; current packet included',
            'R_ref': 'archived G0 Reff_ss; G0 is E0-LORO-sigma_b, not original E0'}
    write_json(OUT / 'RUN_CONTRACT.json', lane)
    char = json.loads((M6 / 'characterization/RUN_CONTRACT.json').read_text(encoding='utf-8'))
    all_rows, packet_rows, checks = [], [], {}
    for route in ('R2', 'R4', 'R5'):
        tr = load(M6 / f'attempt_02/implementation/seed10/{route}_G0.npz')
        p = load(next(c for c in char['cells'] if c['route'] == route)['online']['path'])
        d3 = load(char['d3'][route]['path'])
        for grid in ('t', 'pose_id'):
            assert np.array_equal(tr[grid], p[grid]) and np.array_equal(tr[grid], d3[grid])
        assert np.array_equal(tr['mask'], d3['mask'])
        t, mask = tr['t'], tr['mask']
        g, r, distance = abs(tr['H'][:, 1, 2]), tr['Reff'][:, 1, 1], tr['rho_before']
        inc = (p['gy'][1:] - tr['x'][:-1, 3] * p['dt'][1:] + np.pi) % (2*np.pi) - np.pi
        priorinc = (tr['prior'][1:, 2] - tr['x'][:-1, 2] + np.pi) % (2*np.pi) - np.pi
        err = float(np.max(abs(inc - priorinc)))
        assert err < 1e-10
        arc = np.r_[0., np.cumsum(abs(p['ds'][1:]))]
        yaw = np.r_[0., np.cumsum(abs(inc))]
        assert np.all(np.diff(arc) >= 0) and np.all(np.diff(yaw) >= 0)
        k = calc_kernel(t, arc, yaw, mask, g, r)
        rel = float(np.max(abs(k['I_cell'] - k['I_cell_hazard']) / np.maximum(1., k['I_cell'])))
        assert rel < 1e-12
        assert np.all(k['N_eff'] >= 1. - 1e-10) and np.all(k['N_eff'] <= k['N'] + 1e-10)
        assert np.all(k['N_w'] >= 1. - 1e-10) and np.all(k['N_w'] <= k['N'] + 1e-10)
        eps, slow, support = d3['eps'][:, 1], d3['slow'][:, 1], d3['decomposition_support']
        assert np.max(abs(d3['eps'][support] - (d3['route_mean'] + d3['slow'][support] + d3['fast'][support]))) < 1e-10
        groups = [(f'[{a},{b})', (a <= distance) & (distance < b))
                  for a, b in zip((0.,1.5,3.,6.), (1.5,3.,6.,10.), strict=True)]
        groups += [('near_[0,3)', distance < 3.), ('far_[3,10)', (distance >= 3.) & (distance < 10.)),
                   ('all', np.ones(t.size, bool))]
        for label, group in groups:
            for population, eligible in [('accepted_supported', mask & support), ('accepted', mask)]:
                use = group & eligible
                if not use.any():
                    continue
                es, rs = eps[use], r[use]
                row = {'route': route, 'seed': 10, 'distance_bin_m': label, 'population': population,
                       'packets': int(use.sum()), 'R_ref_ss_median': float(np.median(rs)),
                       'g_median': float(np.median(g[use])), 'g_rms': float(np.sqrt(np.mean(g[use]**2))),
                       'raw_second_over_R': float(np.mean(es**2/rs)),
                       'raw_centered_over_R': float(np.mean((es-es.mean())**2/rs)),
                       'raw_var_over_mean_R': float(np.var(es)/np.mean(rs)),
                       'signed_raw_mean': float(es.mean())}
                if population == 'accepted_supported':
                    sl = slow[use]
                    row.update(slow_second_over_R=float(np.mean(sl**2/rs)),
                               slow_centered_over_R=float(np.mean((sl-sl.mean())**2/rs)),
                               slow_var_over_mean_R=float(np.var(sl)/np.mean(rs)),
                               signed_slow_mean=float(sl.mean()))
                else:
                    row.update(slow_second_over_R=None, slow_centered_over_R=None,
                               slow_var_over_mean_R=None, signed_slow_mean=None)
                row.update({key+'_median': float(np.median(value[use])) for key, value in k.items()
                            if key != 'I_cell_hazard'})
                all_rows.append(row)
        for i in range(t.size):
            packet_rows.append({'route': route, 't_s': float(t[i]), 'pose_id': int(tr['pose_id'][i]),
                                'accepted': bool(mask[i]), 'D3_supported': bool(support[i]),
                                'distance_m': float(distance[i]), 'g': float(g[i]), 'R_ref_ss': float(r[i]),
                                'eps_s': float(eps[i]), 'slow_s': float(slow[i]),
                                **{name: float(v[i]) for name,v in k.items()}})
        checks[route] = {'grid_mask': 'EXACT', 'prior_control_yaw_max_abs': err,
                         'Icell_independent_relative_error': rel,
                         'D3_supported_accepted': int((mask & support).sum()),
                         'accepted': int(mask.sum()), 'rows': int(t.size)}
    after = {b['path']: sha(b['path']) for b in root['bindings']}
    assert before == after
    csv_write(OUT / 'DISTANCE_EXPOSURE.csv', all_rows)
    csv_write(OUT / 'PACKET_EXPOSURE.csv', packet_rows)
    write_json(OUT / 'RESULTS.json', {'classification': 'DIAGNOSTIC_ONLY', 'definitions': lane,
                                     'rows': all_rows, 'checks': checks})
    outputs = {p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name != 'RECEIPT.json'}
    write_json(OUT / 'RECEIPT.json', {'status': 'PASS', 'utc':datetime.now(timezone.utc).isoformat(),
                                     'python':PYTHON, 'command':f'{PYTHON} -B -X utf8 {__file__}',
                                     'exit_code':0, 'root_contract_sha256':sha(contract_path),
                                     'implementation_sha256':sha(__file__), 'outputs':outputs,
                                     'checks':checks, 'all_bound_inputs_unchanged': before == after})
    for row in all_rows:
        if row['population'] == 'accepted_supported':
            print(row['route'],row['distance_bin_m'],row['packets'],
                  'raw/R',round(row['raw_centered_over_R'],4),
                  'slow/R',round(row['slow_centered_over_R'],4),
                  'g',round(row['g_median'],2),'Nw',round(row['N_w_median'],1),
                  'Neff',round(row['N_eff_median'],1),'Icell',round(row['I_cell_median'],1))


if __name__ == '__main__':
    main()
