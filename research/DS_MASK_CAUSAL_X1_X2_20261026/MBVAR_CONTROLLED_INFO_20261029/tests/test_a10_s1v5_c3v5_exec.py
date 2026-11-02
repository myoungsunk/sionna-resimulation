"""Execution-level regression tests for the A010 S1V5/C3V5 draft (defects D1, D2, D5 of the 2026-11-01 cross-check).

Unlike test_a10_canonical.py (string / AST / py_compile only), these tests IMPORT and EXECUTE s1v5 and c3v5.
They need the pinned inputs (REFLECT_ROOT from reflect_model/fetch_inputs.sh, FETCH_RF=0):
  - inputs absent and MBVAR_A010_REQUIRE_INPUTS != 1  -> skipped (e.g. the mechanical contract-check job),
  - inputs absent and MBVAR_A010_REQUIRE_INPUTS == 1  -> FAIL (technical smoke workflow; fail-closed),
  - (iii) reduced SMOKE end-to-end runs only with MBVAR_A010_E2E=1 (about 30-40 min on a 4-vCPU runner).
SMOKE fields 900/901 only. Never DEV3 (20-29), HOLDOUT2 (5000-5059), reserve (5060-5119) or RT. No truth/oracle
quantity is used to choose an estimate anywhere in these tests.
"""
from __future__ import annotations

import builtins
import dis
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
REQUIRE = os.environ.get("MBVAR_A010_REQUIRE_INPUTS") == "1"


class _LockCalled(Exception):
    pass


def _sentinel(*_a, **_k):
    raise _LockCalled("lock_v5 called")


@pytest.fixture(scope="module")
def mods():
    try:
        import s1v5 as T
        import c3v5 as C
    except ModuleNotFoundError as ex:            # pinned FFD/EKF sources (REFLECT_ROOT) not fetched
        if REQUIRE:
            pytest.fail(f"MBVAR_A010_REQUIRE_INPUTS=1 but inputs are missing: {ex}")
        pytest.skip(f"REFLECT_ROOT inputs not available: {ex}")
    return T, C


# ----------------------------------------------------------------------------- (i) D1: real import + lock_v5 call path
def test_s1v5_cmd_run_calls_lock_v5(mods, monkeypatch, tmp_path):
    T, _ = mods
    monkeypatch.setattr(T, "lock_v5", _sentinel)
    with pytest.raises(_LockCalled):
        T.cmd_run([900], "SMOKE", tmp_path / "run")


def test_s1v5_cmd_aggregate_calls_lock_v5(mods, monkeypatch, tmp_path):
    T, _ = mods
    monkeypatch.setattr(T, "lock_v5", _sentinel)
    with pytest.raises(_LockCalled):
        T.cmd_aggregate(str(tmp_path), "SMOKE", tmp_path / "agg")


def test_c3v5_entry_points_call_lock_v5(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(T, "lock_v5", _sentinel)
    for call in (lambda: C.cmd_run(900, "LH", tmp_path / "c3"), lambda: C.cmd_aggregate(str(tmp_path), tmp_path / "c3agg"), C.linear_exact):
        with pytest.raises(_LockCalled):
            call()


def _global_loads(code):
    for ins in dis.get_instructions(code):
        if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME"):
            yield ins.argval
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            yield from _global_loads(c)


@pytest.mark.parametrize("name", ["s1v5", "c3v5"])
def test_no_undefined_globals_or_stale_v4_names(mods, name):
    """Every global referenced by a function of s1v5/c3v5 must exist (D1 class); no stale S1V4/C3V4 identifiers."""
    mod = mods[0] if name == "s1v5" else mods[1]
    undefined = set()
    for obj in vars(mod).values():
        if isinstance(obj, types.FunctionType) and obj.__module__ == mod.__name__:
            undefined |= {g for g in _global_loads(obj.__code__) if g not in vars(mod) and not hasattr(builtins, g)}
    assert not undefined, f"{name}: undefined globals {sorted(undefined)}"
    src = (CODE / f"{name}.py").read_text()
    stale = re.findall(r'lock_v4|run_plan\[\s*["\'](?:S1V4|C3V4)["\']\s*\]|PREFIX\s*=\s*["\']S1V4|S1V4_INPUTS|S1V3_INPUTS', src)
    assert not stale, f"{name}: stale references {stale}"
    assert mods[0].PREFIX == "S1V5"


# ----------------------------------------------------------------------------- (ii) D2: receipt loader on fake shard zips
def _sig(seed, n=6):
    a = np.random.default_rng(seed).standard_normal((n, n))
    return a @ a.T + n * np.eye(n)


def _write_shards(d, shards):
    """shards: {zip tag: {key: array}} -> S1V5_INPUTS_SMOKE_<tag>.zip + MANIFEST.json (output_sha256)."""
    d.mkdir(parents=True, exist_ok=True); man = {}
    for tag, arrs in shards.items():
        p = d / f"S1V5_INPUTS_SMOKE_{tag}.zip"
        with open(p, "wb") as fh:
            np.savez_compressed(fh, **arrs)
        man[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (d / "MANIFEST.json").write_text(json.dumps({"output_sha256": man}))
    return d


def _shard(T, f, Sig, models, role="LOW", cell="POSE_HIGH"):
    rec = {f"{f}|{role}|{cell}|0|z": np.full((3, 2), float(f))}
    rec.update(T.mat_receipt(f, role, cell, Sig, models))
    return rec


def test_load_receipts_two_shards_same_matrices_pass(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    models = {"IID_BATCH": _sig(2), "ORACLE_CORR_BATCH": _sig(3)}
    d = _write_shards(tmp_path, {"900": _shard(T, 900, _sig(1), models), "901": _shard(T, 901, _sig(1), models)})
    rec, st = C.load_receipts_with_stats(d)
    assert st["n_receipt_files"] == 2 and st["mat_duplicate_keys"] == 0 and st["mat_conflicts"] == 0
    assert st["mat_keys"] == 6
    x = C.mat_cross_field_report(rec)
    assert x["n_groups_multi_field"] == 3 and x["n_byte_identical"] == 3 and x["n_differ"] == 0
    for f in (900, 901):
        assert np.array_equal(rec[T.mat_key(f, "LOW", "POSE_HIGH")], _sig(1))
        assert np.array_equal(rec[T.mat_key(f, "LOW", "POSE_HIGH", "ORACLE_CORR_BATCH")], _sig(3))
    assert set(C.load_receipts(d)) == set(rec)


def test_load_receipts_cross_field_difference_is_reported_not_merged(mods, monkeypatch, tmp_path):
    """Field-qualified keys: a per-runner ULP difference between fields is kept per field and REPORTED, never mixed."""
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    s1 = _sig(1); s1b = s1.copy(); s1b[0, 0] = np.nextafter(s1b[0, 0], np.inf)
    models = {"IID_BATCH": _sig(2)}
    d = _write_shards(tmp_path, {"900": _shard(T, 900, s1, models), "901": _shard(T, 901, s1b, models)})
    rec, st = C.load_receipts_with_stats(d)
    assert st["mat_conflicts"] == 0
    x = C.mat_cross_field_report(rec)
    assert x["n_differ"] == 1 and x["n_byte_identical"] == 1 and 0 < x["max_rel_diff"] < 1e-15
    assert np.array_equal(rec[T.mat_key(901, "LOW", "POSE_HIGH")], s1b)


def test_load_receipts_duplicate_mat_key_identical_bytes_fails(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    models = {"IID_BATCH": _sig(2)}
    a = _shard(T, 900, _sig(1), models)
    b = {"900|HIGH|POSE_HIGH|0|z": np.zeros((3, 2)), **T.mat_receipt(900, "LOW", "POSE_HIGH", _sig(1), models)}
    d = _write_shards(tmp_path, {"900": a, "900_b": b})
    with pytest.raises(SystemExit, match="ERR_C3V5_DUPLICATE_INPUT_KEY"):
        C.load_receipts(d)


def test_load_receipts_duplicate_mat_key_different_bytes_conflict(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    models = {"IID_BATCH": _sig(2)}
    a = _shard(T, 900, _sig(1), models)
    b = {"900|HIGH|POSE_HIGH|0|z": np.zeros((3, 2)), **T.mat_receipt(900, "LOW", "POSE_HIGH", _sig(9), models)}
    d = _write_shards(tmp_path, {"900": a, "900_b": b})
    with pytest.raises(SystemExit, match="ERR_C3V5_MAT_CONFLICT"):
        C.load_receipts(d)


def test_load_receipts_non_mat_duplicate_fails(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    models = {"IID_BATCH": _sig(2)}
    a = _shard(T, 900, _sig(1), models)
    b = {"900|LOW|POSE_HIGH|0|z": np.full((3, 2), 900.0)}           # same estimator-input key, identical bytes
    d = _write_shards(tmp_path, {"900": a, "900_b": b})
    with pytest.raises(SystemExit, match="ERR_C3V5_DUPLICATE_INPUT_KEY"):
        C.load_receipts(d)


def test_load_receipts_legacy_fieldless_mat_key_fails(mods, monkeypatch, tmp_path):
    """The pre-fix S1V5 schema MAT|role|cell|... (no field) must not be silently accepted."""
    _, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    d = _write_shards(tmp_path, {"900": {"900|LOW|POSE_HIGH|0|z": np.zeros((3, 2)), "MAT|LOW|POSE_HIGH|Sig_true": _sig(1)}})
    with pytest.raises(SystemExit, match="ERR_C3V5_LEGACY_MAT_KEY"):
        C.load_receipts(d)


def test_load_receipts_mat_field_outside_its_shard_fails(mods, monkeypatch, tmp_path):
    T, C = mods
    monkeypatch.setattr(C, "SPLIT", "SMOKE")
    d = _write_shards(tmp_path, {"900": {"900|LOW|POSE_HIGH|0|z": np.zeros((3, 2)), **T.mat_receipt(901, "LOW", "POSE_HIGH", _sig(1), {})}})
    with pytest.raises(SystemExit, match="ERR_C3V5_MAT_FIELD_MISMATCH"):
        C.load_receipts(d)


# ----------------------------------------------------------------------------- D5: MODE_AMBIGUITY per R4
def test_mode_ambiguity_counts_any_truth_free_alternative(mods):
    T, C = mods
    X = np.zeros((5, 4)); dref = T.D_REF
    alt = X.copy(); alt[-1, 0] += 2.2 * dref[0]                      # 2.2 d_ref away, +0.05 chi^2
    near = X.copy(); near[-1, 1] += 1.5 * dref[1]                    # within 2 d_ref: not ambiguous
    edge = X.copy(); edge[-1, 2] += 1.99 * dref[2]                   # just inside 2 d_ref, +0.5 chi^2: not ambiguous
    far_cost = X.copy(); far_cost[-1, 0] += 9.0 * dref[0]            # far but +1.5 chi^2: not ambiguous
    sol = {"E": (10.0, X), "psi+1": (10.05, alt), "psi-1": (10.2, near), "x+1": (10.5, edge), "y+1": (11.5, far_cost),
           "truth": (9.0, X + 50 * dref)}                              # ORACLE start: lower cost, must never count or be best
    m = C.mode_ambiguity(sol)
    assert m["n_alt_ambiguous"] == 1 and m["alt_ambiguous_starts"] == "psi+1"
    assert math.isclose(m["max_alt_dref_within_1chi2"], 2.2, rel_tol=1e-9)
    # the pre-fix rule (truth-free best start only vs E') misses this case: the best truth-free start is E' itself
    nonoracle = {k: v for k, v in sol.items() if k != "truth"}
    best = min(nonoracle, key=lambda k: nonoracle[k][0])
    assert best == "E" and T.dref_diff(X[-1], nonoracle[best][1][-1]) == 0.0


def test_mode_ambiguity_no_alternative(mods):
    _, C = mods
    X = np.zeros((5, 4))
    m = C.mode_ambiguity({"E": (3.0, X), "psi+1": (3.0, X.copy()), "truth": (1.0, X + 1.0)})
    assert m == dict(n_alt_ambiguous=0, max_alt_dref_within_1chi2=0.0, alt_ambiguous_starts="")


# ----------------------------------------------------------------------------- (iii) reduced SMOKE end-to-end
E2E = os.environ.get("MBVAR_A010_E2E") == "1"


def _run_parallel(cmds, work, tag):
    logs, procs = [], []
    for i, c in enumerate(cmds):
        lp = work / f"LOG_{tag}_{i}.txt"; logs.append(lp)
        procs.append(subprocess.Popen([sys.executable, "-u", str(Path(__file__).parent / "a10_e2e_smoke.py"), *c, "--work", str(work)],
                                      stdout=open(lp, "w"), stderr=subprocess.STDOUT, cwd=str(ROOT)))
    rcs = [p.wait() for p in procs]
    return rcs, [lp.read_text()[-4000:] for lp in logs]


@pytest.mark.skipif(not E2E, reason="set MBVAR_A010_E2E=1 (technical smoke workflow)")
def test_smoke_reduced_end_to_end(mods, tmp_path):
    import a10_e2e_smoke as D
    T, C = mods
    work = Path(os.environ.get("MBVAR_A010_E2E_WORK") or tmp_path).resolve(); work.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); timing = {}
    rcs, logs = _run_parallel([["s1run", "--field", str(f)] for f in D.SMOKE_FIELDS], work, "s1run")
    timing["s1run_s"] = round(time.time() - t0)
    assert rcs == [0] * len(rcs), logs
    rcs, logs = _run_parallel([["s1agg"]], work, "s1agg")
    assert rcs[0] in (0, 1), logs                                      # 1 = full-split row count not met (subset), checked below
    agg = work / "s1agg"
    for f in D.SMOKE_FIELDS:
        assert (agg / f"S1V5_INPUTS_SMOKE_{f}.zip").exists()
    assert (agg / "MANIFEST.json").exists()
    qa = json.loads((agg / "S1V5_QA.json").read_text())
    n_sub = D.expected_s1_rows()
    # S1V5 QA on the subset: every component of qaj["pass"] except the full-split row count, which is replaced by n_sub
    assert qa["fields_got"] == list(D.SMOKE_FIELDS) and qa["fields_expected"] == list(D.SMOKE_FIELDS) and qa["request_field_rule_ok"]
    assert qa["mahalanobis_mean"] and all(abs(v - 1) <= qa["mahalanobis_tol"] for v in qa["mahalanobis_mean"].values())
    assert qa["revisit_pose_identical_max"] == 0.0 and (qa["revisit_time_differs_min"] or 0) > 0
    assert qa["stops"] == 0 and qa["failures"] == 0 and qa["n_rows"] == n_sub
    assert not qa["NOT_CERTIFIED_v31_cells_failing"] and qa["primary_P_pd_all"] and qa["A82_polish_all_within_scope"]
    assert qa["n_input_receipt_files"] == len(D.SMOKE_FIELDS)
    assert qa["A010_KP_BYTE_MATCH"]["n_fields"] == len(D.SMOKE_FIELDS)
    import pandas as pd
    res = pd.read_csv(agg / "S1V5_RESULTS_SMOKE.csv")
    assert not res.duplicated(["field", "role", "cell", "sensor_seed", "arm"]).any()
    # receipts: field-qualified MAT keys only, one set per field
    for f in D.SMOKE_FIELDS:
        with np.load(agg / f"S1V5_INPUTS_SMOKE_{f}.zip", allow_pickle=False) as z:
            mats = [k for k in z.files if k.startswith("MAT|")]
            assert mats and all(k.split("|")[1] == str(f) for k in mats)
    t1 = time.time()
    rcs, logs = _run_parallel([["c3run", "--field", str(f), "--group", g, "--cells", ",".join(cells)] for f, g, cells in D.C3_PLAN], work, "c3run")
    timing["c3run_s"] = round(time.time() - t1)
    assert rcs == [0] * len(rcs), logs
    rcs, logs = _run_parallel([["c3agg"]], work, "c3agg")
    assert rcs[0] in (0, 1), logs
    st = json.loads((work / "c3agg" / "C3V5_STATUS.json").read_text())
    assert (work / "c3agg" / "MANIFEST.json").exists()
    crit, tol = st["criteria"], st["tolerances"]
    rl = st["receipt_load"]
    assert rl["n_receipt_files"] == 2 and rl["mat_duplicate_keys"] == 0 and rl["mat_conflicts"] == 0
    assert st["MAT_CROSS_FIELD_REPORTED"]["n_groups_multi_field"] > 0
    Cr = pd.read_csv(work / "c3agg" / "C3V5_ROWS.csv")
    assert len(Cr) == crit["rows"]["n"] and len(Cr) > 0 and Cr.found.astype(bool).all()
    # Recompute the prospective G5 hard gates on the REDUCED subset, never
    # misreport the full field-level gate as PASS (the original rows gate FAILs).
    gating = [k for k in st["gating"] if k not in ("rows", "SOLVER_REPRO")]
    assert crit["SOLVER_REPRO"]["pass_"] is False
    assert set(gating) == {"RECEIPT_INTEGRITY", "GENERATOR_LAW", "CROSS_FIELD_COV_EQUIVALENCE",
                           "STATE_COST_REPRO", "FULL_C10_REPRO", "STATUS_REPRO", "NO_WRONG_BASIN",
                           "ITER_CAP", "PROBE_POWER", "LINEAR_EXACT", "KINK_FIXTURES"}
    nc = Cr[Cr.conv != "CONVERGED"]
    old_input_math = bool(Cr.INPUT_EXACT.astype(bool).all() and
                          (Cr.d_z <= tol["z"]).all() and
                          (Cr[["d_ds", "d_gy", "d_x0"]].max(axis=1) <= tol["ctl"]).all() and
                          Cr.taps_equal.astype(bool).all() and Cr.pose_keys_equal.astype(bool).all() and
                          (Cr[["d_sig_true_rel", "d_sig_model_rel"]].max(axis=1) <= tol["fp_rel"]).all())
    law_jsons = sorted((work / "c3sh").glob("**/C3V5_GENERATOR_LAW_*.json"))
    law_verified = bool(len(law_jsons) == len(D.C3_PLAN) and
                        all(json.loads(p.read_text())["pass_"] for p in law_jsons))
    xf = pd.read_csv(work / "c3agg" / "A010_CROSS_FIELD_COV.csv")
    checks = dict(
        RECEIPT_INTEGRITY=bool(old_input_math and rl["strict_index_verified"] and
                               rl["array_hashes_verified"] > 0 and
                               Cr.RECEIPT_ARRAY_EXACT.astype(bool).all() and
                               Cr.TRUTH_ONLY_VERIFIED.astype(bool).all()),
        GENERATOR_LAW=law_verified,
        CROSS_FIELD_COV_EQUIVALENCE=bool(xf.pass_.astype(bool).all() and
                                          (xf.delta_max <= 1e-10).all() and
                                          (xf.delta_F <= 1e-10).all() and
                                          (xf.min_eig > 0).all()),
        STATE_COST_REPRO=bool((Cr.d_state_dref <= tol["state_dref"]).all() and
                               (Cr.d_cost <= tol["cost"]).all() and Cr.same_best_k.astype(bool).all()),
        FULL_C10_REPRO=bool(Cr.full_C10_spd_pass.astype(bool).all() and
                             (Cr.d_P_C10_rel <= tol["P_rel"]).all() and
                             (Cr.d_P_full_C10_rel <= tol["P_rel"]).all() and
                             (Cr.d_NEES4_C10_rel <= tol["P_rel"]).all() and
                             (Cr.c10_log10_cond_delta <= 1e-3).all()),
        STATUS_REPRO=bool(Cr.same_class_v31.astype(bool).all()),
        NO_WRONG_BASIN=bool((Cr.gap_E <= tol["basin"]).all()),
        ITER_CAP=bool((nc.E300_vs_E_dref <= tol["itercap_dref"]).all()),
        PROBE_POWER=bool((Cr.pp_class == "NOT_CERTIFIED").mean() >= tol["probe_power_frac"]),
        LINEAR_EXACT=bool(crit["LINEAR_EXACT"]["pass_"]),
        KINK_FIXTURES=bool(crit["KINK_FIXTURES"]["pass_"]))
    assert st["status"] == "FAIL", "reduced SMOKE must not be represented as full G5 success"
    assert st["G5_NUMERIC_REPLAY"]["status"] == "FAIL"
    assert st["SOLVER_REPRO_CROSS_RUNNER"] == "NOT_YET_VERIFIED"
    assert st["G5_MODE_IDENTIFIABILITY"]["scientific_release"] is False
    summary = dict(timing=timing, s1v5_rows=qa["n_rows"], s1v5_rows_expected_subset=n_sub, c3v5_rows=len(Cr), c3v5_status=st["status"],
                   c3v5_subset_checks=checks, receipt_load=rl, mat_cross_field=st["MAT_CROSS_FIELD_REPORTED"],
                   mode_ambiguity=crit["MODE_AMBIGUITY_REPORTED"], kp_byte_match=qa["A010_KP_BYTE_MATCH"])
    (work / "E2E_SUMMARY.json").write_text(json.dumps(summary, indent=1, default=float))
    assert all(checks.values()), checks
    for k in ("n_alt_ambiguous", "max_alt_dref_within_1chi2", "alt_ambiguous_starts"):
        assert k in Cr.columns
    assert crit["MODE_AMBIGUITY_REPORTED"]["n_ambiguous"] == int((Cr.n_alt_ambiguous > 0).sum())
    assert st["science_release_allowed"] is False and st["holdout2_allowed"] is False
