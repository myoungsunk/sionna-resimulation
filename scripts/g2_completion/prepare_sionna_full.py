"""S0: build and freeze the full-campaign inputs (no RF calls).

    python scripts/g2_completion/prepare_sionna_full.py --campaign-root <root> --dry-run
    python scripts/g2_completion/prepare_sionna_full.py --campaign-root <root> --write-inputs

--dry-run builds and validates every target and prints the census; it writes
nothing. --write-inputs writes <root>/00_inputs/ atomically. An existing
00_inputs is never overwritten: if the regenerated TARGETS digest differs the
run stops with INPUT_REVISION_CHANGED (make a new campaign revision instead).
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rt_cp_uwb_py.g2_full_inputs import (CLEARANCE_M, EXPECTED_TOTAL, STATIC9_FAMILY, build_targets, canonical,
                                        endpoint_clearance)
from rt_cp_uwb_py.g2_full_panels import CONTRACT_ID, METAL_PANEL, OCCLUDER_PANEL, panel_ply
from rt_cp_uwb_py.g2_full_paths import file_sha, load_paths, resolve_banks

PATH_MAP = ROOT/'config/sionna_full_paths.example.json'
F0, DF, N_BINS = 6250400000., 1950000., 257
TARGET_FIELDS = ('target_id', 'family', 'identity', 'scene_id', 'condition', 'tx', 'rx', 'pose_id', 'frame_ref',
                 'panel_id', 'rx_relocated', 'geometric_range_m', 'source_sha256', 'clearance_m', 'clearance_owner',
                 'panel_clearance_m')


def snapshot_check(paths, config):
    """Compare current input files with PLAN_INPUT_SNAPSHOT (Windows digests)."""
    snap = json.loads((paths['campaign']/'PLAN_INPUT_SNAPSHOT.json').read_text(encoding='utf8'))
    win = config['environments']['windows_workspace']
    win_root = win['root'].replace('/', '\\') + '\\'
    local = {}
    for key in ('relocated_inputs', 'geometry', 'operating_config'):
        local[(win_root + win['paths'][key].replace('/', '\\'))] = paths[key]
    result = {}
    for src, expected in snap['inputs_sha256'].items():
        target = None
        if src.endswith('COMMON_ENVIRONMENT_POSE_CONTRACT.json'):
            target = paths['static9_contract']
        elif src.endswith('_bank.npz'):
            target = paths['bank_dir']/src.rsplit('\\', 1)[1]
        else:
            for prefix, base in local.items():
                if src == prefix or src.startswith(prefix + '\\'):
                    target = base/src[len(prefix):].lstrip('\\').replace('\\', '/') if src != prefix else base
                    break
        if target is None or not Path(target).is_file():
            result[src] = 'NOT_AN_S0_INPUT' if src.endswith('.py') else 'ABSENT'
            continue
        data = Path(target).read_bytes()
        if hashlib.sha256(data).hexdigest() == expected:
            result[src] = 'EXACT'
        elif hashlib.sha256(data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')).hexdigest() == expected:
            result[src] = 'CRLF_ONLY'
        else:
            result[src] = 'CHANGED'
    return result


def static9_overlay(paths):
    source = paths['static9_contract']
    return dict(
        status='OVERLAY_DEFINED_NOT_SOURCE_REPRODUCTION',
        source_contract=dict(path_key='static9_contract', sha256=file_sha(source),
                             semantics='ideal Jones response, 3 frequencies, no added noise, detector not run'),
        operating_contract=dict(ffd='common 6-port FFD bank', frequency_bins=N_BINS, noise='same synthetic '
                                'operating point as production targets', clean_channel_preserved=True),
        claim='not a reproduction of the source analytic contract and not an analytic PASS')


def build(paths, config):
    targets, poses, panels, census = build_targets(paths['relocated_inputs'], paths['geometry'],
                                                   paths['static9_contract'])
    clearance = endpoint_clearance(targets, panels, paths['geometry'])
    indep = json.loads((paths['relocated_inputs']/'CLEARANCE_INDEPENDENT.json').read_text(encoding='utf8'))
    relocated = [t['clearance_m'][1] for t in targets if t['rx_relocated']]
    census['relocated_clearance_crosscheck'] = dict(
        independent_min=min(indep['distances_m']), independent_max=max(indep['distances_m']),
        s0_min=min(relocated), s0_max=max(relocated),
        consistent=all(any(abs(v-d) < 1e-9 for d in indep['distances_m']) for v in relocated))
    census['clearance'] = dict(threshold_m=CLEARANCE_M, rule=clearance['rule'],
                               inside_material=sum(1 for t in targets for v in t['clearance_m']
                                                   if v is not None and v < 0),
                               below_threshold_targets=len(clearance['violations']))
    census['snapshot'] = snapshot_check(paths, config)
    for t in targets:
        t.pop('room_size', None)
    return targets, poses, panels, census, clearance


def gate(census):
    """Hard S0 exit conditions (plan section 6 S0)."""
    failures = list(census['issues'])
    if census['targets'] != EXPECTED_TOTAL:
        failures.append('TARGET_COUNT')
    if census['clearance']['inside_material']:
        failures.append('ENDPOINT_INSIDE_MATERIAL')
    if not census['relocated_clearance_crosscheck']['consistent']:
        failures.append('RELOCATION_CLEARANCE_CROSSCHECK')
    if any(v in ('CHANGED', 'ABSENT') for v in census['snapshot'].values()):
        failures.append('INPUT_SNAPSHOT_DRIFT')
    return failures


def write_inputs(root, paths, config, targets, poses, panels, census, clearance, banks):
    out = root/'00_inputs'
    stage = Path(tempfile.mkdtemp(prefix='.00_inputs.', dir=root))
    try:
        (stage/'dynamic').mkdir()
        with (stage/'TARGETS.jsonl').open('w', encoding='utf8', newline='\n') as f:
            for t in targets:
                f.write(canonical({k: t[k] for k in TARGET_FIELDS}) + '\n')
        for pid, p in sorted(panels.items()):
            p['ply'] = f'dynamic/{pid}.ply'
            (stage/p['ply']).write_text(panel_ply(p['panel']), encoding='ascii', newline='\n')
        dump = lambda name, obj: (stage/name).write_text(json.dumps(obj, indent=1, sort_keys=True,
                                                                    allow_nan=False) + '\n', encoding='utf8')
        dump('POSES.json', poses)
        dump('PANELS.json', panels)
        dump('STATIC9_OVERLAY_CONTRACT.json', static9_overlay(paths))
        dump('CLEARANCE_REPORT.json', clearance)
        op = json.loads(paths['operating_config'].read_text(encoding='utf8'))
        digests = {n: file_sha(stage/n) for n in ('TARGETS.jsonl', 'POSES.json', 'PANELS.json',
                                                   'STATIC9_OVERLAY_CONTRACT.json')}
        dump('CONFIG.json', dict(
            campaign_id=config['campaign_id'], rows='see TARGETS.jsonl (target_id keyed)',
            targets_sha256=digests['TARGETS.jsonl'], poses_sha256=digests['POSES.json'],
            panels_sha256=digests['PANELS.json'], static9_overlay_sha256=digests['STATIC9_OVERLAY_CONTRACT.json'],
            frequencies=dict(rule='6250400000 + 1950000*k Hz', k=[0, N_BINS-1]),
            arms=dict(CP=['RHCP', 'LHCP'], LP_AXIS=['LP_X', 'LP_Y'], LP_DIAG=['LP_plus45', 'LP_minus45']),
            ports=op['ports'], bank_sha256=op['bank_sha256'], solver=op['solver'], noise=op['noise'],
            detector=op['detector'], backend=op['backend'], model=op['model'],
            ideal_material_mapping=op['ideal_material_mapping'], exclusions=op['exclusions'],
            search_completeness_claim=False, classification=op['classification'],
            geometry_manifest_sha256=file_sha(paths['geometry']/'SCENE_MESH_MANIFEST.json'),
            geometry_contract_sha256=file_sha(paths['geometry']/'MODEL_CONTRACT.json'),
            condition_panel_material=dict(contract_id=CONTRACT_ID, metal=METAL_PANEL, occluder=OCCLUDER_PANEL),
            path_map='config/sionna_full_paths.example.json (logical keys; no absolute roots)'))
        dump('TARGET_CENSUS.json', census)
        inputs = {}
        for key in ('relocated_inputs', 'geometry'):
            base = paths[key]
            names = (['CHANGED_LINKS.json', 'MOVES.json', 'MANIFEST.json', 'CLEARANCE_INDEPENDENT.json',
                      'common/LINKS.jsonl', 'common/FRAMES.jsonl'] +
                     [f'inputs_v6/{f}/INPUT.json' for f in ('L1', 'L1multi', 'L2static', 'L2multi')]
                     if key == 'relocated_inputs' else
                     ['SCENE_MESH_MANIFEST.json', 'MODEL_CONTRACT.json', 'FINAL_MANIFEST.json', 'STATUS.json'])
            inputs.update({f'{key}/{n}': file_sha(base/n) for n in names})
        manifest = json.loads((paths['geometry']/'SCENE_MESH_MANIFEST.json').read_text(encoding='utf8'))
        inputs.update({f"geometry/{m['mesh']}": m['sha256'] for s in manifest['scenes'] for m in s['materials']})
        inputs.update({f'bank_dir/{p}_bank.npz': b['sha256'] for p, b in banks.items()})
        inputs.update({k: file_sha(paths[k]) for k in ('bank_manifest', 'operating_config', 'static9_contract')})
        code = ['rt_cp_uwb_py/g2_full_inputs.py', 'rt_cp_uwb_py/g2_full_panels.py', 'rt_cp_uwb_py/g2_full_paths.py',
                'rt_cp_uwb_py/l1_l2_rf_synthesis.py', 'scripts/g2_completion/prepare_sionna_full.py',
                'config/sionna_full_paths.example.json']
        outputs = {str(p.relative_to(stage)).replace(os.sep, '/'): file_sha(p)
                   for p in sorted(stage.rglob('*')) if p.is_file()}
        dump('INPUT_MANIFEST.json', dict(
            status='S0_INPUTS_WRITTEN', timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            command=sys.argv, environment='repo_checkout', rf_calls=0, inputs_sha256=inputs,
            code_sha256={c: file_sha(ROOT/c) for c in code}, outputs_sha256=outputs,
            config_sha256=file_sha(stage/'CONFIG.json')))
        if out.exists():
            old = json.loads((out/'CONFIG.json').read_text(encoding='utf8'))['targets_sha256']
            if old != digests['TARGETS.jsonl']:
                raise SystemExit('INPUT_REVISION_CHANGED: existing 00_inputs has a different TARGETS digest')
            shutil.rmtree(stage)
            return out, False
        os.replace(stage, out)  # atomic on the same filesystem
        return out, True
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign-root', type=Path, required=True)
    ap.add_argument('--environment', default='repo_checkout')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--write-inputs', action='store_true')
    a = ap.parse_args()
    config, paths = load_paths(PATH_MAP, a.environment, ROOT)
    root = a.campaign_root if a.campaign_root.is_absolute() else ROOT/a.campaign_root
    if root.resolve() != paths['campaign'].resolve():
        raise SystemExit('CAMPAIGN_ROOT_NOT_PATH_MAP_CAMPAIGN')
    banks = resolve_banks(config, paths)
    targets, poses, panels, census, clearance = build(paths, config)
    failures = gate(census)
    summary = dict(targets=census['targets'], family_counts=census['family_counts'], scenes=census['scenes'],
                   frames=census['frames_bound'], relocated=census['relocated_rx_rows'], poses=census['poses'],
                   condition_panels=census['condition_panels'], clearance=census['clearance'],
                   relocated_clearance_crosscheck=census['relocated_clearance_crosscheck']['consistent'],
                   snapshot={v: sum(x == v for x in census['snapshot'].values())
                             for v in set(census['snapshot'].values())},
                   gate_failures=failures)
    print(json.dumps(summary, indent=1))
    if failures:
        raise SystemExit('S0_GATE_FAILED')
    if a.write_inputs:
        out, written = write_inputs(root, paths, config, targets, poses, panels, census, clearance, banks)
        print(f'written: {out.relative_to(ROOT)}' if written else
              f'unchanged: {out.relative_to(ROOT)} already holds the identical TARGETS digest')


if __name__ == '__main__':
    main()
