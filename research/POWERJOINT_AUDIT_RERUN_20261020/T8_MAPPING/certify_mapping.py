"""Certify ordered M45/Tnone binding; failed binding never enters recursion."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import traceback
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wrap(degrees): return (np.asarray(degrees)+180) % 360-180


def resolve(base, name):
    path = Path(name)
    return path if path.is_absolute() else base/path


def poses(frame, columns, fixed_z=None, allow_missing_time=False):
    required = ('x', 'y', 'time', 'body')
    for key in required:
        if columns[key] not in frame: raise ValueError('MISSING_COLUMN:'+columns[key])
    x, y, t, body = [frame[columns[k]].to_numpy(float) for k in required]
    if columns.get('z') in frame:
        z = frame[columns['z']].to_numpy(float)
    elif fixed_z is not None:
        z = np.full(len(frame), float(fixed_z))
    else:
        raise ValueError('MISSING_HEIGHT_EVIDENCE')
    xyz = np.column_stack((x, y, z))
    ant = frame[columns['antenna']].to_numpy(float) if 'antenna' in columns else None
    if not np.isfinite(np.c_[xyz, body] if allow_missing_time else np.c_[xyz, t, body]).all() or (ant is not None and not np.isfinite(ant).all()):
        raise ValueError('NONFINITE_POSE_OR_TIME')
    return xyz, t, body, ant


def physical_observations(H, observer, frequencies):
    if H.ndim != 4 or H.shape[1] != len(frequencies) or H.shape[2] != 2 or H.shape[3] < 1:
        raise ValueError('RF_SHAPE_CONTRACT')
    valid = np.isfinite(H).all(axis=(1, 2, 3)) & (np.sum(abs(H)**2, axis=(1, 2, 3)) > 0)
    result = dict(valid=valid, s=np.full(len(H), np.nan), range_m=np.full(len(H), np.nan),
                  tap=np.full(len(H), -1, int), q=np.full(len(H), np.nan))
    if valid.any():
        observed = observer.observe(H[valid], frequencies, None, None)
        result['s'][valid] = observed['s']; result['range_m'][valid] = observed['range_m']
        result['tap'][valid] = observed['index']
        n = len(frequencies); window = .5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
        cir = np.fft.ifft(H[valid, :, :, 0]*window[None, :, None], n=4*n, axis=1)*n
        at_tap = cir[np.arange(valid.sum()), observed['index']]
        result['q'][valid] = np.log10(np.maximum(np.sum(abs(at_tap)**2, axis=1), np.finfo(float).tiny))
        result['valid'] &= np.isfinite(result['s']) & np.isfinite(result['range_m'])
    return result


def static_compare(rec, reference_case, matches, source_root, base, observer, frequencies):
    if not matches: return []
    H0 = np.load(source_root/reference_case['full_path'], mmap_mode='r', allow_pickle=False)
    L0 = np.load(source_root/reference_case['los_path'], mmap_mode='r', allow_pickle=False)
    H45 = np.load(resolve(base, rec['full_h']), mmap_mode='r', allow_pickle=False)
    L45 = np.load(resolve(base, rec['los_h']), mmap_mode='r', allow_pickle=False)
    out = []
    for start in range(0, len(matches), 48):
        chosen = matches[start:start+48]
        ii = np.array([m['reference_index'] for m in chosen], int)
        jj = np.array([m['m45_index'] for m in chosen], int)
        for mount, full, los, ids in [(0, H0, L0, ii), (45, H45, L45, jj)]:
            f = physical_observations(full[ids], observer, frequencies)
            l = physical_observations(los[ids], observer, frequencies)
            for k, match in enumerate(chosen):
                valid = bool(f['valid'][k] and l['valid'][k])
                out.append(dict(match, mount_deg=mount, full_valid=bool(f['valid'][k]),
                    los_valid=bool(l['valid'][k]), full_minus_los_s=float(f['s'][k]-l['s'][k]) if valid else None,
                    full_minus_los_range_m=float(f['range_m'][k]-l['range_m'][k]) if valid else None,
                    FP_mismatch=bool(f['tap'][k] != l['tap'][k]) if valid else None,
                    los_abs_s_gt_0p95=bool(abs(l['s'][k]) > .95) if l['valid'][k] else None,
                    q_log10_total_power=float(f['q'][k]) if f['valid'][k] else None,
                    full_s=float(f['s'][k]) if f['valid'][k] else None,
                    los_s=float(l['s'][k]) if l['valid'][k] else None,
                    scope='STATIC_SAME_POSE_SINGLE_OBSERVATION_NOT_EKF'))
    return out


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--static-physics', action='store_true')
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    lock = json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
    config = json.loads(args.config.read_text()); base = args.config.parent
    manifest_path = args.source_root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
    source_manifest = json.loads(manifest_path.read_text())
    if source_manifest['physical_contract']['Tnone_only'] is not True:
        raise ValueError('REFERENCE_NOT_FROZEN_TNONE')
    cases = {c['id']: c for c in source_manifest['cases']}
    observer = None
    if args.static_physics:
        for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                    'research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016'):
            sys.path.insert(0, str(args.source_root/rel))
        from p0_initial import O as observer
    contract = source_manifest['physical_contract']
    frequencies = np.linspace(*contract['frequency_hz'], contract['frequency_bins'])
    evidence = {str(path): sha(path) for path in (args.config, manifest_path, HERE/'PROTOCOL_LOCK.json', Path(__file__))}
    row_log, matches_log, static_rows, summaries, errors = [], [], [], [], []
    expected = {'R4_aA_m0', 'R4_aB_m0', 'R5_aA_m0', 'R5_aB_m0'}
    supplied = [r['reference_case'] for r in config['cases']]
    if len(set(supplied)) != len(supplied): raise ValueError('DUPLICATE_CASE_CONFIGURATION')
    for missing in sorted(expected-set(supplied)):
        errors.append(dict(case=missing, error='MISSING_REQUESTED_CASE_INPUT', retry='requires input'))
        summaries.append(dict(case=missing, recursive_status='BLOCKED_INPUT', reason='MISSING_REQUESTED_CASE_INPUT'))
    for rec in config['cases']:
        cid = rec['reference_case']
        try:
            case = cases[cid]
            if case['mount_deg'] != 0 or not cid.startswith(('R4_', 'R5_')):
                raise ValueError('NOT_REQUESTED_R4_R5_M0_REFERENCE')
            samples = args.source_root/case['samples_path']
            radio = resolve(base, rec['radio_pose'])
            # Capture identities before validation, so failed rows retain provenance.
            paths = [samples, radio, resolve(base, rec['full_h']), resolve(base, rec['los_h'])]
            for key in ('source_receipt', 'metadata_evidence'):
                if rec.get(key): paths.append(resolve(base, rec[key]))
            for path in paths:
                if path.is_file(): evidence[str(path)] = sha(path)
            ref = pd.DataFrame(json.loads(samples.read_text()))
            new = pd.read_csv(radio)
            rc = dict(x='x', y='y', z='z_m', time='t_s', body='yaw_body_deg')
            nc = dict(x='x_m', y='y_m', z='z_m', time='t_s', body='yaw_body_deg', antenna='yaw_antenna_deg')
            rc.update(rec.get('reference_columns', {})); nc.update(rec.get('radio_columns', {}))
            if rc['time'] not in ref:
                # Pose JSON omits time. Use the actual immutable Tnone trace,
                # only after exact pose-id and geometry certification.
                sys.path.insert(0,str(args.source_root/'research/CHAIN_HYPOTHESIS_20261019'))
                from run import frozen_inputs
                raw=frozen_inputs()[(cid,'full')]
                index={int(pid):i for i,pid in enumerate(raw['pose_id'])}
                times=np.full(len(ref),np.nan)
                actual=raw['truth_for_offline_scoring_only'][:,:3]
                for j,row in ref.iterrows():
                    i=index.get(int(row.pose_id))
                    if i is None:continue
                    if np.max(abs(row[['x','y']].to_numpy(float)-actual[i,:2]))>1e-8 or abs(wrap(float(row.yaw_body_deg)-np.degrees(actual[i,2])))>1e-6:
                        raise ValueError('REFERENCE_RF_CLOCK_GEOMETRY_MISMATCH')
                    times[j]=raw['t_s'][i]
                ref[rc['time']]=times
                # Missing clocks forbid recursive certification, but do not erase
                # independently certified geometry-only static pose pairs.
                rec['reference_clock_missing_rows']=int(np.isnan(times).sum())
                evidence[str(args.source_root.parent/'rf_frozen.zip')]=sha(args.source_root.parent/'rf_frozen.zip')
            fixed_z = rec.get('radio_z_m')
            if nc['z'] not in new and (fixed_z is None or not rec.get('metadata_evidence')):
                raise ValueError('M45_HEIGHT_NOT_INDEPENDENTLY_DOCUMENTED')
            oldxyz, oldt, oldbody, _ = poses(ref, rc, case['robot_z_m'], allow_missing_time=True)
            newxyz, newt, newbody, newant = poses(new, nc, fixed_z)
            if newant is None: raise ValueError('M45_ANTENNA_COLUMN_REQUIRED')
            H = np.load(resolve(base, rec['full_h']), mmap_mode='r', allow_pickle=False)
            L = np.load(resolve(base, rec['los_h']), mmap_mode='r', allow_pickle=False)
            h_aligned = len(H) == len(L) == len(new)
            monotone = bool((np.diff(oldt) > 0).all() and (np.diff(newt) > 0).all())
            length_equal = len(new) == len(ref)
            all_rows = True
            for i in range(max(len(new), len(ref))):
                exists = i < len(new) and i < len(ref)
                d = float(np.linalg.norm(newxyz[i]-oldxyz[i])) if exists else None
                yaw = float(abs(wrap(newbody[i]-oldbody[i]))) if exists else None
                dt = float(abs(newt[i]-oldt[i])) if exists else None
                ant = float(abs(wrap(newant[i]-newbody[i]-45))) if i < len(new) else None
                passed = bool(exists and d <= lock['position_tolerance_m']
                    and yaw <= lock['body_yaw_tolerance_deg'] and dt <= lock['time_tolerance_s']
                    and ant <= lock['antenna_relation_tolerance_deg'])
                all_rows &= passed
                row_log.append(dict(case=cid, row=i, reference_exists=i < len(ref), m45_exists=i < len(new),
                    position_error_m=d, body_yaw_error_deg=yaw, time_error_s=dt,
                    antenna_relation_error_deg=ant, pass_=passed))
            # Geometry-only matching is strictly a separate static comparison.
            selected = []
            for j, xyz in enumerate(newxyz):
                distance = np.linalg.norm(oldxyz-xyz, axis=1)
                yaw_difference = abs(wrap(oldbody-newbody[j]))
                candidate = np.flatnonzero((distance <= lock['position_tolerance_m'])
                                          & (yaw_difference <= lock['body_yaw_tolerance_deg']))
                ant_ok = abs(wrap(newant[j]-newbody[j]-45)) <= lock['antenna_relation_tolerance_deg']
                if not len(candidate) or not ant_ok:
                    matches_log.append(dict(case=cid, m45_index=j, matched=False,
                        candidate_count=len(candidate), antenna_relation_valid=bool(ant_ok)))
                    continue
                i = int(candidate[0])
                match = dict(case=cid, m45_index=j, reference_index=i, matched=True,
                    candidate_count=len(candidate), position_error_m=float(distance[i]),
                    body_yaw_error_deg=float(yaw_difference[i]), reference_t_s=float(oldt[i]),
                    m45_t_s=float(newt[j]), antenna_relation_valid=True)
                matches_log.append(match); selected.append(match)
            certified = bool(length_equal and monotone and h_aligned and all_rows)
            summary = dict(case=cid, reference_clock_missing_rows=rec.get('reference_clock_missing_rows',0), reference_n=len(ref), m45_n=len(new), length_equal=length_equal,
                times_strictly_monotone=monotone, h_rows_aligned=h_aligned,
                ordered_rows_all_pass=all_rows, recursive_binding_certified=certified,
                recursive_status='ELIGIBLE_NOT_EXECUTED' if certified else 'BLOCKED_INPUT',
                static_matched_rows=len(selected), static_unmatched_rows=len(new)-len(selected),
                static_ambiguous_rows=sum(m['candidate_count'] > 1 for m in selected))
            summaries.append(summary)
            paths = [samples, radio, resolve(base, rec['full_h']), resolve(base, rec['los_h'])]
            for key in ('source_receipt', 'metadata_evidence'):
                if rec.get(key): paths.append(resolve(base, rec[key]))
            if args.static_physics:
                paths.extend([args.source_root/case['full_path'], args.source_root/case['los_path']])
                if not h_aligned: raise ValueError('M45_H_POSE_LENGTH_MISMATCH_STATIC_BLOCKED')
                static_rows.extend(static_compare(rec, case, selected, args.source_root, base, observer, frequencies))
            evidence.update({str(path): sha(path) for path in paths})
        except Exception as error:
            errors.append(dict(case=cid, error=str(error), traceback=traceback.format_exc(), retry='not automatic'))
            if not any(s['case'] == cid for s in summaries):
                summaries.append(dict(case=cid, recursive_status='BLOCKED_INPUT', reason=str(error)))
    pd.DataFrame(row_log).to_csv(args.out/'ROW_CERTIFICATE.csv', index=False)
    pd.DataFrame(matches_log).to_csv(args.out/'STATIC_POSE_MATCHES.csv', index=False)
    if static_rows: pd.DataFrame(static_rows).to_csv(args.out/'STATIC_RF_COMPARISON.csv', index=False)
    (args.out/'SUMMARY.json').write_text(json.dumps(summaries, indent=2))
    if errors: (args.out/'ERRORS.json').write_text(json.dumps(errors, indent=2))
    if observer is not None: evidence[str(observer.__file__)] = sha(observer.__file__)
    (args.out/'MANIFEST.json').write_text(json.dumps(dict(input_source_sha256=evidence,
        actions_run_id=os.getenv('GITHUB_RUN_ID'), artifact_id=None,
        technical='TECHNICAL_PASS' if not errors else 'PARTIAL_WITH_ERRORS',
        scientific='NOT_ESTABLISHED', recursion_executed=False,
        numpy=np.__version__, pandas=pd.__version__, python=sys.version), indent=2))
    table = '\n'.join(f"| {r['case']} | {r['recursive_status']} | {r.get('static_matched_rows', 0)} |" for r in summaries)
    (args.out/'RESULTS_KO.md').write_text('# T8 시간 바인딩 인증\n\n'
        +'| case | 재귀 입력 인증 | 정적 pose 쌍 |\n|---|---|---|\n'+table
        +'\n\n재귀 EKF는 실행하지 않았다. 실패 행과 정적 pose의 시간·다중 후보 수를 보존했다. '
        +'정적 RF 관측 비교는 필터의 one-step 상태 갱신이나 Heading 평가가 아니다.\n\n'
        +'## 주장하지 않는 것\n\n정적 비교로 시간 바인딩·Heading 개선, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.\n', encoding='utf-8')
    if errors: raise RuntimeError('T8_CASE_ERRORS_PRESERVED')


if __name__ == '__main__': main()
