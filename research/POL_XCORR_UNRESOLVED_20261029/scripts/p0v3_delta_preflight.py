#!/usr/bin/env python3
"""POL-XCORR-001 v0.3 DRAFT: P0V3 delta preflight, label-free ONLY.

Implements R-04 exact tap/branch/separate validity parity (Full+LoS)
and R-14 direct seven-tap Jones port-energy and weak-port diagnostics (LoS).
This is IMPLEMENTER technical QA, not independent scientific audit.
Never read e_s, e_r, eta, labels, or run S0/P1/P2/P3.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import traceback

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SCOPE = HERE.parent
BASE_SHA = "250d617ad89a4105fa1af546cc83ceed9de98f42"
GOV_SHA = "d5f84d9d04d28d465f3357e9299352eb184e6bfc"
OLD_EXEC_SHA = "0574d26f4d71ec11b455d80374e4b6683b9f9f36"
EXPECTED_LOS = 9519
EXPECTED_BOTH = 19038
EXPECTED_WEAK = 3492
THRESHOLD = 0.05
TINY = np.finfo(np.float64).tiny
DET_NEG_REL = 1e-12
# Fixed before executing on data: numerical inverse is ill-conditioned near
# u=0.5, and epsilon near 0 provides no identifiable inverse.
INVERSE_EPS_MIN = 1e-10
INVERSE_U_MAX = 0.499
REFERENCE_COLUMNS = [
    "range_m", "log_fp_power", "abs_s_fp", "early4", "early8", "early16",
    "delay_rms_ns", "peak_diff_ns", "eta_fp_win80", "s_diff4", "s_diff8",
    "s_diff16", "tap_pol_var80", "jones_diversity", "freq_s_var",
    "detector_s_span", "detector_delay_span_ns"
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(2**20), b""):
            h.update(part)
    return h.hexdigest()


def save(path, obj):
    Path(path).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8"
    )


def optional_float(value):
    return float(value) if np.isfinite(value) else None


def source_import(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def r04_differences(tap, branch, fp_valid, g5, cir):
    """Four independent assertions; no scalar equality substitutes for indices."""
    tap = np.asarray(tap, dtype=np.int64)
    branch = np.asarray(branch, dtype=np.int64)
    fp_valid = np.asarray(fp_valid, dtype=bool)
    feat_tap = np.asarray(g5["tap"], dtype=np.int64)
    feat_branch = np.asarray(g5["branch"], dtype=np.int64)
    feat_valid = np.asarray(g5["valid"], dtype=bool)
    n = len(tap)
    amp = np.abs(cir)
    ix = np.arange(n)
    peaks = amp[ix, :, branch].max(axis=1)
    powers_at_shared_tap = amp[ix, tap, :] ** 2
    den = powers_at_shared_tap.sum(axis=1)
    expected_fp = (peaks > 0) & (den > TINY)
    expected_g5 = (peaks > 0) & ((tap + 80) <= cir.shape[1])
    mismatches = {
        "tap": np.flatnonzero(tap != feat_tap),
        "branch": np.flatnonzero(branch != feat_branch),
        "fp_valid": np.flatnonzero(fp_valid != expected_fp),
        "g5_valid": np.flatnonzero(feat_valid != expected_g5),
    }
    with np.errstate(divide="ignore", invalid="ignore"):
        signed = (powers_at_shared_tap[:, 0] - powers_at_shared_tap[:, 1]) / den
    sfp = np.asarray(g5["s_fp"], float)
    # Do not silently accept a port-index swap, two independent taps, or an
    # impossible nonfinite valid observation.
    bad_common = np.flatnonzero(
        expected_fp & (
            ~np.isfinite(signed) | ~np.isfinite(sfp)
            | (np.abs(signed - sfp) > 1e-12)
        )
    )
    mismatches["common_rx_tap"] = bad_common
    return mismatches, {
        "detector_valid_count": int(expected_fp.sum()),
        "g5_80tap_valid_count": int(expected_g5.sum()),
        "semantic_valid_difference_count": int(np.count_nonzero(expected_fp != expected_g5)),
    }


def strict_compare(new, ref, keys, cols, tol=1e-9):
    """Fail-closed reference comparison. No NaN/Inf allowed for listed columns."""
    if not set(keys + cols).issubset(new.columns) or not set(keys + cols).issubset(ref.columns):
        return {"status": "FAIL", "reason": "MISSING_COLUMN"}
    if new.duplicated(keys).any() or ref.duplicated(keys).any():
        return {"status": "FAIL", "reason": "DUPLICATE_KEY"}
    merged = new[keys + cols].merge(
        ref[keys + cols], on=keys, how="outer", validate="one_to_one",
        suffixes=("_new", "_ref"), indicator=True
    )
    if (merged["_merge"] != "both").any():
        return {"status": "FAIL", "reason": "KEY_COVERAGE", "unmatched": int((merged["_merge"] != "both").sum())}
    worst = 0.0
    for col in cols:
        a = merged[col + "_new"].to_numpy(float)
        b = merged[col + "_ref"].to_numpy(float)
        if not (np.isfinite(a).all() and np.isfinite(b).all()):
            return {"status": "FAIL", "reason": "NONFINITE_" + col}
        worst = max(worst, float(np.max(np.abs(a - b)))) if len(a) else worst
    return {"status": "PASS" if worst <= tol else "FAIL",
            "reason": "MATCHED" if worst <= tol else "VALUE_MISMATCH",
            "n": len(merged), "max_abs": worst, "tolerance_abs": tol}


def from_jones(J):
    """Independent explicit 2x2 algebra, never infer u from q/epsilon."""
    if J.shape != (2, 2) or not np.isfinite(J).all():
        return {"status": "NONFINITE"}
    a = float(J[0, 0].real)
    b = float(J[1, 1].real)
    t = a + b
    if not np.isfinite([a, b, t]).all():
        return {"status": "NONFINITE"}
    if t <= 0 or a <= TINY or b <= TINY:
        return {"status": "NULL_PORT"}
    cross = float(np.abs(J[0, 1])**2)
    det_raw = a*b - cross
    if not np.isfinite(det_raw):
        return {"status": "NONFINITE"}
    if det_raw < -DET_NEG_REL * t*t:
        return {"status": "NEGATIVE_DET", "det_raw": det_raw}
    det = max(det_raw, 0.0)  # only predeclared rounding-level negative
    u = min(a, b) / t
    q = 4.0 * det / (t*t)
    eps = det / (a*b)
    csq = cross / (a*b)
    if min(u, q, eps, csq) < -1e-10 or max(u, q, eps, csq) > 1.0 + 1e-10:
        return {"status": "NONPSD_NORMALIZATION"}
    return {"status": "VALID", "u": float(u), "q_W": float(q),
            "eps_rho": float(eps), "coherence_sq": float(csq),
            "weak_port": bool(u < THRESHOLD), "a": a, "b": b,
            "trace_j": t, "det_raw": det_raw}


def direct_port_metrics(cir, tap, inherited):
    """Same frozen seven-tap W and boundary flags, direct normalized J."""
    q_old, eps_old, status_old = inherited.coherency(cir, tap)
    if tap - 2 < 0 or tap + 6 >= len(cir) or tap - 10 < 0 or tap + 12 >= len(cir):
        return {"status": "INVALID_WINDOW"}
    w = cir[tap - 2:tap + 5]
    if not np.isfinite(w).all():
        return {"status": "NONFINITE"}
    scale = float(np.max(np.abs(w)))
    if scale <= TINY:
        return {"status": "NULL_PORT"}
    x = w / scale
    J = x.T @ x.conj()
    J = (J + J.conj().T) / 2
    rec = from_jones(J)
    if rec["status"] != status_old:
        raise AssertionError(f"R14 status mismatch: direct={rec['status']} inherited={status_old}")
    if rec["status"] == "VALID":
        if not (np.isclose(rec["q_W"], q_old, atol=1e-12, rtol=1e-12)
                and np.isclose(rec["eps_rho"], eps_old, atol=1e-12, rtol=1e-12)):
            raise AssertionError("R14 pre-existing seven-tap metric changed")
    return rec


def validate_identity(rec, tol_rel, tol_inverse):
    """Validation returns recorded errors and conditioning-aware inverse skip."""
    if rec["status"] != "VALID":
        return {"checked": False}
    u, q, e, c = rec["u"], rec["q_W"], rec["eps_rho"], rec["coherence_sq"]
    expected_q = 4*u*(1-u)*e
    error_q = abs(q - expected_q)
    error_eps = abs(e - (1-c))
    if error_q > tol_rel*max(1.0, abs(q), abs(expected_q)):
        raise AssertionError(f"q=4u(1-u)eps error {error_q}")
    if error_eps > tol_rel*max(1.0, abs(e), abs(1-c)):
        raise AssertionError(f"eps=1-coherence_sq error {error_eps}")
    inverse_error = None
    inverse_reason = None
    if e <= INVERSE_EPS_MIN:
        inverse_reason = "EPS_SMALL"
    elif u >= INVERSE_U_MAX:
        inverse_reason = "NEAR_BALANCED_INVERSE_ILL_CONDITIONED"
    else:
        r = q/e
        if not (0 <= r <= 1 + tol_rel):
            raise AssertionError(f"q/epsilon out of domain {r}")
        u_inv = (1.0 - np.sqrt(max(0.0, 1.0-r)))/2.0
        inverse_error = abs(u - u_inv)
        if inverse_error > tol_inverse:
            raise AssertionError(f"u inverse error {inverse_error}")
    return {"checked": True, "q_error": error_q, "eps_error": error_eps,
            "inverse_error": inverse_error, "inverse_skip": inverse_reason}


def negative_fixtures(original, feature_source):
    """Every deliberate corruption must be detected by the exact production check."""
    tests = {}
    nf = 257
    k = np.arange(nf)
    late = np.zeros((1, nf, 2), complex)
    late[0, :, 0] = np.exp(-2j*np.pi*k*250/nf)
    late[0, :, 1] = 0.4*np.exp(-2j*np.pi*k*250/nf)
    f = np.linspace(6250400000., 6749600000., nf)
    feats = feature_source.extract(late, f)
    cir, tap, branch, s, logp, valid_fp = original.independent_observer(late)
    mism, semantics = r04_differences(tap, branch, valid_fp, feats, cir)
    assert all(len(v)==0 for v in mism.values()), "uncorrupted late-tap parity"
    assert valid_fp[0] and not feats["valid"][0] and semantics["semantic_valid_difference_count"]==1
    tests["late_tap_FP_true_G5_false"] = "PASS"
    alt = tap.copy(); alt[0] += 1
    assert len(r04_differences(alt, branch, valid_fp, feats, cir)[0]["tap"]) == 1
    tests["wrong_tap_detected"] = "PASS"
    altb = branch.copy(); altb[0] = 1-altb[0]
    assert len(r04_differences(tap, altb, valid_fp, feats, cir)[0]["branch"]) == 1
    tests["wrong_branch_detected"] = "PASS"
    wrongfeat = dict(feats); wrongfeat["valid"] = ~np.asarray(feats["valid"])
    assert len(r04_differences(tap, branch, valid_fp, wrongfeat, cir)[0]["g5_valid"]) == 1
    tests["wrong_g5_valid_detected"] = "PASS"
    swapped = late[:,:,::-1].copy()
    cs, ts, bs, _, _, vs = original.independent_observer(swapped)
    assert len(r04_differences(ts, bs, vs, feats, cs)[0]["branch"]) == 1
    tests["swapped_rx_port_detected"] = "PASS"
    fpflip = ~valid_fp
    assert len(r04_differences(tap, branch, fpflip, feats, cir)[0]["fp_valid"]) == 1
    tests["wrong_FP_valid_detected"] = "PASS"
    # One-port-only false tap is not a shared two-port observation.
    fake = dict(feats); fake["s_fp"] = np.asarray(feats["s_fp"]).copy()+0.1
    assert len(r04_differences(tap, branch, valid_fp, fake, cir)[0]["common_rx_tap"]) == 1
    tests["separate_port_tap_or_power_detected"] = "PASS"

    new = pd.DataFrame({"case":["A","B"],"pose_id":[1,2],"value":[1.,2.]})
    ref = new.copy()
    assert strict_compare(new,ref,["case","pose_id"],["value"])["status"] == "PASS"
    bad = ref.copy();bad.loc[0,"value"] = np.nan
    assert strict_compare(new,bad,["case","pose_id"],["value"])["status"] == "FAIL"
    tests["reference_nan_detected"] = "PASS"
    bad = ref.copy();bad.loc[0,"value"] = np.inf
    assert strict_compare(new,bad,["case","pose_id"],["value"])["status"] == "FAIL"
    tests["reference_inf_detected"] = "PASS"
    assert strict_compare(new,ref.iloc[:1],["case","pose_id"],["value"])["status"] == "FAIL"
    tests["reference_missing_key_detected"] = "PASS"
    assert strict_compare(new,pd.concat([ref,ref.iloc[:1]]),["case","pose_id"],["value"])["status"] == "FAIL"
    tests["reference_duplicate_key_detected"] = "PASS"
    bad = ref.copy();bad.loc[0,"value"] = 3.
    assert strict_compare(new,bad,["case","pose_id"],["value"])["status"] == "FAIL"
    tests["reference_value_tamper_detected"] = "PASS"

    t = np.arange(1028)
    pulse = np.exp(-0.5*((t-80)/5)**2)
    ideal = np.column_stack((pulse, .6j*pulse))
    rank1 = direct_port_metrics(ideal, 80, original)
    assert rank1["status"] == "VALID" and rank1["q_W"] < 1e-10
    tests["rank1_complex_ellipse_valid"] = "PASS"
    bal = np.column_stack((pulse, 1j*pulse))
    r = direct_port_metrics(bal, 80, original)
    assert r["status"] == "VALID" and not r["weak_port"] and abs(r["u"]-0.5)<1e-12
    tests["balanced_port_valid"] = "PASS"
    near = np.column_stack((pulse, 1e-5*pulse + 4e-6*np.roll(pulse, 1)))
    r = direct_port_metrics(near, 80, original)
    assert r["status"] == "VALID" and r["weak_port"] and np.isfinite(r["eps_rho"])
    tests["tiny_nonzero_port_valid_weak"] = "PASS"
    assert direct_port_metrics(np.zeros_like(ideal),80,original)["status"] == "NULL_PORT"
    tests["zero_over_zero_null"] = "PASS"
    one = ideal.copy();one[:,1] = 0
    assert direct_port_metrics(one,80,original)["status"] == "NULL_PORT"
    tests["null_port_invalid"] = "PASS"
    bad = ideal.copy();bad[80,0] = np.nan
    assert direct_port_metrics(bad,80,original)["status"] == "NONFINITE"
    tests["nan_CIR_invalid"] = "PASS"
    bad = ideal.copy();bad[80,0] = np.inf
    assert direct_port_metrics(bad,80,original)["status"] == "NONFINITE"
    tests["inf_CIR_invalid"] = "PASS"
    assert from_jones(np.array([[1.,2.],[2.,1.]],complex))["status"] == "NEGATIVE_DET"
    tests["negative_determinant_rejected"] = "PASS"
    assert direct_port_metrics(ideal,1,original)["status"] == "INVALID_WINDOW"
    tests["boundary_window_invalid"] = "PASS"
    return tests


def summary_port_balance(table):
    """No weak rows dropped; stratification is diagnostic only."""
    groups = [("ALL",table),("TIMELINE",table[table.stratum=="TIMELINE"]),
              ("TIMELINE_DRIVE",table[(table.stratum=="TIMELINE") & (table.phase=="drive")]),
              ("TIMELINE_TURN",table[(table.stratum=="TIMELINE") & (table.phase=="turn")]),
              ("STATIC_YAW_SWEEP",table[table.stratum=="STATIC_YAW_SWEEP"])]
    for (case, stratum, phase), grp in table.groupby(["case","stratum","phase"],dropna=False,sort=True):
        groups.append((f"{case}/{stratum}/{phase}",grp))
    records = []
    for ident, grp in groups:
        good = grp[grp.status=="VALID"]
        weak = good[good.weak_port==True]
        strong = good[good.weak_port==False]
        row = {"group":ident,"n_total":len(grp),"n_valid":len(good),
               "n_invalid":len(grp)-len(good),
               "n_weak":len(weak),
               "fraction_weak":len(weak)/len(good) if len(good) else None}
        for subset_name, subset in [("all",good),("weak",weak),("strong",strong)]:
            for var in ["q_W","eps_rho"]:
                for level in [5,50,95]:
                    row[f"{var}_{subset_name}_p{level:02}"] = (
                        float(subset[var].quantile(level/100)) if len(subset) else None
                    )
        records.append(row)
    return pd.DataFrame(records)


def run(args):
    repo=Path(args.repo_root).resolve()
    scope=repo/"research/POL_XCORR_UNRESOLVED_20261029"
    output=Path(args.out).resolve()
    if output.exists():
        raise FileExistsError(f"Append-only P0V3 output already exists: {output}")
    output.mkdir(parents=True)
    checks={}; problems=[]; status="BLOCKED"; outputs=[]
    meta={"base_git_sha": BASE_SHA,"governance_git_sha":GOV_SHA,
          "historic_p0_execution_source_sha":OLD_EXEC_SHA,
          "independent_auditor":"NOT_ASSIGNED",
          "scope":"P0V3_DELTA_PREFLIGHT_ONLY",
          "full_channel_M1_computation":"PROHIBITED",
          "metric_label_relationship":"PROHIBITED"}
    def record(name, value, classification="CORE"):
        checks[name]={"class":classification,**value}
    try:
        old=source_import(HERE/"p0_preflight.py","pol_xcorr_p0_original")
        source=repo/"research/PHYSICS_RS_STAGED_20261015/code/features.py"
        feat=source_import(source,"locked_g5_features")
        params_path=scope/"config/PLAN_PARAMETERS_v0.3.json"
        lock_path=scope/"config/INPUT_LOCK_v2.json"
        params=json.loads(params_path.read_text())
        lock=json.loads(lock_path.read_text())
        tol=params["tolerances_fixed_before_run"]
        assert float(tol["r14_q_identity_rel"])==1e-10
        assert float(tol["r14_u_inverse_abs"])==1e-9
        assert int(tol["r04_tap_branch_valid_mismatch_count"])==0
        assert list(feat.GROUPS["G5"])==REFERENCE_COLUMNS
        assert params["metrics"]["weak_port_policy"]["nominal_threshold"]==THRESHOLD
        expected_feat=next(x["sha256"] for x in lock["assets"] if x["path"].endswith("/features.py"))
        if sha(source)!=expected_feat:
            raise AssertionError("Locked features.py SHA mismatch")
        meta.update({"draft_v03_contract_sha256":sha(scope/"contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md"),
                     "draft_v03_config_sha256":sha(params_path),"v03_science_spec_sha256":sha(scope/"SCIENCE_SPEC_v0.3.md"),
                     "input_lock_sha256":sha(lock_path),"features_source_sha256":sha(source),
                     "inherited_p0_sha256":sha(HERE/"p0_preflight.py"),
                     "p0v3_script_sha256":sha(Path(__file__).resolve()),
                     "r04_threshold_count":0,"r14_identity_tolerance":1e-10,
                     "r14_inverse_tolerance":1e-9, "r14_inverse_condition":{
                         "eps_min":INVERSE_EPS_MIN,"u_max_exclusive":INVERSE_U_MAX}})
        fixture_results=negative_fixtures(old,feat)
        save(output/"P0V3_NEGATIVE_FIXTURES.json",{"status":"PASS","count":len(fixture_results),
                                                  "tests":fixture_results})
        outputs.append("P0V3_NEGATIVE_FIXTURES.json")
        record("NEGATIVE_FIXTURES",{"status":"PASS","count":len(fixture_results)})
        if args.fixtures_only:
            status="FIXTURES_ONLY_NO_RAW_DATA"
            return status
        locked,missing,wrong,t4=old.verify_hashes(repo,lock)
        record("LOCKED_INPUT_SHA256",{"status":"FAIL" if wrong or missing else "PASS",
                                    "missing":missing,"mismatch":wrong,"n_assets":len(locked)})
        record("TRACE_SET_HASHES",t4,"T4_ONLY")
        if missing or wrong:
            raise AssertionError("Core input hashes missing or mismatched")
        master=json.loads((repo/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
        align,pose_counts,_=old.align_poses(repo,master)
        assert len(align)==EXPECTED_LOS
        if align.duplicated(["case","pose_id"]).any():
            raise AssertionError("pose keys duplicate")
        join=align[["case","pose_id","stratum","phase","yaw_body_deg"]]
        fpath=next(x["path"] for x in lock["assets"] if x["kind"]=="FREQUENCY")
        frequency=np.load(repo/fpath,allow_pickle=False)
        assert len(frequency)==257 and np.isfinite(frequency).all()
        parity_rows=[]; weak_rows=[]; reference_rows=[]
        failures=[]; n_checked=0
        for case in master["cases"]:
            name=case["id"]; route=case["route"]
            samples=json.loads((repo/case["samples_path"]).read_text())
            pose_ids=np.asarray([r["pose_id"] for r in samples],dtype=np.int64)
            for channel,key in (("full","full_path"),("los","los_path")):
                H=np.load(repo/case[key],mmap_mode="r",allow_pickle=False)
                if H.shape!=(len(pose_ids),257,2,2):
                    raise AssertionError(f"H shape mismatch: {name}/{channel}")
                totals={name:0 for name in ("tap","branch","fp_valid","g5_valid","common_rx_tap")}
                edge_differences=0; seen=0
                for start in range(0,len(pose_ids),64):
                    stop=min(start+64,len(pose_ids))
                    chunk=np.asarray(H[start:stop,:,:,0])
                    f=feat.extract(chunk,frequency)
                    cir,tap,branch,s,logp,valid=old.independent_observer(chunk)
                    d,sem=r04_differences(tap,branch,valid,f,cir)
                    for category, indices in d.items():
                        totals[category]+=len(indices)
                        for index in indices[:max(0,20-len(failures))]:
                            failures.append({"case":name,"channel":channel,
                                             "pose_id":int(pose_ids[start+index]),
                                             "type":category})
                    edge_differences+=sem["semantic_valid_difference_count"]
                    seen+=stop-start
                    if channel=="full":
                        frame=pd.DataFrame({"case":name,"pose_id":pose_ids[start:stop],
                                            "s_fp":s,"log_fp_power":logp})
                        for col in REFERENCE_COLUMNS:
                            frame[col]=f[col]
                        reference_rows.append(frame)
                    else:
                        for j,pose in enumerate(pose_ids[start:stop]):
                            r=direct_port_metrics(cir[j],int(tap[j]),old)
                            qa=validate_identity(r,float(tol["r14_q_identity_rel"]),
                                                float(tol["r14_u_inverse_abs"]))
                            weak_rows.append({"case":name,"route":route,"pose_id":int(pose),
                                              "n0":int(tap[j]),"branch":int(branch[j]),
                                              "status":r["status"],"u":r.get("u"),
                                              "weak_port":r.get("weak_port"),
                                              "q_W":r.get("q_W"),"eps_rho":r.get("eps_rho"),
                                              "coherence_sq":r.get("coherence_sq"),
                                              "j11_normalized":r.get("a"),"j22_normalized":r.get("b"),
                                              "q_identity_err":qa.get("q_error"),
                                              "eps_identity_err":qa.get("eps_error"),
                                              "u_inverse_err":qa.get("inverse_error"),
                                              "u_inverse_skip":qa.get("inverse_skip")})
                n_checked+=seen
                parity_rows.append({"case":name,"channel":channel,"n":seen,
                                    **{f"{category}_mismatches":value for category,value in totals.items()},
                                    "expected_FP_vs_G5_valid_differences":edge_differences,
                                    "status":"PASS" if not any(totals.values()) else "FAIL"})
        parity=pd.DataFrame(parity_rows)
        parity.to_csv(output/"P0V3_TAP_BRANCH_PARITY.csv",index=False)
        outputs.append("P0V3_TAP_BRANCH_PARITY.csv")
        save(output/"P0V3_R04_ADVERSARIAL_KEYS.json",{"first20":failures[:20]})
        outputs.append("P0V3_R04_ADVERSARIAL_KEYS.json")
        R04_pass=(n_checked==EXPECTED_BOTH and len(parity)==14
                  and (parity.status=="PASS").all() and (parity.n.sum()==EXPECTED_BOTH))
        record("R04_DIRECT_TAP_BRANCH_VALID",
               {"status":"PASS" if R04_pass else "FAIL","rows_checked":n_checked,
                "cases_channels":len(parity),
                "mismatch_total":int(parity[[x for x in parity.columns if x.endswith("_mismatches")]].to_numpy().sum()),
                "first20":failures[:20]})
        if not R04_pass:
            raise AssertionError("R04 direct per-index parity failure")
        los=pd.DataFrame(weak_rows)
        los=los.merge(join,on=["case","pose_id"],how="left",validate="one_to_one",indicator=True)
        if len(los)!=EXPECTED_LOS or (los["_merge"]!="both").any():
            raise AssertionError("R14 LoS key coverage mismatch")
        los.drop(columns=["_merge"],inplace=True)
        los.to_csv(output/"P0V3_LOS_PORT_BALANCE.csv",index=False)
        outputs.append("P0V3_LOS_PORT_BALANCE.csv")
        valid=los[los.status=="VALID"]
        summary=summary_port_balance(los)
        summary.to_csv(output/"P0V3_WEAK_PORT_SUMMARY.csv",index=False)
        outputs.append("P0V3_WEAK_PORT_SUMMARY.csv")
        inverse_e=valid.u_inverse_err.dropna()
        errs={"q_identity_max":float(valid.q_identity_err.max()),
              "eps_identity_max":float(valid.eps_identity_err.max()),
              "u_inverse_max":float(inverse_e.max()) if len(inverse_e) else None,
              "inverse_n_checked":len(inverse_e),
              "inverse_n_skipped":int(valid.u_inverse_err.isna().sum()),
              "inverse_skip_counts":valid.u_inverse_skip.value_counts().to_dict()}
        passed=(len(valid)==EXPECTED_LOS and int(valid.weak_port.sum())==EXPECTED_WEAK
                and int(((los.stratum=="TIMELINE")&(los.weak_port==True)).sum())==3105
                and int(((los.stratum=="TIMELINE")).sum())==7251)
        save(output/"P0V3_R14_MATH_QA.json",{
            "status":"PASS" if passed else "FAIL", "n_total":len(los),
            "n_valid":len(valid),"n_weak":int(valid.weak_port.sum()),
            "n_timeline":int((los.stratum=="TIMELINE").sum()),
            "n_timeline_weak":int(((los.stratum=="TIMELINE")&(los.weak_port==True)).sum()),
            "expected_guard":{"n_valid":EXPECTED_LOS,"n_weak":EXPECTED_WEAK,"timeline":7251,"timeline_weak":3105},
            "tolerance":{"q_identity_rel":float(tol["r14_q_identity_rel"]),
                         "u_inverse_abs":float(tol["r14_u_inverse_abs"])},
            "errors":errs,
            "note":"WEAK_PORT is a flag only; no rows masked, no oracle label reads, no S0 q_ref."
        })
        outputs.append("P0V3_R14_MATH_QA.json")
        record("R14_DIRECT_J_PORT_BALANCE",{"status":"PASS" if passed else "FAIL",**errs,
                "n_valid":len(valid),"n_weak":int(valid.weak_port.sum())})
        if not passed:
            raise AssertionError("R14 valid or weak-port count violates fixed guard")

        # Preserve and recheck the historical reference lineage, but never load
        # e_s/e_r/label columns. The supplemental R-13b artifact remains historical.
        refs=json.loads((scope/"config/P0_REFERENCES_v0.2.json").read_text())["references"]
        full=pd.concat(reference_rows,ignore_index=True)
        hp_path=repo/refs["R-02"]["table"]
        um_path=repo/refs["R-13a"]["table"]
        assert sha(hp_path)==refs["R-02"]["sha256"],"HP reference SHA"
        assert sha(um_path)==refs["R-13a"]["sha256"],"UM reference SHA"
        hp=pd.read_csv(hp_path,usecols=["case","pose_id","sF_+0","log_fp_power"])
        um=pd.read_csv(um_path,usecols=["case","pose_id"]+REFERENCE_COLUMNS)
        checks_ref={
            "R-02":strict_compare(full,hp.rename(columns={"sF_+0":"s_fp"}),
                                  ["case","pose_id"],["s_fp"],1e-9),
            "R-12":strict_compare(full,hp,["case","pose_id"],["log_fp_power"],1e-9),
            "R-13a":strict_compare(full,um,["case","pose_id"],REFERENCE_COLUMNS,1e-9)
        }
        save(output/"P0V3_REFERENCE_AUDIT.json",{
            "checks":checks_ref,"r13b_status":"HISTORICAL_PASS_NOT_REEXECUTED",
            "r13b_historical_run":39376076166,
            "r13b_expires_utc":"2026-11-19T05:41:39Z",
            "no_label_columns_read":True,
            "source_sha256":{"HP_PACKETS":sha(hp_path),"UM_POSE_TABLE":sha(um_path)}
        })
        outputs.append("P0V3_REFERENCE_AUDIT.json")
        record("R02_R12_R13A_REFERENCE_RECHECK",{
            "status":"PASS" if all(v["status"]=="PASS" for v in checks_ref.values()) else "FAIL",
            "checks":checks_ref})
        if any(v["status"]!="PASS" for v in checks_ref.values()):
            raise AssertionError("Stored reference check failed")
        status="P0V3_CORE_TECHNICAL_PASS"
    except Exception as exc:
        problems.append({"error":str(exc),"traceback":traceback.format_exc()})
        status="P0V3_CORE_FAIL"
    finally:
        save(output/"P0V3_STATUS.json",{
            "role":"IMPLEMENTER","contract_id":"POL-XCORR-001","phase":"P0V3_DELTA_PREFLIGHT_ONLY",
            "status":status,"checks":checks,"errors":problems,
            "science":"NOT_RUN","auditor":"NOT_ASSIGNED",
            "frozen":False,"S0_P1_P2_P3":"BLOCKED_CONTRACT_INCOMPLETE"})
        outputs.append("P0V3_STATUS.json")
        git_sha = None
        try:
            git_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
        except Exception:
            pass
        meta.update({"execution_git_sha":git_sha,
                     "execution_script_git_path":"research/POL_XCORR_UNRESOLVED_20261029/scripts/p0v3_delta_preflight.py",
                     "timestamp_utc":datetime.now(timezone.utc).isoformat(),
                     "command":sys.argv,"python":platform.python_version(),
                     "numpy":np.__version__,"pandas":pd.__version__,
                     "host":platform.platform(),"result_status":status,
                     "results":{"R01_T4":"T4_ONLY_BLOCKED","R03":"MEASURED_ONLY",
                                "R10_INDEPENDENT_AUDITOR":"BLOCKED",
                                "S0_P1_P2_P3":"NOT_RUN"},
                     "original_P0_results":"PRESERVED_IMMUTABLE",
                     "output_file_sha256":{f.name:sha(f) for f in output.iterdir() if f.is_file()},
                     "issues":problems})
        save(output/"MANIFEST.json",meta)
        outputs.append("MANIFEST.json")
        (output/"IMPLEMENTER_REVIEW_02.md").write_text(
            "# IMPLEMENTER_REVIEW_02 — POL-XCORR P0V3 delta\n\n"
            + f"- Role: IMPLEMENTER\n- Status: {status}\n- Execution git SHA: {git_sha}\n"
            + f"- Base source SHA: {BASE_SHA}\n- Governance SHA: {GOV_SHA}\n"
            + f"- Contract v0.3 SHA256: {meta.get('draft_v03_contract_sha256','UNAVAILABLE')}\n"
            + "- Scope: R04 exact per-packet tap, branch and two distinct valid definitions (Full+LoS);"
              " R14 direct 7-tap LoS-only weak-port flag, exact identities and negative fixtures.\n"
            + "- Prior source/data/results: UNMODIFIED. No Full M1 metrics, metric-label analysis, RT, S0/P1/P2/P3.\n"
            + "- R01 T4_ONLY_BLOCKED; R03 MEASURED_ONLY; independent AUDITOR R10 pending; FROZEN NOT AUTHORIZED.\n"
            + f"- Checks: {json.dumps({k:v.get('status') for k,v in checks.items()}, ensure_ascii=False)}\n"
            + f"- Problems: {json.dumps(problems, ensure_ascii=False)}\n"
            + "- Next: independent auditor re-derivation and signed pre-freeze review; verify F-11 and reference archival.\n",
            encoding="utf-8"
        )
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root",required=True)
    p.add_argument("--out",required=True,help="New append-only output directory")
    p.add_argument("--fixtures-only",action="store_true")
    args=p.parse_args()
    status=run(args)
    print(json.dumps({"result_status":status,"output":args.out}))
    return 0 if status in ("P0V3_CORE_TECHNICAL_PASS","FIXTURES_ONLY_NO_RAW_DATA") else 2


if __name__=="__main__":
    raise SystemExit(main())
