"""D8: range-correction-specific held-out CIR error models (USER-RUN).

The *online* model sees whitelisted RX CIR features only. Truth is used
exclusively to train targets and score held-out routes. Q0 keeps R0; Q1-Q3
separately regress conditional MEAN and centered residual second moment.
Their outputs remain exploratory proxies, not certified noise covariances.
No cross-route RF-scene independence is asserted. Q4 requires independent
relative-RX phase and receiver-noise evidence and is disabled by default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from d6_d9_common import (RR, RS, P3_MODEL, P3_SHA256, atomic_json, file_sha, finish, make_out,
                          read_csv, write_csv, wrap)
from d7_cir_multipath_audit import E1_DETECTOR_FEATURES, NUMERIC_FEATURES, ONLINE_KEYS
from p3_compat import predict_e1_bias

QUALITY_FEATURES = {
    'Q0_FIXED': (),
    'Q1_S_ONLY': ('s_fp',),
    'Q2_CIR_TIME_POWER': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns'),
    'Q3_CIR_POL': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns',
        'first_late_s_difference','rx_port_first_tap_delta_m',
        's_neighborhood_std','tap_step_delta_m','phase_valid',
        'rx1_fp_power','rx2_fp_power'),
    'Q4_COMPLEX_PHASE': (
        's_fp','range_raw_m','log_fp_power','peak_fp_ratio',
        'peak_minus_fp_m','late_energy_fraction','tau_rms_ns',
        'first_late_s_difference','rx_port_first_tap_delta_m',
        's_neighborhood_std','tap_step_delta_m','phase_valid',
        'rx1_fp_power','rx2_fp_power',
        'phase_fp_rad','phase_late_shift_rad'),
}
RANGE_LABELS = {
    'B_OLD': 'error_range_B_OLD_m',
    'E1_FULL_LORO': 'error_range_E1_FULL_LORO_m',
}
# Explicit s and range target baselines/floors. Never infer the target from
# the shape of D7's available columns.
TARGETS = {'s': ('error_s', RS, 1e-4, 4.),
           'r': ('error_range_B_OLD_m', RR, 1e-5, 9.)}


def target_config(target: str, range_model: str):
    if target not in TARGETS or range_model not in RANGE_LABELS:
        raise ValueError('Unknown D8 target/range correction')
    column, baseline, floor, cap = TARGETS[target]
    return (RANGE_LABELS[range_model] if target == 'r' else column,
            baseline, floor, cap)


def outer_e1_labels(rows: list[dict], holdout: str, frozen: dict) -> list[dict]:
    """Use only coefficients fit WITHOUT the outer route for every label.

    Reusing each training row's own route-excluded fold would introduce the
    outer evaluation route's truth through that fold's fitted coefficients.
    No coefficients are retrained, and model-family selection remains an
    earlier scene-internal exploratory choice rather than nested validation.
    """
    if frozen.get('chosen') != 'E1_on_B' or holdout not in frozen['loro_fold_params']:
        raise RuntimeError('Missing frozen outer-route-excluded E1 fold')
    fold = frozen['loro_fold_params'][holdout]
    vectors = np.asarray([[float(row[key]) for key in E1_DETECTOR_FEATURES]
                          for row in rows], float)
    bias = predict_e1_bias(vectors, fold)
    return [row | {'error_range_E1_FULL_LORO_m':
                   float(row['error_range_B_OLD_m'])-float(b),
                   'e1_label_outer_excluded_route': holdout}
            for row, b in zip(rows, bias)]


def online_vector(row: dict, names: tuple[str, ...]) -> list[float]:
    if not set(names) <= set(NUMERIC_FEATURES):
        raise RuntimeError('Oracle/off-contract field requested by predictor')
    values = [float(row[n]) for n in names]
    if not np.isfinite(values).all():
        raise RuntimeError('Nonfinite online CIR feature')
    return values


def ridge(X, y, penalty):
    mu = np.mean(X, axis=0)
    sd = np.maximum(np.std(X, axis=0), 1e-10)
    z = (X - mu) / sd
    center = float(np.mean(y))
    coefficients = np.linalg.solve(z.T @ z + penalty * np.eye(z.shape[1]),
                                   z.T @ (y - center))
    return {'center': center, 'mu': mu.tolist(), 'sd': sd.tolist(),
            'coef': coefficients.tolist()}


def affine(row, params, fields):
    if not fields:
        return float(params['center'])
    x = np.asarray(online_vector(row, tuple(fields)), float)
    mu = np.asarray(params['mu'], float)
    sd = np.asarray(params['sd'], float)
    w = np.asarray(params['coef'], float)
    if x.shape != w.shape or mu.shape != w.shape or sd.shape != w.shape or np.any(sd <= 0):
        raise RuntimeError('Invalid D8 regression model dimensions')
    return float(params['center'] + ((x - mu) / sd) @ w)


def fit_ridge(train: list[dict], target: str, variant: str, ridge_penalty: float,
              range_model: str = 'B_OLD') -> dict:
    """Fit conditional residual mean, then log *centered* squared error.

    Training residuals here are in-sample, so an optimistic variance proxy
    is possible. Held-out calibration gates are required before D9's Q3 arm.
    """
    col, baseline, floor, cap = target_config(target, range_model)
    if variant not in QUALITY_FEATURES or ridge_penalty <= 0 or not train:
        raise ValueError('Invalid D8 model request')
    fields = QUALITY_FEATURES[variant]
    base = {'variant': variant, 'target': target, 'target_label': col,
            'range_model': range_model, 'feature_names': list(fields),
            'floor': floor, 'cap': cap, 'baseline_variance': baseline}
    if variant == 'Q0_FIXED':
        return base | {'learned': False,
                       'mean_model': {'center': 0., 'mu': [], 'sd': [], 'coef': []},
                       'variance_model': {'center': math.log(baseline),
                                          'mu': [], 'sd': [], 'coef': []}}
    X = np.asarray([online_vector(r, fields) for r in train], float)
    errors = np.asarray([float(r[col]) for r in train], float)
    if not np.isfinite(errors).all():
        raise RuntimeError('Missing/nonfinite D8 training target '+col)
    center_fit = ridge(X, errors, ridge_penalty)
    mu_pred = np.asarray([affine(r, center_fit, fields) for r in train])
    resid = errors - mu_pred
    var_fit = ridge(X, np.log(resid**2 + floor), ridge_penalty)
    return base | {'learned': True,
                   'mean_model': center_fit, 'variance_model': var_fit,
                   'training_residual_mean': float(np.mean(resid)),
                   'training_residual_second_moment': float(np.mean(resid**2))}


def predict_mean(row: dict, params: dict) -> float:
    result = affine(row, params['mean_model'], params['feature_names'])
    if not math.isfinite(result):
        raise RuntimeError('Nonfinite conditional mean predictor')
    return result


def predict_variance(row: dict, params: dict) -> float:
    log_var = affine(row, params['variance_model'], params['feature_names'])
    result = float(np.clip(math.exp(float(np.clip(log_var, -40., 15.))),
                           params['floor'], params['cap']))
    if not math.isfinite(result) or result <= 0:
        raise RuntimeError('Non-positive conditional residual scale')
    return result


def split_exclude_overlap(train: list[dict], holdout: list[dict],
                          tolerance_m: float) -> tuple[list[dict], int]:
    """Do not leak held-out XY into training (handles grid-cell edges)."""
    if tolerance_m <= 0:
        raise ValueError('Positive XY exclusion radius required')
    hgrid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for row in holdout:
        x, y = float(row['true_x_m']), float(row['true_y_m'])
        hgrid.setdefault((math.floor(x/tolerance_m), math.floor(y/tolerance_m)), []).append((x, y))
    kept = []
    dropped = 0
    for row in train:
        x, y = float(row['true_x_m']), float(row['true_y_m'])
        i, j = math.floor(x/tolerance_m), math.floor(y/tolerance_m)
        leak = any((x-u)**2 + (y-v)**2 <= tolerance_m**2
                   for di in (-1,0,1) for dj in (-1,0,1)
                   for u,v in hgrid.get((i+di,j+dj), []))
        if leak:
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped


def load_paired(source: Path):
    receipt = source/'D7_MANIFEST.json'
    if not receipt.is_file():
        raise FileNotFoundError('D7 completed manifest required')
    metadata = json.loads(receipt.read_text(encoding='utf-8'))
    if metadata.get('stage')!='D7' or metadata.get('scientific_PASS') is not False:
        raise RuntimeError('Unexpected D7 manifest')
    files = [source/'D7_ONLINE_CIR_FEATURES.csv', source/'D7_ORACLE_EVALUATION_LABELS.csv']
    for path in files:
        if file_sha(path) != metadata['sha256'][path.name]:
            raise RuntimeError('D7 data hash mismatch: '+path.name)
    online, labels = (read_csv(x) for x in files)
    if not online or set(online[0]) != set(ONLINE_KEYS):
        raise RuntimeError('D7 online schema mismatch; oracle fields leaked')
    def key(row):
        return row['case'], row['channel'], row['sample_index']
    lookup = {key(r): r for r in labels}
    if len(lookup) != len(labels) or len(online) != len(labels):
        raise RuntimeError('Duplicate D7 labels or cardinality mismatch')
    joint = []
    for row in online:
        lab = lookup.get(key(row))
        if lab is None or lab['route'] != row['route'] or lab['pose_id'] != row['pose_id']:
            raise RuntimeError('D7 labels missing or misaligned')
        joint.append(row | {k: v for k, v in lab.items() if k not in row})
    if len({key(r) for r in joint}) != len(joint):
        raise RuntimeError('Duplicate D7 online sample')
    return joint, {x.name: file_sha(x) for x in files}


def phase_evidence(path: Path | None) -> dict | None:
    """Q4 cannot run on numerical port-power threshold alone."""
    if path is None:
        return None
    j = json.loads(path.read_text(encoding='utf-8'))
    if (j.get('independent_rx_phase_calibration') is not True or
        j.get('independent_snr_calibration') is not True or
        not isinstance(j.get('calibration_source_sha256'), str) or
        len(j['calibration_source_sha256']) != 64):
        raise RuntimeError('Independent phase/SNR calibration evidence required for Q4')
    # A self-declared checksum is insufficient: verify its actual external
    # calibration evidence file, and never accept the declaration itself.
    external = Path(j['calibration_source_file'])
    if not external.is_absolute():
        external = path.parent / external
    if external.resolve()==path.resolve() or not external.is_file():
        raise RuntimeError('Independent phase calibration source file missing')
    if file_sha(external)!=j['calibration_source_sha256']:
        raise RuntimeError('Independent phase calibration source checksum mismatch')
    noise = float(j['noise_floor_cir_tap_power'])
    snr = float(j['min_both_rx_snr_db'])
    offset = float(j['rx_relative_phase_offset_rad'])
    if noise <= 0 or not all(map(math.isfinite, (noise,snr,offset))):
        raise RuntimeError('Invalid Q4 SNR/phase evidence')
    return {'evidence_sha256': file_sha(path), 'noise_floor_cir_tap_power': noise,
            'min_both_rx_snr_db': snr, 'rx_relative_phase_offset_rad': offset}


def validated_phase_row(row: dict, phase: dict) -> dict:
    snr = 10*math.log10(max(min(float(row['rx1_fp_power']),
                                float(row['rx2_fp_power'])), 1e-300) /
                        phase['noise_floor_cir_tap_power'])
    if not (int(row['phase_valid']) and snr >= phase['min_both_rx_snr_db']):
        raise RuntimeError('Q4 phase uncalibrated or SNR below independent threshold')
    return row | {'phase_fp_rad': wrap(float(row['phase_fp_rad']) -
                                      phase['rx_relative_phase_offset_rad'])}


def score_model(rows, params):
    error = np.asarray([float(row[params['target_label']]) for row in rows])
    mean = np.asarray([predict_mean(row,params) for row in rows])
    var = np.asarray([predict_variance(row,params) for row in rows])
    res = error-mean
    return {'n': len(rows), 'mse': float(np.mean(res**2)),
            'mean_predicted_second_moment': float(np.mean(var)),
            'calibration_empirical_over_predict_var': float(np.mean(res**2)/np.mean(var)),
            'mean_centered_error': float(np.mean(res)),
            'mean_original_error': float(np.mean(error)),
            'zero_mean_gaussian_nll_proxy': float(np.mean(.5*(np.log(var)+res**2/var)))}


def calibration_gate(q0: dict, q3: dict, lo=.5, hi=2., min_gain=0., *, q1: dict | None = None):
    improvement = q0['zero_mean_gaussian_nll_proxy']-q3['zero_mean_gaussian_nll_proxy']
    q1_improvement = (q1['zero_mean_gaussian_nll_proxy']-q3['zero_mean_gaussian_nll_proxy']
                      if q1 is not None else None)
    ratio = q3['calibration_empirical_over_predict_var']
    passed = (math.isfinite(improvement) and improvement >= min_gain and
              q1_improvement is not None and math.isfinite(q1_improvement) and
              q1_improvement >= min_gain and lo <= ratio <= hi)
    return {'status': 'EXPLORATORY_HELDOUT_GATE_PASS' if passed else 'EXPLORATORY_HELDOUT_GATE_FAIL',
            'nll_improvement_vs_Q0': improvement, 'calibration_ratio': ratio,
            'nll_improvement_vs_Q1': q1_improvement,
            'calibration_min': lo, 'calibration_max': hi, 'minimum_nll_gain': min_gain}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d7',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--ridge',type=float,default=10.)
    ap.add_argument('--xy-buffer-m',type=float,default=1e-4)
    ap.add_argument('--min-train-rows',type=int,default=100)
    ap.add_argument('--range-models',nargs='+', choices=list(RANGE_LABELS),
                    default=list(RANGE_LABELS))
    ap.add_argument('--phase-evidence',type=Path,default=None,
                    help='Independent RX phase AND tap SNR calibration JSON; Q4 skipped otherwise')
    ap.add_argument('--gate-calibration-min',type=float,default=.5)
    ap.add_argument('--gate-calibration-max',type=float,default=2.)
    ap.add_argument('--gate-min-nll-gain',type=float,default=0.)
    args = ap.parse_args()
    if (args.ridge <= 0 or args.xy_buffer_m <= 0 or args.min_train_rows < 10 or
        not 0 < args.gate_calibration_min < args.gate_calibration_max or
        len(set(args.range_models)) != len(args.range_models)):
        raise ValueError('Invalid D8 training/gate settings')
    records, hashes = load_paired(args.d7)
    if file_sha(P3_MODEL) != P3_SHA256:
        raise RuntimeError('Frozen E1 coefficient checksum mismatch')
    frozen_e1 = json.loads(P3_MODEL.read_text(encoding='utf-8'))
    records = [row for row in records if int(row['eval_after_30s'])]
    if any(not math.isfinite(float(r['error_s'])) for r in records):
        raise RuntimeError('Invalid D8 polarization scoring label')
    routes = sorted({row['route'] for row in records})
    if len(routes) < 3:
        raise RuntimeError('D8 requires 3 heldout routes')
    phase = phase_evidence(args.phase_evidence)
    variants = [name for name in QUALITY_FEATURES if name!='Q4_COMPLEX_PHASE']
    if phase:
        # Fail before output publication; Q4 is all-or-nothing, not selected by
        # ground-truth error/quality on held-out samples.
        records = [validated_phase_row(row,phase) for row in records]
        variants.append('Q4_COMPLEX_PHASE')
    folds = {}; predictions = []; summary = []; strata = []
    for holdout in routes:
        for channel in ('los','full'):
            test = [r for r in records if r['route']==holdout and r['channel']==channel]
            candidates = [r for r in records if r['route']!=holdout and r['channel']==channel]
            train, dropped = split_exclude_overlap(candidates,test,args.xy_buffer_m)
            unique = {}
            for r in train:
                unique.setdefault((r['case'],r['pose_id']),r)
            train = list(unique.values())
            if len(train) < args.min_train_rows or not test:
                raise RuntimeError('Insufficient independent-position D8 rows: '+holdout+'/'+channel)
            by_model = {}
            for range_model in args.range_models:
                if channel=='los' and range_model!='B_OLD':
                    continue  # E1 is FULL RF only. No invented LoS label.
                model_train, model_test = train, test
                e1_test_overlap_dropped = 0
                if range_model == 'E1_FULL_LORO':
                    # Original E1 coefficients saw all non-outer routes,
                    # including cross-route shared XY. Those sites cannot
                    # count as held-out E1 evaluation. Match its original
                    # no-shared-site scoring boundary before relabelling.
                    model_test, e1_test_overlap_dropped = split_exclude_overlap(
                        test, candidates, args.xy_buffer_m)
                    if not model_test:
                        raise RuntimeError('No spatially unseen E1 held-out rows: '+holdout)
                    model_train = outer_e1_labels(train, holdout, frozen_e1)
                    model_test = outer_e1_labels(model_test, holdout, frozen_e1)
                range_target = RANGE_LABELS[range_model]
                all_rows = model_train+model_test
                if any(r.get(range_target) in (None,'') or not math.isfinite(float(r[range_target]))
                       for r in all_rows):
                    raise RuntimeError('Missing correction-specific D7 label: '+range_target)
                models = {}; saved_scores = {}
                for variant in variants:
                    model = {target: fit_ridge(model_train,target,variant,args.ridge,range_model)
                             for target in ('s','r')}
                    models[variant] = model
                    saved_scores[variant] = {}
                    for target, params in model.items():
                        score = score_model(model_test,params)
                        saved_scores[variant][target]=score
                        summary.append({'heldout_route':holdout,'channel':channel,
                            'range_model':range_model,'range_target':range_target,
                            'variant':variant,'target':target,
                            'n_test':len(model_test),'n_train_unique':len(model_train),
                            'xy_overlap_train_dropped':dropped,
                            'e1_shared_xy_test_dropped':e1_test_overlap_dropped,
                            **score})
                        for row in model_test:
                            predictions.append({'case':row['case'],'channel':channel,
                               'route':holdout,'sample_index':row['sample_index'],
                               'range_model':range_model,'target':target,'variant':variant,
                               'predicted_bias':predict_mean(row,params),
                               'predicted_residual_variance':predict_variance(row,params),
                               'observed_error_oracle_only':float(row[params['target_label']])})
                gates = {target: calibration_gate(saved_scores['Q0_FIXED'][target],
                                  saved_scores['Q3_CIR_POL'][target],
                                  args.gate_calibration_min,args.gate_calibration_max,
                                  args.gate_min_nll_gain,
                                  q1=saved_scores['Q1_S_ONLY'][target])
                         for target in ('s','r')}
                passed = all(g['status']=='EXPLORATORY_HELDOUT_GATE_PASS' for g in gates.values())
                # Same-time s/r centered residual covariance, TRAIN ROUTES ONLY.
                # Not applied to EKF until an independent R_sr calibration.
                q3=models['Q3_CIR_POL']
                residual_s=np.asarray([float(r['error_s'])-predict_mean(r,q3['s'])
                                       for r in model_train])
                residual_r=np.asarray([float(r[range_target])-predict_mean(r,q3['r'])
                                       for r in model_train])
                train_cov_sr=float(np.mean((residual_s-residual_s.mean())*
                                           (residual_r-residual_r.mean())))
                if np.std(residual_s)>0 and np.std(residual_r)>0:
                    train_rho_sr=float(np.corrcoef(residual_s,residual_r)[0,1])
                else:
                    train_rho_sr=0.
                # These are exploratory scene-internal gates, not proof of
                # independent-scene calibration.
                by_model[range_model] = {'range_model':range_model,
                    'range_target':range_target,'models':models,
                    'e1_label_outer_excluded_route':holdout if range_model=='E1_FULL_LORO' else None,
                    'e1_outer_coefficients_sha256':hashlib.sha256(json.dumps(
                        frozen_e1['loro_fold_params'][holdout]['E1'],
                        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
                        if range_model=='E1_FULL_LORO' else None,
                    'e1_shared_xy_test_dropped':e1_test_overlap_dropped,
                    'q3_heldout_gate':{'status':'EXPLORATORY_GATE_PASS' if passed
                                      else 'EXPLORATORY_GATE_FAIL','targets':gates},
                    'conditional_rsr_unvalidated':True,
                    'train_centered_residual_cov_sr':train_cov_sr,
                    'train_centered_residual_correlation_sr':train_rho_sr,
                    'n_train_unique':len(train)}
                # Offline nuisance-variable stratification: geometry features
                # are scoring ONLY, never added to online model features.
                for distance_bin, mask in [('lt5m',lambda d:d<5),
                                           ('5to10m',lambda d:5<=d<10),
                                           ('ge10m',lambda d:d>=10)]:
                    segment=[r for r in model_test if mask(float(r['true_range_m']))]
                    if not segment:continue
                    for target, params in models['Q3_CIR_POL'].items():
                        strata.append({'heldout_route':holdout,'channel':channel,
                                       'range_model':range_model,'distance_bin':distance_bin,
                                       'target':target,**score_model(segment,params)})
            folds.setdefault(holdout,{})[channel]={
                'heldout_route':holdout,
                'train_routes':sorted({r['route'] for r in train}),
                'n_xy_overlap_removed':dropped,
                'range_models':by_model}
    out = make_out(args.out)
    summ = out/'D8_CIR_QUALITY_VALIDATION.csv'
    pred = out/'D8_HELDOUT_PREDICTIONS.csv'
    strata_file = out/'D8_DISTANCE_STRATIFIED_VALIDATION.csv'
    fold_path = out/'D8_FOLD_MODELS.json'
    write_csv(summ,summary);write_csv(pred,predictions);write_csv(strata_file,strata)
    contract = {'schema':'D8_ROUTE_HELDOUT_CORRECTION_SPECIFIC_V2',
                'd7_input_sha256':hashes,
                'online_features':list(NUMERIC_FEATURES),
                'range_targets':RANGE_LABELS,
                'models_trained_for':args.range_models,
                'separate_centered_bias_and_variance':True,
                'train_never_uses_heldout_truth':True,
                'e1_outer_fold_contract': 'SINGLE_OUTER_ROUTE_EXCLUDED_FOLD_FOR_ALL_LABELS',
                'e1_frozen_model_sha256':file_sha(P3_MODEL),
                'e1_model_family_selection_nested':False,
                'phase_q4':{'status':'Q4_EXPLORATORY_ONLY_WITH_CALIBRATION' if phase
                            else 'NOT_RUN_INDEPENDENT_PHASE_SNR_EVIDENCE_MISSING',
                            'evidence':phase},
                'independent_scene_validation':False,
                'scientific_PASS':False,
                'folds':folds}
    atomic_json(fold_path,contract)
    finish(out,'D8',vars(args),[summ,pred,strata_file,fold_path],caveats=[
        'Range target and conditional residual scale tied to identical B_OLD or E1 correction',
        'Train-only residual mean and residual second moment remain unconfirmed noise model',
        'LORO in same frozen corridor is not independent-scene confirmation',
        'E1 labels use one outer-route-excluded coefficient fold for train and test; shared-XY E1 test sites excluded',
        'Frozen E1 family was selected using prior scene-wide LORO; selection is not nested; train E1 residuals remain in-sample',
        'RX phase Q4 is disabled without independent calibrated phase AND noise floor',
        'Q3 heldout gates are exploratory, not scientific_PASS'])
    print('D8_EXPLORATORY_DONE',str(out))

if __name__=='__main__':
    main()
