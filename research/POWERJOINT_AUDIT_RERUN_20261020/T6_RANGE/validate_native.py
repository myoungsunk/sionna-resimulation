"""Native-LoS detector consistency and honest active-cell FD diagnostics.

No P1 fit/replay is performed by this script. Run only after lock commit.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import sys
import traceback
import zipfile
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np
import pandas as pd
from src_range_model import SourceTapRange

HERE = Path(__file__).resolve().parent
B_OLD = -.5315983906250129


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def frozen_los(path):
    out = {}
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('P2_ONE_STEP_SUMMARY.json'))
        meta = json.loads(archive.read(name))
        for rec in meta['per_case']:
            if rec['channel'] != 'los': continue
            file = str(Path(name).parent / rec['trace_file']).replace('\\', '/')
            if file not in archive.namelist():
                matches = [n for n in archive.namelist() if n.endswith(rec['trace_file'])]
                if len(matches) != 1: raise RuntimeError('NONUNIQUE_LOS_TRACE')
                file = matches[0]
            with np.load(io.BytesIO(archive.read(file)), allow_pickle=False) as trace:
                out[rec['case']] = {k: trace[k].copy() for k in trace.files}
    return out


def load_model(source_root, execution_root, out):
    for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                'research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016'):
        sys.path.insert(0, str(source_root/rel))
    import p0_initial
    p0_initial.DATA = execution_root
    p0_initial.OUT = out/'bank_audit'; p0_initial.OUT.mkdir(exist_ok=True)
    from source_model import SourceFFD
    return SourceFFD(), p0_initial


def summarize(frame, keys):
    rows = []
    grouped = [((), frame)] if not keys else frame.groupby(keys, observed=True, dropna=False)
    for label, group in grouped:
        if not isinstance(label, tuple): label = (label,)
        rec = dict(zip(keys, [str(v) for v in label]))
        for arm, field in [('B_OLD', 'error_old_m'), ('SRC_TAP', 'error_src_m'), ('B_REFIT_ONLY', 'error_refit_m')]:
            e = group[field].to_numpy()
            rows.append(dict(rec, arm=arm, n=len(e), mean_m=float(e.mean()),
                             rmse_m=float(np.sqrt(np.mean(e*e))), max_abs_m=float(abs(e).max())))
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--execution-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--batch', type=int, default=24)
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    rows, fdrows = [], []
    try:
        lock = json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
        model, p0 = load_model(args.source_root, args.execution_root, args.out)
        adapter = SourceTapRange(model)
        manifest_path = args.source_root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
        cases = json.loads(manifest_path.read_text())['cases']
        raw_path = args.execution_root/'rf_frozen.zip'
        raw = frozen_los(raw_path)
        for case in cases:
            data = raw[case['id']]
            truth = data['truth_for_offline_scoring_only'][:, :3]
            states = np.c_[truth, np.zeros(len(truth))]
            observed = data['z_r_m']
            last_tap = None
            for start in range(0, len(states), args.batch):
                stop = min(start+args.batch, len(states)); state = states[start:stop]
                old, _, _ = model.batch(state, case, gradient=False, return_diagnostics=True)
                predicted, J, diag = adapter.batch(state, case, return_diagnostics=True)
                height = case['anchor'][2]-case['robot_z_m']
                planar = np.hypot(state[:, 0]-case['anchor'][0], state[:, 1]-case['anchor'][1])
                for j in range(len(state)):
                    tap = int(diag['tap'][j]); i = start+j
                    transition = last_tap is not None and tap != last_tap
                    rows.append(dict(case=case['id'], route=case['id'].split('_')[0],
                        pose_id=int(data['pose_id'][i]), t_s=float(data['t_s'][i]),
                        distance_m=float(old[j, 0]-B_OLD), theta_deg=float(np.degrees(np.arctan2(planar[j], height))),
                        tap=tap, tap_transition=transition, strong_port=int(diag['strong_port'][j]),
                        fp_margin=float(diag['fp_margin'][j]), observed_m=float(observed[i]),
                        predicted_src_m=float(predicted[j, 0]), error_old_m=float(observed[i]-old[j, 0]),
                        error_src_m=float(observed[i]-predicted[j, 0])))
                    last_tap = tap
                for axis, coordinate in enumerate(('x', 'y', 'yaw')):
                    epsilons = lock['fd']['yaw_eps_rad' if axis == 2 else 'xy_eps_m']
                    for eps in epsilons:
                        plus = state.copy(); minus = state.copy()
                        plus[:, axis] += eps; minus[:, axis] -= eps
                        hp, _, dp = adapter.batch(plus, case, gradient=False, return_diagnostics=True)
                        hm, _, dm = adapter.batch(minus, case, gradient=False, return_diagnostics=True)
                        finite = (hp[:, 0]-hm[:, 0])/(2*eps)
                        stable = (dp['tap'] == diag['tap']) & (dm['tap'] == diag['tap'])
                        for j in range(len(state)):
                            fdrows.append(dict(case=case['id'], pose_id=int(data['pose_id'][start+j]),
                                coordinate=coordinate, eps=eps, tap=int(diag['tap'][j]),
                                tap_plus=int(dp['tap'][j]), tap_minus=int(dm['tap'][j]), stable_cell=bool(stable[j]),
                                finite_difference=float(finite[j]), declared_jacobian=float(J[j, 0, axis]),
                                abs_difference=float(abs(finite[j]-J[j, 0, axis]))))
                print('T6_NATIVE_PROGRESS', case['id'], stop, len(states), flush=True)
        frame, fd = pd.DataFrame(rows), pd.DataFrame(fdrows)
        # B refit is a distinct train-only offset control; no modification to SRC_TAP.
        offsets = {}
        for held in ('R2', 'R4', 'R5'):
            train = frame[frame.route != held]
            offsets[held] = float((train.observed_m-train.distance_m).mean())
        frame['refit_offset_m'] = frame.route.map(offsets)
        frame['error_refit_m'] = frame.observed_m-frame.distance_m-frame.refit_offset_m
        frame['distance_bin'] = pd.cut(frame.distance_m, lock['distance_bins_m'], right=False)
        frame['theta_bin'] = pd.cut(frame.theta_deg, lock['theta_bins_deg'], right=False)
        frame.to_csv(args.out/'NATIVE_RESIDUALS.csv', index=False)
        fd.to_csv(args.out/'FD_STENCILS.csv', index=False)
        stats = []
        for keys in ([], ['case'], ['case', 'distance_bin'], ['case', 'theta_bin'], ['case', 'tap_transition']):
            stats.extend(dict(grouping='+'.join(keys) or 'all', **row) for row in summarize(frame, keys))
        pd.DataFrame(stats).to_csv(args.out/'RESIDUAL_GROUPS.csv', index=False)
        error = frame.error_src_m.to_numpy()
        stable = fd.loc[fd.stable_cell, 'abs_difference']
        crossing = int((~fd.stable_cell).sum())
        summary = dict(n=len(frame), expected_n=lock['native_los_expected_points'],
            n_matches=len(frame) == lock['native_los_expected_points'],
            src_range_rmse_m=float(np.sqrt(np.mean(error**2))),
            residual_target_met=bool(np.sqrt(np.mean(error**2)) < lock['residual_target_rmse_m']),
            stable_fd_max_abs=float(stable.max()) if len(stable) else None,
            stable_fd_pass=bool(len(stable) and stable.max() <= lock['fd']['stable_cell_max_abs_target']),
            total_fd_stencils=len(fd), crossing_stencils=crossing,
            global_fd_status='NOT_ESTABLISHED_NONSMOOTH' if crossing else 'NO_CROSSING_OBSERVED',
            refit_train_offsets_m=offsets, recursive_evaluation='NOT_EXECUTED')
        (args.out/'SUMMARY.json').write_text(json.dumps(summary, indent=2))
        source_files = [Path(sys.modules['source_model'].__file__), Path(p0.__file__), Path(p0.O.__file__),
                        HERE/'src_range_model.py', HERE/'validate_native.py', HERE/'PROTOCOL_LOCK.json', manifest_path]
        inputs = [raw_path, args.execution_root/'BANK_MANIFEST.json',
                  args.execution_root/'LP_plus45_bank.npz', args.execution_root/'LP_minus45_bank.npz']
        provenance = dict(source_sha256={str(f): digest(f) for f in source_files},
            input_sha256={str(f): digest(f) for f in inputs}, actions_run_id=os.getenv('GITHUB_RUN_ID'),
            artifact_id=None, python=sys.version, numpy=np.__version__, pandas=pd.__version__,
            blas_threads={k: os.environ[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
            technical='TECHNICAL_PASS' if summary['n_matches'] else 'FAIL_POINT_COUNT', scientific='NOT_ESTABLISHED')
        (args.out/'MANIFEST.json').write_text(json.dumps(provenance, indent=2))
        (args.out/'RESULTS_KO.md').write_text(
            '# T6 Native LoS 검출기 진단\n\n'
            +f"점수 {len(frame)} / expected {lock['native_los_expected_points']}; SRC_TAP RMSE {summary['src_range_rmse_m']:.12g} m, <.01 m 목표 {summary['residual_target_met']}.\n\n"
            +f"안정 셀 FD 최대차 {summary['stable_fd_max_abs']}; tap 전환 stencil {crossing}/{len(fd)}. 전환에서는 미분이 정의되지 않는다.\n\n"
            +'P1 재학습·POWER1 재귀·LoS 안전성 평가: NOT_EXECUTED. 잔차 개선만으로 추정 개선을 주장하지 않는다.\n\n'
            +'## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, tap 전환점의 미분 가능성을 주장하지 않는다.\n', encoding='utf-8')
        if not summary['n_matches']: raise RuntimeError('NATIVE_LOS_POINT_COUNT_MISMATCH')
    except Exception as error:
        if rows: pd.DataFrame(rows).to_csv(args.out/'PARTIAL_NATIVE_RESIDUALS.csv', index=False)
        if fdrows: pd.DataFrame(fdrows).to_csv(args.out/'PARTIAL_FD_STENCILS.csv', index=False)
        (args.out/'ERRORS.json').write_text(json.dumps([dict(error=str(error),
            traceback=traceback.format_exc(), retry='not automatic')], indent=2))
        raise


if __name__ == '__main__': main()
