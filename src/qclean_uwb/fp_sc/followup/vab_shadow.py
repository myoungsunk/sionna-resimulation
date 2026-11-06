"""Code-only VAB shadow pipeline: selection -> observation -> same-prior EKF.

Purpose: inspect proposed FP decisions without switching a production selector or
inventing a VALID prior. Results are counterfactual diagnostics, never a live FP
correction, E1-02/E2 scientific acceptance, or an authenticated integrity provider.
Evaluator references and ground truth must stay in separate, later functions.
"""
from __future__ import annotations

from dataclasses import asdict
import math
import numpy as np

from .contracts import ContractError, Policy, STEP_M, Support, jsonable
from .detection import binding_for
from .integrity import assess_prior
from .numerics import (cir_from_spectrum, factorial, raw_detection,
                       measurement, same_prior_factorial)
from .selection import (decide_prepared_candidate_set, native_support,
                        prepare_candidate_set)

MODES = ("C", "P", "M", "PM")
SHADOW_SCOPE = "OFFLINE_COUNTERFACTUAL_NO_VALID_NO_PRODUCTION_WRITE"


def _check_adapter(adapter):
    revision = getattr(adapter, "revision_evidence", None)
    if (revision is None or getattr(revision, "arm", None) != "VAB" or
            getattr(revision, "mode", None) != "TWO_PORT_UNION"):
        raise ContractError("SHADOW_REQUIRES_SHA_LOCKED_VAB_TWO_PORT_ADAPTER")


def _raw_motion_support(previous, now, offset, ds, policy):
    """Untrusted adjacent raw-FP hypothesis, NOT a trusted-history provider.

    Time-joined previous packet only. The full motion radius is a diagnostic
    sensitivity envelope, not a statistically calibrated accuracy guarantee.
    """
    if previous is None:
        return None
    age = float(now - previous["t"])
    if age <= 0 or age > policy.history_max_age_s:
        return None
    if not np.isfinite(ds) or abs(float(ds)) > policy.vmax_mps * age + policy.motion_slack_m:
        return None
    radius = max(policy.vmax_mps * age, abs(float(ds))) + policy.motion_slack_m + policy.mapping_slack_m
    center = previous["tap"] * STEP_M + offset - previous["offset"]
    return Support(float(center-radius), float(center+radius),
                   policy.mapping_slack_m, "UNTRUSTED_PREVIOUS_RAW_FP_DIAGNOSTIC_ONLY")


def shadow_decision(e, mode, policy, *, prior=None, motion=None):
    """Evaluate EXACT current scoring/selection logic on VAB candidate sets.

    Reuses the same prepare_candidate_set and pure decide_prepared_candidate_set
    called by select(). It does NOT invoke select() (which correctly blocks VAB
    operational use), does not emit a live Decision and never validates a prior.
    """
    if mode not in MODES:
        raise ContractError("SHADOW_NO_FORCED_OR_PRODUCTION_MODE")
    binding = binding_for(e, policy)   # checks VAB bridge/recipe/Policy SHA
    prepared = prepare_candidate_set(e, mode, policy, prior=prior,
                                     motion=motion, binding=binding)
    decision = decide_prepared_candidate_set(e, mode, policy, prepared)
    return dict(scope=SHADOW_SCOPE, mode=mode, counterfactual=True,
                valid_provider=False, decision=asdict(decision),
                candidate_set_sha256=prepared.sha,
                held=prepared.status != "BUILT",
                prepared_status=prepared.status)


def shadow_select_case(case, adapter, policy: Policy, *, modes=MODES):
    """S1: propose taps on actual Full/LoS CFR, NO GT or evaluator access.

    Uses frozen premeasurement archived prior when P/M diagnostic scores are
    requested. M uses only the immediately preceding RAW detector tap and
    timestamp; it is not persisted as a trusted or corrected FP.
    """
    _check_adapter(adapter)
    if case.corpus != "dynamic" or tuple(modes) != MODES:
        raise ContractError("SHADOW_S1_DYNAMIC_FIXED_MODES_ONLY")
    if np.any(np.diff(case.t) <= 0):
        raise ContractError("NONMONOTONIC_SHADOW_TIME")
    rows = []
    previous = None
    for k in range(len(case.t)):
        cir = cir_from_spectrum(case.Hrf[k])
        e = adapter.evidence(cir, case.noise_variance)
        integrity = assess_prior(case.prior[k], case.Pprior[k], float(case.t[k]),
                                 None if k == 0 else float(case.t[k-1]))
        # UNKNOWN does NOT become VALID; this is a clearly-labeled offline
        # diagnostic for deciding whether the provider is even worth building.
        p, offset = None, None
        if integrity.state == "UNKNOWN":
            p, offset = native_support(case.prior[k], case.Pprior[k], adapter.native, policy)
        m = (_raw_motion_support(previous, case.t[k], offset,
                                 case.ds[k], policy)
             if offset is not None else None)
        for mode in modes:
            result = shadow_decision(e, mode, policy, prior=p, motion=m)
            choice = result["decision"]["selected_tap"]
            obs = factorial(cir, e.raw_tap, choice)
            rows.append(dict(case_id=case.case_id, k=k, t=float(case.t[k]),
                pose_id=int(case.pose_id[k]), mode=mode, scope=SHADOW_SCOPE,
                integrity=asdict(integrity), provider_allowed=False,
                raw_tap=e.raw_tap, hypothetical_selected_tap=choice,
                decision=result["decision"], candidate_set_sha256=result["candidate_set_sha256"],
                prepared_status=result["prepared_status"],
                p_interval=None if p is None else asdict(p),
                m_interval=None if m is None else asdict(m),
                observations={name: None if v is None else v.tolist() for name, v in obs.items()}))
        previous = (dict(t=float(case.t[k]), tap=int(e.raw_tap), offset=float(offset))
                    if e.valid and e.raw_tap is not None and offset is not None else None)
    return rows


def compare_shadow_observations(case, online_rows, reference_H, *, modes=MODES):
    """S2: AFTER S1 is stored/locked, evaluate ref against F00/F01/F11.

    The clean Native-LoS reference is never passed to S1's selector. This is
    reference-tap evaluation, not a claim of an optimal Full-path estimator.
    """
    ref = np.asarray(reference_H)
    if ref.shape != case.Hrf.shape or not np.iscomplexobj(ref):
        raise ContractError("SHADOW_S2_REFERENCE_SHAPE")
    expected = {(k,mode) for k in range(len(case.t)) for mode in modes}
    got = {(int(r["k"]),r["mode"]) for r in online_rows}
    if len(online_rows) != len(expected) or got != expected:
        raise ContractError("SHADOW_S2_INCOMPLETE_S1_ROWS")
    result = []
    for row in online_rows:
        if row.get("scope") != SHADOW_SCOPE or row.get("provider_allowed") is not False:
            raise ContractError("SHADOW_S2_WRONG_PROVENANCE")
        k = int(row["k"])
        ref_cir = cir_from_spectrum(ref[k])
        ref_tap, _, ref_obs = raw_detection(ref_cir)
        observations = row["observations"]
        vals = {name: observations.get(name) for name in ("F00", "F01", "F11")}
        errors = {name: None if value is None or ref_obs is None else
                  (np.asarray(value, dtype=float)-ref_obs).tolist()
                  for name,value in vals.items()}
        raw = row["raw_tap"]; selected = row["hypothetical_selected_tap"]
        result.append(dict(case_id=case.case_id, k=k, mode=row["mode"],
            raw_tap=raw, proposed_tap=selected, reference_tap=ref_tap,
            reference_valid=ref_obs is not None,
            raw_correct=raw == ref_tap if ref_tap is not None else None,
            proposed_correct=selected == ref_tap if ref_tap is not None else None,
            changed=(raw != selected), errors=errors,
            scope="EVALUATOR_POSTHOC_ONLY_NOT_OPERATED"))
    return result


def same_prior_shadow_one_step(case, online_rows, adapter, *, mode="PM"):
    """S3: one update per arm from the SAME archived premeasurement prior.

    No closed-loop, model refit, ground truth, new mean or R, production output,
    or dynamically self-updated FP history. GT bias need not be fabricated.
    """
    if case.baseline_trace is None:
        raise ContractError("SHADOW_S3_ARCHIVED_CONTEXT_MISSING")
    unique = {}
    for row in online_rows:
        if row["mode"] != mode:
            continue
        k=int(row["k"])
        if k in unique:
            raise ContractError("SHADOW_S3_DUPLICATE_PACKET")
        if row.get("scope") != SHADOW_SCOPE or row.get("provider_allowed") is not False:
            raise ContractError("SHADOW_S3_WRONG_SOURCE_SCOPE")
        unique[k]=row
    if len(unique) != len(case.t):
        raise ContractError("SHADOW_S3_INCOMPLETE_PACKET_SERIES")
    trace=case.baseline_trace
    result=[]
    for k in range(len(case.t)):
        xp,pp=case.prior[k].copy(),case.Pprior[k].copy()
        h,H=adapter.observe(xp)
        for field,a in (("h",h),("H",H),("prior",xp),("Pprior",pp)):
            stored=trace[field][k]
            if np.max(np.abs(a-stored)/np.maximum(1.,np.abs(stored))) > 1e-10:
                raise ContractError("SHADOW_S3_BASELINE_CONTEXT_MISMATCH:"+field)
        obs={name: None if value is None else np.asarray(value,dtype=float)
             for name,value in unique[k]["observations"].items()}
        step=same_prior_factorial(xp,pp,h,H,obs,case.muMB[k],
                                  trace["Reff"][k],bool(trace["mask"][k]))
        result.append(dict(k=k,case_id=case.case_id,mode=mode,
                           t=float(case.t[k]), pose_id=int(case.pose_id[k]),
                           scope="FIXED_PRIOR_ONE_STEP_DIAGNOSTIC",
                           valid=step["valid"],
                           reason=step.get("reason"),
                           context=jsonable(dict(prior=xp, Pprior=pp, h=h, H=H,
                               mu=case.muMB[k], R=trace["Reff"][k],
                               accepted=bool(trace["mask"][k]))),
                           observations=jsonable(obs),
                           updates=jsonable(step.get("updates")),
                           checks=step.get("checks"), 
                           delta_psi_deg=None if not step["valid"] else {
                               arm:float(np.degrees(step["updates"][arm]["unwrapped_delta"][2]-
                                   step["updates"]["F00"]["unwrapped_delta"][2]))
                               for arm in ("F01","F11")}))
    return result
