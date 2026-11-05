"""Read-only source adapters, canonical input contract, and six-arm recursion.

No real payloads are loaded at import. The model adapter is supplied explicitly;
production uses the SHA-pinned SourceFFD/original motion core, never a toy RF
model. Synthetic test doubles are declared only in tests.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import importlib.util
import math
import re
import numpy as np
from .contracts import ContractError, Policy, STEP_M, Support, covariance, finite
from .numerics import (apply_residual_model, cir_from_spectrum, factorial, measurement,
                       residual_bin, update, raw_detection)
from .selection import Candidate, Decision, Evidence, TrustedHistory, from_pool, native_support, select

GATE = 9.210340371976184
ARMS = ("A", "B", "C", "D", "E", "F")


@dataclass
class OnlineCase:
    """Only observations/controls/archived priors. Never evaluator truth/LoS."""
    case_id: str
    route: str
    bias: str
    channel: str
    sensor_seed: int
    split: str
    Hrf: np.ndarray
    t: np.ndarray
    pose_id: np.ndarray
    ds: np.ndarray
    gy: np.ndarray
    dt: np.ndarray
    x0: np.ndarray
    P0: np.ndarray
    z: np.ndarray
    muMB: np.ndarray
    muBASE: np.ndarray
    R: np.ndarray
    D: np.ndarray
    prior: np.ndarray
    Pprior: np.ndarray
    noise_variance: float = 0.
    corpus: str = "dynamic"
    baseline_trace: dict | None = None
    clean_Hrf: np.ndarray | None = None
    environment_id: str = "ORIGINAL_CORRIDOR"

    def __post_init__(self):
        n = len(self.t)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.case_id):
            raise ContractError("UNSAFE_CASE_ID")
        if not n or not self.case_id or self.split not in {"TRAIN", "CAL", "SEALED", "EXPOSED_DEV", "SYNTHETIC"}:
            raise ContractError("INVALID_CASE_ID_SPLIT_OR_LENGTH")
        if type(self.sensor_seed) is not int or self.sensor_seed < 0 or self.channel not in {"Full", "Native_LoS"} or self.bias not in {"B0", "L2"}:
            raise ContractError("INVALID_BIAS_CHANNEL_OR_SEED")
        if self.corpus not in {"dynamic", "static_g4", "external"}:
            raise ContractError("INVALID_CORPUS")
        if self.Hrf.shape != (n, 257, 2) or not np.iscomplexobj(self.Hrf) or not np.isfinite(self.Hrf).all():
            raise ContractError("INVALID_CASE_SPECTRUM")
        for name in ("t", "ds", "gy", "dt", "D"):
            finite(getattr(self, name), (n,), name)
        for name in ("z", "muMB", "muBASE"):
            finite(getattr(self, name), (n, 2), name)
        finite(self.prior, (n, 4), "ARCHIVED_PRIOR")
        finite(self.Pprior, (n, 4, 4), "ARCHIVED_PPRIOR")
        finite(self.R, (n, 2, 2), "ORIGINAL_R")
        finite(self.x0, (4,), "INITIAL_STATE")
        covariance(self.P0, 4, positive=True)
        if (self.pose_id.shape != (n,) or self.pose_id.dtype.kind not in "iu" or
                len(np.unique(self.pose_id)) != n or np.any(np.diff(self.pose_id) <= 0) or
                np.any(np.diff(self.t) <= 0) or np.any(self.dt[1:] <= 0)):
            raise ContractError("INVALID_TIMELINE_OR_POSE_IDS")
        if self.corpus == "dynamic" and not np.allclose(self.dt[1:], np.diff(self.t), rtol=0, atol=1e-10):
            raise ContractError("CONTROLS_TIMESTAMP_MISMATCH")
        if not math.isfinite(self.noise_variance) or self.noise_variance < 0:
            raise ContractError("INVALID_RF_NOISE_VARIANCE")
        if self.clean_Hrf is not None and (self.clean_Hrf.shape != self.Hrf.shape or
                not np.iscomplexobj(self.clean_Hrf) or not np.isfinite(self.clean_Hrf).all()):
            raise ContractError("INVALID_CLEAN_SOURCE_SPECTRUM")
        if self.baseline_trace is not None:
            shapes = {"h":(n,2), "H":(n,2,4), "prior":(n,4), "Pprior":(n,4,4),
                      "Reff":(n,2,2), "K":(n,4,2)}
            for name, shape in shapes.items():
                finite(self.baseline_trace[name], shape, "TRACE_"+name)
            if self.baseline_trace["mask"].dtype != np.dtype(bool) or self.baseline_trace["mask"].shape != (n,):
                raise ContractError("ARCHIVE_MASK_MUST_BE_EXACT_BOOLEAN")
        for k in range(n):
            covariance(self.R[k], 2, positive=True)
            covariance(self.Pprior[k], 4)

    def measurement_domain(self):
        return dict(bias=self.bias, channel=self.channel, noise_variance=float(self.noise_variance))

    def sample_id(self, k):
        return f"{self.case_id}:{int(self.pose_id[k])}"

    def baseline_packet(self):
        return {name: getattr(self, name) for name in ("t", "pose_id", "z", "muMB", "muBASE", "R", "D", "P0")}

    def controls(self):
        if self.x0[3] != 0:
            raise ContractError("ORIGINAL_W0_INITIAL_BIAS_MUST_BE_ZERO")
        return dict(ds=self.ds, gy=self.gy, dt=self.dt, x0=self.x0[:3])


class OriginalAdapter:
    """Late imports reuse original source functions after outer authorization."""
    def __init__(self, repo: Path, *, revision_evidence=None):
        from qclean_uwb.fp_sc.e0_baseline import load_original_model, SPEC
        from qclean_uwb.fp_sc.candidates import CandidateConfig, generate_candidates
        self.core, self.online, self.model, self.source_hashes = load_original_model(repo)
        self.spec = SPEC.copy()
        self.anchor = np.asarray(SPEC["anchor"][:2])
        self._candidate_config, self._generate = CandidateConfig, generate_candidates
        self.revision_evidence = revision_evidence
        path = repo / "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/pilot.py"
        data = path.read_bytes()
        blob = hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()
        if blob != "e8d3ed20a1c034ca09a6523eab0bfa1d9b5f3f3c":
            raise ContractError("B37_REFERENCE_SOURCE_CHANGED")
        spec = importlib.util.spec_from_file_location("fp_sc_b37_readonly_reference", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.legacy_choose = module.choose

    def observe(self, x):
        h, H = self.model.batch(np.asarray(x)[None], self.spec)
        return h[0], H[0]

    def native(self, states):
        _, _, diag = self.model.batch(states, self.spec, gradient=False, return_diagnostics=True)
        anchor = np.asarray(self.spec["anchor"])
        geometry = np.sqrt(np.sum((states[:, :2]-anchor[:2])**2, axis=1) +
                           (anchor[2]-self.spec["robot_z_m"])**2)
        return diag["native_range"], geometry

    def predict(self, x, P, k, case):
        return self.online.predict(self.core, x, P, k, case.controls())

    def evidence(self, cir, variance=0.):
        if self.revision_evidence is not None:
            return self.revision_evidence.evidence(cir, variance)
        pool = self._generate(cir, config=self._candidate_config(noise_var_per_bin=variance))
        return from_pool(pool, cir)

    def legacy(self, cir, e, prior, P):
        if not e.valid:
            return e.raw_tap
        h, H = self.observe(prior)
        sigma = np.sqrt(max(0., float(H[0]@P@H[0]))+.20**2)
        mag = np.abs(cir)
        strong = mag[:, int(mag.max(axis=0).argmax())]
        chosen, _ = self.legacy_choose(np.array([e.raw_tap]), strong[None],
                                      np.array([strong.max()]), np.array([h[0]]),
                                      np.array([sigma]), STEP_M)
        return int(chosen[0])

    def original_replay(self, case):
        return self.online.replay(case.baseline_packet(), case.controls(), "W0", self.core, self.model, self.spec)


def _sigma(x, anchor):
    rho = float(np.linalg.norm(x[:2]-anchor))
    return float(np.interp(rho, [0., 1.5, 3., 6., 10.], [.011, .020, .050, .120, .240]))


def open_loop(case: OnlineCase, adapter, policy: Policy, mode: str, *, teacher_forced=False,
              prior_transform=None, history_fault=None, unavailable=frozenset()) -> list[dict]:
    """E1/E2 own history with fixed, PRE-measurement archived state priors."""
    tracker = TrustedHistory()
    rows = []
    for k in range(len(case.t)):
        cir = cir_from_spectrum(case.Hrf[k])
        e = (Evidence(None, None, False, False, (), "MISSING_PACKET") if k in unavailable else
             adapter.evidence(cir, case.noise_variance))
        x, P = case.prior[k].copy(), case.Pprior[k].copy()
        if prior_transform is not None:
            x, P = prior_transform(x, P)
        prior, offset = native_support(x, P, adapter.native, policy)
        if case.corpus == "static_g4":
            tracker = TrustedHistory()  # four static yaws are NEVER a time series.
        tracker.advance(float(case.t[k]), int(case.pose_id[k]), float(case.ds[k]), policy)
        if history_fault is not None:
            history_fault(tracker, k)
        motion = tracker.support(float(case.t[k]), offset, policy)
        if mode == "B37":
            n = adapter.legacy(cir, e, x, P)
            decision = Decision(e.raw_tap, n, "KEEP_ORIGINAL" if n == e.raw_tap else "REPLACE_LEGACY",
                                "B37_UNCHANGED_REFERENCE", mode, None, None, None, None, None, (), e.pool_hash)
        else:
            decision = select(e, mode, policy, prior=prior, motion=motion)
        # Evaluator receives observations but never feeds a label back here.
        rows.append(dict(k=k, pose_id=int(case.pose_id[k]), t=float(case.t[k]),
                         evidence=e, decision=decision, prior_support=asdict(prior),
                         motion_support=None if motion is None else asdict(motion),
                         history=asdict(tracker), observation=factorial(cir, e.raw_tap, decision.selected_tap)))
        history_decision = select(e, "B0", policy) if teacher_forced else decision
        tracker.observe(e, history_decision, float(case.t[k]), offset, prior, policy)
    return rows


class ArmProcessor:
    """Exactly one externally visible update per packet; independent arm state."""
    def __init__(self, case, adapter, policy: Policy, arm: str, models=None):
        if arm not in ARMS:
            raise ContractError("UNKNOWN_CLOSED_LOOP_ARM")
        if case.corpus == "static_g4":
            raise ContractError("STATIC_YAW_NOT_CLOSED_LOOP_TRAJECTORY")
        self.case, self.adapter, self.policy, self.arm = case, adapter, policy, arm
        self.models = models or {}
        self.x, self.P = case.x0.copy(), case.P0.copy()
        self.sx, self.sp = self.x.copy(), self.P.copy()
        self.history, self.last_k = TrustedHistory(), -1

    def step(self, k: int, *, available: bool = True) -> dict:
        if k != self.last_k+1:
            raise ContractError("PACKET_REPLAY_OR_REORDER_NOT_ALLOWED")
        case, adapter, policy, arm = self.case, self.adapter, self.policy, self.arm
        t = float(case.t[k])
        start_x = self.x.copy()
        xp, pp = adapter.predict(self.x, self.P, k, case)
        sx, sp = adapter.predict(self.sx, self.sp, k, case)
        h, H = adapter.observe(xp)
        sh, sH = adapter.observe(sx)
        cir = cir_from_spectrum(case.Hrf[k])
        if arm in {"A", "B"}:
            tap, _, raw_observation = raw_detection(cir)
            valid = raw_observation is not None
            e = Evidence(tap, float(raw_observation[1]) if valid else None, valid, False,
                         (Candidate(tap, float(raw_observation[1]), 0., (), False),) if valid else (),
                         "BASELINE_DETECTOR_ONLY")
            prior, offset = None, 0.
            decision = select(e, "B0", policy)
        else:
            e = adapter.evidence(cir, case.noise_variance)
            self.history.advance(t, int(case.pose_id[k]), float(case.ds[k]), policy)
            prior, offset = native_support(xp, pp, adapter.native, policy)
            motion = self.history.support(t, offset, policy)
            decision = select(e, "PM", policy, prior=prior, motion=motion)
        raw = measurement(cir, e.raw_tap, e.raw_tap) if e.valid else None
        if raw is not None and not np.allclose(raw, case.z[k], rtol=0, atol=1e-12):
            raise ContractError("CANONICAL_PACKET_RAW_RECEIVER_PARITY_FAIL")
        changed = arm in {"D", "E", "F"} and decision.selected_tap != e.raw_tap
        extractor = "F01" if arm == "F" else "F11" if arm in {"D", "E"} else "F00"
        observations = factorial(cir, e.raw_tap, decision.selected_tap)
        chosen = observations[extractor] if changed else raw
        if not available or raw is None or chosen is None:
            self.x, self.P, self.sx, self.sp = xp, pp, sx, sp
            self.last_k = k
            self.history.reset_trust()
            return dict(k=k, t=t, pose_id=int(case.pose_id[k]), arm=arm, x=xp.copy(), P=pp.copy(),
                        prior=xp.copy(), Pprior=pp.copy(), mask=False, decision=asdict(decision),
                        status="HOLD_NO_MEASUREMENT", updated=False, z=None)
        # Preserve exact no-op archive observation bits, apply only actual CIR delta.
        z = case.z[k] + (chosen-raw)
        mu, R, gate_mu, gate_R = case.muMB[k].copy(), case.R[k].copy(), case.muBASE[k].copy(), case.R[k].copy()
        sig = _sigma(start_x, adapter.anchor)
        if arm in {"A", "D"}:
            R[1, 1] += sig**2
        else:
            model = self.models.get(extractor)
            if model is None:
                raise ContractError(f"MATCHED_MODEL_MISSING:{arm}:{extractor}")
            bin_name = residual_bin(changed, decision.confidence_score)
            mu, R = apply_residual_model(model, target_route=case.route, extractor=extractor,
                                        policy_sha=policy.sha, sample_id=case.sample_id(k),
                                        bin_name=bin_name, original_mu=case.muMB[k], domain=case.measurement_domain())
            gate_mu, gate_R = mu.copy(), R.copy()
            if arm == "C" and decision.wrong_score is not None and decision.wrong_score >= policy.wrong_cut:
                T = np.diag([1., math.sqrt(policy.risk_R_multiplier)])
                R, gate_R = T@R@T.T, T@gate_R@T.T  # PSD including cross covariance.
        shadow_trial = update(sx, sp, sh, sH, z, gate_mu, gate_R, permitted=True)
        allowed = shadow_trial["nis"] <= GATE
        if allowed:
            self.sx, self.sp = shadow_trial["x"], shadow_trial["P"]
        else:
            self.sx, self.sp = sx, sp
        post = update(xp, pp, h, H, z, mu, R, permitted=allowed)
        self.x, self.P, self.last_k = post["x"], post["P"], k
        actual = decision if arm in {"D", "E", "F"} else select(e, "B0", policy)
        if arm not in {"A", "B"}:
            self.history.observe(e, actual, t, offset, prior, policy)
        return dict(k=k, t=t, pose_id=int(case.pose_id[k]), arm=arm, x=self.x.copy(), P=self.P.copy(),
                    prior=xp.copy(), Pprior=pp.copy(), h=h, H=H, mu=mu, R=R, z=z, K=post["K"],
                    innovation=post["innovation"], S=post["S"], nis=post["nis"],
                    mask=bool(allowed), decision=asdict(actual), risk_decision=asdict(decision),
                    shadow_state=self.sx.copy(), shadow_P=self.sp.copy(), sigma_original=sig,
                    history=asdict(self.history), status="UPDATED" if allowed else "GATE_REJECTED",
                    updated=bool(allowed), extractor=extractor)


def run_arms(case, adapter, policy, models=None, *, arms=ARMS) -> dict:
    result = {}
    for arm in arms:
        processor = ArmProcessor(case, adapter, policy, arm, models)
        result[arm] = [processor.step(k) for k in range(len(case.t))]
    if "A" in result:
        reference = adapter.original_replay(case)
        for key in ("x", "P", "prior", "Pprior"):
            actual = np.asarray([r[key] for r in result["A"]])
            expected = reference[key]
            if actual.shape != expected.shape or not np.isfinite(expected).all():
                raise ContractError("W0_REFERENCE_SHAPE_OR_FINITE_FAILURE")
            if np.max(abs(actual-expected)/np.maximum(1., abs(expected))) > 1e-10:
                raise ContractError(f"W0_NOOP_PARITY_FAILED:{key}")
        if not np.array_equal(np.array([r["mask"] for r in result["A"]]), reference["mask"]):
            raise ContractError("W0_NOOP_MASK_PARITY_FAILED")
    return result
