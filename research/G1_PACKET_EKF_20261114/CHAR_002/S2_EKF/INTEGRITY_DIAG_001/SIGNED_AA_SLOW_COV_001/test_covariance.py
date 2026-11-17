"""Mandatory T00--T09, synthetic only. No actual covariance fits or RF access."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import traceback
import numpy as np
import covariance_core as C
from p0_inputs_v2 import put, sha, support_report, pairs_for
from p1_design_v2 import overlapping_blocks, revisit_groups, components
from reference_d3 import decompose

D3 = dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5., min_window_packets=10)


def test_all():
    results = {}
    rng = np.random.default_rng(20261116)
    n = 10; arc = np.arange(n)*.15; yaw = np.arange(n)*.01
    K = C.kernel(arc, yaw); a = np.where(np.arange(n)%2, -1., 1.)*(.3+np.arange(n)*.15)
    def check(name, action):
        try: results[name] = dict(passed=True, evidence=action())
        except Exception as e: results[name] = dict(passed=False, error=str(e), traceback=traceback.format_exc())

    def t00():
        positive_a = abs(a)
        expected = .02*K+.01*(positive_a[:, None]*K)*positive_a[None, :]
        samples = rng.standard_normal((20000, n))@np.linalg.cholesky(expected).T
        empirical = np.cov(samples, rowvar=False)
        assert expected[0, 1] > 0 and empirical[0, 1] > 0
        assert np.max(abs(empirical-expected)) < .003
        return dict(expected_cov01=float(expected[0, 1]), empirical_cov01=float(empirical[0, 1]), draws=20000)
    check("T00", t00)

    def t01():
        aa = np.array([1., -1., 1.]); k = C.kernel(np.zeros(3), np.zeros(3))
        signed = C.covariance(k, aa, "S1", [.001, .02], 1e-6)
        unsigned = C.covariance(k, aa, "S2", [.001, .02], 1e-6)
        assert signed[0, 1] < 0 < unsigned[0, 1]
        L = np.linalg.cholesky(signed)
        # +/- basis ensemble has exactly the target second moment.
        samples = np.r_[np.sqrt(3)*L.T, -np.sqrt(3)*L.T]
        ds = np.mean([C.logscore(e, signed)-C.logscore(e, unsigned) for e in samples])
        assert ds > 0
        return dict(signed_cov01=float(signed[0, 1]), unsigned_cov01=float(unsigned[0, 1]), signed_score_gain=float(ds))
    check("T01", t01)

    # Population s-only second moment, represented by an exact deterministic ensemble.
    L = np.linalg.cholesky(.02*K)
    ensemble = np.r_[np.sqrt(n)*L.T, -np.sqrt(n)*L.T]
    donor = [dict(K=K, a=a, e=e, cluster=i, time=float(i*10)) for i, e in enumerate(ensemble)]
    fitted = None
    def t02():
        nonlocal fitted
        fitted = C.fit_models(donor)
        assert fitted["models"]["S1"]["theta_boundary"]
        assert fitted["models"]["S1"]["parameters"][1] == 0
        return fitted
    check("T02", t02)

    def t03():
        t = np.arange(200)*.2
        p = pairs_for(t, np.ones(200), np.ones(200)*7, t*.1, np.zeros(200))
        result = support_report(p, t)[3]
        assert result["status"] == "NO_SIGN_SUPPORT"
        # Constant signed design columns are exactly collinear even if magnitudes fit.
        x = np.c_[p["K"], p["K"]]
        assert np.linalg.matrix_rank(x) == 1
        return dict(status=result["status"], rank=int(np.linalg.matrix_rank(x)))
    check("T03", t03)

    def t04():
        t = np.arange(5000)*.2; arc = np.arange(5000)*.01; yaw = np.zeros(5000)
        white = rng.standard_normal((5000, 2)); shifted = white+np.array([2., -3.])
        parts = decompose(shifted, t, arc, yaw, D3)
        slow = parts["slow"][:, 1]
        raw_corr = float(np.corrcoef(white[:-1, 1], white[1:, 1])[0, 1])
        smooth_corr = float(np.corrcoef(slow[:-1], slow[1:])[0, 1])
        assert abs(raw_corr) < .08 and smooth_corr > .8
        donor_mean = float(shifted[:1000, 1].mean())
        holdout = shifted[3000:, 1]+5
        assert abs((holdout-donor_mean).mean()) > 4
        assert abs((holdout-holdout.mean()).mean()) < 1e-12
        return dict(raw_lag1=raw_corr, D3_slow_lag1=smooth_corr, oracle_holdout_centering_detected=True,
                    config=D3, D3_reference_sha256=sha(Path(__file__).with_name("reference_d3.py")))
    check("T04", t04)

    def t05():
        d = dict(t=np.array([0., 1., 20.]), truth=np.array([[0., 0., 0.], [1., 0., 0.], [0., 0., 0.]]))
        test = dict(t=np.array([50.]), truth=np.array([[0., 0., 0.]]))
        assert overlapping_blocks(d, test) == [0, 2]
        groups, pairs = revisit_groups(d)
        assert any(0 in g and 2 in g for g in groups)
        return dict(purged_train_blocks=[0, 2], linked_groups=groups, repeated_site_pairs=pairs)
    check("T05", t05)

    def t06():
        theta = .004; fac = np.pi/180
        rad = C.covariance(K, a, "S1", [.02, theta], 1e-9)
        degree = C.covariance(K, a*fac, "S1", [.02, theta/fac**2], 1e-9)
        assert np.allclose(rad, degree, rtol=1e-14, atol=1e-16)
        e = ensemble[0]
        diff = abs(C.logscore(e, rad)-C.logscore(e, degree))
        assert diff < 1e-10
        return dict(score_difference=diff, theta_rad2=theta, theta_deg2=theta/fac**2)
    check("T06", t06)

    def t07():
        assert fitted is not None
        before = json.dumps(fitted, sort_keys=True)
        heldout = dict(donor[0]); heldout["e"] = np.ones(n)*50
        after = C.fit_models(donor)
        assert before == json.dumps(after, sort_keys=True)
        score1, _ = C.score_models([donor[0]], fitted)
        score2, _ = C.score_models([heldout], fitted)
        assert score1[0]["scores"]["S0"] != score2[0]["scores"]["S0"]
        return dict(donor_fit_identical=True, holdout_perturbation_only_changes_score=True)
    check("T07", t07)

    def t08():
        for m in [K, (a[:, None]*K)*a[None, :]]:
            assert np.linalg.eigvalsh(m).min() >= -1e-12
            np.linalg.cholesky(m+1e-10*np.eye(n))
        s0 = C.covariance(K, a, "S0", [.02], 1e-9)
        s1 = C.covariance(K, a, "S1", [.02, 0.], 1e-9)
        assert np.array_equal(s0, s1)
        return dict(theta0_exact_parity=True, minimum_kernel_eigenvalue=float(np.linalg.eigvalsh(K).min()))
    check("T08", t08)

    def t09():
        size = 20; t = np.arange(size)*.2
        raw = dict(e_rf=np.ones(size)*.1, s_full=np.ones(size)*.1, s_los=np.zeros(size),
                   t=t, pose_id=np.arange(size), a_truth=np.ones(size), truth=np.zeros((size, 3)),
                   arc_m=t*.1, yaw_arc_rad=np.zeros(size), rho_m=np.ones(size)*7)
        C.validate_primary(raw, "ORIGINAL_NOISE_FREE_FULL_O30_MINUS_LOS_O30")
        caught = []
        for change, definition in [(dict(e_rf=np.ones(size)*.2), "ORIGINAL_NOISE_FREE_FULL_O30_MINUS_LOS_O30"),
                                   ({}, "M6_raw_s"), (dict(pose_id=np.zeros(size)), "ORIGINAL_NOISE_FREE_FULL_O30_MINUS_LOS_O30")]:
            try: C.validate_primary(dict(raw, **change), definition)
            except ValueError as e: caught.append(str(e))
        assert len(caught) == 3
        # Gate is not an input to primary component generation. All eligible raw points survive once.
        cmp = components(raw, np.ones(size, bool))
        assert sorted(i for c in cmp for i in c["indices"]) == list(range(size))
        return dict(rejected=caught, primary_has_no_gate_input=True, component_partition_exact=True)
    check("T09", t09)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    files = [Path(__file__), Path(__file__).with_name("covariance_core.py"), Path(__file__).with_name("reference_d3.py")]
    put(args.out/"RUN_CONTRACT.json", dict(stage="P2_SYNTHETIC_ONLY", inputs="synthetic only, no RF files opened", seed=20261116,
        sources={p.name: sha(p) for p in files}, mix_grid=list(map(float, np.linspace(0, 1, 21))),
        scale_log_bounds="log(donor mean square) +/-25", preliminary_S0="pseudoinverse for exact singular repeat coordinates; nullspace energy gate1e-10*max(1,sum_e2)",
        D3=D3, timestamp=dt.datetime.now(dt.timezone.utc).isoformat()))
    result = test_all()
    put(args.out/"TESTS.json", dict(passed=all(r["passed"] for r in result.values()), tests=result,
                                  timestamp=dt.datetime.now(dt.timezone.utc).isoformat()))
    print({k: r["passed"] for k, r in result.items()}, flush=True)
    raise SystemExit(0 if all(r["passed"] for r in result.values()) else 1)
