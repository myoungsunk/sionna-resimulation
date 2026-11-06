"""Executable E1-02..E5 study operations; all data access is caller-authorized.

Stage functions keep full per-packet evidence and negative cases. They neither
silently tune parameters nor promote a numerical check to independent science.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from pathlib import Path
import math
import numpy as np
from .contracts import ContractError, Policy, STEP_M, digest, finite
from .engine import ARMS, GATE, ArmProcessor, OnlineCase, open_loop, run_arms
from .evaluation import (confidence_report, detection_curve, episodes, error_stats,
                         paired_seed_bootstrap, selection_summary, trajectory_metrics)
from .numerics import (apply_residual_model, cir_from_spectrum, factorial, fit_residual_model,
                       inject_noise, measurement, perturb_prior, residual_bin,
                       residual_decomposition, same_prior_factorial, stress_grid, update)
from .runtime import DeadlineRunner, arrivals
from .selection import policy_grid


class Evaluator:
    def __init__(self, case: OnlineCase, clean_H: np.ndarray, truth: np.ndarray, adapter, *,
                 detection_only=False, allow_partial_truth=False):
        n = len(case.t)
        if clean_H.shape != (n, 257, 2) or not np.iscomplexobj(clean_H) or not np.isfinite(clean_H).all():
            raise ContractError("INVALID_EVALUATOR_LOS")
        self.case, self.clean_H, self.adapter = case, clean_H, adapter
        self.detection_only = detection_only
        columns = 3 if (detection_only or allow_partial_truth) and truth.shape == (n, 3) else 4
        self.truth = finite(truth, (n, columns), "EVALUATOR_TRUTH")

    def label(self, online: list[dict], *, detect_only=False) -> list[dict]:
        if self.detection_only and not detect_only:
            raise ContractError('DETECTION_EVALUATOR_CANNOT_EVALUATE_CORRECTION')
        rows = []
        for item in online:
            k, e, d = item["k"], item["evidence"], item["decision"]
            direct = cir_from_spectrum(self.clean_H[k])
            ref = self.adapter.evidence(direct, 0.)
            reference = measurement(direct, ref.raw_tap, ref.raw_tap) if ref.valid else None
            obs = item["observation"]
            raw = obs["F00"] if e.valid else None
            selected = raw if detect_only else obs["F11"]
            chosen = e.raw_tap if detect_only else d.selected_tap
            row = dict(case_id=self.case.case_id, pose_id=item["pose_id"], t=item["t"],
                       raw_valid=e.valid, reference_valid=ref.valid and reference is not None,
                       raw_tap=e.raw_tap, selected_tap=chosen, reference_tap=ref.raw_tap,
                       wrong_score=d.wrong_score, confidence_score=d.confidence_score,
                       flag=None if d.wrong_score is None else bool(d.wrong_score >= self._wrong_cut),
                       reason=d.reason, mode=d.mode, margin=d.margin, group_margin=d.group_margin,
                       pol_ambiguity=d.pol_ambiguity, candidate_scores=list(d.scores),
                       reference_in_usable_pool=bool(e.valid and not e.overflow and ref.valid and
                           any(c.tap == ref.raw_tap and c.supported for c in e.candidates)),
                       pool_hash=e.pool_hash, history=item["history"],
                       prior_support=item["prior_support"], motion_support=item["motion_support"])
            if detect_only and 'prior_integrity' in item:
                # Carry the protected online output through evaluation unchanged.
                # Diagnostic costs are never promoted to the flag/score above.
                for key in ('prior_integrity', 'effective_mode', 'diagnostic_only_scores',
                            'diagnostic_only_prior_scores', 'diagnostic_status'):
                    row[key] = item[key]
            for name, value in (("raw", raw), ("selected", selected)):
                valid = reference is not None and value is not None and row["reference_valid"]
                row[name+"_range_error"] = float(value[0]-reference[0]) if valid else None
                row[name+"_s_error"] = float(value[1]-reference[1]) if valid else None
            rows.append(row)
        return rows

    _wrong_cut = 2.


def labelled(case, ev, adapter, policy, mode, *, detect_only=False, **kwargs):
    if detect_only:
        kwargs.setdefault("teacher_forced", True)
    online = open_loop(case, adapter, policy, mode, **kwargs)
    ev._wrong_cut = policy.wrong_cut
    return ev.label(online, detect_only=detect_only), online


def static_cir_control(case, ev, adapter, policy):
    from .selection import select
    online=[]
    for k in range(len(case.t)):
        cir=cir_from_spectrum(case.Hrf[k]); e=adapter.evidence(cir,case.noise_variance)
        d=select(e,"C",policy)
        online.append(dict(k=k,pose_id=int(case.pose_id[k]),t=float(case.t[k]),evidence=e,decision=d,
                           history={},prior_support=None,motion_support=None,
                           observation=factorial(cir,e.raw_tap,d.selected_tap)))
    ev._wrong_cut=policy.wrong_cut
    rows=ev.label(online,detect_only=True)
    return dict(rows=rows,summary=selection_summary(rows),
                scope="STATIC_CIR_ONLY_NO_TEMPORAL_PRIOR_NO_ORACLE_STATE",
                static_conditions_not_independent_environments=True)


def e1_detection(case, ev, adapter, policy, *, vab_detection=False):
    if vab_detection:
        from .detection import detection_loop, HISTORY_RECIPE
        outputs = {}
        for mode in (('C',) if case.corpus == 'static_g4' else ('C', 'P', 'M', 'PM')):
            online = detection_loop(case, adapter, policy, mode)
            ev._wrong_cut = policy.wrong_cut
            rows = ev.label(online, detect_only=True)
            outputs[mode] = dict(rows=rows, summary=selection_summary(rows),
                curve=detection_curve(rows, split=case.split), episodes=episodes(rows),
                history_recipe=HISTORY_RECIPE, interpretation='FLAGS_ONLY_UNCALIBRATED_NO_REPLACEMENT')
        return outputs
    if case.corpus == "static_g4":
        return {"C": static_cir_control(case,ev,adapter,policy),
                "P_M_PM": {"status":"NOT_APPLICABLE_NO_CAUSAL_STATIC_PRIOR"}}
    outputs = {}
    for mode in ("C", "P", "M", "PM"):
        rows, _ = labelled(case, ev, adapter, policy, mode, detect_only=True)
        curve = detection_curve(rows, split=case.split)
        outputs[mode] = dict(rows=rows, summary=selection_summary(rows), curve=curve,
                             episodes=episodes(rows), interpretation="FLAGS_ONLY_NO_FP_REPLACEMENT")
    return outputs


def e2_select(case, ev, adapter, policy):
    if case.corpus == "static_g4":
        raise ContractError("E2_TIME_CAUSAL_CANARY_REQUIRES_DYNAMIC_CASE")
    result = {}
    for mode in ("B0", "B37", "C", "P", "M", "PM", "PM-FORCE", "NN-HARD"):
        rows, _ = labelled(case, ev, adapter, policy, mode)
        result[mode] = dict(rows=rows, summary=selection_summary(rows), episodes=episodes(rows))
    # The oracle is evaluated separately, AFTER all online policies. It cannot
    # insert reference candidates or influence any prior/history/state.
    oracle = []
    for k, row in enumerate(result["B0"]["rows"]):
        r = dict(row, mode="O-REF_EVALUATOR_ONLY", selected_tap=row["reference_tap"])
        z = measurement(cir_from_spectrum(case.Hrf[k]), row["reference_tap"], row["reference_tap"])
        ref = measurement(cir_from_spectrum(ev.clean_H[k]), row["reference_tap"], row["reference_tap"])
        valid = r["reference_valid"] and z is not None and ref is not None
        r["selected_range_error"] = float(z[0]-ref[0]) if valid else None
        r["selected_s_error"] = float(z[1]-ref[1]) if valid else None
        oracle.append(r)
    result["O-REF_EVALUATOR_ONLY"] = dict(rows=oracle, summary=selection_summary(oracle),
                                          interpretation="MECHANISM_CONTROL_NOT_UNIVERSAL_OPTIMUM")
    return result


def e2_history(case, ev, adapter, policy):
    result = {}
    for teacher in (False, True):
        rows, _ = labelled(case, ev, adapter, policy, "PM", teacher_forced=teacher)
        wrong_runs, run = [], 0
        for r in rows:
            bad = r["raw_valid"] and r["reference_valid"] and r["selected_tap"] != r["reference_tap"]
            if bad:
                run += 1
            elif run:
                wrong_runs.append(run)
                run = 0
        if run:
            wrong_runs.append(run)
        result["teacher_forced" if teacher else "self_updated"] = dict(rows=rows, summary=selection_summary(rows),
                 longest_wrong_run=max(wrong_runs, default=0), wrong_run_lengths=wrong_runs)
    return result


def e2_confidence(case, ev, adapter, policy):
    rows, _ = labelled(case, ev, adapter, policy, "PM")
    return dict(rows=rows, bins=confidence_report(rows), summary=selection_summary(rows),
                probability_calibrated=False, calibration_fit_performed=False)


def stress(case, ev, adapter, policy, *, detect_only=False, noise_namespace="FP_SC_NEW_RF_NOISE_V1"):
    if case.corpus == "static_g4":
        return static_cir_control(case,ev,adapter,policy)
    results = []
    for setting in stress_grid(case.noise_variance):
        kind, value = setting["kind"], setting["value"]
        modified, kwargs = case, {}
        if kind in {"identity", "radial_m", "tangential_m", "yaw_deg", "P_radial_scale", "P_heading_scale"}:
            kwargs["prior_transform"] = lambda x, P, k=kind, v=value: perturb_prior(x, P, adapter.anchor, k, v)
        elif kind == "missing_ticks":
            begin = max(1, len(case.t)//3)
            kwargs["unavailable"] = set(range(begin, min(begin+int(value), len(case.t))))
        elif kind == "wrong_history_taps":
            def corrupt(history, k, shift=value):
                if k == max(1, len(case.t)//3) and history.detector_m is not None:
                    history.detector_m += shift*STEP_M
            kwargs["history_fault"] = corrupt
        elif kind == "snr_delta_db":
            variance = case.noise_variance*10**(-value/10.)
            if case.clean_Hrf is None:
                results.append(dict(setting=setting, status="BLOCKED_MISSING_CLEAN_SOURCE_FOR_NEW_NOISE"))
                continue
            noisy = [inject_noise(h, variance=variance, namespace=noise_namespace,
                                  packet_id=case.sample_id(k), seed=case.sensor_seed)
                     for k, h in enumerate(case.clean_Hrf)]
            H = np.stack([r[0] for r in noisy])
            z = []
            for h in H:
                cir = cir_from_spectrum(h)
                evidence = adapter.evidence(cir, variance)
                m = measurement(cir, evidence.raw_tap, evidence.raw_tap)
                z.append(np.zeros(2) if m is None else m)
            modified = replace(case, Hrf=H, z=np.asarray(z), noise_variance=variance)
            setting = dict(setting, noise_hashes=[r[1] for r in noisy],
                           provenance="NEW_NOISE_REALIZATION_NOT_HISTORICAL_NOISY_REPLAY")
        elif kind == "null_cir":
            modified = replace(case, Hrf=np.zeros_like(case.Hrf), z=np.zeros_like(case.z))
        rows, _ = labelled(modified, ev, adapter, policy, "PM", detect_only=detect_only, **kwargs)
        results.append(dict(setting=setting, rows=rows, summary=selection_summary(rows)))
    return dict(one_factor_at_a_time=results,
                snr_status="NOT_TESTED_NO_FINITE_SNR_BASELINE" if case.noise_variance == 0 else "NEW_NOISE_REALIZATIONS",
                geometry_changed=False, new_RT_calls=0)


def e3_observations(case, ev, adapter, policy, *, decomposition=False):
    _, online = labelled(case, ev, adapter, policy, "PM")
    rows = []
    for item in online:
        k, raw, selected = item["k"], item["evidence"].raw_tap, item["decision"].selected_tap
        row = dict(k=k, pose_id=int(case.pose_id[k]), t=float(case.t[k]), observations=item["observation"],
                   selected_tap=selected, raw_tap=raw)
        if decomposition:
            direct = cir_from_spectrum(ev.clean_H[k])
            ref = adapter.evidence(direct, 0.)
            row["decomposition"] = (residual_decomposition(cir_from_spectrum(case.Hrf[k]), direct,
                                                          raw, selected, ref.raw_tap)
                if item["evidence"].valid and ref.valid else dict(valid=False, reason="UNKNOWN_REFERENCE"))
        rows.append(row)
    return dict(rows=rows, scope="MEASUREMENT_FACTORIAL_NO_STATE_FEEDBACK")


def calibration_records(case, ev, adapter, policy):
    if case.split not in {"TRAIN", "CAL"}:
        raise ContractError("CALIBRATION_REQUIRES_TRAIN_OR_CAL_CASE")
    _, online = labelled(case, ev, adapter, policy, "PM")
    records = []
    for item in online:
        k = item["k"]
        h, _ = adapter.observe(ev.truth[k])  # evaluator-only calibration, never selector.
        changed = item["decision"].selected_tap != item["evidence"].raw_tap
        for extractor in ("F00", "F01", "F11"):
            z = item["observation"][extractor]
            if z is None:
                continue
            b = residual_bin(changed and extractor != "F00", item["decision"].confidence_score)
            records.append(dict(sample_id=case.sample_id(k), route=case.route, bias=case.bias,
                                channel=case.channel, split=case.split, extractor=extractor, bin=b,
                                residual=(z-h-case.muMB[k]).tolist(), t=float(case.t[k]),
                                noise_variance=float(case.noise_variance), environment_id=case.environment_id))
    return records


def fit_models(records: list[dict], target_case: OnlineCase, policy: Policy, min_samples=20):
    models = {}
    for extractor in ("F00", "F01", "F11"):
        fit = [r for r in records if r["route"] != target_case.route and r["extractor"] == extractor and
               r["bias"] == target_case.bias and r["channel"] == target_case.channel and
               r["noise_variance"] == target_case.noise_variance and r["split"] == "TRAIN"]
        if not fit or any(r["split"] not in {"TRAIN", "CAL"} for r in fit):
            raise ContractError("NO_VALID_ROUTE_HELDOUT_CALIBRATION")
        models[extractor] = fit_residual_model(np.asarray([r["residual"] for r in fit]),
                        [r["bin"] for r in fit], [r["sample_id"] for r in fit], [r["route"] for r in fit],
                        target_route=target_case.route, split="TRAIN", extractor=extractor,
                        policy_sha=policy.sha, min_samples=min_samples, domain=target_case.measurement_domain())
    return models


def e3_one_step(case, ev, adapter, policy, models):
    if case.baseline_trace is None:
        raise ContractError("MISSING_ARCHIVED_ONE_STEP_TRACE")
    _, online = labelled(case, ev, adapter, policy, "PM")
    rows = []
    for item in online:
        k = item["k"]
        xp, pp = case.prior[k], case.Pprior[k]
        h, H = adapter.observe(xp)
        observations = item["observation"]
        if any(z is None for z in observations.values()):
            rows.append(dict(k=k, valid=False, reason="INVALID_MEASUREMENT"))
            continue
        archived = case.baseline_trace
        for key, actual in (("h", h), ("H", H), ("prior", xp), ("Pprior", pp)):
            expected = archived[key][k]
            if np.max(abs(actual-expected)/np.maximum(1., abs(expected))) > 1e-10:
                raise ContractError("ARCHIVED_ONE_STEP_CONTEXT_MISMATCH:"+key)
        R = archived["Reff"][k]
        fixed_mask = bool(archived["mask"][k])
        fixed = same_prior_factorial(xp, pp, h, H, observations, case.muMB[k], R, fixed_mask)
        matched = {}
        for extractor in ("F00", "F01", "F11"):
            changed = item["decision"].selected_tap != item["evidence"].raw_tap and extractor != "F00"
            mu, rr = apply_residual_model(models[extractor], target_route=case.route, extractor=extractor,
                          policy_sha=policy.sha, sample_id=case.sample_id(k),
                          bin_name=residual_bin(changed, item["decision"].confidence_score), original_mu=case.muMB[k],
                          domain=case.measurement_domain())
            unmasked = update(xp, pp, h, H, observations[extractor], mu, rr)
            matched[extractor] = dict(fixed_mask=update(xp, pp, h, H, observations[extractor], mu, rr, permitted=fixed_mask),
                                      own_gate=update(xp, pp, h, H, observations[extractor], mu, rr,
                                                      permitted=unmasked["nis"] <= GATE))
        rows.append(dict(k=k, valid=True, fixed=fixed, matched=matched,
                         mask_scope="ARCHIVED_W0_PRIOR_H_H_MU_REFF_AND_BASE_SHADOW_MASK"))
    return dict(rows=rows, duplicate_information=False, state_dependent_mean="FIXED_CONTEXT_ONLY")


def e4_closed_loop(case, ev, adapter, policy, models):
    traces = run_arms(case, adapter, policy, models)
    metrics = {}
    for arm, trace in traces.items():
        metrics[arm] = trajectory_metrics(np.asarray([r["x"] for r in trace]),
                                         np.asarray([r["P"] for r in trace]), ev.truth, case.t,
                                         anchor=adapter.anchor)
        metrics[arm]["update_count"] = sum(r["updated"] for r in trace)
        metrics[arm]["dropout_count"] = sum(r["status"] == "HOLD_NO_MEASUREMENT" for r in trace)
        metrics[arm]["fallback_count"] = sum(r["decision"]["action"] == "KEEP_ORIGINAL" for r in trace)
    return dict(traces=traces, metrics=metrics, original_noop_parity=True,
                scientific_gate="REQUIRES_STRATIFIED_PAIRED_AGGREGATION", same_RF_conditional=True)


def e5_runtime(case, adapter, policy, models, *, hardware_id, sink, faults=False):
    result = {}
    settings = ("NONE", "DROP_2", "DROP_5", "DROP_10", "DUPLICATE", "REORDER", "DELAY", "NULL_CIR", "STALE_HISTORY") if faults else ("NONE",)
    for arm in ("A", "E", "F"):
        for fault in settings:
            active_case=case
            if fault == "NULL_CIR":
                H=case.Hrf.copy(); z=case.z.copy(); pivot=min(max(len(case.t)//3,1),len(case.t)-1)
                H[pivot]=0.; z[pivot]=0.
                active_case=replace(case,Hrf=H,z=z)
            processor = ArmProcessor(active_case, adapter, policy, arm, models)
            result[f"{arm}:{fault}"] = DeadlineRunner(processor, hardware_id=hardware_id, sink=sink).run(arrivals(active_case, fault))
    return result


def select_policy_from_calibration(candidate_results: dict[str, list[dict]], *, split: str,
                                   expected_strata: set[str]) -> dict:
    """One common winner, maximum 27; all protected strata must be present.

    No safe do-nothing policy may win. Thresholds are frozen before CAL. This
    selection does not turn conditional/descriptive rates into safety bounds.
    """
    if split != "CAL" or not 0 < len(candidate_results) <= 27 or not expected_strata:
        raise ContractError("INVALID_POLICY_SELECTION_SCOPE")
    eligible = []
    for policy_sha, grouped in candidate_results.items():
        if len(policy_sha) != 64 or {r["stratum"] for r in grouped} != expected_strata or len(grouped) != len(expected_strata):
            raise ContractError("POLICY_STRATA_INCOMPLETE_OR_DUPLICATE")
        summaries=[r["summary"] for r in grouped]
        normal=sum(r["normal"] for r in summaries); wrong=sum(r["wrong"] for r in summaries)
        changed=sum(r["corrected"] for r in summaries)
        high=sum(r["high_confidence_corrected"] for r in summaries)
        high_correct=sum((r["high_confidence_precision"] or 0.)*r["high_confidence_corrected"] for r in summaries)
        protect=all(not r["normal"] or r["false_correction_rate"] <= .01 for r in summaries)
        rescue=all(not r["wrong"] or r["rescue_rate"] >= .30 for r in summaries)
        # A correctly untouched LoS stratum need not invent errors to be rescued.
        if normal and wrong and changed and high and protect and rescue and high_correct/high >= .95:
            eligible.append((float(np.mean([r["rescue_rate"] for r in summaries if r["wrong"]])),policy_sha))
    if not eligible:
        return dict(status="NO_ELIGIBLE_COMMON_POLICY", selected_policy_sha=None, E4_GO=False)
    score, winner = sorted(eligible, key=lambda x: (-x[0], x[1]))[0]
    return dict(status="CAL_SELECTED_PENDING_FROZEN_CONFIRMATION", selected_policy_sha=winner,
                macro_rescue=score, E4_GO=False, population_safety_proven=False)


def validate_trajectory_grid(cases: list[OnlineCase], stage: str) -> None:
    if stage not in {"E4-01", "E4-02"}:
        return
    from itertools import product
    seeds = range(10) if stage == "E4-01" else range(40, 60)
    expected = set(product(("R2", "R4", "R5"), ("B0", "L2"), ("Full", "Native_LoS"), seeds))
    actual = [(c.route, c.bias, c.channel, c.sensor_seed) for c in cases]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ContractError("TRAJECTORY_GRID_MISSING_DUPLICATE_OR_EXTRA")
    split = {"TRAIN", "EXPOSED_DEV"} if stage == "E4-01" else {"SEALED"}
    if any(c.split not in split or c.corpus != "dynamic" or abs(float(c.t[0])) > 1e-12 for c in cases):
        raise ContractError("TRAJECTORY_GRID_SPLIT_MISMATCH")
