"""VAB flags-only preparation path. No replacement or recursive filter calls.

Scores are uncalibrated. This module does not grant stage authorization.
Raw history retains the legacy raw-support gate; revised ranking is never
used as history confidence. Production mapping remains a separate gate.
"""
from dataclasses import asdict, dataclass
import json
from .contracts import ContractError, STEP_M
from .selection import (Decision, SelectionBinding, TrustedHistory,
                        prepare_candidate_set, native_support)
from .bridge import RECIPE_SHA
from .numerics import cir_from_spectrum, factorial
from .integrity import checked_integrity, assess_prior

PROFILE = 'VAB_DETECTION_ONLY_R1'
HISTORY_RECIPE = 'RAW_ONLY_PRIOR_INTEGRITY_RESET_R2'


def binding_for(e, policy):
    if e.bridge_identity_json is None:
        raise ContractError('VAB_DETECTION_REQUIRES_BRIDGE')
    identity = json.loads(e.bridge_identity_json)
    if identity['arm'] != 'VAB':
        raise ContractError('VAB_PRIMARY_REQUIRED')
    return SelectionBinding('VAB', identity['mode'],
                            identity['candidate_config_sha256'], RECIPE_SHA, policy.sha)


@dataclass(frozen=True)
class DetectionPreparation:
    active: object
    diagnostic: object
    integrity: object
    effective_mode: str
    reason: str
    active_wrong_score: float | None
    diagnostic_prior: object


def prepare_detection(e, mode, policy, *, prior=None, motion=None, integrity=None):
    """Shared protected component; no decision, history update, or truth input."""
    if mode not in ('C', 'P', 'M', 'PM'):
        raise ContractError('DETECTION_MODE_NOT_ALLOWED')
    state = checked_integrity(integrity)
    binding = binding_for(e, policy)
    active = prepare_candidate_set(e, 'C', policy, binding=binding)
    diagnostic = active if mode == 'C' else prepare_candidate_set(
        e, mode, policy, prior=prior, motion=motion, binding=binding)
    diagnostic_prior = active if mode == 'C' else prepare_candidate_set(
        e, 'P', policy, prior=prior, binding=binding)
    raw = next((r for r in active.rows if r['tap'] == e.raw_tap), None)
    wrong = None if raw is None or mode != 'C' else float(raw['score'])
    reason = (active.status if active.status != 'BUILT' else
              'FLAGS_ONLY_UNCALIBRATED' if mode == 'C' else
              'HOLD_PRIOR_INTEGRITY_' + state.state)
    return DetectionPreparation(active, diagnostic, state,
                                'C' if mode == 'C' else 'HOLD', reason, wrong, diagnostic_prior)


def detect(e, mode, policy, *, prior=None, motion=None, integrity=None):
    """Detection-only wrapper; untrusted P/M diagnostics never become flags."""
    result = prepare_detection(e, mode, policy, prior=prior, motion=motion, integrity=integrity)
    decision = Decision(e.raw_tap, e.raw_tap, 'KEEP_ORIGINAL', result.reason, mode,
                        result.active_wrong_score, None, None, None, None,
                        result.active.rows, e.pool_hash)
    return decision, result.active


class RawDetectionHistory(TrustedHistory):
    def reset_trust(self):
        super().reset_trust()
        self.offset_m = 0.
        self.trusted_distance = self.total_distance

    def support(self, now, native_offset, policy, *, integrity=None):
        checked_integrity(integrity)
        self.reset_trust()
        return None

    def observe_raw(self, e, t, offset, prior, policy, *, integrity=None):
        checked_integrity(integrity)
        binding_for(e, policy)
        # Validate provenance/eligibility even when no score is needed.
        prepare_candidate_set(e, 'C', policy, binding=binding_for(e, policy))
        # R1 has no VALID provider. Raw observations are retained by the caller;
        # none may bootstrap or refresh trusted state using an unverified prior.
        self.reset_trust()


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
        integrity = None
        if mode != 'C':
            integrity = assess_prior(case.prior[k], case.Pprior[k], float(case.t[k]),
                                     None if k == 0 else float(case.t[k-1]))
            if integrity.state != 'INVALID':
                prior, offset = native_support(case.prior[k].copy(), case.Pprior[k].copy(),
                                               adapter.native, policy)
        if mode in ('M', 'PM'):
            tracker.advance(float(case.t[k]), int(case.pose_id[k]), float(case.ds[k]), policy)
            motion = tracker.support(float(case.t[k]), offset, policy, integrity=integrity)
        protection = prepare_detection(e, mode, policy, prior=prior, motion=motion, integrity=integrity)
        decision, prepared = detect(e, mode, policy, prior=prior, motion=motion, integrity=integrity)
        rows.append(dict(k=k, pose_id=int(case.pose_id[k]), t=float(case.t[k]),
                         evidence=e, decision=decision,
                         prior_support=None if prior is None else asdict(prior),
                         motion_support=None if motion is None else asdict(motion),
                         history=asdict(tracker), candidate_set_sha256=prepared.sha,
                         prior_integrity=asdict(protection.integrity),
                         effective_mode=protection.effective_mode,
                         diagnostic_only_scores=protection.diagnostic.rows,
                         diagnostic_only_prior_scores=protection.diagnostic_prior.rows,
                         diagnostic_status=protection.diagnostic.status,
                         eligible_taps=[r['tap'] for r in prepared.eligible],
                         observation=factorial(cir, e.raw_tap, e.raw_tap)))
        if mode in ('M', 'PM'):
            tracker.observe_raw(e, float(case.t[k]), offset, prior, policy, integrity=integrity)
    return rows
