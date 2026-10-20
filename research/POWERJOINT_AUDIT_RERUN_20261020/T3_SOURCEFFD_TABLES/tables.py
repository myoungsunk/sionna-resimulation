"""Locked SourceFFD slide tables; preserves oracle labels and failed checks."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import io
import json
import os
import sys
import traceback
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np
import pandas as pd
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE.parent/'T1_MEMORY'))
from replay import score
from unit_tests import load_engine
R0 = np.diag([.0068578637, .0081])


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def unique(root, pattern):
    paths = list(root.rglob(pattern))
    if not paths: raise ValueError('BLOCKED_INPUT:'+pattern)
    if len({sha(p) for p in paths}) != 1: raise ValueError('NONIDENTICAL_DUPLICATE:'+pattern)
    return paths[0]


def frozen(path):
    out = {}
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('P2_ONE_STEP_SUMMARY.json'))
        for rec in json.loads(archive.read(name))['per_case']:
            matches = [n for n in archive.namelist() if n.endswith(rec['trace_file'])]
            if len(matches) != 1: raise ValueError('NONUNIQUE_FROZEN_TRACE')
            with np.load(io.BytesIO(archive.read(matches[0])), allow_pickle=False) as trace:
                out[(rec['case'], rec['channel'])] = {k: trace[k].copy() for k in trace.files}
    return out


def parameters(frame, cid, ids):
    q = frame[(frame.case == cid) & (frame.channel == 'full')].set_index('pose_id').loc[ids]
    mu = q[['mu_r', 'mu_s']].to_numpy(); C = np.zeros((len(q), 2, 2))
    C[:, 0, 0] = q.C00; C[:, 1, 1] = q.C11; C[:, 0, 1] = C[:, 1, 0] = q.C01
    # These tables use POWER1, never the reconstructed P4 classifier.
    return mu, C, q.risk.to_numpy() if 'risk' in q else np.zeros(len(q))


class DimensionModel:
    def __init__(self, model): self.model_source = model
    def model(self, state, case):
        h, H = self.model_source.model(state, case)
        return h, H[:, :len(state)]


def los_selected(t, controls, initial, z, case, source_model, original):
    names = ['DR4', 'S3', 'J3', 'S4', 'J4']; model = DimensionModel(source_model)
    states = np.zeros((len(t), len(names), 4)); cov = np.zeros((len(t), len(names), 4, 4))
    gates = np.zeros((len(t), len(names)), bool)
    current = {}
    for name in names:
        n = int(name[-1]); x = initial.copy() if n == 3 else np.r_[initial, 0.]
        P = np.diag([.1**2, .1**2, np.radians(5)**2] + ([] if n == 3 else [np.radians(.1)**2]))
        current[name] = (x, P)
    for i in range(len(t)):
        for j, name in enumerate(names):
            x, P = current[name]; n = len(x)
            if i:
                x, P = original.predict_one(x, P, controls['ds_odom'][i], controls['dtheta_gyro'][i], controls['dt_s'][i])
            x, P, status, _ = original.filter_one(x, P, z[i], name, case, model)
            current[name] = (x, P)
            states[i, j, :n] = x; cov[i, j, :n, :n] = P; gates[i, j] = status == 'APPLIED'
    return dict(state=states, cov=cov, names=np.array(names), accepted=gates, t=t)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source-root', type=Path, required=True)
    p.add_argument('--execution-root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--engine-root', type=Path, default=REPO)
    p.add_argument('--parameters', type=Path); p.add_argument('--parameter-manifest', type=Path)
    p.add_argument('--range-model', choices=['B_OLD', 'SRC_TAP'], default='B_OLD')
    args = p.parse_args(); args.out.mkdir(parents=True, exist_ok=True); (args.out/'traces').mkdir(exist_ok=True)
    tables = {key: [] for key in ('SLIDE1_LOS', 'SLIDE2_RANGE_STATS', 'SLIDE2_HYBRID', 'SLIDE4_POWER')}
    checks, inputs = [], {}
    try:
        for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                    'research/EKF4_RANGE_S_STAGED_20261014', 'research/FFD_P0P3_20261016'):
            sys.path.insert(0, str(args.source_root/rel))
        import p0_initial
        p0_initial.DATA = args.execution_root
        p0_initial.OUT = args.out/'bank_audit'; p0_initial.OUT.mkdir(exist_ok=True)
        from source_model import SourceFFD
        import r2_bias_replay as original
        model_old = SourceFFD(); model = model_old
        if args.range_model == 'SRC_TAP':
            if args.parameters is None or args.parameter_manifest is None:
                raise ValueError('BLOCKED_INPUT:SRC_TAP_RETRAINED_PARAMETERS_AND_MANIFEST_REQUIRED')
            if json.loads(args.parameter_manifest.read_text()).get('range_model') != 'SRC_TAP':
                raise ValueError('SRC_TAP_PARAMETER_MODEL_MISMATCH')
            inputs[str(args.parameter_manifest)] = sha(args.parameter_manifest)
            sys.path.insert(0, str(HERE.parent/'T6_RANGE'))
            from src_range_model import SourceTapRange
            model = SourceTapRange(model_old)
        engine, engine_path = load_engine(args.engine_root)
        raw_path = args.execution_root/'rf_frozen.zip'; raw = frozen(raw_path)
        cache_path = unique(args.execution_root/'reference_ae', 'OOF_PARAMETERS.csv.gz')
        cached = pd.read_csv(cache_path); chosen_path = args.parameters or cache_path
        chosen = pd.read_csv(chosen_path)
        manifest_path = args.source_root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
        cases = json.loads(manifest_path.read_text())['cases']
        key_path = args.engine_root/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv'
        key = pd.read_csv(key_path)
        for path in (raw_path, cache_path, chosen_path, manifest_path, key_path, engine_path,
                     Path(original.__file__), Path(sys.modules['source_model'].__file__), HERE/'PROTOCOL_LOCK.json'):
            inputs[str(path)] = sha(path)

        def evaluate(result, truth, bias, cid, label, scope):
            records = []
            for j, name in enumerate(result['names']):
                values = score(result['state'][:, j], result['cov'][:, j], truth, bias, result['t'] >= 30)
                independent = score(result['state'][:, j], result['cov'][:, j], truth, bias, result['t'] >= 30, scalar=True)
                delta = max(abs(values[k]-independent[k]) for k in values)
                if delta > 1e-9: raise RuntimeError('INDEPENDENT_SCORER:'+cid+':'+str(name))
                if str(name).endswith('3'):
                    for field in ('bias_rmse_dps', 'bias_mean_dps', 'bias_final_dps'): values[field] = None
                records.append(dict(case=cid, bias=label, arm=str(name), table_scope=scope,
                    range_model=args.range_model, bias_metrics_status='N/A_NO_BIAS_STATE' if str(name).endswith('3') else 'DEFINED', **values))
                checks.append(dict(case=cid, bias=label, scope=scope, arm=str(name), independent_scorer_max_abs=delta))
            return records

        for case in cases:
            cid = case['id']; full, los = raw[(cid, 'full')], raw[(cid, 'los')]
            t = full['t_s']; truth = full['truth_for_offline_scoring_only'][:, :3]
            if not np.array_equal(full['pose_id'], los['pose_id']) or not np.array_equal(t, los['t_s']):
                raise ValueError('FULL_LOS_CLOCK_ALIGNMENT')
            if np.max(abs(truth-los['truth_for_offline_scoring_only'][:, :3])) > 1e-12:
                raise ValueError('FULL_LOS_TRUTH_ALIGNMENT')
            ids = full['pose_id'].astype(int)
            zf = np.c_[full['z_r_m'], full['z_s']]; zl = np.c_[los['z_r_m'], los['z_s']]
            old_mu, old_C, old_risk = parameters(cached, cid, ids)
            mu, C, risk = parameters(chosen, cid, ids)
            controls, initial = original.build_positive_bias_controls(t, truth, 'B0', 0)
            specs = [dict(name='JOINT4', base='r0'), dict(name='POWER1', base='power')]
            baseline = engine.run(t, controls, initial, zf, old_mu, old_C, old_risk, case, model_old, specs)
            power_index = list(baseline['names']).index('POWER1')
            value = score(baseline['state'][:, power_index], baseline['cov'][:, power_index], truth, 0., t >= 30)
            target = key[(key.case == cid) & (key.method == 'POWER1')]
            if len(target) != 1: raise ValueError('MISSING_HISTORICAL_POWER1_KEY')
            rmse_delta = float(abs(value['heading_rmse_deg']-target.heading_rmse_deg.iloc[0]))
            trace_path = unique(args.execution_root/'reference_ae', cid+'_B0.npz')
            inputs[str(trace_path)] = sha(trace_path)
            with np.load(trace_path, allow_pickle=False) as trace:
                index = list(trace['names']).index('POWER1')
                old_gate = trace['accepted'][:, index]
                if old_gate.shape != baseline['accepted'][:, power_index].shape: raise ValueError('HISTORICAL_GATE_SHAPE')
                gate_diff = int(np.count_nonzero(old_gate != baseline['accepted'][:, power_index]))
            checks.append(dict(case=cid, bias='B0', scope='HISTORICAL_FULL_POWER1', heading_rmse_delta_deg=rmse_delta, gate_mismatch=gate_diff))
            if rmse_delta > 1e-6 or gate_diff: raise RuntimeError('HISTORICAL_POWER1_PARITY:'+cid)
            selected = baseline if args.range_model == 'B_OLD' and chosen_path == cache_path else engine.run(t, controls, initial, zf, mu, C, risk, case, model, specs)
            tables['SLIDE4_POWER'].extend(evaluate(selected, truth, 0., cid, 'B0', 'FULL_REPLAY'))
            selected.update(truth_for_offline_scoring_only=truth)
            np.savez_compressed(args.out/'traces'/f'{cid}_B0_FULL.npz', **selected)
            if cid in ('R2_aA_m0', 'R2_aA_m45', 'R2_aB_m0'):
                predicted = []
                for start in range(0, len(t), 32):
                    predicted.append(model.batch(np.c_[truth[start:start+32], np.zeros(len(truth[start:start+32]))], case, gradient=False)[0])
                error = (zf-np.concatenate(predicted))[t >= 30]
                variance = float(np.var(error[:, 0], ddof=0))
                rho = float(np.corrcoef(error.T)[0, 1]) if (np.std(error, axis=0) > 0).all() else None
                tables['SLIDE2_RANGE_STATS'].append(dict(case=cid, n=len(error), table_scope='GT_EVALUATION_ONLY', range_model=args.range_model,
                    mu_r_m=float(error[:, 0].mean()), V_r_m2=variance, V_r_over_R0_r=variance/R0[0, 0], rho_er_es=rho))
            if cid not in ('R2_aA_m0', 'R2_aA_m45'): continue
            for label, bias in [('B0', 0.), ('L2', .20)]:
                controls, initial = original.build_positive_bias_controls(t, truth, label, 0)
                lo = los_selected(t, controls, initial, zl, case, model, original)
                tables['SLIDE1_LOS'].extend(evaluate(lo, truth, bias, cid, label, 'ORACLE_DIAGNOSTIC_NATIVE_LOS'))
                lo.update(truth_for_offline_scoring_only=truth)
                np.savez_compressed(args.out/'traces'/f'{cid}_{label}_LOS.npz', **lo)
                if label != 'L2': continue
                for cell, channels in {'E00': ('los', 'los'), 'E10': ('full', 'los'), 'E01': ('los', 'full'), 'E11': ('full', 'full')}.items():
                    observation = np.column_stack(((zf if channels[0] == 'full' else zl)[:, 0], (zf if channels[1] == 'full' else zl)[:, 1]))
                    result = engine.run(t, controls, initial, observation, mu, C, risk, case, model, specs)
                    records = evaluate(result, truth, bias, cid, label, 'ORACLE_DIAGNOSTIC_CHANNEL_ISOLATION')
                    tables['SLIDE2_HYBRID'].extend(dict(r, hybrid_cell=cell, POWER_parameter_policy='FIXED_ORIGINAL_FULL_ONLY') for r in records)
                    result.update(truth_for_offline_scoring_only=truth)
                    np.savez_compressed(args.out/'traces'/f'{cid}_L2_{cell}.npz', **result)
        old_lut = {}
        for cid in ('R2_aA_m0', 'R2_aA_m45'):
            old_lut[(cid, 'B0', 'DR4')] = .48; old_lut[(cid, 'L2', 'DR4')] = 24.97
        for cid, b0, l2, j4 in [('R2_aA_m0', .23, 17.94, .24), ('R2_aA_m45', .11, 17.37, .16)]:
            old_lut[(cid, 'B0', 'J3')] = b0; old_lut[(cid, 'L2', 'J3')] = l2; old_lut[(cid, 'L2', 'J4')] = j4
        changes = []
        for record in tables['SLIDE1_LOS']:
            old = old_lut.get((record['case'], record['bias'], record['arm']))
            record['old_lut_heading_rmse_deg'] = old; record['old_lut_source'] = 'USER_PROVIDED' if old is not None else 'NOT_PROVIDED'
            if old is not None:
                delta = record['heading_rmse_deg']-old
                if abs(delta) > .05 or abs(delta)/abs(old) > .1:
                    changes.append(dict(case=record['case'], bias=record['bias'], arm=record['arm'],
                        old_lut_heading_rmse_deg=old, new_heading_rmse_deg=record['heading_rmse_deg'], delta_deg=delta,
                        old_source='USER_PROVIDED', range_model=args.range_model))
        for name, rows in tables.items(): pd.DataFrame(rows).to_csv(args.out/(name+'.csv'), index=False)
        pd.DataFrame(changes).to_csv(args.out/'OLD_LUT_CHANGES.csv', index=False)
        pd.DataFrame(checks).to_csv(args.out/'VERIFICATION.csv', index=False)
        (args.out/'MANIFEST.json').write_text(json.dumps(dict(input_source_sha256=inputs,
            actions_run_id=os.getenv('GITHUB_RUN_ID'), artifact_id=None, range_model=args.range_model,
            historical_E1_ZIP_parity='NOT_ESTABLISHED', technical='TECHNICAL_PASS', scientific='NOT_ESTABLISHED',
            numpy=np.__version__, pandas=pd.__version__, python=sys.version), indent=2))
        (args.out/'RESULTS_KO.md').write_text('# T3 SourceFFD 표 재생성\n\n'
            +'네 표와 구 LUT 변화 목록을 실제 실행에서 산출했다. VERIFICATION에 기존 POWER1 RMSE·gate 및 독립 scorer 검사를 기록했다.\n\n'
            +'Native LoS 및 hybrid는 ORACLE_DIAGNOSTIC으로 분리했다. Hybrid POWER 파라미터는 네 셀 모두 원본 Full-only로 고정했다. 미확보 E1 ZIP parity는 NOT_ESTABLISHED다.\n\n'
            +'## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.\n', encoding='utf-8')
    except Exception as error:
        for name, rows in tables.items():
            if rows: pd.DataFrame(rows).to_csv(args.out/('PARTIAL_'+name+'.csv'), index=False)
        if checks: pd.DataFrame(checks).to_csv(args.out/'PARTIAL_VERIFICATION.csv', index=False)
        (args.out/'ERRORS.json').write_text(json.dumps([dict(error=str(error), traceback=traceback.format_exc(), retry='not automatic')], indent=2))
        raise


if __name__ == '__main__': main()
