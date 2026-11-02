"""MBVAR-INFO-001 A010 prospective D2/D3/D4/D6 checks (IMPLEMENTER, SCIENCE DRAFT).

All covariance and receipt diagnostics are independent of the optimizer.  This
module may be used on SMOKE 900/901 and archived DEV2 only until a signed freeze.
It does not authorize opening DEV3, HOLDOUT2, reserve, or physical RT.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np

COV_EQ_TOL = 1e-10
GENERATOR_TOL = 1e-10
C10_COND_LOG_TOL = 1e-3
G5_NUMERIC_GATE_IDS = (
    "RECEIPT_INTEGRITY", "GENERATOR_LAW", "CROSS_FIELD_COV_EQUIVALENCE",
    "SOLVER_REPRO", "STATE_COST_REPRO", "FULL_C10_REPRO", "STATUS_REPRO", "NO_WRONG_BASIN",
    "ITER_CAP", "PROBE_POWER", "LINEAR_EXACT", "KINK_FIXTURES", "rows",
)
HISTORICAL_FAILURES = (
    "C3 run 40992589158 FAIL",
    "C3V4 run 41005158792 FAIL",
    "S1V3/S1V4 DEV2 H1 LOW POSE_HIGH tan FAIL / H2 tan DID sign reversal",
)


def array_sha(a):
    """Hash includes dtype, shape, and complete C-order binary payload."""
    a = np.ascontiguousarray(np.asarray(a))
    return hashlib.sha256(a.dtype.str.encode() + str(a.shape).encode()
                          + a.tobytes(order="C")).hexdigest()


def make_array_index(arrays, fields, zip_file):
    """Per-shard declaration; the ZIP and JSON are separately MANIFEST hashed."""
    return dict(schema="A010_ARRAY_INDEX_V1", fields=sorted(map(int, fields)),
                zip_name=Path(zip_file).name,
                zip_sha256=_sha_file(zip_file),
                array_sha256={k: array_sha(v) for k, v in sorted(arrays.items())},
                array_dtype={k: np.asarray(v).dtype.str for k, v in sorted(arrays.items())},
                array_shape={k: list(np.asarray(v).shape) for k, v in sorted(arrays.items())})


def _sha_file(file):
    h = hashlib.sha256()
    with open(file, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _check_array_schema(key, a):
    """Fail closed against reshaping, little/big endian and nonfinite data."""
    a = np.asarray(a)
    if a.ndim and any(n == 0 for n in a.shape):
        raise ValueError("ERR_A010_ZERO_LENGTH_ARRAY " + key)
    if a.dtype.hasobject or a.dtype.kind not in "fiuU":
        raise ValueError("ERR_A010_ARRAY_DTYPE " + key)
    if a.dtype.kind in "fiu" and (not a.dtype.isnative or not np.isfinite(a).all()):
        raise ValueError("ERR_A010_ARRAY_ENDIAN_NONFINITE " + key)
    p = key.split("|")
    if p[0] == "MAT":
        if (len(p) not in (5, 6) or not p[1].isdigit() or
                (p[-1] == "Sig_true") == (len(p) == 6) or
                p[-1] not in ("Sig_true", "Sig_model")):
            raise ValueError("ERR_A010_MAT_SCHEMA " + key)
        if a.dtype.str != "<f8" or a.ndim != 2 or a.shape[0] != a.shape[1] or a.shape[0] % 2:
            raise ValueError("ERR_A010_MAT_DTYPE_SHAPE " + key)
        if not np.allclose(a, a.T, rtol=0, atol=1e-10 * max(float(np.max(np.abs(a))), 1e-300)):
            raise ValueError("ERR_A010_MAT_ASYMMETRY " + key)
        if np.linalg.eigvalsh(0.5 * (a + a.T))[0] <= 0:
            raise ValueError("ERR_A010_MAT_NOT_SPD " + key)
        return
    if p[0] == "TRUTH":
        if len(p) != 5 or not p[1].isdigit() or p[-1] not in (
                "Xtrue", "poses", "dts", "ds_true", "dth_true", "prior_P0", "mu", "pose_keys_sha"):
            raise ValueError("ERR_A010_TRUTH_SCHEMA " + key)
    elif len(p) < 5 or not p[0].isdigit():
        raise ValueError("ERR_A010_OBSERVATION_SCHEMA " + key)
    suffix = p[-1]
    if suffix in ("pose_keys_sha",):
        if a.dtype.kind != "U" or a.ndim != 0:
            raise ValueError("ERR_A010_STRING_SCHEMA " + key)
    elif suffix == "taps":
        if a.ndim != 1 or a.dtype.kind not in "iu" or np.any(a < 0) or np.any(a >= 4096):
            raise ValueError("ERR_A010_TAP_SCHEMA " + key)
    elif suffix in ("Sig_true_fp", "Sig_model_fp"):
        if a.dtype.str != "<f8" or a.ndim != 1:
            raise ValueError("ERR_A010_FINGERPRINT_SCHEMA " + key)
    elif suffix in ("z", "mu"):
        if a.dtype.str != "<f8" or a.ndim != 2 or a.shape[1] != 2:
            raise ValueError("ERR_A010_OBS_SHAPE " + key)
    elif suffix in ("Xtrue", "poses"):
        if a.dtype.str != "<f8" or a.ndim != 2 or a.shape[1] not in (3, 4):
            raise ValueError("ERR_A010_GEOMETRY_SHAPE " + key)
    elif suffix == "prior_P0":
        if a.dtype.str != "<f8" or a.shape != (4, 4):
            raise ValueError("ERR_A010_PRIOR_SHAPE " + key)
    elif suffix in ("x0",):
        if a.dtype.str != "<f8" or a.shape != (4,):
            raise ValueError("ERR_A010_X0_SHAPE " + key)
    elif suffix in ("ds_m", "gy_m", "dts", "ds_true", "dth_true"):
        if a.dtype.str != "<f8" or a.ndim != 1:
            raise ValueError("ERR_A010_CONTROL_SHAPE " + key)
    else:
        raise ValueError("ERR_A010_UNREGISTERED_ARRAY " + key)


def verify_receipt_index(zip_path, index_path, output_hashes):
    """Verification occurs BEFORE any estimator value is read or used."""
    zip_path, index_path = Path(zip_path), Path(index_path)
    for path in (zip_path, index_path):
        if path.name not in output_hashes or _sha_file(path) != output_hashes[path.name]:
            raise ValueError("ERR_A010_MANIFEST_SHA " + path.name)
    idx = json.loads(index_path.read_text())
    if idx.get("schema") != "A010_ARRAY_INDEX_V1" or idx.get("zip_name") != zip_path.name:
        raise ValueError("ERR_A010_ARRAY_INDEX_SCHEMA")
    if idx.get("zip_sha256") != _sha_file(zip_path):
        raise ValueError("ERR_A010_ARRAY_INDEX_ZIP_SHA")
    with zipfile.ZipFile(zip_path) as z:
        members = z.namelist()
        if len(members) != len(set(members)) or any(not n.endswith(".npy") or "/" in n for n in members):
            raise ValueError("ERR_A010_ZIP_DUPLICATE_OR_PATH")
        names = [n[:-4] for n in members]
    if not names or len(names) != len(set(names)) or set(names) != set(idx["array_sha256"]):
        raise ValueError("ERR_A010_ARRAY_SET")
    if set(names) != set(idx["array_dtype"]) or set(names) != set(idx["array_shape"]):
        raise ValueError("ERR_A010_ARRAY_META_SET")
    fields = set(map(int, idx["fields"]))
    if not fields or any(not isinstance(f, int) for f in idx["fields"]):
        raise ValueError("ERR_A010_FIELDS_SCHEMA")
    out = {}
    with np.load(zip_path, allow_pickle=False) as z:
        for k in names:
            a = z[k]
            _check_array_schema(k, a)
            if (array_sha(a) != idx["array_sha256"][k] or
                    a.dtype.str != idx["array_dtype"][k] or
                    list(a.shape) != idx["array_shape"][k]):
                raise ValueError("ERR_A010_ARRAY_SHA_DTYPE_SHAPE " + k)
            p = k.split("|")
            if int(p[1] if p[0] in ("MAT", "TRUTH") else p[0]) not in fields:
                raise ValueError("ERR_A010_FIELD_SCOPE " + k)
            out[k] = np.array(a, copy=True)
    actual = {int(k.split("|")[0]) for k in names if k.split("|")[0].isdigit()}
    if actual != fields:
        raise ValueError("ERR_A010_FIELD_COVERAGE")
    return out, dict(fields_count=len(fields), n_arrays=len(out),
                     zip_sha256=idx["zip_sha256"], array_sha256=idx["array_sha256"])


def verify_estimator_inputs(rec, key, inputs, sigma_model, taps, arm, truth_arrays=None):
    expected = {key + "|" + suffix: value for suffix, value in inputs.items()
                if suffix in ("z", "x0", "ds_m", "gy_m")}
    expected[key + "|taps"] = taps
    p = key.split("|")
    mk = "MAT|" + "|".join(p[:3]) + "|" + arm + "|Sig_model"
    expected[mk] = sigma_model
    if truth_arrays:
        expected.update(truth_arrays)
    missing = sorted(set(expected) - set(rec))
    bad = [k for k, a in expected.items()
           if k in rec and array_sha(a) != array_sha(rec[k])]
    return dict(pass_=not missing and not bad, n_checked=len(expected),
                n_missing=len(missing), n_byte_mismatches=len(bad),
                missing=missing, mismatches=bad,
                estimator_uses_truth_covariance=False)


def covariance_equivalence(rec, tol=COV_EQ_TOL, expected_fields=None):
    groups = defaultdict(dict)
    for key, a in rec.items():
        if not key.startswith("MAT|"):
            continue
        p = key.split("|")
        if len(p) not in (5, 6):
            raise ValueError("ERR_A010_MAT_SCHEMA " + key)
        field = int(p[1])
        g = "|".join(p[2:])
        if field in groups[g]:
            raise ValueError("ERR_A010_DUPLICATE_MAT " + key)
        groups[g][field] = np.asarray(a)
    details = []
    for g, fields in sorted(groups.items()):
        fs = sorted(fields)
        ref = np.asarray(fields[fs[0]], dtype=np.float64)
        mn = math.inf
        for f in fs:
            a = fields[f]
            if (a.dtype.str != "<f8" or a.shape != ref.shape or a.ndim != 2 or
                    a.shape[0] != a.shape[1]):
                raise ValueError("ERR_A010_CROSS_FIELD_SCHEMA " + g)
            if np.max(np.abs(a - a.T)) > 1e-10 * max(float(np.max(np.abs(a))), 1e-300):
                raise ValueError("ERR_A010_CROSS_FIELD_ASYMMETRY " + g)
            mn = min(mn, float(np.linalg.eigvalsh(a)[0]))
        dmax = max(float(np.max(np.abs(fields[f] - ref)) /
                         max(float(np.max(np.abs(ref))), 1e-300)) for f in fs)
        dF = max(float(np.linalg.norm(fields[f] - ref, ord="fro") /
                       max(float(np.linalg.norm(ref, ord="fro")), 1e-300)) for f in fs)
        enough = expected_fields is None or set(fs) == set(expected_fields)
        details.append(dict(group=g, n_fields=len(fs), reference_field=fs[0],
                            delta_max=dmax, delta_F=dF, min_eig=mn,
                            exact_schema=True, field_coverage=bool(enough),
                            pass_=bool(enough and mn > 0 and dmax <= tol and dF <= tol)))
    return dict(pass_=bool(details and all(x["pass_"] for x in details)),
                n_groups=len(details), n_groups_multi_field=sum(x["n_fields"] > 1 for x in details),
                n_failed=sum(not x["pass_"] for x in details),
                delta_max=max((x["delta_max"] for x in details), default=None),
                delta_F=max((x["delta_F"] for x in details), default=None),
                tolerance=tol, details=details)


def _pose_kernel(xy, yaw, ell, ellpsi):
    d = xy[:, None, :] - xy[None, :, :]
    dp2 = (d * d).sum(axis=2)
    a = np.exp(-dp2 / (2 * ell * ell)) if ell > 0 else (dp2 == 0).astype(float)
    if ellpsi is not None:
        angle = yaw[:, None] - yaw[None, :]
        a = a * np.exp(-2 * np.sin(angle / 2) ** 2 / ellpsi ** 2)
    return a


def independent_sigma(w, cell, s1):
    """Independent path: no info_core.k_pose/k_time/obs_covariance call."""
    poses = np.asarray(w["poses"], dtype=np.float64)
    times = np.asarray(w["t"], dtype=np.float64)
    Kp = _pose_kernel(poses[:, :2], poses[:, 2], s1["pose_corr_length_m"],
                      math.radians(s1["pose_corr_yaw_deg"]))
    tau = float(cell["tau"])
    Kt = np.exp(-np.abs(times[:, None] - times[None, :]) / tau) if tau > 0 else np.eye(len(times))
    ap, at, aw = cell["alphas"]
    C = np.array([[1., cell["c"]], [cell["c"], 1.]])
    ker = ap * Kp + at * Kt + aw * np.eye(len(times))
    sig = np.tile([s1["sigma_r_m"], s1["sigma_s"]], len(times))
    cov = np.kron(ker, C) * sig[:, None] * sig[None, :]
    return 0.5 * (cov + cov.T), Kp, Kt


def generator_law(w, S, cell_name, Sigma_true, *, tol=GENERATOR_TOL):
    expected, Kp, Kt = independent_sigma(w, S["cells"][cell_name], S["s1"])
    actual = np.asarray(Sigma_true)
    if actual.shape != expected.shape or actual.dtype.str != "<f8":
        return dict(pass_=False, reason="ERR_A010_SIGMA_SHAPE_DTYPE")
    scale = max(float(np.max(np.abs(expected))), 1e-300)
    err = float(np.max(np.abs(actual - expected)) / scale)
    eig = float(np.linalg.eigvalsh(actual)[0])
    normal = bool(np.allclose(np.diag(Kp), 1.0, atol=tol, rtol=0)
                  and np.allclose(np.diag(Kt), 1.0, atol=tol, rtol=0))
    return dict(pass_=bool(err <= tol and eig > 0 and normal),
                max_relative_error=err, min_eig=eig, K_pose_diag_ok=normal,
                time_ou_checked=True, shape=list(actual.shape), tol=tol)


def factor_law(Lhalf, poses, s1, tol=GENERATOR_TOL):
    P = np.asarray(poses, dtype=np.float64)
    K = _pose_kernel(P[:, :2], P[:, 2], s1["pose_corr_length_m"],
                     math.radians(s1["pose_corr_yaw_deg"]))
    L = np.asarray(Lhalf)
    if L.shape != K.shape or L.dtype.str != "<f8":
        return dict(pass_=False, reason="ERR_A010_FACTOR_SHAPE_DTYPE")
    d = float(np.max(np.abs(L @ L.T - K)) / max(float(np.max(np.abs(K))), 1e-300))
    return dict(pass_=bool(d <= tol), relative_max=d, n_poses=len(P), tol=tol)


def c10_matrix(row):
    mat = np.empty((4, 4), dtype=float)
    for i in range(4):
        for j in range(i, 4):
            x = float(row[f"C10rot_{i}{j}"])
            mat[i, j] = x
            mat[j, i] = x
    return mat


def c10_diagnostics(row, *, scales=None):
    p = c10_matrix(row)
    if not np.isfinite(p).all():
        return dict(pass_=False, min_eigenvalue=None, normalized_condition=None)
    eig = np.linalg.eigvalsh(p)
    diag = np.diag(p)
    if eig[0] <= 0 or np.any(diag <= 0):
        return dict(pass_=False, min_eigenvalue=float(eig[0]), normalized_condition=None)
    d = np.sqrt(diag) if scales is None else np.asarray(scales)
    normalized = p / d[:, None] / d[None, :]
    cond = float(np.linalg.cond(normalized))
    return dict(pass_=bool(np.isfinite(cond)), min_eigenvalue=float(eig[0]),
                normalized_condition=cond, log10_condition=float(np.log10(cond)))


def covariance_replay_check(a, b, *, scaled_difference, nees_tolerance=1e-3):
    x, y = c10_diagnostics(a), c10_diagnostics(b)
    if not x["pass_"] or not y["pass_"]:
        return dict(pass_=False, source=x, replay=y)
    diff = float(scaled_difference(a, b))
    nees = abs(float(a["nees4_C10"]) - float(b["nees4_C10"])) / max(abs(float(b["nees4_C10"])), 1e-300)
    logdiff = abs(x["log10_condition"] - y["log10_condition"])
    return dict(pass_=bool(diff <= nees_tolerance and nees <= nees_tolerance and logdiff <= C10_COND_LOG_TOL),
                full_C10_rel=diff, nees4_rel=nees, condition_log10_delta=logdiff,
                source=x, replay=y)


def split_diff(baseline, candidate, dev3=range(20, 30)):
    """No global merge change, no revival of a legacy HOLDOUT track."""
    baseline, candidate = dict(baseline), dict(candidate)
    extra = set(candidate) - set(baseline)
    changed = sorted(k for k in baseline if k not in candidate or baseline[k] != candidate[k])
    return dict(pass_=not changed and extra == {"DEV3"} and
                candidate.get("DEV3") == list(dev3) and "HOLDOUT" not in candidate,
                old_tracks_unchanged=not changed, changed_keys=changed,
                added_keys=sorted(extra), old_track_keys=sorted(baseline),
                no_legacy_holdout="HOLDOUT" not in candidate,
                dev3_count=len(candidate.get("DEV3", [])))


def gate_verdict(criteria):
    unknown = [k for k in G5_NUMERIC_GATE_IDS if k not in criteria]
    if unknown:
        return dict(status="BLOCKED", missing_gate_ids=unknown, gated=list(G5_NUMERIC_GATE_IDS))
    ok = all(bool(criteria[k].get("pass_", False)) for k in G5_NUMERIC_GATE_IDS)
    return dict(status="PASS" if ok else "FAIL", missing_gate_ids=[], gated=list(G5_NUMERIC_GATE_IDS))


def mode_identifiability(rows, tol1=1., tol2=2., fraction=.99):
    """Rows retained in all science metrics.  Subset is diagnostic ONLY."""
    rows = list(rows)
    if not rows:
        return dict(status="NOT_RUN", n_rows=0, n_excluded=0, scientific_release=False)
    alt = [r for r in rows if int(r["n_alt_ambiguous"]) > 0]
    clean = [r for r in rows if int(r["n_alt_ambiguous"]) == 0]
    groups = defaultdict(list)
    for r in rows:
        k = (r["field"], r["role"], r["cell"], r["arm"])
        groups[k].append(r)
    clean_ok = (bool(clean) and sum(float(r["E_vs_best_dref"]) <= tol1 for r in clean) / len(clean) >= fraction
                and all(float(r["E_vs_best_dref"]) <= tol2 for r in clean))
    legacy_ok = (sum(float(r["E_vs_best_dref"]) <= tol1 for r in rows) / len(rows) >= fraction
                 and all(float(r["E_vs_best_dref"]) <= tol2 for r in rows))
    return dict(status="MIXED" if alt else ("GRID_LOCAL_ONLY" if clean_ok else "NOT_IDENTIFIABLE"),
                n_rows=len(rows), n_ambiguous=len(alt), n_excluded_from_nonambiguous_diagnostic=len(alt),
                ambiguous_fraction=len(alt) / len(rows), clean_subset_stability_pass=clean_ok,
                legacy_full_rows_pass=legacy_ok, strata_count=len(groups),
                stratum_ambiguity={"|".join(map(str, k)): dict(rows=len(v),
                    ambiguous=sum(int(r["n_alt_ambiguous"]) > 0 for r in v))
                    for k, v in sorted(groups.items())},
                all_rows_retained_in_science=True, unique_map_claim_allowed=False,
                scientific_release=False, sensitivity="REVIEW_REQUIRED_IF_ANY_AMBIGUOUS")


def validate_two_runner_solver_receipts(a, b, *, state_tol=1e-6, cost_tol=1e-6,
                                        cov_tol=1e-3, cond_log_tol=1e-3):
    """Strict contract for independently produced SAME-CANONICAL-INPUT solver evidence.

    Each receipt must contain source_git_sha, manifest_sha256, input_sha256,
    runner_id, environment, rows. This does not create or approve the receipts.
    A pair alone never overrides the original G5 scientific status.
    """
    required = ("source_git_sha", "manifest_sha256", "input_sha256", "runner_id", "environment", "rows")
    if any(k not in x for x in (a, b) for k in required):
        return dict(pass_=False, reason="ERR_SOLVER_REPRO_MISSING_METADATA")
    if not a["runner_id"] or not b["runner_id"] or a["runner_id"] == b["runner_id"]:
        return dict(pass_=False, reason="ERR_SOLVER_REPRO_NOT_TWO_RUNNERS")
    for k in ("source_git_sha", "manifest_sha256", "input_sha256"):
        if not a[k] or a[k] != b[k]:
            return dict(pass_=False, reason=f"ERR_SOLVER_REPRO_MISMATCH_{k}")
    if not a["rows"] or not b["rows"]:
        return dict(pass_=False, reason="ERR_SOLVER_REPRO_EMPTY_ROWS")
    def rowmap(rows):
        keys = [(r["field"], r["role"], r["cell"], r["sensor_seed"], r["arm"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("ERR_SOLVER_REPRO_DUPLICATE_ROW")
        return dict(zip(keys, rows))
    x, y = rowmap(a["rows"]), rowmap(b["rows"])
    if set(x) != set(y):
        return dict(pass_=False, reason="ERR_SOLVER_REPRO_ROW_SET", missing=len(set(x)-set(y)), extra=len(set(y)-set(x)))
    failures = []
    for key in sorted(x):
        one, two = x[key], y[key]
        if (one.get("class_v31") != two.get("class_v31") or
                one.get("n_alt_ambiguous") != two.get("n_alt_ambiguous")):
            failures.append(dict(key=key, reason="CLASS_OR_MODE")); continue
        if abs(float(one["cost"])-float(two["cost"]))>cost_tol:
            failures.append(dict(key=key, reason="COST"));continue
        delta = np.array([float(one[f"xend_{i}"])-float(two[f"xend_{i}"]) for i in range(4)])
        delta[2] = float(np.arctan2(np.sin(delta[2]),np.cos(delta[2])))
        d = float(np.max(np.abs(delta) / np.array([.02,.02,np.deg2rad(.25),np.deg2rad(.01)])))
        if d>state_tol:
            failures.append(dict(key=key, reason="STATE"));continue
        cv = covariance_replay_check(one, two, scaled_difference=lambda u,v:
            _scaled_c10_diff(u,v), nees_tolerance=cov_tol)
        if not cv["pass_"] or cv.get("condition_log10_delta", np.inf)>cond_log_tol:
            failures.append(dict(key=key, reason="FULL_C10"));continue
    return dict(pass_=not failures, n_rows=len(x), n_fail=len(failures),
                failure_details=failures, runner_ids=[a["runner_id"],b["runner_id"]],
                same_input_sha=a["input_sha256"], same_source_sha=a["source_git_sha"])


def _scaled_c10_diff(a, b):
    P,Q=c10_matrix(a),c10_matrix(b)
    denom=np.maximum(np.sqrt(np.maximum(np.diag(P),0))[:,None] *
                     np.sqrt(np.maximum(np.diag(P),0))[None,:],
                     np.sqrt(np.maximum(np.diag(Q),0))[:,None] *
                     np.sqrt(np.maximum(np.diag(Q),0))[None,:])
    for j in range(4):
        denom[j,j]=max(denom[j,j],1e-300)
    return float(np.max(np.abs(P-Q)/np.maximum(denom,1e-300)))
