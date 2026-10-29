#!/usr/bin/env python3
"""POL-XCORR-001 v0.3 DRAFT — P0V3_DELTA_PREFLIGHT_ONLY (role IMPLEMENTER).

Implements TASK_HANDOFF_v0.3: R-04 exact tap/branch/valid parity, R-14 independent weak-port calculation (LoS only),
R-12/R-13 reference-lineage preservation with hardened comparison, negative fixtures, label isolation.
NO S0/P1/P2/P3, no metric-label join, no AUC, no model. Historical P0 code (scripts/p0_preflight.py) and run
directories are not modified; reviewed helper functions (sha, verify_hashes, align_poses, load_source) are imported.
Exit 0 only for status TECHNICAL_QA_ONLY.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCOPE_REL = "research/POL_XCORR_UNRESOLVED_20261029"
BASE_SHA = "250d617ad89a4105fa1af546cc83ceed9de98f42"
GOV_SHA = "d5f84d9d04d28d465f3357e9299352eb184e6bfc"          # TASK_HANDOFF_v0.3 pinned governance router commit
V02_IMMUTABLE = {                                             # v0.2 files must still carry their recorded hashes
    "contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.2.md": "468249a7b32c9699c20a3227fc0241eef3ab92773d00bc52a981a32cf6e56ddb",
    "SCIENCE_SPEC_v0.2.md": "0beeab98c28e3a2933845069172bb8288ac91809325437549d0c4d9d7733efa1",
    "config/INPUT_LOCK_v2.json": "bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184",
    "config/PLAN_PARAMETERS_v0.2.json": "c73a5e7fe36eb5922854e1382e0f8f916672b76fcb395fdc59139f41e3f70d3a",
}
V03_DOCS = ["contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md", "SCIENCE_SPEC_v0.3.md", "config/PLAN_PARAMETERS_v0.3.json",
            "reviews/PROPOSER_DECISION_03.md", "TASK_HANDOFF_v0.3.md", "PROPOSER_FREEZE_CHECKLIST_v0.3.md", "PRE_CONTRACT_DISCLOSURE_v0.3.md",
            "config/P0_REFERENCES_v0.2.json", "scripts/p0v3_preflight.py", "scripts/p0_preflight.py"]
WORKFLOW_REL = ".github/workflows/pol-xcorr-p0v3-preflight.yml"
P0_RUN_REF = "results_p0/run_40867521966"                    # historic P0 PASS run (reconciliation guard)
EXPECTED_R14 = dict(n_valid=9519, n_weak=3492, timeline_weak=3105, timeline_n=7251)   # re-audit guard (TASK_HANDOFF R-14 §6)
# Implementer-declared tolerances, fixed in code before the run (PLAN_PARAMETERS_v0.3 values where they exist)
TOL = dict(r14_q_identity_rel=1e-10, r14_u_inverse_abs=1e-9, r14_eps_identity_abs=1e-12,
           r14_inverse_min_eps=1e-6, r14_inverse_min_disc=1e-6, s_fp_parity_abs=1e-9, p0_reconcile_abs=1e-12)
LABEL_PATTERNS = ("label", "truth", "e_s", "e_r", "nolos", "rd_los", "hb_", "class", "y_true", "target")
N_TAPS = 4 * 257
LEADING = 0.3
_OPENED = []                                                   # (path, columns) of every tabular read, for label isolation


# ----------------------------------------------------------------------------- helpers
def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def jsave(p, v):
    Path(p).write_text(json.dumps(v, indent=2, ensure_ascii=False, allow_nan=False, default=_jd) + "\n")


def _jd(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def read_csv_cols(path, cols, label_ok=False):
    """Every tabular read goes through here: usecols only, recorded for the label-isolation audit."""
    df = pd.read_csv(path, usecols=cols)
    _OPENED.append(dict(path=str(path), columns=list(df.columns)))
    if not label_ok:
        bad = [c for c in df.columns if any(t in c.lower() for t in LABEL_PATTERNS)]
        if bad:
            raise RuntimeError(f"LABEL_ISOLATION violated: {path} columns {bad}")
    return df


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


# ----------------------------------------------------------------------------- R-04: fresh observer
def observer_v3(H):
    """Third independent implementation of the stronger-RX 30 % leading-edge detector (row loop, no shared code).
    Returns dict(tap, branch, peak, p (N,2) port powers at the common tap, valid_fp, valid_g5, port_taps (N,2))."""
    H = np.asarray(H, np.complex128); n, nf, nr = H.shape
    if nf != 257 or nr != 2:
        raise ValueError("H must be (N,257,2)")
    k = np.arange(nf); w = 0.5 - 0.5 * np.cos(2 * np.pi * k / (nf - 1))
    out = dict(tap=np.zeros(n, int), branch=np.zeros(n, int), peak=np.zeros(n), p=np.zeros((n, 2)), port_taps=np.zeros((n, 2), int),
               p_own_tap=np.zeros((n, 2)))
    for i in range(n):
        c = np.fft.ifft(H[i] * w[:, None], n=N_TAPS, axis=0) * nf          # (N_TAPS, 2)
        a = np.abs(c)
        pk = a.max(axis=0)                                                  # per-port peak
        br = 0 if pk[0] >= pk[1] else 1                                     # argmax tie -> port 0 (numpy convention)
        thr = LEADING * pk[br]
        idx = np.flatnonzero(a[:, br] >= thr)
        tp = int(idx[0]) if idx.size else 0
        out["tap"][i] = tp; out["branch"][i] = br; out["peak"][i] = pk[br]
        out["p"][i] = np.abs(c[tp, :]) ** 2                                 # BOTH ports at the single common tap
        for q in range(2):
            j = np.flatnonzero(a[:, q] >= LEADING * pk[q]); out["port_taps"][i, q] = int(j[0]) if j.size else 0
            out["p_own_tap"][i, q] = abs(c[out["port_taps"][i, q], q]) ** 2      # alternative (WRONG) per-port extraction, for discrimination
    tiny = np.finfo(float).tiny
    out["valid_fp"] = (out["peak"] > 0) & (out["p"].sum(axis=1) > tiny)   # detector/FP definition
    out["valid_g5"] = (out["peak"] > 0) & (out["tap"] + 80 <= N_TAPS)      # features.extract 80-tap window definition
    return out


def r04_compare(feat, obs, old_valid, s_fp_old=None):
    """Exact array equality, no tolerance. Returns dict of mismatch masks."""
    m = dict(tap=np.asarray(feat["tap"]) != obs["tap"], branch=np.asarray(feat["branch"]) != obs["branch"],
             valid_g5=np.asarray(feat["valid"]).astype(bool) != obs["valid_g5"])
    if old_valid is not None:
        m["valid_fp_old_observer"] = np.asarray(old_valid).astype(bool) != obs["valid_fp"]
    den = obs["p"].sum(axis=1)
    s_new = np.divide(obs["p"][:, 0] - obs["p"][:, 1], den, out=np.full(len(den), np.nan), where=den > np.finfo(float).tiny)
    lp_new = np.log10(np.maximum(den, np.finfo(float).tiny))
    fs = np.asarray(feat["s_fp"], float); fl = np.asarray(feat["log_fp_power"], float)
    both = np.isfinite(fs) & np.isfinite(s_new)
    m["s_fp_common_tap"] = (np.isfinite(fs) != np.isfinite(s_new)) | (both & (np.abs(np.nan_to_num(fs) - np.nan_to_num(s_new)) > TOL["s_fp_parity_abs"]))
    fin = np.isfinite(fl)
    m["log_fp_power_common_tap"] = fin & (np.abs(np.nan_to_num(fl) - lp_new) > TOL["s_fp_parity_abs"])
    return m


# ----------------------------------------------------------------------------- R-14: coherency + classification
def build_J(cir, tap):
    """ORIGINAL 7-tap window n0+[-2,4] and validity order of p0_preflight.coherency (window incl. +-8 lag reach)."""
    N = cir.shape[0]
    if tap - 2 < 0 or tap + 6 >= N or tap - 2 - 8 < 0 or tap + 4 + 8 >= N:
        return None, "INVALID_WINDOW"
    h = cir[tap - 2:tap + 5, :]
    if not np.isfinite(h).all():
        return None, "NONFINITE"
    scale = np.max(np.abs(h))
    if scale <= np.finfo(float).tiny:
        return None, "NULL_PORT"
    u = h / scale
    J = u.T @ u.conj(); J = 0.5 * (J + J.conj().T)
    return J, "OK"


def classify_J(J):
    """R-14 §2-3: invalid statuses are flagged, never clipped; weak_port is a diagnostic flag only."""
    r = dict(status=None, a=np.nan, b=np.nan, t=np.nan, d_raw=np.nan, u=np.nan, weak_port=None, q_W=np.nan, eps_rho=np.nan,
             coherence_sq=np.nan)
    if not np.isfinite(J).all():
        r["status"] = "NONFINITE"; return r
    a, b = float(J[0, 0].real), float(J[1, 1].real); c2 = float(abs(J[0, 1]) ** 2); t = a + b; d = a * b - c2
    r.update(a=a, b=b, t=t, d_raw=d)
    tiny = np.finfo(float).tiny
    if t <= 0 or min(a, b) <= tiny:
        r["status"] = "NULL_PORT"; return r
    if d < -1e-12 * t * t:
        r["status"] = "NEGATIVE_DET"; return r
    d = max(d, 0.0)                                                         # rounding-level only (same rule as P0)
    u = min(a, b) / t
    r.update(status="VALID", u=u, weak_port=bool(u < 0.05), q_W=4 * d / (t * t), eps_rho=d / (a * b), coherence_sq=c2 / (a * b))
    return r


def r14_identities(r):
    """Returns dict of identity residuals for a VALID row (registered tolerances in TOL)."""
    q, e, u = r["q_W"], r["eps_rho"], r["u"]
    q_from = 4 * u * (1 - u) * e
    out = dict(q_identity_rel=abs(q - q_from) / max(abs(q), np.finfo(float).tiny) if q > 0 else abs(q_from),
               eps_identity_abs=abs(e - (1 - r["coherence_sq"])), u_inverse_abs=np.nan, inverse_checked=False)
    if e >= TOL["r14_inverse_min_eps"]:
        disc = 1 - q / e
        if disc >= TOL["r14_inverse_min_disc"]:
            out["u_inverse_abs"] = abs(u - 0.5 * (1 - math.sqrt(disc))); out["inverse_checked"] = True
    return out


# ----------------------------------------------------------------------------- reference parity (hardened)
def compare_reference_v3(new, ref, keys, cols, tol):
    """Explicit duplicate/absent-key detection, NaN pattern, +-inf pattern, finite max abs diff."""
    res = dict(status="FAIL", reasons=[], tolerance_abs=tol)
    for nm, df in (("new", new), ("ref", ref)):
        miss = [c for c in keys + cols if c not in df.columns]
        if miss:
            res["reasons"].append(f"{nm}_missing_columns:{miss}"); return res
        dup = int(df.duplicated(keys).sum())
        if dup:
            res["reasons"].append(f"{nm}_duplicate_keys:{dup}")
    if res["reasons"]:
        return res
    m = new[keys + cols].merge(ref[keys + cols], on=keys, how="outer", suffixes=("_new", "_ref"), indicator=True, validate="one_to_one")
    cov = dict(rows_new=len(new), rows_ref=len(ref), matched=int((m._merge == "both").sum()), only_new=int((m._merge == "left_only").sum()),
               only_ref=int((m._merge == "right_only").sum()))
    res["coverage"] = cov
    if cov["only_new"] or cov["only_ref"]:
        res["reasons"].append("absent_keys")
    m = m[m._merge == "both"]; worst = 0.0; per = {}
    for c in cols:
        a = m[c + "_new"].to_numpy(float); b = m[c + "_ref"].to_numpy(float)
        nan_mm = int(np.sum(np.isnan(a) != np.isnan(b)))
        inf_mm = int(np.sum((np.isinf(a) | np.isinf(b)) & ~(np.isinf(a) & np.isinf(b) & (np.sign(a) == np.sign(b)))))
        fin = np.isfinite(a) & np.isfinite(b)
        d = float(np.max(np.abs(a[fin] - b[fin]))) if fin.any() else 0.0
        per[c] = dict(max_abs=d, nan_mismatch=nan_mm, inf_mismatch=inf_mm, n_finite=int(fin.sum()))
        worst = max(worst, d)
        if nan_mm:
            res["reasons"].append(f"nan_pattern:{c}")
        if inf_mm:
            res["reasons"].append(f"inf_pattern:{c}")
    res.update(max_abs=worst, per_column=per)
    if worst > tol:
        res["reasons"].append("max_abs_exceeds_tol")
    res["status"] = "PASS" if not res["reasons"] else "FAIL"
    return res


# ----------------------------------------------------------------------------- negative fixtures
def negative_fixtures(feat_mod, H_chunk, freqs, old_obs):
    """Every deliberately false input must FAIL its specific test (TASK_HANDOFF R-04 §5, R-14 §7, R-12/13 fixtures)."""
    fx = []

    def rec(name, test, expect_fail, failed, detail=None):
        fx.append(dict(fixture=name, test=test, expect_fail=expect_fail, observed_fail=bool(failed), ok=(bool(failed) == expect_fail), detail=detail))
    feat = feat_mod.extract(H_chunk, freqs); obs = observer_v3(H_chunk); old_valid = old_obs(H_chunk)[5]
    base = r04_compare(feat, obs, old_valid)
    rec("baseline_chunk", "all_R04", False, any(v.any() for v in base.values()))
    f2 = dict(feat); f2["tap"] = np.array(feat["tap"]).copy(); f2["tap"][3] += 1
    rec("offset_tap_one_record", "tap", True, r04_compare(f2, obs, None)["tap"].any())
    f3 = dict(feat); f3["branch"] = np.array(feat["branch"]).copy(); f3["branch"][5] = 1 - f3["branch"][5]
    rec("swap_branch_one_record", "branch", True, r04_compare(f3, obs, None)["branch"].any())
    f4 = dict(feat); f4["valid"] = np.array(feat["valid"]).copy(); f4["valid"][7] = ~f4["valid"][7]
    rec("flip_feature_valid", "valid_g5", True, r04_compare(f4, obs, None)["valid_g5"].any())
    obs_sw = observer_v3(H_chunk[:, :, ::-1])                                # RX port order swapped, reference held fixed
    msw = r04_compare(feat, obs_sw, None)
    rec("swap_rx_port_order", "s_fp_common_tap|branch", True, bool(msw["s_fp_common_tap"].any() or msw["branch"].any()),
        dict(s_mismatch=int(msw["s_fp_common_tap"].sum()), branch_mismatch=int(msw["branch"].sum())))
    # detector-valid but tap+80 > 4*257: impulse near the end of the padded CIR
    k = np.arange(257); d0 = 1000
    Himp = np.zeros((1, 257, 2), complex); Himp[0, :, 0] = np.exp(-2j * np.pi * k * d0 / N_TAPS); Himp[0, :, 1] = 0.5 * Himp[0, :, 0]
    fe = feat_mod.extract(Himp, freqs); oe = observer_v3(Himp)
    rec("edge_tap_plus80_beyond_cir", "valid_fp_vs_valid_g5_separate", False,
        not (bool(oe["valid_fp"][0]) and not bool(oe["valid_g5"][0]) and not bool(fe["valid"][0]) and int(fe["tap"][0]) == int(oe["tap"][0])),
        dict(tap=int(oe["tap"][0]), valid_fp=bool(oe["valid_fp"][0]), valid_g5=bool(oe["valid_g5"][0]), features_valid=bool(fe["valid"][0])))
    # R-14 classification fixtures
    t = np.arange(N_TAPS, dtype=float); pulse = np.exp(-0.5 * ((t - 500) / 3) ** 2)
    def cir_of(a0, a1, extra=None, centre=500):
        pl = pulse if centre == 500 else np.exp(-0.5 * ((t - centre) / 3) ** 2)
        c = np.zeros((N_TAPS, 2), complex); c[:, 0] = a0 * pl; c[:, 1] = a1 * pl
        if extra is not None:
            c += extra
        return c
    def cls(c, tap=500):
        J, st = build_J(c, tap)
        return st if J is None else classify_J(J)["status"], (None if J is None else classify_J(J))
    st, r = cls(cir_of(1.0, 1e-9)); rec("tiny_nonzero_one_port", "weak_flag_valid", False, not (st == "VALID" and r["weak_port"]), dict(status=st, u=r and r["u"]))
    st, r = cls(cir_of(1.0, 1.0j)); rec("balanced_two_port", "not_weak", False, not (st == "VALID" and not r["weak_port"] and abs(r["u"] - 0.5) < 1e-12), dict(status=st, u=r and r["u"]))
    st, r = cls(cir_of(0.8, 0.3 - 0.2j)); rec("rank1_jones", "q_zero", False, not (st == "VALID" and r["q_W"] <= 1e-12), dict(q=r and r["q_W"]))
    st, r = cls(np.zeros((N_TAPS, 2), complex)); rec("null_port_0_over_0", "NULL_PORT", False, st != "NULL_PORT", dict(status=st))
    c = cir_of(1.0, 0.5); c[499, 0] = np.nan; st, _ = cls(c); rec("nan_in_window", "NONFINITE", False, st != "NONFINITE", dict(status=st))
    c = cir_of(1.0, 0.5); c[501, 1] = np.inf; st, _ = cls(c); rec("inf_in_window", "NONFINITE", False, st != "NONFINITE", dict(status=st))
    Jneg = np.array([[1.0, 2.0], [2.0, 1.0]], complex); rn = classify_J(Jneg)
    rec("significantly_negative_det", "NEGATIVE_DET", False, rn["status"] != "NEGATIVE_DET", dict(status=rn["status"], d_raw=rn["d_raw"]))
    st, _ = cls(cir_of(1.0, 0.5), tap=9); rec("window_lower_boundary", "INVALID_WINDOW", False, st != "INVALID_WINDOW", dict(status=st))
    st, _ = cls(cir_of(1.0, 0.5), tap=N_TAPS - 12); rec("window_upper_boundary", "INVALID_WINDOW", False, st != "INVALID_WINDOW", dict(status=st))
    st, _ = cls(cir_of(1.0, 0.5j, centre=12), tap=10); rec("window_lower_inside", "VALID", False, st != "VALID", dict(status=st))
    st, _ = cls(cir_of(1.0, 0.5j, centre=N_TAPS - 14), tap=N_TAPS - 13); rec("window_upper_inside", "VALID", False, st != "VALID", dict(status=st))
    # Reference-comparison fixtures (R-12/R-13 lineage guard)
    keys = ["case", "pose_id"]; ref = pd.DataFrame(dict(case=["A"] * 4, pose_id=[1, 2, 3, 4], v=[0.1, np.nan, 0.3, 0.4]))
    good = ref.copy()
    rec("ref_identical", "compare_reference_v3", False, compare_reference_v3(good, ref, keys, ["v"], 1e-9)["status"] != "PASS")
    x = ref.copy(); x.loc[1, "v"] = 0.2; rec("ref_nan_pattern", "compare_reference_v3", True, compare_reference_v3(x, ref, keys, ["v"], 1e-9)["status"] == "FAIL")
    x = ref.copy(); x.loc[2, "v"] = np.inf; rec("ref_inf_vs_finite", "compare_reference_v3", True, compare_reference_v3(x, ref, keys, ["v"], 1e-9)["status"] == "FAIL")
    rec("ref_inf_vs_finite_OLD_compare_reference", "p0_preflight.compare_reference (proposer patch)", True,
        _old_compare_fails(x, ref, keys, ["v"]), "documents the v0.2 defect if this fixture is not ok")
    x = ref.iloc[:3]; rec("ref_absent_key", "compare_reference_v3", True, compare_reference_v3(x, ref, keys, ["v"], 1e-9)["status"] == "FAIL")
    x = pd.concat([ref, ref.iloc[[0]]]); rec("ref_duplicate_key", "compare_reference_v3", True, compare_reference_v3(x, ref, keys, ["v"], 1e-9)["status"] == "FAIL")
    sw = observer_v3(H_chunk[:, :, ::-1]); den = sw["p"].sum(1); s_sw = (sw["p"][:, 0] - sw["p"][:, 1]) / den
    a = pd.DataFrame(dict(case="X", pose_id=np.arange(len(den)), s_fp=s_sw)); b = pd.DataFrame(dict(case="X", pose_id=np.arange(len(den)), s_fp=np.asarray(feat["s_fp"], float)))
    rec("ref_swapped_port_mapping", "compare_reference_v3", True, compare_reference_v3(a, b, keys, ["s_fp"], 1e-9)["status"] == "FAIL")
    return fx


_OLD = {}


def _old_compare_fails(new, ref, keys, cols):
    try:
        return _OLD["mod"].compare_reference(new, ref, keys, cols, 1e-9)["status"] == "FAIL"
    except Exception:  # noqa: BLE001
        return True


# ----------------------------------------------------------------------------- main run
def run(args):
    root = Path(args.repo_root).resolve(); scope = root / SCOPE_REL; out = Path(args.out).resolve()
    if out.exists():
        raise FileExistsError(f"append-only output exists: {out}")
    out.mkdir(parents=True)
    checks = {}; problems = []; status = "BLOCKED"

    def record(key, cls, stat, obs):
        checks[key] = dict(**{"class": cls, "status": stat, "observed": obs})
    try:
        old = load_module(scope / "scripts/p0_preflight.py", "p0_preflight_v02"); _OLD["mod"] = old
        # ---- provenance and immutability
        imm = {p: dict(expected=h, observed=sha(scope / p) if (scope / p).is_file() else None) for p, h in V02_IMMUTABLE.items()}
        record("V02_FILES_IMMUTABLE", "CORE", "PASS" if all(v["expected"] == v["observed"] for v in imm.values()) else "FAIL", imm)
        v03 = {p: (sha(scope / p) if (scope / p).is_file() else None) for p in V03_DOCS}
        wf = root / WORKFLOW_REL; v03[WORKFLOW_REL] = sha(wf) if wf.is_file() else None
        record("V03_DOC_SOURCE_SHA256_RECORDED", "CORE", "PASS" if all(v03.values()) else "FAIL", v03)
        lock = json.loads((scope / "config/INPUT_LOCK_v2.json").read_text())
        listed, missing, wrong, t4 = old.verify_hashes(root, lock)
        jsave(out / "P0V3_INPUT_HASH_CHECKS.json", dict(assets=listed, trace=t4))
        record("INPUT_CORE_SHA256", "CORE", "FAIL" if wrong else ("BLOCKED" if missing else "PASS"), dict(missing=missing, mismatch=wrong))
        record("INPUT_T4_SHA256", "T4_ONLY", t4["status"], {k: t4[k] for k in ("status", "errors_count")})
        if wrong or missing:
            raise RuntimeError("core input hash failure")
        manifest = json.loads((root / "research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text()); manifest["_lock_assets"] = lock["assets"]
        align, summary, _ = old.align_poses(root, manifest)
        record("R05_POSE_JOIN", "CORE", "PASS", dict(rows=len(align), timeline=int((align.stratum == "TIMELINE").sum())))
        src = next(x["path"] for x in lock["assets"] if x["path"].endswith("/features.py"))
        feat_mod = old.load_source(root / src)
        freqs = np.load(root / next(e for e in lock["assets"] if e["kind"] == "FREQUENCY")["path"], allow_pickle=False)
        # ---- R-04 + R-14 over all cases/channels
        par_rows = []; adversarial = []; los_rows = []; g5_rows = []; neg_chunk = None
        for case in manifest["cases"]:
            name = case["id"]; ids = np.array([x["pose_id"] for x in json.loads((root / case["samples_path"]).read_text())], int)
            for channel, key in (("full", "full_path"), ("los", "los_path")):
                Hall = np.load(root / case[key], mmap_mode="r", allow_pickle=False)
                if Hall.shape != (len(ids), 257, 2, 2):
                    raise ValueError(f"{name}/{channel} H shape {Hall.shape}")
                agg = dict(case=name, channel=channel, n=len(ids))
                mm_tot = {}; n_fp_not_g5 = 0; n_port_tap_diff = 0; n_own_differs = 0
                for lo in range(0, len(ids), 64):
                    hi = min(lo + 64, len(ids)); Hc = np.asarray(Hall[lo:hi, :, :, 0])           # SAME tx index 0
                    if neg_chunk is None:
                        neg_chunk = Hc.copy()
                    feat = feat_mod.extract(Hc, freqs); obs = observer_v3(Hc)
                    oc, otap, obr, osfp, ologp, ovalid = old.independent_observer(Hc)
                    mm = r04_compare(feat, obs, ovalid)
                    for k2, v in mm.items():
                        mm_tot[k2] = mm_tot.get(k2, 0) + int(v.sum())
                        for j in np.flatnonzero(v)[: max(0, 20 - len(adversarial))]:
                            adversarial.append(dict(case=name, channel=channel, pose_id=int(ids[lo + j]), test=k2, feat_tap=int(feat["tap"][j]), obs_tap=int(obs["tap"][j]),
                                                    feat_branch=int(feat["branch"][j]), obs_branch=int(obs["branch"][j])))
                    n_fp_not_g5 += int((obs["valid_fp"] & ~obs["valid_g5"]).sum())
                    n_port_tap_diff += int((obs["port_taps"][:, 0] != obs["port_taps"][:, 1]).sum())
                    po = obs["p_own_tap"]; s_own = (po[:, 0] - po[:, 1]) / (po[:, 0] + po[:, 1])
                    n_own_differs += int((np.abs(s_own - np.asarray(feat["s_fp"], float)) > TOL["s_fp_parity_abs"]).sum())
                    g = pd.DataFrame(dict(case=name, channel=channel, pose_id=ids[lo:hi]))
                    for f in feat_mod.GROUPS["G5"]:
                        g[f] = np.asarray(feat[f], float)
                    den = obs["p"].sum(1); g["s_fp"] = np.where(den > np.finfo(float).tiny, (obs["p"][:, 0] - obs["p"][:, 1]) / np.where(den > 0, den, 1), np.nan)
                    g["log_fp_power_obs"] = np.log10(np.maximum(den, np.finfo(float).tiny))
                    g5_rows.append(g)
                    if channel == "los":
                        cir = np.fft.ifft(Hc * (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(257) / 256))[None, :, None], n=N_TAPS, axis=1) * 257
                        for j in range(hi - lo):
                            J, st = build_J(cir[j], int(obs["tap"][j]))
                            r = classify_J(J) if J is not None else dict(status=st)
                            row = dict(case=name, route=case["route"], pose_id=int(ids[lo + j]), tap=int(obs["tap"][j]), branch=int(obs["branch"][j]))
                            row.update({k3: r.get(k3, np.nan) for k3 in ("status", "a", "b", "t", "d_raw", "u", "weak_port", "q_W", "eps_rho", "coherence_sq")})
                            if row["status"] == "VALID":
                                row.update(r14_identities(r))
                            los_rows.append(row)
                agg.update({f"mismatch_{k2}": v for k2, v in mm_tot.items()}, n_fp_valid_not_g5_valid=n_fp_not_g5, n_port_taps_differ=n_port_tap_diff,
                           n_per_port_tap_s_differs_from_features=n_own_differs)
                par_rows.append(agg)
        PAR = pd.DataFrame(par_rows); PAR.to_csv(out / "P0V3_TAP_BRANCH_PARITY.csv", index=False)
        mcols = [c for c in PAR.columns if c.startswith("mismatch_")]
        tot = int(PAR[mcols].to_numpy().sum())
        record("R04_TAP_BRANCH_VALID_EXACT", "CORE", "PASS" if (tot == 0 and int(PAR.n.sum()) == 19038) else "FAIL",
               dict(records=int(PAR.n.sum()), total_mismatches=tot, per_test={c: int(PAR[c].sum()) for c in mcols}, adversarial_first20=adversarial,
                    n_fp_valid_not_g5_valid=int(PAR.n_fp_valid_not_g5_valid.sum()), n_port_taps_differ_info=int(PAR.n_port_taps_differ.sum()),
                    n_per_port_tap_s_differs_from_features=int(PAR.n_per_port_tap_s_differs_from_features.sum()),
                    common_tap_discrimination="features.s_fp equals the common-tap extraction in every row while the per-port-tap alternative differs in the rows counted here",
                    note="valid_g5 vs features.valid and valid_fp vs old observer flag compared separately; their mutual equality is NOT asserted"))
        # ---- R-14 outputs
        L = pd.DataFrame(los_rows).merge(align[["case", "pose_id", "stratum", "phase"]], on=["case", "pose_id"], how="left", validate="one_to_one")
        if L[["stratum", "phase"]].isna().any().any():
            raise RuntimeError("LoS stratum alignment")
        L.to_csv(out / "P0V3_LOS_PORT_BALANCE.csv", index=False, float_format="%.17g")
        V = L[L.status == "VALID"]
        summ = []
        for keys_, g in [(("ALL", "ALL", "ALL"), L)] + [((c, s, p), gg) for (c, s, p), gg in L.groupby(["case", "stratum", "phase"])] + \
                [(("ALL", s, "ALL"), gg) for s, gg in L.groupby("stratum")] + [((c, s, "ALL"), gg) for (c, s), gg in L.groupby(["case", "stratum"])]:
            gv = g[g.status == "VALID"]; w = gv[gv.weak_port.astype(bool)]; s_ = gv[~gv.weak_port.astype(bool)]
            row = dict(case=keys_[0], stratum=keys_[1], phase=keys_[2], n_total=len(g), n_valid=len(gv), n_weak=len(w),
                       fraction_weak=len(w) / len(gv) if len(gv) else np.nan,
                       n_weak_u_lt_0p02=int((gv.u < 0.02).sum()), n_weak_u_lt_0p10=int((gv.u < 0.10).sum()))
            for nm, sub in (("all", gv), ("weak", w), ("strong", s_)):
                for qq in (0.5, 0.95, 0.99):
                    row[f"q_W_{nm}_q{int(qq*100)}"] = float(sub.q_W.quantile(qq)) if len(sub) else np.nan
                    row[f"eps_{nm}_q{int(qq*100)}"] = float(sub.eps_rho.quantile(qq)) if len(sub) else np.nan
            summ.append(row)
        S = pd.DataFrame(summ); S.to_csv(out / "P0V3_WEAK_PORT_SUMMARY.csv", index=False, float_format="%.10g")
        tl = V[V.stratum == "TIMELINE"]
        counts = dict(n_valid=len(V), n_weak=int(V.weak_port.astype(bool).sum()), timeline_weak=int(tl.weak_port.astype(bool).sum()), timeline_n=len(tl),
                      n_total=len(L), status_counts=L.status.value_counts().to_dict())
        # reconciliation against the historic P0 LOS_FLOOR (same math, same input)
        ref = read_csv_cols(scope / P0_RUN_REF / "LOS_FLOOR.csv", ["case", "pose_id", "q_W", "eps_rho", "status"])
        rr = L.merge(ref, on=["case", "pose_id"], how="outer", suffixes=("", "_p0"), indicator=True, validate="one_to_one")
        both = rr[rr._merge == "both"]
        rec_ok = dict(only_new=int((rr._merge == "left_only").sum()), only_p0=int((rr._merge == "right_only").sum()),
                      status_mismatch=int((both.status != both.status_p0).sum()),
                      q_max_abs=float(np.nanmax(np.abs(both.q_W - both.q_W_p0))), eps_max_abs=float(np.nanmax(np.abs(both.eps_rho - both.eps_rho_p0))))
        idq = dict(q_identity_rel_max=float(V.q_identity_rel.max()), eps_identity_abs_max=float(V.eps_identity_abs.max()),
                   u_inverse_abs_max=float(V.u_inverse_abs.max()) if V.inverse_checked.any() else None, n_inverse_checked=int(V.inverse_checked.sum()),
                   n_inverse_skipped=int((~V.inverse_checked.astype(bool)).sum()))
        id_ok = (idq["q_identity_rel_max"] <= TOL["r14_q_identity_rel"] and idq["eps_identity_abs_max"] <= TOL["r14_eps_identity_abs"]
                 and (idq["u_inverse_abs_max"] is None or idq["u_inverse_abs_max"] <= TOL["r14_u_inverse_abs"]))
        cnt_ok = all(counts[k] == v for k, v in EXPECTED_R14.items())
        rc_ok = rec_ok["only_new"] == 0 and rec_ok["only_p0"] == 0 and rec_ok["status_mismatch"] == 0 and rec_ok["q_max_abs"] <= TOL["p0_reconcile_abs"] \
            and rec_ok["eps_max_abs"] <= TOL["p0_reconcile_abs"]
        mqa = dict(tolerances_declared_before_run=TOL, identities=idq, identities_pass=bool(id_ok), counts=counts, expected_counts_audit_guard=EXPECTED_R14,
                   counts_pass=bool(cnt_ok), p0_reconciliation=rec_ok, p0_reconciliation_pass=bool(rc_ok),
                   weak_port_role="boolean diagnostic flag; not an invalid status; not an exclusion mask; all valid rows retained",
                   channel_scope="LoS only (Full M1 metrics and label relations prohibited before FROZEN)")
        jsave(out / "P0V3_R14_MATH_QA.json", mqa)
        record("R14_MATH_IDENTITIES", "CORE", "PASS" if id_ok else "FAIL", idq)
        record("R14_COUNTS_AUDIT_GUARD", "CORE", "PASS" if cnt_ok else "FAIL", dict(counts=counts, expected=EXPECTED_R14))
        record("R14_P0_RECONCILIATION", "CORE", "PASS" if rc_ok else "FAIL", rec_ok)
        # ---- R-02/R-12/R-13 lineage with hardened comparison
        refs = json.loads((scope / "config/P0_REFERENCES_v0.2.json").read_text())["references"]
        G = pd.concat(g5_rows, ignore_index=True); full = G[G.channel == "full"]; G5 = list(feat_mod.GROUPS["G5"])
        rp = {}
        for rid in ("R-02", "R-13a"):
            rp[rid + "_table_sha256_match"] = sha(root / refs[rid]["table"]) == refs[rid]["sha256"]
        hp = read_csv_cols(root / refs["R-02"]["table"], ["case", "pose_id", "sF_+0", "log_fp_power"]).rename(columns={"sF_+0": "s_fp"})
        rp["R-02"] = compare_reference_v3(full, hp, ["case", "pose_id"], ["s_fp"], refs["R-02"]["tolerance_abs"])
        rp["R-12"] = compare_reference_v3(full, hp, ["case", "pose_id"], ["log_fp_power"], refs["R-12"]["tolerance_abs"])
        um = read_csv_cols(root / refs["R-13a"]["table"], refs["R-13a"]["columns"])
        rp["R-13a"] = compare_reference_v3(full, um, ["case", "pose_id"], G5, refs["R-13a"]["tolerance_abs"])
        if not rp["R-02_table_sha256_match"]:
            rp["R-02"]["status"] = rp["R-12"]["status"] = "FAIL"
        if not rp["R-13a_table_sha256_match"]:
            rp["R-13a"]["status"] = "FAIL"
        b = refs["R-13b"]
        if args.g5_artifact and Path(args.g5_artifact).is_file():
            art = read_csv_cols(args.g5_artifact, b["columns"], label_ok=False)
            rp["R-13b"] = compare_reference_v3(G, art, ["case", "channel", "pose_id"], G5, b["tolerance_abs"])
            rp["R-13b"]["artifact_sha256"] = sha(args.g5_artifact)
            if args.archive_r13b:                                                  # F-16: label-free projection archived before expiry
                art.to_csv(out / "R13B_REFERENCE_PROJECTION_KEYS_G5.csv.gz", index=False, float_format="%.17g")
                rp["R-13b"]["archived_projection"] = "R13B_REFERENCE_PROJECTION_KEYS_G5.csv.gz (key + G5 columns only; labels never loaded)"
        else:
            rp["R-13b"] = dict(status="BLOCKED_REFERENCE_UNAVAILABLE")
        jsave(out / "P0V3_REFERENCE_PARITY.json", rp)
        for rid in ("R-02", "R-12", "R-13a"):
            record(f"{rid.replace('-', '')}_LINEAGE", "CORE", rp[rid]["status"], {k: rp[rid].get(k) for k in ("coverage", "max_abs", "reasons")})
        record("R13b_LINEAGE", "SUPPLEMENTARY", rp["R-13b"]["status"], {k: rp["R-13b"].get(k) for k in ("coverage", "max_abs", "reasons", "artifact_sha256")})
        record("R13_INDEPENDENCE_NOTE", "MEASURED", "MEASURED", "R-13a and R-13b share upstream (run 39376076166); not independent science replicates")
        # ---- negative fixtures
        fx = negative_fixtures(feat_mod, neg_chunk, freqs, old.independent_observer)
        jsave(out / "P0V3_NEGATIVE_FIXTURES.json", dict(fixtures=fx))
        bad = [f for f in fx if not f["ok"] and not f["fixture"].endswith("_OLD_compare_reference")]
        old_def = [f for f in fx if f["fixture"].endswith("_OLD_compare_reference")][0]
        record("NEGATIVE_FIXTURES", "CORE", "PASS" if not bad else "FAIL", dict(n=len(fx), failed=[f["fixture"] for f in bad]))
        record("V02_COMPARE_REFERENCE_INF_DEFECT", "MEASURED", "DEFECT_CONFIRMED" if not old_def["ok"] else "NOT_REPRODUCED",
               "p0_preflight.compare_reference treats inf vs finite as equal (excluded from the finite diff); hardened in compare_reference_v3")
        # ---- label isolation
        viol = [o for o in _OPENED if any(any(t in c.lower() for t in LABEL_PATTERNS) for c in o["columns"])]
        record("LABEL_ISOLATION", "CORE", "PASS" if not viol else "FAIL", dict(tabular_reads=_OPENED, violations=viol))
        core_fail = any(v["class"] == "CORE" and v["status"] != "PASS" for v in checks.values())
        status = "CORE_FAIL" if core_fail else "TECHNICAL_QA_ONLY"
    except Exception as exc:  # noqa: BLE001
        problems.append(dict(error=str(exc), traceback=traceback.format_exc())); record("UNHANDLED", "CORE", "FAIL", str(exc)); status = "CORE_FAIL"
    finally:
        try:
            exe = args.execution_git_sha or subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        except Exception:  # noqa: BLE001
            exe = None
        st = dict(role="IMPLEMENTER", contract_id="POL-XCORR-001", phase="P0V3_DELTA_PREFLIGHT_ONLY", contract_status="DRAFT_v0.3",
                  base_git_sha=BASE_SHA, governance_git_sha=GOV_SHA, execution_git_sha=exe, result_status=status, independent_auditor="NONE (R-10 pending)",
                  scientific_verdict="NOT_ISSUED", s0_p1_p2_p3="BLOCKED (DRAFT)", checks=checks, problems=problems)
        jsave(out / "P0V3_STATUS.json", st)
        man = dict(schema="POL_XCORR_P0V3_MANIFEST_V1", role="IMPLEMENTER", contract_id="POL-XCORR-001", timestamp_utc=datetime.now(timezone.utc).isoformat(),
                   base_git_sha=BASE_SHA, governance_git_sha=GOV_SHA, execution_git_sha=exe,
                   execution_git_sha_is_40hex=bool(exe and len(exe) == 40 and all(c in "0123456789abcdef" for c in exe)),
                   v03_document_and_source_sha256=checks.get("V03_DOC_SOURCE_SHA256_RECORDED", {}).get("observed"),
                   input_lock_sha256=V02_IMMUTABLE["config/INPUT_LOCK_v2.json"], command=sys.argv,
                   versions=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__), hardware=platform.platform(),
                   result_status=status, scientific_verdict="NOT_ISSUED", label_free=True)
        man["files"] = {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != "MANIFEST.json"}
        jsave(out / "MANIFEST.json", man)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--g5-artifact"); ap.add_argument("--archive-r13b", action="store_true"); ap.add_argument("--execution-git-sha")
    a = ap.parse_args(); s = run(a)
    print(json.dumps(dict(status=s, output=a.out)))
    return 0 if s == "TECHNICAL_QA_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
