"""Frozen F1 events, oracle diagnostic interventions, and independent scoring.

Preparation is not execution. Run only after PROTOCOL_LOCK.json is committed.
Old inputs use T1 BUNDLE.json; new inputs use seed0 T2 traces plus case metadata.
Results from per-route jobs can be combined with --aggregate ONLY after all jobs.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import traceback
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent/'T1_MEMORY'))
from replay import score
LOCK = json.loads((HERE/'PROTOCOL_LOCK.json').read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_npz(path):
    with np.load(path, allow_pickle=False) as data:
        return {k: data[k].copy() for k in data.files}


def wrap(value):
    return (value+np.pi) % (2*np.pi)-np.pi


def event_indices(data, event):
    """Frozen coordinate membership; visits defined on RF rows, never on errors."""
    ri = np.flatnonzero(data['radio_mask'])
    coord = data['truth'][ri, 0 if event['axis'] == 'x' else 1]
    mask = (coord >= event['low']) & (coord < event['high']) & (data['t'][ri] >= 0)
    change = np.diff(np.r_[False, mask, False].astype(int))
    starts, ends = np.flatnonzero(change == 1), np.flatnonzero(change == -1)
    visit = event['visit']-1
    if visit >= len(starts):
        raise ValueError('BLOCKED_INPUT:VISIT_NOT_PRESENT:'+event['event'])
    lo, hi = int(starts[visit]), int(ends[visit])
    if hi-lo < 3:
        raise ValueError('BLOCKED_INPUT:TOO_FEW_RF_ROWS:'+event['event'])
    return int(ri[lo]), int(ri[hi-1])+1, lo, hi


def normalize(raw):
    aliases = {'truth': 'truth_for_offline_scoring_only', 'z': 'observations',
               'mu': 'mu_input', 'C': 'C_input'}
    data = dict(raw)
    for key, alt in aliases.items():
        if key not in data:
            data[key] = data[alt]
    n = len(data['t'])
    data.setdefault('radio_mask', np.ones(n, bool))
    data.setdefault('risk', np.zeros(n))
    data['radio_mask'] = np.asarray(data['radio_mask'], bool)
    for key in ('truth', 'z', 'mu', 'C', 'radio_mask', 'risk', 'controls_dt', 'controls_ds', 'controls_dyaw'):
        if len(data[key]) != n:
            raise ValueError('INPUT_LENGTH:'+key)
    if not np.all(np.diff(data['t']) > 0):
        raise ValueError('NONINCREASING_TIME')
    return data


def run(engine, model, data, case, spec):
    controls = {'dt_s': data['controls_dt'], 'ds_odom': data['controls_ds'],
                'dtheta_gyro': data['controls_dyaw']}
    result = engine.run(data['t'], controls, data['initial_pose'], data['z'], data['mu'],
                        data['C'], data['risk'], case, model, [spec], radio_mask=data['radio_mask'])
    # D4 can invalidate a prior between the engine's periodic covariance checks.
    for field in ('prior_cov', 'cov'):
        eigenvalues = np.linalg.eigvalsh(result[field][:, 0])
        where = np.argwhere(eigenvalues <= 0)
        if len(where):
            i, k = map(int, where[0])
            raise FloatingPointError(f'ERROR_NONSPD_NO_REPAIR:{field}:frame={i}:eigenvalue={eigenvalues[i,k]}')
    return result


def metrics(result, data, mask):
    if not np.any(mask):
        return {'status': 'EMPTY_SCOPE', 'n': 0}
    values = score(result['state'][:, 0], result['cov'][:, 0], data['truth'], 0., mask)
    independent = score(result['state'][:, 0], result['cov'][:, 0], data['truth'], 0., mask, scalar=True)
    delta = max(abs(values[k]-independent[k]) for k in values)
    if not np.isfinite(list(values.values())).all() or delta > 1e-9:
        raise RuntimeError('INDEPENDENT_SCORER:'+str(delta))
    return dict(status='TECHNICAL_PASS', n=int(mask.sum()), scorer_max_abs_difference=delta, **values)


def check_reference(result, data, historical_path, cid, key, check_key=True):
    reference = load_npz(historical_path)
    j = list(reference['names'].astype(str)).index('POWER1')
    if len(reference['state']) != len(data['t']):
        raise ValueError('HISTORICAL_FRAME_COUNT:'+cid)
    if 't' in reference and not np.array_equal(reference['t'], data['t']):
        raise ValueError('HISTORICAL_TIME_MISMATCH:'+cid)
    mask = data['t'] >= 30
    actual = metrics(result, data, mask)['heading_rmse_deg']
    state = reference['state'][:, j]
    expected = float(np.sqrt(np.mean(np.degrees(wrap(state[mask, 2]-data['truth'][mask, 2]))**2)))
    gates = reference['accepted'][:, j]
    mismatches = int(np.count_nonzero(result['accepted'][:, 0] != gates))
    rec = dict(case=cid, stored_heading_difference_deg=abs(actual-expected), gate_mismatches=mismatches,
               stored_state_max_abs_difference=float(np.max(np.abs(result['state'][:, 0, :4]-state[:, :4]))))
    if abs(actual-expected) > 1e-6 or mismatches:
        raise RuntimeError('POWER1_STORED_PARITY:'+json.dumps(rec))
    selected = key[(key.case == cid) & (key.method == 'POWER1')]
    if check_key and cid.startswith('R'):
        if len(selected) != 1:
            raise ValueError('BLOCKED_INPUT:KEY_B0_CASE:'+cid)
        rec['key_b0_heading_difference_deg'] = abs(actual-float(selected.iloc[0].heading_rmse_deg))
        if rec['key_b0_heading_difference_deg'] > 1e-6:
            raise RuntimeError('POWER1_KEY_B0_PARITY:'+json.dumps(rec))
    return rec


def packet_rows(result, data, event, arm, a, b):
    t = data['t']; start, end = t[a], t[b-1]
    indices = np.flatnonzero(data['radio_mask'] & (t >= start-10) & (t <= end+30))
    records = []
    for i in indices:
        prior, post = result['prior'][i, 0], result['state'][i, 0]
        P = result['prior_cov'][i, 0]; K = result['K'][i, 0]; nu = result['innovation'][i, 0]
        accepted = bool(result['accepted'][i, 0]); active = a <= i < b
        row = dict(event=event['event'], case=event['case'], arm=arm,
                   label='ORACLE_DIAGNOSTIC', reference_control=(arm == 'POWER1'),
                   frame=int(i), t_s=float(t[i]), in_event=active, accepted=accepted,
                   prior_x_m=prior[0], prior_y_m=prior[1], prior_psi_rad=prior[2], prior_bg_rad_s=prior[3],
                   prior_error_x_m=prior[0]-data['truth'][i, 0], prior_error_y_m=prior[1]-data['truth'][i, 1],
                   prior_error_psi_deg=np.degrees(wrap(prior[2]-data['truth'][i, 2])),
                   prior_error_bg_dps=np.degrees(prior[3]), nu_r_m=nu[0], nu_s=nu[1],
                   nis=result['nis'][i, 0], H_spsi=result['H'][i, 0, 1, 2],
                   gate_threshold=6.6348966010212145 if arm in ('D1', 'D2') and active else 9.210340371976184,
                   K_psi_r_nu_deg=np.degrees(K[2, 0]*nu[0]), K_psi_s_nu_deg=np.degrees(K[2, 1]*nu[1]),
                   K_b_r_nu_dps=np.degrees(K[3, 0]*nu[0]), K_b_s_nu_dps=np.degrees(K[3, 1]*nu[1]),
                   applied_dpsi_deg=np.degrees(wrap(post[2]-prior[2])),
                   applied_db_dps=np.degrees(post[3]-prior[3]))
        for j, s1 in enumerate(('x', 'y', 'psi', 'bg')):
            for k, s2 in enumerate(('x', 'y', 'psi', 'bg')):
                row['P_'+s1+'_'+s2] = P[j, k]
        for j in range(2):
            for k in range(2):
                row[f'S{j}{k}'] = result['S'][i, 0, j, k]
        records.append(row)
    return records


def first_harmful(baseline, data, event, a, b):
    pre = np.degrees(wrap(baseline['prior'][:, 0, 2]-data['truth'][:, 2]))
    post = np.degrees(wrap(baseline['state'][:, 0, 2]-data['truth'][:, 2]))
    increase = post**2-pre**2
    eligible = np.flatnonzero(baseline['accepted'][:, 0] & data['radio_mask'] &
                              (np.arange(len(pre)) >= a) & (np.arange(len(pre)) < b))
    maximum = max(0., float(np.max(increase[eligible]))) if len(eligible) else 0.
    threshold = max(.01, .1*maximum)
    selected = eligible[increase[eligible] >= threshold]
    rec = dict(event=event['event'], case=event['case'], label='ORACLE_DIAGNOSTIC',
               threshold_deg2=threshold, maximum_positive_increase_deg2=maximum,
               status='NONE_ABOVE_LOCKED_THRESHOLD')
    if len(selected):
        i = int(selected[0]); nu = baseline['innovation'][i, 0]
        delta = np.degrees(baseline['K'][i, 0, 2]*nu)
        allocated = 2*pre[i]*delta+delta*delta.sum()
        rec.update(status='FOUND', frame=i, t_s=float(data['t'][i]), increase_deg2=float(increase[i]),
                   prior_error_deg=float(pre[i]), applied_error_deg=float(post[i]),
                   channel=('r', 's')[int(np.argmax(allocated))], range_attribution_deg2=float(allocated[0]),
                   s_attribution_deg2=float(allocated[1]), wrap_nonadditivity_deg2=float(increase[i]-allocated.sum()))
    return rec


def divergence(baseline, skipped, data, event, a, b):
    t = data['t']; end = t[b-1]
    dh = np.degrees(wrap(baseline['state'][:, 0, 2]-skipped['state'][:, 0, 2]))
    db = np.degrees(baseline['state'][:, 0, 3]-skipped['state'][:, 0, 3])
    mask = (t >= t[a]-10) & (t <= end+30)
    rows = [dict(event=event['event'], case=event['case'], label='ORACLE_DIAGNOSTIC', frame=int(i), t_s=float(t[i]),
                 delta_psi_deg=float(dh[i]), delta_bg_dps=float(db[i])) for i in np.flatnonzero(mask)]
    fit = (t >= end) & (t <= end+10)
    rec = dict(event=event['event'], fit_n=int(fit.sum()), fit_start_s=float(end), fit_end_s=float(end+10))
    for name, delta, floor in (('heading', dh, 1e-9), ('bias', db, 1e-12)):
        values = np.abs(delta[fit]); rec[name+'_floor_hits'] = int(np.count_nonzero(values <= floor))
        rec[name+'_log_slope_per_s'] = (float(np.polyfit(t[fit]-end, np.log(np.maximum(values, floor)), 1)[0])
                                             if fit.sum() >= 3 else None)
    return rows, rec


def decide(rows):
    global_rows = { (r['event'], r['arm']): r for r in rows
                    if r.get('scope') == 'GLOBAL_T30' and r.get('status') == 'TECHNICAL_PASS' }
    def effect(event, arm):
        base = global_rows.get((event, 'POWER1')); other = global_rows.get((event, arm))
        return None if base is None or other is None else base['heading_rmse_deg']-other['heading_rmse_deg']
    beneficial = [e for e in LOCK['events'] if e['role'] == 'beneficial']
    safe = {}
    for arm in ('D3', 'D4', 'D6'):
        checks = [(effect(e['event'], 'SKIP'), effect(e['event'], arm)) for e in beneficial]
        safe[arm] = all(s is not None and d is not None and s < 0 and -d <= -.5*s for s, d in checks)
    supported = []; falsified = []; detail = []
    for event in LOCK['events']:
        eid = event['event']; skip = effect(eid, 'SKIP'); ratios = {}
        for arm in ('D1', 'D2', 'D3', 'D4', 'D5', 'D6'):
            delta = effect(eid, arm)
            ratios[arm] = None if skip is None or skip <= 0 or delta is None else delta/skip
        qualifies = [arm for arm in ('D3', 'D4', 'D6') if safe[arm] and ratios[arm] is not None and ratios[arm] >= .5]
        if event['role'] == 'harmful':
            if qualifies: supported.append(eid)
            channels = any(ratios[arm] is not None and ratios[arm] >= .5 for arm in ('D1', 'D2'))
            small = all(ratios[arm] is not None and ratios[arm] < .2 for arm in ('D3', 'D4', 'D6'))
            if channels and small: falsified.append(eid)
        detail.append(dict(event=eid, role=event['role'], skip_gain_deg=skip,
                           sign_changed=None if skip is None else bool(skip*event['previous_skip_gain_deg'] <= 0),
                           recovery_ratios=ratios, qualifying_safe_diagnostics=qualifies))
    # Support/falsification definitions cannot both apply to three out of five.
    verdict = ('SUPPORTED_BUT_LIMITED' if len(supported) >= 3 else
               'FALSIFIED_FOR_TESTED' if len(falsified) >= 3 else 'NOT_ESTABLISHED')
    return dict(scientific=verdict, fixed_harmful_count=5, fixed_beneficial_count=5,
                conservative_all_beneficial_safety=safe, supported_events=supported,
                channel_only_events=falsified, events=detail)


def annotate_gains(rows):
    lookup = {(r['event'], r['scope'], r['arm']): r for r in rows if r.get('status') == 'TECHNICAL_PASS'}
    for row in rows:
        base = lookup.get((row['event'], row['scope'], 'POWER1'))
        skipped = lookup.get((row['event'], row['scope'], 'SKIP'))
        if base is not None and row.get('status') == 'TECHNICAL_PASS':
            row['intervention_gain_deg'] = base['heading_rmse_deg']-row['heading_rmse_deg']
            if skipped is not None:
                gain = base['heading_rmse_deg']-skipped['heading_rmse_deg']
                row['skip_gain_deg'] = gain
                if gain > 0: row['recovery_ratio'] = row['intervention_gain_deg']/gain
    return rows


def main():
    global LOCK
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundle', type=Path); source.add_argument('--new-traces', type=Path)
    source.add_argument('--aggregate', type=Path, nargs='+', help='INTERVENTIONS.csv files; no RF replay')
    parser.add_argument('--case-config', type=Path, help='New cases: {cases:[{case:{metadata},trace:relative.npz}]}')
    parser.add_argument('--source-root', type=Path); parser.add_argument('--execution-root', type=Path)
    parser.add_argument('--key-b0', type=Path, default=REPO/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--range-model', choices=['B_OLD','SRC_TAP'], default='B_OLD')
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    lock_path = HERE/('PROTOCOL_LOCK_SRC.json' if args.range_model == 'SRC_TAP' else 'PROTOCOL_LOCK.json')
    LOCK = json.loads(lock_path.read_text(encoding='utf-8'))
    if args.aggregate:
        tables = [pd.read_csv(path) for path in args.aggregate]
        merged = pd.concat(tables, ignore_index=True)
        if merged.duplicated(['event', 'arm', 'scope']).any():
            raise ValueError('DUPLICATE_AGGREGATE_EVENT_ARM_SCOPE')
        merged.to_csv(args.out/'INTERVENTIONS.csv', index=False)
        decision = decide(merged.to_dict('records'))
        (args.out/'DECISION.json').write_text(json.dumps(decision, indent=2, allow_nan=False), encoding='utf-8')
        complete = all(((merged.event == e['event']) & (merged.arm == arm) &
                       (merged.scope == 'GLOBAL_T30') & (merged.status == 'TECHNICAL_PASS')).sum() == 1
                       for e in LOCK['events'] for arm in LOCK['arms'])
        (args.out/'RESULTS_KO.md').write_text('# T4 F1 병합 결과\n\nTECHNICAL: '+
             ('TECHNICAL_PASS' if complete else 'INCOMPLETE_OR_ERROR')+'; 과학 판정: '+decision['scientific']+
             '.\n\n고정 5+5 이벤트를 대상으로 같은 개입의 전체 유익 이벤트 안전성을 요구했다. 세부 회수 비율·부호 변경은 DECISION.json, 모든 지표는 INTERVENTIONS.csv에 보존한다.\n\n'
             '## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 모든 개입 비교는 ORACLE_DIAGNOSTIC이다.\n', encoding='utf-8')
        (args.out/'MANIFEST.json').write_text(json.dumps(dict(inputs={str(p):sha(p) for p in args.aggregate},
             protocol_sha256=sha(lock_path), range_model=args.range_model, technical='TECHNICAL_PASS' if complete else 'INCOMPLETE_OR_ERROR',
             scientific=decision['scientific'], actions_run_id=os.getenv('GITHUB_RUN_ID'), artifact_id=None), indent=2), encoding='utf-8')
        return
    if args.source_root is None or args.execution_root is None:
        parser.error('--source-root and --execution-root required for replay')
    rows, checks, errors, first, divergences, growth, events = [], [], [], [], [], [], []
    inputs = {str(lock_path):sha(lock_path), str(Path(__file__)):sha(Path(__file__))}
    try:
        for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                    'research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016'):
            sys.path.insert(0, str(args.source_root/rel))
        sys.path.insert(0, str(HERE.parent/'T1_MEMORY/vendor'))
        import p0_initial
        p0_initial.DATA = args.execution_root; p0_initial.OUT = args.out/'bank_audit'; p0_initial.OUT.mkdir(exist_ok=True)
        from source_model import SourceFFD
        old_model = SourceFFD()
        model = old_model
        if args.range_model == 'SRC_TAP':
            sys.path.insert(0, str(HERE.parent/'T6_RANGE'))
            from src_range_model import SourceTapRange
            model = SourceTapRange(old_model)
        engine_path = HERE.parent/'canonical_engine.py'
        spec = importlib.util.spec_from_file_location('f1_canonical_engine', engine_path)
        engine = importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
        for path in (engine_path, Path(sys.modules['source_model'].__file__), args.key_b0): inputs[str(path)] = sha(path)
        key = pd.read_csv(args.key_b0)
        manifest_path = args.bundle or args.case_config
        if manifest_path is None: raise ValueError('BLOCKED_INPUT:NEW_CASE_CONFIG_REQUIRED')
        config = json.loads(manifest_path.read_text(encoding='utf-8')); inputs[str(manifest_path)] = sha(manifest_path)
        if config.get('range_model', 'B_OLD') != args.range_model:
            raise ValueError('NEW_RANGE_MODEL_REQUIRES_NEW_PROTOCOL_LOCK')
        selected_cases = config['cases']
        seen = set()
        for item in selected_cases:
            if item.get('bias', 'B0') != 'B0': continue
            case = item['case']; cid = case['id']
            selected_events = [e for e in LOCK['events'] if e['case'] == cid]
            if not selected_events: continue
            if cid in seen: raise ValueError('DUPLICATE_CASE:'+cid)
            seen.add(cid)
            try:
                path = ((args.bundle.parent/item['npz']) if args.bundle else
                        args.new_traces/item.get('trace', cid+'_B0.npz'))
                inputs[str(path)] = sha(path); data = normalize(load_npz(path))
                historical = (args.bundle.parent/item['historical_power1_trace']) if args.bundle else path
                if args.range_model == 'SRC_TAP':
                    historical = args.new_traces/item['bold_reference']
                    original_data = normalize(load_npz(historical))
                    original_result = run(engine, old_model, original_data, case, dict(name='POWER1', base='power'))
                    check = check_reference(original_result, original_data, historical, cid, key)
                    check['range_model'] = 'B_OLD_REFERENCE'; checks.append(check)
                    inputs[str(historical)] = sha(historical)
                baseline = run(engine, model, data, case, dict(name='POWER1', base='power'))
                if args.range_model == 'B_OLD':
                    inputs[str(historical)] = sha(historical)
                    checks.append(check_reference(baseline, data, historical, cid, key))
                elif item.get('source_reference'):
                    source_reference = args.new_traces/item['source_reference']
                    inputs[str(source_reference)] = sha(source_reference)
                    check = check_reference(baseline, data, source_reference, cid, key, check_key=False)
                    check['range_model'] = 'SRC_TAP_T6_REFERENCE'; checks.append(check)
                else:
                    checks.append(dict(case=cid, range_model='SRC_TAP', source_baseline='NEW_REPLAY_INDEPENDENTLY_SCORED',
                                       **metrics(baseline, data, data['t'] >= 30)))
            except Exception as exc:
                errors.append(dict(case=cid, arm='POWER1', error=str(exc), traceback=traceback.format_exc(), retry=False))
                continue
            for event in selected_events:
                eid = event['event']; packet = []
                try:
                    a, b, rf_lo, rf_hi = event_indices(data, event); t = data['t']
                    events.append(dict(**event, i0=a, i1=b, rf_lo=rf_lo, rf_hi=rf_hi,
                                       start_s=float(t[a]), end_s=float(t[b-1]), event_rf_count=rf_hi-rf_lo))
                    first.append(first_harmful(baseline, data, event, a, b))
                    arms = [('POWER1', {})]+[(name, details) for name, details in LOCK['arms'].items() if name != 'POWER1']
                    for arm, details in arms:
                        try:
                            arm_spec = dict(name=arm, base='power', diagnostic_event=[a, b], **details)
                            if arm == 'D3': arm_spec['oracle_heading'] = float(data['truth'][a, 2])
                            result = baseline if arm == 'POWER1' else run(engine, model, data, case, arm_spec)
                            masks = {'GLOBAL_T30': t >= 30, 'GLOBAL_T30_RADIO': (t >= 30)&data['radio_mask'],
                                     'EVENT': (t >= t[a])&(t <= t[b-1]),
                                     'POST30': (t >= t[b-1])&(t <= t[b-1]+30)}
                            for scope, mask in masks.items():
                                rows.append(dict(event=eid, case=cid, role=event['role'], arm=arm, scope=scope,
                                                 label='ORACLE_DIAGNOSTIC', reference_control=(arm == 'POWER1'),
                                                 **metrics(result, data, mask)))
                            packet.extend(packet_rows(result, data, event, arm, a, b))
                            (args.out/'traces').mkdir(exist_ok=True)
                            np.savez_compressed(args.out/'traces'/f'{eid}_{arm}.npz', **result)
                            if arm == 'SKIP':
                                dr, gr = divergence(baseline, result, data, event, a, b)
                                divergences.extend(dr); growth.append(gr)
                        except Exception as exc:
                            errors.append(dict(case=cid, event=eid, arm=arm, error=str(exc), traceback=traceback.format_exc(), retry=False))
                    pd.DataFrame(packet).to_csv(args.out/f'PACKET_LOG_{eid}.csv', index=False)
                except Exception as exc:
                    errors.append(dict(case=cid, event=eid, error=str(exc), traceback=traceback.format_exc(), retry=False))
    except Exception as exc:
        errors.append(dict(error=str(exc), traceback=traceback.format_exc(), retry=False))
    annotate_gains(rows)
    for name, records in [('INTERVENTIONS', rows), ('BASELINE_CHECKS', checks), ('FIRST_HARMFUL_UPDATE', first),
                           ('DIVERGENCE', divergences), ('GROWTH', growth), ('EVENT_RECEIPT', events)]:
        pd.DataFrame(records).to_csv(args.out/(name+'.csv'), index=False)
    decision = decide(rows)
    (args.out/'DECISION.json').write_text(json.dumps(decision, indent=2, allow_nan=False), encoding='utf-8')
    (args.out/'ERRORS.json').write_text(json.dumps(errors, indent=2), encoding='utf-8')
    manifest = dict(task='T4_F1_EVENT', range_model=args.range_model, protocol_sha256=sha(lock_path), technical='TECHNICAL_PASS' if not errors else 'ERROR_OR_BLOCKED_INPUT',
                    inputs=inputs, actions_run_id=os.getenv('GITHUB_RUN_ID'), artifact_id=None,
                    output_sha256={p.name:sha(p) for p in args.out.iterdir() if p.is_file() and p.name != 'MANIFEST.json'},
                    scientific=decision['scientific'], executed_case_ids=sorted({r['case'] for r in rows}),
                    traces='Actions artifact only; publisher must add archive SHA256 and artifact id after upload')
    (args.out/'MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    text = '# T4 F1 이벤트 진단\n\n'+f"TECHNICAL: {manifest['technical']}; 과학 판정: {decision['scientific']}.\n\n"
    text += '고정 이벤트의 역할·bin·visit은 결과에 따라 변경하지 않았다. D1–D6 및 skip은 ORACLE_DIAGNOSTIC이며 온라인 정책 성능 주장이 아니다. 전체 모션 t≥30 s 판정과 RF 시점 비교·이벤트·이후 30 s 지표를 함께 보존한다. 분할 실행의 최종 판정은 전체 INTERVENTIONS.csv를 합친 뒤 수행한다.\n\n'
    text += '| 이벤트 | 기존 역할 | 정본 skip 개선량 ° | 부호 변경 | ≥50% 회수 및 전체 유익 안전성 충족 개입 |\n| --- | --- | --- | --- | --- |\n'
    for event in decision['events']:
        text += f"| {event['event']} | {event['role']} | {event['skip_gain_deg']} | {event['sign_changed']} | {','.join(event['qualifying_safe_diagnostics']) or '없음/미확립'} |\n"
    text += '\nFIRST_HARMFUL_UPDATE.csv는 최초 유해 update의 채널을, DECISION.json은 개입별 회수 비율을 제공한다. 어느 개입의 RMSE 회수가 가장 큰지는 인과 경로의 유일성을 뜻하지 않는다.\n\n'
    text += '## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 이전 skip 수치는 정본 센서 재실행과 직접 동일하다고 가정하지 않는다.\n'
    (args.out/'RESULTS_KO.md').write_text(text, encoding='utf-8')
    if errors: raise SystemExit(1)


if __name__ == '__main__':
    main()
