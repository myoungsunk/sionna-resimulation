"""Run the B/L2 paired sensitivity with identical mount +45 B/B0 RF and frozen L2 controls."""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np

import run_compare_mount45 as compare


ROOT, NATIVE, B0 = compare.ROOT, compare.mount.NATIVE, compare.PACKETS
EXT = ROOT.parent / 'G1_CHAR002_S2_EXTENSIONS_20261115'
DIAG = ROOT.parent / 'G1_INT_DIAG_001_20261115'
OUT = ROOT / 'l2'
PACKETS = OUT / 'packets'
LOCK = OUT / 'RUN_CONTRACT.json'
STRUCTURE = ROOT / 'structure/RUN_CONTRACT.json'
source = compare.mount
ROUTES = tuple(source.ROWS)
STATE_KEYS = (*source.TRACE_FIELDS, 'x', 'P')


def stem(route):
    return f'{route}_B_L2_m45_Full_10'


def freeze():
    parent = compare.ROOT / 'comparison/RUN_CONTRACT.json'
    base = source.load(parent)
    parity = B0 / 'PARITY_RESULTS.json'
    b0 = source.load(parity)
    controls_receipt = EXT / 'L2_INPUT_RECEIPT.json'
    controls = source.load(controls_receipt)
    sources = dict(base['inputs_sha256'])
    sources.update({str(p): source.sha(p) for p in (Path(__file__), parent, controls_receipt)})
    for path in (STRUCTURE, DIAG / 'd0_d5.py', DIAG / 'structure_sc_ki/structure.py',
                 DIAG / 'structure_sc_ki/score_structure.py'):
        sources[str(path)] = source.sha(path)
    reference = B0 / 'e0_reference.py'
    sources[str(reference)] = b0['source_sha256'][reference.name]
    packets = {}
    for route in ROUTES:
        mapping = {}
        for kind in ('online', 'evaluator', 'reference'):
            if kind != 'reference':
                bp = B0 / f'{source.stem(route)}__{kind}.npz'
                sources[str(bp)] = b0['routes'][route]['output_sha256'][bp.name]
                mapping[f'b0_{kind}'] = str(bp)
            lp = EXT / f'{route}_L2_Full_10__{kind}.npz'
            sources[str(lp)] = controls['cases'][route]['outputs_sha256'][lp.name]
            mapping[f'archived_l2_{kind}'] = str(lp)
        packets[route] = mapping
    for path, digest in sources.items():
        source.checked(Path(path), digest)
    OUT.mkdir()
    source.write(LOCK, base | {'question': 'G1-CHAR002-S2-MOUNT45/B-L2', 'frozen_utc': source.utc(),
        'scope': base['scope'] | {'bias': 'L2'}, 'sources_commit_controls': controls['source_commit'],
        'scope_note': 'Identical Full RF and frozen MB_VAR for +45 B/B0 and B/L2. L2 is a paired control sensitivity.',
        'historical_m45_reference': 'The mount 0 L2 archive authenticates L2 controls and grid. Mount +45 L2 uses two recursive implementations with shared SourceFFD.',
        'SC_KI': 'B/B0 fit and sigma remain frozen; L2 uses its own E0 fixed mask.',
        'input_arrays': packets, 'inputs_sha256': sources})


def replay_structures(core, online, model, result_root):
    sys.path[:0] = [str(DIAG), str(DIAG / 'structure_sc_ki')]
    from d0_d5 import replay_sigma
    from replay_s2 import parity
    from score_structure import recheck_trace, score
    from structure import replay_structure

    destination = OUT / 'structure'
    destination.mkdir()
    inherited = source.load(STRUCTURE)
    cells, checks = [], {}
    for cell in inherited['cells']:
        route = cell['route']
        prefix = PACKETS / stem(route)
        online_path = prefix.with_name(prefix.name + '__online.npz')
        evaluator_path = prefix.with_name(prefix.name + '__evaluator.npz')
        e0_path = result_root / f'execution/{route}_E0_trace.npz'
        b, gate = source.npz(online_path), source.npz(e0_path)['mask']
        table, fit = np.asarray(cell['sigma_b']), cell['kernel']
        args = b, source.controls(b), gate, core, online, model, source.SPEC, table
        loro = replay_sigma(*args)
        grid = {k: b[k] for k in ('t', 'pose_id')}
        loro_path = destination / f'{route}_LORO_trace.npz'
        source.save_npz(loro_path, loro | grid)
        checks[route] = {}
        for arm in ('SC', 'KI'):
            identical = {}
            for switch in inherited['implementation_gates'][f'{arm.lower()}_switches']:
                test = replay_structure(*args, fit, arm=arm, check_special=switch)
                expected = {k: loro[k] for k in STATE_KEYS}
                if switch == 'phi_zero':
                    expected['R_ref'] = expected.pop('Reff')
                identical[switch] = parity(test, expected)
            trace = replay_structure(*args, fit, arm=arm)
            checked = recheck_trace(trace, {'spec': source.SPEC, 'packet': b, 'mask': gate, 'table': table,
                                           'fit': fit, 'controls': source.controls(b)}, arm)
            checks[route][arm] = {'identity': identical, 'invariants': checked}
            source.save_npz(destination / f'{route}_{arm}_trace.npz', trace | grid)
        paths = {'evaluator': evaluator_path, 'fixed_gate_trace': e0_path, 'loro_trace': loro_path}
        cells.append(cell | {k: {'path': str(p), 'sha256': source.sha(p)} for k, p in paths.items()})
    score(destination, inherited | {'cells': cells})
    source.write(destination / 'CHECKS.json', checks)
    source.write(destination / 'EXECUTION.json', {'status': 'PASS_EXECUTION', 'exit_code': 0,
        'contract_sha256': source.sha(LOCK), 'B_B0_structure_sha256': source.sha(STRUCTURE), 'finished_utc': source.utc(),
        'outputs': {p.name: source.sha(p) for p in destination.iterdir()}})


def run():
    lock = source.load(LOCK)
    for path, digest in lock['inputs_sha256'].items():
        source.checked(Path(path), digest)
    sys.path[:0] = [str(NATIVE / 'src'), str(compare.S2_RUN / 'executed_source_2a_2b')]
    from e0_reference import reference
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    from replay_s2 import validate_trace

    core, online, model, _ = load_original_model(NATIVE)
    PACKETS.mkdir()
    parity = {}
    all_hashes = dict(lock['inputs_sha256'])
    for route, files in lock['input_arrays'].items():
        case = {label: source.npz(Path(path)) for label, path in files.items()}
        b0, ev = case['b0_online'], case['b0_evaluator']
        old, oldev = case['archived_l2_online'], case['archived_l2_evaluator']
        for values in (ev, old, oldev, case['archived_l2_reference']):
            for field in ('t', 'pose_id'):
                np.testing.assert_array_equal(b0[field], values[field])
        np.testing.assert_allclose(ev['truth'], oldev['truth'], rtol=0, atol=1e-12)
        spec0 = source.SPEC | {'mount_deg': 0.}
        old_l2 = online.replay(old, source.controls(old), 'W0', core, model, spec0)
        historic = source.evaluate_parity({k: case['archived_l2_reference'][k] for k in STATE_KEYS}, old_l2)
        packet = {key: b0[key] for key in ('t', 'pose_id', 'Hrf', 'clean_Hrf', 'z', 'R', 'C0', 'muMB', 'muBASE', 'D') if key in b0}
        packet.update({key: old[key] for key in ('ds', 'gy', 'dt', 'x0', 'P0')})
        native = online.replay(packet, source.controls(packet), 'W0', core, model, source.SPEC)
        validate_trace(native)
        m45 = source.evaluate_parity({k: native[k] for k in STATE_KEYS}, reference(model, source.SPEC, packet))
        packet.update(prior=native['prior'], Pprior=native['Pprior'])
        packet.update({'trace_' + k: native[k] for k in source.TRACE_FIELDS})
        if set(packet) != set(b0):
            raise ValueError(f'Online schema changed {route}: {set(b0) ^ set(packet)}')
        arrays = {'online': packet, 'evaluator': ev, 'e0_trace': {'t': b0['t'], 'pose_id': b0['pose_id'],
                  **{k: v for k, v in native.items() if k != 'latency_ns'}}}
        for kind, array in arrays.items():
            target = PACKETS / f'{stem(route)}__{kind}.npz'
            source.save_npz(target, array)
            for key, val in source.npz(target).items():
                np.testing.assert_array_equal(val, array[key])
            all_hashes[str(target)] = source.sha(target)
        parity[route] = {'historical_l2_mount0': historic, 'mount45_l2': m45,
                         'n_accepted': int(native['mask'].sum()), 'rows': len(b0['t']),
                         'same_RF_observation': True}
        print(f'{route} L2 +45 parity passed', flush=True)
    source.write(OUT / 'PACKET_PARITY.json', {'status': 'PASS', 'routes': parity, 'contract_sha256': source.sha(LOCK)})
    result_root = OUT / 'comparison'
    result_root.mkdir()
    source.write(result_root / 'RUN_CONTRACT.json', lock | {'inputs_sha256': all_hashes,
        'controls_rf_contract_sha256': source.sha(LOCK), 'parity_sha256': source.sha(OUT / 'PACKET_PARITY.json')})
    compare.PACKETS = PACKETS
    compare.mount.stem = stem
    compare.run(SimpleNamespace(out=result_root))
    replay_structures(core, online, model, result_root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('freeze', 'run'))
    {'freeze': freeze, 'run': run}[parser.parse_args().stage]()
