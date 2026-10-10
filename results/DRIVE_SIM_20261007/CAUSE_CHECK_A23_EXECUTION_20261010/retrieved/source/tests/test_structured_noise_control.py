import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("structured_noise_control_under_test", ROOT / "scripts" / "drive_sim" / "structured_noise_control.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_targets(m, n=400):
    rng = np.random.default_rng(0)
    r_s = m.ar1_from(rng.standard_normal(n), 0.05, 0.03, 0.9)
    r_r = m.ar1_from(rng.standard_normal(n), 0.05, 0.015, 0.7)
    keep = np.ones(n, bool)
    return dict(s=m.stats_of(r_s), range=m.stats_of(r_r), corr_s_range=0.5, keep=keep, r_s_m=r_s, r_r_m=r_r, r_s_full=r_s, r_r_full=r_r,
                dbin=np.searchsorted([5.0, 10.0], np.linspace(1, 14, n)), tbin=np.arange(n) % 4, d3=np.linspace(1, 14, n),
                dist_mean={0: 0.0, 1: 0.05, 2: 0.1}, dist_var={0: 0.01, 1: 0.01, 2: 0.02}, tap_mean={k: 0.0 for k in range(4)}, tap_var={k: 0.01 for k in range(4)})


def test_ar1_reproduces_mean_variance_and_lag1():
    m = load()
    runs = np.array([m.ar1_from(np.random.default_rng(i).standard_normal(400), 0.05, 0.03, 0.9) for i in range(200)])
    assert abs(runs.mean() - 0.05) < 0.01 and abs(runs.var() - 0.03) < 0.004
    c = runs - runs.mean(1, keepdims=True)
    assert 0.8 < float((c[:, :-1] * c[:, 1:]).sum() / (c * c).sum()) < 0.95          # finite-length mean removal biases it slightly low


def test_arm_table_tiers_and_run_counts():
    m = load()
    assert len(m.ARMS) == 22 and set(a for a, v in m.ARMS.items() if v[2] == 0) == {"A0_real_real", "M0_Rmatched_Rmatched", "W0_white_white"}
    assert len(m.expand_arms(["tier0"])) == 3 and len(m.expand_arms(["tier1"])) == 11 and len(m.expand_arms(["tier2"])) == 11 and len(m.expand_arms(["tier3"])) == 6
    assert len(m.expand_arms(["all"])) == 22 and m.expand_arms(["tier1", "S1_bias"]) == m.expand_arms(["tier1"])
    with pytest.raises(SystemExit):
        m.expand_arms(["nope"])


def test_common_random_numbers_and_variance_models():
    m = load()
    m._G.update(sigma_mismatch=0.161, R_range=0.0068579)
    tg = fake_targets(m)
    z = m.stream(3, 1, 101, 400)
    assert np.allclose(m.stream(3, 1, 101, 400), z) and not np.allclose(m.stream(3, 2, 101, 400), z)          # drift enters the stream key
    w = m.gen_noise("s", "white", 400, tg, 3, 1, z, None, None)
    r = m.gen_noise("s", "Rmatched", 400, tg, 3, 1, z, None, None)
    assert np.allclose(w / tg["s"]["rms"], z) and np.allclose(r / 0.161, z)                                   # same innovations, different scale
    rr = m.gen_noise("range", "Rmatched", 400, tg, 3, 1, z, np.zeros(400), None)
    assert np.allclose(rr, z * math.sqrt(0.0068579))
    ar = m.gen_noise("s", "ar1", 400, tg, 3, 1, z, None, None)
    assert np.allclose(ar, m.ar1_from(z, tg["s"]["mean"], tg["s"]["var"], tg["s"]["phi"]))                  # the AR(1) arm is built from the same innovations


def test_joint_block_uses_one_index_for_both_series_and_correlated_innovations_hit_the_target():
    m = load()
    rng = np.random.default_rng(2)
    idx = m.block_index(1000, 50, 300, rng)
    assert idx.min() >= 0 and idx.max() < 300 and np.all(np.diff(idx[:50]) % 300 == 1)                        # contiguous circular blocks
    ps, pr, rho = 0.93, 0.80, 0.5
    c = rho * (1 - ps * pr) / math.sqrt((1 - ps ** 2) * (1 - pr ** 2))
    zs, zr = np.random.default_rng(5).standard_normal((2, 200000))
    zr_eff = c * zs + math.sqrt(1 - c * c) * zr
    xs, xr = m.ar1_from(zs, 0, 1, ps), m.ar1_from(zr_eff, 0, 1, pr)
    assert abs(float(np.corrcoef(xs, xr)[0, 1]) - rho) < 0.03


# ---------------------------------------------------------------- A0 / S6 check (rev3): false-PASS regressions
import pandas as pd  # noqa: E402


def _frames(m, seeds=(0, 1, 2), drifts=(0, 1, 2)):
    rows = []
    for d in drifts:
        for s in seeds:
            rows.append(dict(route="R2", anchor="A", lateral=0.0, mount_deg=0.0, drift=d, snr_db=30.0, seed=s, baseline="range_s_P0", **{"filter": "ekf"}, error="",
                             heading_rmse_deg=1.0 + 0.1 * s + d, pos_rmse_m=0.2 + 0.01 * s, nees_mean=3.0 + s))
    df = pd.DataFrame(rows)
    req = m.requested_keys(["R2A"], [0.0], list(drifts), len(seeds), seeds[0])
    return df, req


def test_a0_check_passes_only_on_a_complete_identical_set():
    m = load()
    a0, req = _frames(m)
    r = m.check_a0(a0, a0.copy(), req)
    assert r["inference_valid"] and r["n_matched"] == 9 and r["max_abs_diff_nees_mean"] == 0.0


def test_a0_check_rejects_a_missing_seed_replaced_by_a_duplicate_with_equal_row_count():
    m = load()
    a0, req = _frames(m)
    s6 = a0.copy()
    gone = s6[(s6.seed == 1) & (s6.drift == 0)].index[0]
    dupe = s6[(s6.seed == 2) & (s6.drift == 0)].iloc[[0]]
    s6 = pd.concat([s6.drop(gone), dupe], ignore_index=True)
    assert len(s6) == len(a0)                                                  # same number of rows as the complete set
    r = m.check_a0(a0, s6, req)
    kinds = {p["kind"] for p in r["problems"]}
    assert not r["inference_valid"] and {"duplicate_keys", "missing_keys"} <= kinds


def test_a0_check_rejects_missing_metric_columns_failed_rows_nonfinite_and_mismatch():
    m = load()
    a0, req = _frames(m)
    no_metrics = a0.drop(columns=list(m.METRICS))
    r = m.check_a0(a0, no_metrics, req)
    assert not r["inference_valid"] and r["problems"][0]["kind"] == "missing_columns" and set(r["problems"][0]["columns"]) == set(m.METRICS)
    failed = a0.copy()
    failed.loc[0, "error"] = "LinAlgError: boom"
    assert any(p["kind"] == "failed_rows" for p in m.check_a0(a0, failed, req)["problems"])
    nan = a0.copy()
    nan.loc[3, "nees_mean"] = float("nan")
    assert any(p["kind"] == "non_finite_metric" for p in m.check_a0(a0, nan, req)["problems"])
    off = a0.copy()
    off["pos_rmse_m"] = off["pos_rmse_m"] + 1e-6
    r = m.check_a0(a0, off, req)
    assert not r["inference_valid"] and any(p["kind"] == "metric_mismatch" and p["metric"] == "pos_rmse_m" for p in r["problems"])
    assert m.check_a0(a0, a0.iloc[:-1], req)["inference_valid"] is False         # one requested key absent


def test_a0_gate_blocks_on_changed_fingerprint_inputs_or_uncovered_keys():
    m = load()
    a0, req = _frames(m)
    keys = [list(r) for r in req.itertuples(index=False, name=None)]
    inputs = dict(H={"R2A_m0": "h1"}, timelines={"R2A": {"none": "t1"}}, rf_poses={"R2A": "p1"})
    check = dict(inference_valid=True, fingerprint="F", inputs=inputs, requested=keys)
    now = dict(fingerprint="F", inputs=inputs)
    assert m.a0_gate(check, now, [tuple(k) for k in keys])[0]
    assert not m.a0_gate(dict(check, inference_valid=False), now, [tuple(k) for k in keys])[0]
    assert not m.a0_gate(check, dict(now, fingerprint="G"), [tuple(k) for k in keys])[0]
    assert not m.a0_gate(check, dict(fingerprint="F", inputs=dict(inputs, H={"R2A_m0": "h2"})), [tuple(k) for k in keys])[0]
    assert not m.a0_gate(check, now, [tuple(keys[0][:-1]) + (99,)])[0]
    assert not m.a0_gate(None, now, [])[0]


def test_closure_statuses_and_seed_eligibility_after_a_failed_drift():
    m = load()
    rng = np.random.default_rng(0)
    w0 = 5.0 + rng.normal(0, 0.2, 40)
    a0 = w0 + 50.0 + rng.normal(0, 2.0, 40)
    ok = m.closure(w0 + 25.0, a0, w0)
    assert ok["status"] == "defined" and 0.3 < ok["closure"] < 0.7 and ok["closure_ci"][0] < ok["closure"] < ok["closure_ci"][1]
    assert m.closure(w0 + 80.0, a0, w0)["note"].startswith("over_reproduced")
    assert m.closure(w0, w0 + rng.normal(0, 2.0, 40), w0)["status"] == "withheld_denominator_interval_includes_0"
    assert m.closure(w0, w0 - 10.0, w0)["status"] == "not_applicable_negative_denominator"
    rows = [dict(case="R2A", mount_deg=0.0, arm=arm, seed=s, drift=d) for arm in ("A0_real_real", "W0_white_white", "S3_ar1") for s in range(4) for d in (0, 1, 2)]
    ok_df = pd.DataFrame(rows)
    ok_df = ok_df[~((ok_df.arm == "S3_ar1") & (ok_df.seed == 2) & (ok_df.drift == 1))]          # one failed drift of one arm
    seeds, cnt = m.eligible_seeds(ok_df, "R2A", 0.0, ["S3_ar1", "A0_real_real", "W0_white_white"], [0, 1, 2])
    assert seeds == [0, 1, 3]                                                                     # seed 2 is not compared with a partial drift set
