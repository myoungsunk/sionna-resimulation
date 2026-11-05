"""E1-02/E2 causal detector, selective policies and self-updated history.

All numbers are uncalibrated scores. GT/LoS/route/seed/posterior are absent
from the selector API. P and M are correlated: PM uses max, not a product of
independent likelihoods. One identical CIR pool is shared by C/P/M/PM.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from typing import Callable
import numpy as np
from .contracts import ContractError, Policy, STEP_M, Support, covariance, finite


@dataclass(frozen=True)
class Candidate:
    tap: int
    signed_s: float
    support: float
    groups: tuple[int, ...]
    supported: bool
    phase_difference: float = 0.
    # Bridge R1: eligibility is not a calibrated ranking/trust score.
    selection_eligible: bool | None = None
    exclusion_reason: str | None = None
    polarization_valid: bool = True
    source_signed_s: float | None = None
    support_records_json: str | None = None
    legacy_support: float | None = None
    history_trust_eligible: bool = False
    phase_available: bool = True


@dataclass(frozen=True)
class Evidence:
    raw_tap: int | None
    raw_s: float | None
    valid: bool
    overflow: bool
    candidates: tuple[Candidate, ...]
    pool_hash: str
    bridge_identity_json: str | None = None
    selector_ready: bool = True

    def __post_init__(self) -> None:
        taps = [c.tap for c in self.candidates]
        if len(taps) != len(set(taps)):
            raise ContractError("DUPLICATE_CANDIDATE_TAP")
        for c in self.candidates:
            if type(c.tap) is not int or not 0 <= c.tap < 1028:
                raise ContractError("INVALID_TAP")
            if not np.isfinite([c.signed_s, c.support, c.phase_difference]).all():
                raise ContractError("NONFINITE_CANDIDATE")
            if not -1 <= c.signed_s <= 1 or not 0 <= c.support <= 1:
                raise ContractError("INVALID_CANDIDATE_SUPPORT")
        if self.valid and (self.raw_tap not in taps or self.raw_s is None):
            raise ContractError("VALID_RAW_FALLBACK_REQUIRED")
        if self.valid and (not math.isfinite(self.raw_s) or abs(self.raw_s) > 1):
            raise ContractError("INVALID_RAW_S")
        if not self.valid and taps:
            raise ContractError("INVALID_SIGNAL_MAY_NOT_FABRICATE_CANDIDATES")


def from_pool(pool: dict, cir: np.ndarray) -> Evidence:
    """Adapt the unchanged, locked E1-01 generator's actual output schema."""
    if pool.get('candidate_revision') or pool.get('support_semantics_version'):
        raise ContractError('REVISION_REQUIRES_EXPLICIT_BRIDGE')
    c = np.asarray(cir)
    if c.shape != (1028, 2) or not np.iscomplexobj(c):
        raise ContractError("EXPECTED_COMPLEX_CIR_1028_2")
    raw = pool["raw"]
    peak = float(raw.get("peak", 0.))
    candidates = []
    for r in pool["candidates"]:
        n = int(r["tap"])
        supports = [min(1., float(s["prominence"]) / max(peak, 1e-300)) *
                    math.exp(-abs(n - int(s["edge_tap"])))
                    for s in r["support_records"]]
        signal = max(supports, default=0.)
        candidates.append(Candidate(n, float(r["signed_s"]), signal,
                                    tuple(int(i) for i in r["group_ids"]), bool(r["supported"]),
                                    float(np.angle(c[n, 0] * c[n, 1].conjugate()))))
    return Evidence(raw.get("tap"), raw.get("signed_s"), bool(raw["valid"]),
                    bool(pool["overflow"]), tuple(candidates), pool["pool_hash"])


def native_support(x: np.ndarray, P: np.ndarray, native: Callable,
                   policy: Policy) -> tuple[Support, float]:
    """Deterministic 7-point x/y/yaw stencil through actual SourceFFD detector.

    This is a sensitivity envelope, NOT a guaranteed confidence region. The
    explicit mapping slack and the stencil must pass the future mapping gate.
    Gyro bias affects prediction upstream and has no instantaneous RF effect.
    """
    x = finite(x, (4,), "PRIOR")
    P = covariance(P, 4)
    ev, U = np.linalg.eigh(P[:3, :3])
    delta = U * np.sqrt(np.maximum(ev, 0.))[None, :] * policy.native_sigma_scale
    points = np.tile(x, (7, 1))
    points[1:4, :3] += delta.T
    points[4:7, :3] -= delta.T
    # native returns actual detector range and geometric distance, never h_r.
    ranges, geometry = native(points)
    ranges = finite(ranges, (7,), "NATIVE_RANGE")
    geometry = finite(geometry, (7,), "GEOMETRY")
    slack = policy.mapping_slack_m
    support = Support(float(ranges.min() - slack), float(ranges.max() + slack),
                      slack, "SOURCEFFD_NATIVE_STENCIL_PLUS_REVIEWED_SLACK")
    return support, float(ranges[0] - geometry[0])


@dataclass(frozen=True)
class Decision:
    raw_tap: int | None
    selected_tap: int | None
    action: str
    reason: str
    mode: str
    wrong_score: float | None
    margin: float | None
    group_margin: float | None
    confidence_score: float | None
    pol_ambiguity: float | None
    scores: tuple[dict, ...]
    pool_hash: str


def select(e: Evidence, mode: str, policy: Policy, *, prior: Support | None = None,
           motion: Support | None = None) -> Decision:
    if not e.selector_ready:
        raise ContractError('BRIDGE_ONLY_SELECTOR_SAFETY_NOT_VALIDATED')
    if mode not in {"B0", "C", "P", "M", "PM", "PM-FORCE", "NN-HARD"}:
        raise ContractError("UNKNOWN_ONLINE_POLICY")
    def keep(reason, wrong=None, scores=(), margin=None, group=None, ambiguity=None):
        return Decision(e.raw_tap, e.raw_tap, "KEEP_ORIGINAL", reason, mode,
                        wrong, margin, group, None, ambiguity, tuple(scores), e.pool_hash)
    if not e.valid:
        return keep("ORIGINAL_INVALID")
    if mode == "B0":
        return keep("BASELINE")
    if e.overflow:
        return keep("CANDIDATE_OVERFLOW")
    use_p, use_m = mode in {"P", "PM", "PM-FORCE", "NN-HARD"}, mode in {"M", "PM", "PM-FORCE"}
    if use_p and (prior is None or prior.high - prior.low > policy.max_prior_width_m):
        return keep("HOLD_PRIOR")
    if use_m and motion is None:
        return keep("HOLD_HISTORY")
    if mode == "NN-HARD":
        n = int(np.clip(np.rint((prior.low + prior.high) / (2 * STEP_M)), 0, 1027))
        return Decision(e.raw_tap, n, "REPLACE_NEGATIVE_CONTROL" if n != e.raw_tap else "KEEP_ORIGINAL",
                        "HARD_ROUNDING_NEGATIVE_ONLY", mode, None, None, None, None, None, (), e.pool_hash)
    rows = []
    for c in e.candidates:
        rf = -math.log(max(c.support, 1e-12))
        p = prior.residual(c.tap * STEP_M) if use_p else 0.
        m = motion.residual(c.tap * STEP_M) if use_m else 0.
        temporal = max(p, m)  # P and M are not independent observations.
        score = policy.rf_weight * rf + policy.prior_weight * temporal**2
        rows.append(dict(tap=c.tap, score=score, rf=rf, p=p if use_p else None,
                         m=m if use_m else None, support=c.support, groups=list(c.groups),
                         supported=c.supported, delta_n=c.tap-e.raw_tap,
                         delta_r_m=(c.tap-e.raw_tap)*STEP_M, signed_s=c.signed_s,
                         delta_s=c.signed_s-e.raw_s, phase_difference=c.phase_difference))
    raw = next(r for r in rows if r["tap"] == e.raw_tap)
    eligible = sorted((r for r in rows if r["supported"] and r["support"] >= policy.min_support),
                      key=lambda r: (r["score"], r["tap"]))
    wrong = float(raw["score"])
    ambiguity = float(np.ptp([r["signed_s"] for r in eligible])) if eligible else None
    if not eligible:
        return keep("NO_SUPPORTED_PATH", wrong, rows, ambiguity=ambiguity)
    best = eligible[0]
    margin = float(eligible[1]["score"] - best["score"]) if len(eligible) > 1 else None
    rivals = [r for r in eligible[1:] if not set(r["groups"]) & set(best["groups"])]
    group = float(rivals[0]["score"] - best["score"]) if rivals else None
    gain = float(raw["score"] - best["score"])
    if best["tap"] == e.raw_tap:
        return keep("ORIGINAL_BEST", wrong, rows, margin, group, ambiguity)
    force = mode == "PM-FORCE"
    if not force and (wrong < policy.wrong_cut or gain < policy.replace_gain):
        return keep("INSUFFICIENT_WRONGNESS_OR_GAIN", wrong, rows, margin, group, ambiguity)
    # Do not manufacture infinite confidence when only one candidate exists.
    if not force and (margin is not None and margin < policy.margin or
                      group is not None and group < policy.margin):
        return keep("ABSTAIN_AMBIGUOUS", wrong, rows, margin, group, ambiguity)
    if not force and max(best["p"] or 0., best["m"] or 0.) > 1.:
        return keep("NULL_PATH_PRIOR_CONFLICT", wrong, rows, margin, group, ambiguity)
    conf = min([gain, best["support"]] + ([] if margin is None else [margin]) +
               ([] if group is None else [group]))
    return Decision(e.raw_tap, int(best["tap"]), "REPLACE_SUPPORTED", "FORCED_NEGATIVE" if force else "SUPPORTED",
                    mode, wrong, margin, group, float(conf), ambiguity, tuple(rows), e.pool_hash)


@dataclass
class TrustedHistory:
    t: float | None = None
    detector_m: float | None = None
    offset_m: float = 0.
    streak: int = 0
    total_distance: float = 0.
    trusted_distance: float = 0.
    last_seen_t: float | None = None
    last_pose: int | None = None

    def advance(self, t: float, pose_id: int, ds: float, policy: Policy) -> None:
        if not np.isfinite([t, ds]).all():
            raise ContractError("NONFINITE_HISTORY_INPUT")
        if self.last_seen_t is not None:
            elapsed = t - self.last_seen_t
            if elapsed <= 0 or pose_id <= self.last_pose:
                raise ContractError("DUPLICATE_OR_REORDERED_HISTORY")
            if abs(ds) > policy.vmax_mps * elapsed + policy.motion_slack_m:
                self.reset_trust()
        self.total_distance += abs(ds)
        self.last_seen_t, self.last_pose = t, pose_id

    def reset_trust(self) -> None:
        self.t, self.detector_m, self.streak = None, None, 0

    def support(self, now: float, native_offset: float, policy: Policy) -> Support | None:
        if self.t is None or self.detector_m is None:
            return None
        age = now - self.t
        if age <= 0 or age > policy.history_max_age_s:
            return None
        # Elapsed time is explicit; no fixed 4cm rule after lost ticks.
        distance = self.total_distance - self.trusted_distance
        radius = max(policy.vmax_mps * age, distance) + policy.motion_slack_m + policy.mapping_slack_m
        center = self.detector_m + native_offset - self.offset_m
        return Support(center-radius, center+radius, policy.mapping_slack_m,
                       "TRUSTED_TAP_ELAPSED_MOTION_NATIVE_OFFSET")

    def observe(self, e: Evidence, decision: Decision, t: float, native_offset: float,
                prior: Support | None, policy: Policy) -> None:
        if not e.selector_ready:
            raise ContractError('BRIDGE_ONLY_HISTORY_NOT_VALIDATED')
        n = decision.selected_tap
        c = next((c for c in e.candidates if c.tap == n), None)
        # Bootstrap original high-support observations without forcing a change.
        okay = (e.valid and not e.overflow and c is not None and c.supported and
                c.support >= policy.min_support and prior is not None and
                prior.high-prior.low <= policy.max_prior_width_m and prior.residual(n*STEP_M) <= 1.)
        if not okay:
            self.streak = 0
            return
        self.streak += 1
        if self.streak >= policy.bootstrap_packets:
            self.t, self.detector_m = t, n*STEP_M
            self.offset_m, self.trusted_distance = native_offset, self.total_distance


def policy_grid(base: Policy) -> list[Policy]:
    from itertools import product
    return [Policy(**{**asdict(base), "prior_weight": w, "wrong_cut": cut, "margin": m})
            for w, cut, m in product((.5, 1., 2.), (1., 2., 4.), (.25, .5, 1.))]
