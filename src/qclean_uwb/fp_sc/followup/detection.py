"""VAB flags-only preparation path. No replacement or recursive filter calls.

Scores are uncalibrated. This module does not grant stage authorization.
Raw history retains the legacy raw-support gate; revised ranking is never
used as history confidence. Production mapping remains a separate gate.
"""
from dataclasses import asdict
import json
from .contracts import ContractError, STEP_M
from .selection import (Decision, SelectionBinding, TrustedHistory,
                        prepare_candidate_set, native_support)
from .bridge import RECIPE_SHA
from .numerics import cir_from_spectrum, factorial

PROFILE = 'VAB_DETECTION_ONLY_R1'
HISTORY_RECIPE = 'RAW_ONLY_LEGACY_SUPPORT_GATE_R1'


def binding_for(e, policy):
    if e.bridge_identity_json is None:
        raise ContractError('VAB_DETECTION_REQUIRES_BRIDGE')
    identity = json.loads(e.bridge_identity_json)
    if identity['arm'] != 'VAB':
        raise ContractError('VAB_PRIMARY_REQUIRED')
    return SelectionBinding('VAB', identity['mode'],
                            identity['candidate_config_sha256'], RECIPE_SHA, policy.sha)


def detect(e, mode, policy, *, prior=None, motion=None):
    """Use the real shared candidate set; retain raw tap even if another wins."""
    if mode not in ('C', 'P', 'M', 'PM'):
        raise ContractError('DETECTION_MODE_NOT_ALLOWED')
    prepared = prepare_candidate_set(e, mode, policy, prior=prior, motion=motion,
                                     binding=binding_for(e, policy))
    raw = next((r for r in prepared.rows if r['tap'] == e.raw_tap), None)
    wrong = None if raw is None else float(raw['score'])
    reason = prepared.status if prepared.status != 'BUILT' else 'FLAGS_ONLY_UNCALIBRATED'
    decision = Decision(e.raw_tap, e.raw_tap, 'KEEP_ORIGINAL', reason, mode,
                        wrong, None, None, None, None, prepared.rows, e.pool_hash)
    return decision, prepared


class RawDetectionHistory(TrustedHistory):
    def observe_raw(self, e, t, offset, prior, policy):
        binding_for(e, policy)
        # Validate provenance/eligibility even when no score is needed.
        prepare_candidate_set(e, 'C', policy, binding=binding_for(e, policy))
        c = next((c for c in e.candidates if c.tap == e.raw_tap), None)
        okay = (e.valid and not e.overflow and c is not None and c.polarization_valid
                and c.supported and c.legacy_support is not None
                and c.legacy_support >= policy.min_support and prior is not None
                and prior.high-prior.low <= policy.max_prior_width_m
                and prior.residual(e.raw_tap*STEP_M) <= 1.)
        if not okay:
            self.streak = 0
            return
        self.streak += 1
        if self.streak >= policy.bootstrap_packets:
            self.t, self.detector_m = t, e.raw_tap*STEP_M
            self.offset_m, self.trusted_distance = offset, self.total_distance


def detection_loop(case, adapter, policy, mode):
    """Future authorized E1-02 loop; never called by preparation preflight.

    C needs no native model or history. P/M/PM use archived premeasurement
    priors. All observations use the original tap. No select(), probe, EKF,
    prior transformation, evaluator labels, or selected-tap history here.
    """
    if mode not in ('C', 'P', 'M', 'PM'):
        raise ContractError('DETECTION_MODE_NOT_ALLOWED')
    if case.corpus == 'static_g4' and mode != 'C':
        raise ContractError('STATIC_HAS_NO_TEMPORAL_PRIOR')
    tracker = RawDetectionHistory()
    rows = []
    for k in range(len(case.t)):
        cir = cir_from_spectrum(case.Hrf[k])
        e = adapter.evidence(cir, case.noise_variance)
        prior = motion = None
        offset = 0.
        if mode != 'C':
            prior, offset = native_support(case.prior[k].copy(), case.Pprior[k].copy(),
                                           adapter.native, policy)
        if mode in ('M', 'PM'):
            tracker.advance(float(case.t[k]), int(case.pose_id[k]), float(case.ds[k]), policy)
            motion = tracker.support(float(case.t[k]), offset, policy)
        decision, prepared = detect(e, mode, policy, prior=prior, motion=motion)
        rows.append(dict(k=k, pose_id=int(case.pose_id[k]), t=float(case.t[k]),
                         evidence=e, decision=decision,
                         prior_support=None if prior is None else asdict(prior),
                         motion_support=None if motion is None else asdict(motion),
                         history=asdict(tracker), candidate_set_sha256=prepared.sha,
                         eligible_taps=[r['tap'] for r in prepared.eligible],
                         observation=factorial(cir, e.raw_tap, e.raw_tap)))
        if mode in ('M', 'PM'):
            tracker.observe_raw(e, float(case.t[k]), offset, prior, policy)
    return rows
