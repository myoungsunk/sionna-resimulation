#!/usr/bin/env python3
"""POL-XCORR-001 v1.0 S0 IMPLEMENTER: signed-freeze synthetic law and R-03.

Scope: S0 only. 257-bin synthetic H, original first-path/CIR observer, saved
label-free P0 LoS floor, deterministic seeded noise. NEVER open Full RF H,
HP_PACKETS, e_s/e_r, labels, P1/P2 datasets or run any trained learner.

Science gate failures are recorded without hiding a technically valid run.
The v1.0 freeze is SELF_REVIEW_ONLY; this code does not issue independent audit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import traceback

import numpy as np
import pandas as pd

PROJECT = Path("research/POL_XCORR_UNRESOLVED_20261029")
CONTRACT_ID = "POL-XCORR-001"
BASE_SHA = "250d617ad89a4105fa1af546cc83ceed9de98f42"
GOV_SHA = "d5f84d9d04d28d465f3357e9299352eb184e6bfc"
FREEZE_SHA = "50703065b8ba716fe50e13bae0ae6fd38eacc3c3"
FROZEN = {
    "contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md":
        "c36c1c56d4db59d39ea85e1d87c1efe622325730a6b4fbc595fc95e583cde219",
    "contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v0.3.md":
        "39c396c72688d88efa84d0fcb7779ad2b5b693891ab87aaae803bd26793cb76e",
    "SCIENCE_SPEC_v0.3.md":
        "5db75dcc0a332833de50d87ba2081bea5ca0cd74e7e093ae00ce987728368450",
    "config/PLAN_PARAMETERS_v1.0.json":
        "a16e8226f2766f4188c144228f99276c0102532667eb1e46816c0b4e0ff42658",
    "config/INPUT_LOCK_v2.json":
        "bddab15801f8d8c653eeb7f825ff71352d48bda7bf7b650f59a2feb300458184",
}
P0_LOS_REL = PROJECT / "results_p0/run_40867521966/LOS_FLOOR.csv"
P0_MANIFEST_REL = PROJECT / "results_p0/run_40867521966/MANIFEST.json"
TINY = np.finfo(float).tiny
PHASE = "S0_SYNTHETIC_ONLY"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def save_json(path, record):
    Path(path).write_text(
        json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8"
    )


def number(value):
    if value is None:
        return None
    f = float(value)
    return f if np.isfinite(f) else None


def load_observer(scope):
    path = scope / "scripts/p0_preflight.py"
    spec = importlib.util.spec_from_file_location("pol_xcorr_frozen_p0_observer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def verify_freeze(scope):
    mismatches = []
    actual = {}
    for relative, expected in FROZEN.items():
        p = scope / relative
        value = sha(p) if p.is_file() else None
        actual[relative] = value
        if value != expected:
            mismatches.append({"path": str(relative), "expected": expected, "actual": value})
    if mismatches:
        raise RuntimeError("BLOCKED_CONTRACT_MISMATCH: " + str(mismatches))
    return actual


def verify_inputs(root, scope):
    lock = json.loads((scope / "config/INPUT_LOCK_v2.json").read_text())
    freq_spec = [x for x in lock["assets"] if x["kind"] == "FREQUENCY"]
    if len(freq_spec) != 1:
        raise AssertionError("FREQUENCY_LOCK_NOT_UNIQUE")
    item = freq_spec[0]
    fpath = root / item["path"]
    if sha(fpath) != item["sha256"]:
        raise AssertionError("FREQUENCY_SHA_MISMATCH")
    freqs = np.load(fpath, allow_pickle=False)
    if freqs.shape != (257,) or not np.isfinite(freqs).all():
        raise AssertionError("FREQUENCY_GRID_INVALID")
    delta_f = np.diff(freqs)
    if not np.allclose(delta_f, delta_f[0], rtol=1e-10, atol=1e-5):
        raise AssertionError("FREQUENCY_GRID_NOT_UNIFORM")
    manifest = json.loads((root / P0_MANIFEST_REL).read_text())
    p0path = root / P0_LOS_REL
    p0_sha = sha(p0path)
    if p0_sha != manifest["files"]["LOS_FLOOR.csv"]:
        raise AssertionError("P0_LOS_FLOOR_SHA_MISMATCH")
    # Strict usecols: no label, no Full channel, no label-score relationship.
    los = pd.read_csv(p0path, usecols=["case", "pose_id", "stratum", "status", "q_W"])
    if len(los) != 9519 or los.duplicated(["case", "pose_id"]).any():
        raise AssertionError("P0_LOS_COVERAGE_INVALID")
    if not (los.status == "VALID").all():
        raise AssertionError("P0_LOS_INVALID_PRESENT")
    if not np.isfinite(los.q_W).all():
        raise AssertionError("P0_LOS_Q_NONFINITE")
    timeline = los.loc[los.stratum == "TIMELINE"]
    if len(timeline) != 7251:
        raise AssertionError("P0_LOS_TIMELINE_COVERAGE")
    q95 = float(np.quantile(timeline.q_W.to_numpy(float), 0.95, method="linear"))
    per_case = timeline.groupby("case").q_W.quantile(.95).to_dict()
    return freqs, los, {"p0_los_sha256": p0_sha, "freq_sha256": item["sha256"],
                        "freq_path": item["path"], "p0_los_path": P0_LOS_REL.as_posix(),
                        "timeline_n": len(timeline), "q95_timeline": q95,
                        "q95_by_case": {k: float(v) for k, v in per_case.items()},
                        "q95_max_case_descriptive_only": float(max(per_case.values())),
                        "delta_f_hz": float(delta_f[0]),
                        "dt_ns": 1e9/(4*len(freqs)*delta_f[0])}


def basis(wedge, ratio_db, a, perp):
    amp = 10.0 ** (ratio_db / 20.0)
    b = amp * (math.sqrt(max(0.0, 1.0 - wedge**2)) * a + wedge * perp)
    if wedge > 0:
        actual = abs(a[0]*b[1] - a[1]*b[0]) / (np.linalg.norm(a)*np.linalg.norm(b))
        if abs(actual-wedge) > 1e-12:
            raise AssertionError(f"WEDGE_GEOMETRY_INVALID {wedge} {actual}")
    return b


def H_two(freqs, a, b, tau0_ns, delta_ns, psi):
    """Exact frozen v1.0 D6 physical-f argument; never substitute f-fc."""
    tau = float(tau0_ns) * 1e-9
    delta = float(delta_ns) * 1e-9
    base = np.exp(-2j*np.pi*freqs*tau)
    delayed = np.exp(1j*float(psi) - 2j*np.pi*freqs*delta)
    return base[:,None]*(a[None,:] + delayed[:,None]*b[None,:])


def observe(H, p0):
    cir, taps, branches, _s, _logp, fpvalid = p0.independent_observer(H[None,:,:])
    n0 = int(taps[0])
    h = cir[0]
    q, eps, flag = p0.coherency(h, n0)
    if not bool(fpvalid[0]) or flag != "VALID":
        return {"status": flag if flag != "VALID" else "FP_INVALID", "n0": n0,
                "q_W": None, "eps_rho": None, "phi_fp": None, "S3_fp": None}, h
    p = np.abs(h[n0])**2
    scalar = h[n0,0] * np.conj(h[n0,1])
    energy = float(p.sum())
    phi = float(np.angle(scalar))
    s3 = float(2.0 * np.imag(scalar)/energy)
    if not np.isfinite([q,eps,phi,s3]).all() or q < -1e-12 or q > 1+1e-12:
        raise AssertionError(f"SYNTHETIC_OBSERVATION_INVALID q={q} eps={eps}")
    return {"status": "VALID", "n0": n0, "q_W": float(q),
            "eps_rho": float(eps), "phi_fp": phi, "S3_fp": s3}, h


def q_ref(freqs, p0, los_info, params):
    spec = params["freeze_deltas"]["D6_disambiguation"]["q_ref_construction"]
    assert spec["delta_ns"] == 1.0 and spec["tau0_ns"] == 20.0
    a = np.array([1+0j, 1+0j], complex)/math.sqrt(2)
    perpendicular = np.array([1+0j, -1+0j], complex)/math.sqrt(2)
    b = basis(0.3,-10.0,a,perpendicular)
    a_alt = np.array([1+0j,.3j],complex)
    a_alt /= np.linalg.norm(a_alt)
    # Normalized complex-orthogonal Jones vector, sensitivity report only.
    alt_perp = np.array([-np.conj(a_alt[1]),np.conj(a_alt[0])],complex)
    b_alt = basis(0.3,-10.,a_alt,alt_perp)
    values = []; sensitivity = []
    for k in range(16):
        psi=2*np.pi*k/16
        near = bool(np.linalg.norm(a+b*np.exp(1j*psi)) < .3*np.linalg.norm(a))
        rec, _ = observe(H_two(freqs,a,b,20.,1.,psi),p0)
        if rec["status"]!="VALID":
            raise AssertionError(f"QREF_INVALID k={k}: {rec['status']}")
        values.append({"psi_index":k,"psi_rad":float(psi),
                       "near_cancel":near,"q_W":rec["q_W"],"n0":rec["n0"]})
        alt, _ = observe(H_two(freqs,a_alt,b_alt,20.,1.,psi),p0)
        if alt["status"]!="VALID":
            raise AssertionError("QREF_SENSITIVITY_INVALID")
        sensitivity.append(alt["q_W"])
    selected=[x["q_W"] for x in values if not x["near_cancel"]]
    if not selected:
        raise AssertionError("QREF_ALL_EXCLUDED")
    reference=float(np.mean(selected))
    if reference <= 0 or not np.isfinite(reference):
        raise AssertionError("QREF_NOT_POSITIVE")
    los95=los_info["q95_timeline"]
    if los95 <= 0.1*reference:
        verdict="NEGLIGIBLE"
    elif los95 <= reference:
        verdict="NUISANCE"
    else:
        verdict="REDESIGN_REQUIRED"
    return {"status":"MEASURED_AND_CLASSIFIED", "q_ref":reference,
            "q95_timeline":los95, "q95_by_case":los_info["q95_by_case"],
            "q95_case_max_descriptive_only":los_info["q95_max_case_descriptive_only"],
            "q95_source_n":los_info["timeline_n"],"q95_method":"np.quantile(linear)",
            "q95_source_sha256":los_info["p0_los_sha256"],
            "threshold_0p1_qref":.1*reference,
            "floor_over_reference":float(los95/reference),
            "decision":verdict,"qref_psi_rows":values,
            "n_qref_psi_included":len(selected),
            "sensitivity_a_complex_elliptic_qref_mean":
                float(np.mean(sensitivity)),
            "sensitivity_perpendicular_construction":
                "(-conj(a[1]),conj(a[0])) (report-only)",
            "rule_frozen_before_S0":True,"reference_amplitude_dB":-10.,
            "wedge":.3,"delta_ns":1.0,"tau0_ns":20.0,
            "contract_v1_sha256":FROZEN["contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md"]}


def law_sweep(freqs, p0, params):
    syn = params["s0_synthetic"]
    fit_lo,fit_hi = params["tolerances_fixed_before_run"]["s0_delta_fit_range_ns"]
    slope_lo,slope_hi = params["tolerances_fixed_before_run"]["s0_delta_square_slope"]
    assert syn["rng"]=="numpy PCG64"
    assert syn["delta_ns_grid"]=="0 to 4 step 0.05"
    assert syn["psi_grid"]=="0 to 2pi, 16 points"
    assert list(syn["amp_ratio_db_grid"])==[-20,-10,-6,-3]
    assert (fit_lo,fit_hi)==(.05,1.)
    delta_vals=np.round(np.linspace(0.,4.,81),12)
    a=np.array([1.+0j,1.+0j], complex)/math.sqrt(2)
    ap=np.array([1.+0j,-1.+0j],complex)/math.sqrt(2)
    wedge_vals=[0.,.1,.3,.6,1.]
    law=[]; slope_records=[]
    n_zero=0;n_invalid=0
    for ratio in syn["amp_ratio_db_grid"]:
        for wedge in wedge_vals:
            b=basis(wedge,ratio,a,ap)
            for k in range(16):
                psi=2*np.pi*k/16
                near=bool(np.linalg.norm(a+b*np.exp(1j*psi)) < .3*np.linalg.norm(a))
                prev=None;segment=-1
                rows=[]
                for d in delta_vals:
                    obs,_=observe(H_two(freqs,a,b,20.,d,psi),p0)
                    switch=(prev is not None and prev!=obs["n0"])
                    if prev is None or switch:
                        segment+=1
                    prev=obs["n0"]
                    line={"mode":"LAW","delta_ns":float(d),"psi":float(psi),
                          "psi_index":k, "wedge":wedge,"amp_ratio_db":ratio,
                          "snr_db":None,"offset_ps":None,"seed":None,
                          "n0":obs["n0"],"n0_switch":bool(switch),
                          "n0_segment":segment,
                          "q_W":obs["q_W"],"eps_rho":obs["eps_rho"],
                          "phi_fp":obs["phi_fp"],"S3_fp":obs["S3_fp"],
                          "near_cancel":near,"valid_flag":obs["status"]}
                    law.append(line);rows.append(line)
                    if obs["status"]!="VALID":
                        n_invalid+=1
                    if wedge==0 and obs["q_W"] is not None:
                        n_zero+=1
                        if obs["q_W"]>params["tolerances_fixed_before_run"]["s0_parallel_jones_eps_max"]:
                            raise AssertionError(f"PARALLEL_JONES_Q_FAIL: {ratio} {k} {d} {obs['q_W']}")
                # Register EVERY segment, including those not eligible for slope.
                for seg in sorted(set(x["n0_segment"] for x in rows)):
                    part=[x for x in rows if x["n0_segment"]==seg]
                    eligible=[x for x in part if fit_lo<=x["delta_ns"]<=fit_hi and
                              x["valid_flag"]=="VALID" and not near and wedge>0
                              and x["q_W"] is not None and x["q_W"]>1e-20]
                    slope=None
                    if near:
                        st="NEAR_CANCEL_PREDEFINED"
                    elif wedge==0:
                        st="PARALLEL_JONES_NEGATIVE_CONTROL"
                    elif len(eligible)<3:
                        st="NOT_EVALUABLE_SHORT_SEGMENT_OR_FLOOR"
                    else:
                        slope=float(np.polyfit(np.log([x["delta_ns"] for x in eligible]),
                                               np.log([x["q_W"] for x in eligible]),1)[0])
                        st="PASS" if slope_lo<=slope<=slope_hi else "FAIL"
                    slope_records.append({"mode":"LAW","amp_ratio_db":ratio,"wedge":wedge,
                                          "psi_index":k,"psi_rad":float(psi),"n0_segment":seg,
                                          "n0":part[0]["n0"],"n0_switch_count":sum(x["n0_switch"] for x in part),
                                          "n_total":len(part),"n_fit":len(eligible),"near_cancel":near,
                                          "slope_log_q_log_delta":slope,"status":st})
    # PHYSICAL: no independently varied phase. Do not fit a slope or adjudicate.
    fc=float(np.mean(freqs))
    for ratio in syn["amp_ratio_db_grid"]:
        for wedge in wedge_vals:
            b=basis(wedge,ratio,a,ap)
            prev=None
            for d in delta_vals:
                psi=float(-2*np.pi*fc*d*1e-9)
                obs,_=observe(H_two(freqs,a,b,20.,d,psi),p0)
                switch=prev is not None and prev!=obs["n0"];prev=obs["n0"]
                law.append({"mode":"PHYSICAL","delta_ns":float(d),"psi":psi,
                            "psi_index":None,"wedge":wedge,"amp_ratio_db":ratio,
                            "snr_db":None,"offset_ps":None,"seed":None,
                            "n0":obs["n0"],"n0_switch":bool(switch),
                            "n0_segment":None,"q_W":obs["q_W"],
                            "eps_rho":obs["eps_rho"],"phi_fp":obs["phi_fp"],
                            "S3_fp":obs["S3_fp"],
                            "near_cancel":bool(np.linalg.norm(a+b*np.exp(1j*psi))<.3*np.linalg.norm(a)),
                            "valid_flag":obs["status"]})
    slopes=pd.DataFrame(slope_records)
    fails=int((slopes.status=="FAIL").sum())
    passes=int((slopes.status=="PASS").sum())
    uneval=int((slopes.status=="NOT_EVALUABLE_SHORT_SEGMENT_OR_FLOOR").sum())
    if fails:
        assessment="H1_FAIL"
    elif uneval:
        assessment="H1_INCONCLUSIVE"
    elif passes:
        assessment="H1_PASS"
    else:
        assessment="H1_NOT_EVALUABLE"
    return pd.DataFrame(law),slopes,{
        "law_rows":len([x for x in law if x["mode"]=="LAW"]),
        "physical_rows":len([x for x in law if x["mode"]=="PHYSICAL"]),
        "parallel_jones_rows_checked":n_zero,
        "law_invalid_rows":n_invalid,
        "slope_n_pass":passes,"slope_n_fail":fails,
        "slope_n_not_evaluable":uneval,
        "slope_n_predefined_negative_control":int((slopes.status=="PARALLEL_JONES_NEGATIVE_CONTROL").sum()),
        "slope_n_near_cancel":int((slopes.status=="NEAR_CANCEL_PREDEFINED").sum()),
        "assessment":assessment,
        "window_switches_all_law":sum(bool(x["n0_switch"]) for x in law if x["mode"]=="LAW"),
        "slope_bounds":[slope_lo,slope_hi],
        "fit_delta_bounds_ns":[fit_lo,fit_hi],
        "physics_model_warning":
            "psi fixed in path coefficient; exp(-i2pi*f*delta) on absolute RF frequencies still rotates carrier phase."
    }


def fixture_tests(freqs, p0, params):
    a=np.array([1.+0j,.3j]);a=a/np.linalg.norm(a)
    parallel=0.3*a
    samples=[]
    for d in [0.,.05,.25,1.,4.]:
        h=H_two(freqs,a,parallel,20.,d,0.35)
        obs,_=observe(h,p0)
        assert obs["status"]=="VALID" and obs["q_W"]<=params["tolerances_fixed_before_run"]["s0_parallel_jones_eps_max"]
        samples.append({"delta_ns":d,"q_W":obs["q_W"]})
    single=H_two(freqs,a,np.zeros_like(a),20.,1.,0.)
    obs,_=observe(single,p0)
    assert obs["status"]=="VALID"
    assert obs["q_W"]<=1e-10 and abs(obs["phi_fp"])>.1 and abs(obs["S3_fp"])>.1
    # F3: eps_rho must be invariant to a constant diagonal complex gain.
    nonparallel=np.array([1.,-1.],complex)/math.sqrt(2)
    H=H_two(freqs,np.array([1.,1.])/math.sqrt(2), .3*nonparallel,20.,1.,.7)
    before,_=observe(H,p0)
    after,_=observe(H*np.array([1.7*np.exp(.5j), .27*np.exp(-1.3j)])[None,:],p0)
    assert before["status"]==after["status"]=="VALID"
    err=abs(before["eps_rho"]-after["eps_rho"])/max(abs(before["eps_rho"]),1e-15)
    assert err<=params["tolerances_fixed_before_run"]["gain_invariance_rel"]
    return {"status":"PASS","flat_single_path":{"q_W":obs["q_W"],
            "phi_fp":obs["phi_fp"],"S3_fp":obs["S3_fp"]},
            "parallel_jones_cases":samples,
            "diagonal_gain_eps_rho_relative_error":float(err),
            "gain_tol":params["tolerances_fixed_before_run"]["gain_invariance_rel"]}


def noise_sweep(freqs, p0, params):
    syn=params["s0_synthetic"]
    a=np.array([1.,1.],complex)/math.sqrt(2)
    H0=H_two(freqs,a,np.zeros_like(a),20.,0.,0.)
    obs,h0=observe(H0,p0)
    assert obs["status"]=="VALID"
    nf=len(freqs);nt=4*nf
    hann=.5-.5*np.cos(2*np.pi*np.arange(nf)/(nf-1))
    # E[sum_rx |n_rx[n0]|²] = 2*factor*variance per complex freq bin.
    noise_time_factor=(nf/nt)**2*float(np.sum(hann**2))
    signal_fp_power=float(np.sum(abs(h0[obs["n0"]])**2))
    seeds=range(200)
    records=[];rows=[];noiseless_offsets=[]
    for offset in syn["port_timing_offset_ps_grid"]:
        Hshift=H0.copy()
        Hshift[:,1]*=np.exp(-2j*np.pi*freqs*float(offset)*1e-12)
        clean,_=observe(Hshift,p0)
        noiseless_offsets.append({"offset_ps":offset,"q_W":clean["q_W"],
                                  "eps_rho":clean["eps_rho"],"n0":clean["n0"],
                                  "status":clean["status"]})
        for snr in syn["snr_db_grid"]:
            variance=signal_fp_power/(2*noise_time_factor*10.0**(float(snr)/10.0))
            sigma=math.sqrt(variance)
            values=[];invalid=0
            for seed in seeds:
                # PCG64 per-seed streams intentionally reused across nuisance arms.
                rng=np.random.Generator(np.random.PCG64(seed))
                noise=(rng.standard_normal(H0.shape)+1j*rng.standard_normal(H0.shape))*(sigma/math.sqrt(2))
                test,_=observe(Hshift+noise,p0)
                if test["status"]!="VALID":
                    invalid+=1
                else:
                    values.append(test["q_W"])
                rows.append({"snr_db":snr,"offset_ps":offset,"seed":seed,
                             "n0":test["n0"],"q_W":test["q_W"],
                             "eps_rho":test["eps_rho"],"status":test["status"]})
            records.append({"snr_db":snr,"offset_ps":offset,"n_seeds":len(seeds),
                            "n_valid":len(values),"n_invalid":invalid,
                            "q50":float(np.quantile(values,.5)) if values else None,
                            "q95":float(np.quantile(values,.95)) if values else None,
                            "qmin":float(min(values)) if values else None,
                            "qmax":float(max(values)) if values else None})
    return pd.DataFrame(records),pd.DataFrame(rows),pd.DataFrame(noiseless_offsets),{
        "noise_model":"frequency-bin complex circular AWGN, no filter process noise",
        "fp_snr_definition":"noise-free common-n0 two-port FP signal power / expected combined two-port noise FP power",
        "signal_fp_power":signal_fp_power,
        "complex_frequency_noise_variance_base":
            "sigma_H2 = signal_fp_power/(2*noise_time_factor*10**(snr_db/10))",
        "noise_time_factor":noise_time_factor,
        "seed_range":"0..199, numpy PCG64; common random numbers across arms",
        "offset_application":"H_minus(f)*exp(-i2pi*f*Delta), before noise",
        "offset_ps":syn["port_timing_offset_ps_grid"],
        "snr_db":syn["snr_db_grid"],
        "total_seed_rows":len(rows)
    }


def run(args):
    root=Path(args.repo_root).resolve()
    scope=root/PROJECT
    output=Path(args.out).resolve()
    if output.exists():
        raise FileExistsError("Append-only output already exists: "+str(output))
    output.mkdir(parents=True,exist_ok=False)
    status="NOT_STARTED"; problems=[];checks={};inputs={}
    def mark(check,status_value,details=None):
        checks[check]={"status":status_value,"details":details}
    try:
        hashes=verify_freeze(scope)
        mark("FROZEN_CONTRACT_SHA","PASS",hashes)
        params=json.loads((scope/"config/PLAN_PARAMETERS_v1.0.json").read_text())
        assert params["contract_id"]==CONTRACT_ID
        assert params["freeze_deltas"]["D5_execution"]["S0"].startswith("GO")
        p0,path=load_observer(scope)
        inputs["p0_observer_sha256"]=sha(path)
        freq,los,source_info=verify_inputs(root,scope)
        inputs.update(source_info)
        mark("FREQUENCY_AND_P0_LOS_LOCK","PASS",
             {"freq_sha":inputs["freq_sha256"],"p0_los_sha":inputs["p0_los_sha256"],
              "timeline_n":inputs["timeline_n"]})
        fixtures=fixture_tests(freq,p0,params)
        save_json(output/"S0_FIXTURES.json",fixtures)
        mark("S0_PHYSICS_FIXTURES",fixtures["status"],
             {"parallel_cases":len(fixtures["parallel_jones_cases"]),
              "eps_rho_gain_relative_error":fixtures["diagonal_gain_eps_rho_relative_error"]})
        s0law,slopes,assessment=law_sweep(freq,p0,params)
        s0law.to_csv(output/"S0_LAW.csv",index=False)
        slopes.to_csv(output/"S0_SLOPES.csv",index=False)
        mark("S0_LAW_COMPUTED","PASS",assessment)
        qref=q_ref(freq,p0,source_info,params)
        save_json(output/"S0_QREF.json",qref)
        mark("R03_FIXED_DECISION","COMPUTED",{
            "decision":qref["decision"],"q_ref":qref["q_ref"],
            "q95_timeline":qref["q95_timeline"]})
        summary,ledger,offsets,noise_meta=noise_sweep(freq,p0,params)
        summary.to_csv(output/"S0_NOISE_FLOOR.csv",index=False)
        ledger.to_csv(output/"S0_NOISE_SEEDS.csv.gz",index=False,
                      compression={"method":"gzip","compresslevel":6,"mtime":0})
        offsets.to_csv(output/"S0_OFFSET_NOISELESS.csv",index=False)
        mark("S0_NOISE_GRID","PASS",noise_meta)
        if len(s0law)!=27540 or len(ledger)!=4000 or len(summary)!=20:
            raise AssertionError(f"S0_GRID_COVERAGE: law={len(s0law)} seeds={len(ledger)} summary={len(summary)}")
        if assessment["law_invalid_rows"]:
            raise AssertionError("S0_LAW_HAS_INVALID_ROWS")
        if summary.n_invalid.sum():
            raise AssertionError("S0_NOISE_HAS_INVALID_ROWS")
        mark("S0_GRID_AND_SEED_COVERAGE","PASS",{
            "law_and_physical_rows":len(s0law),"seed_rows":len(ledger),
            "noise_groups":len(summary)})
        blocked = (qref["decision"]=="REDESIGN_REQUIRED"
                   or assessment["assessment"]!="H1_PASS")
        save_json(output/"S0_DECISIONS.json",{
            "role":"IMPLEMENTER","scientific_verdict":"NOT_ISSUED",
            "mechanical_h1_gate":assessment["assessment"],
            "mechanical_r03_gate":qref["decision"],
            "M1_M2_followup":"STOP" if blocked else "ELIGIBLE_ONLY_AFTER_P1_HOLD_RELEASE",
            "P1_P2_HOLD":True,
            "R10_independent_auditor":"OPEN",
            "claim_limit":"TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE",
            "label_analysis":"NOT_RUN",
            "no_protocol_threshold_changes":True})
        status="TECHNICAL_QA_ONLY_S0_COMPLETE"
    except Exception as exc:
        problems.append({"error":str(exc),"traceback":traceback.format_exc()})
        status="BLOCKED_CONTRACT_MISMATCH" if "BLOCKED_CONTRACT_MISMATCH" in str(exc) else "S0_TECHNICAL_FAIL"
        mark("UNHANDLED","FAIL",str(exc))
    finally:
        save_json(output/"S0_STATUS.json",{
            "role":"IMPLEMENTER","contract_id":CONTRACT_ID,
            "phase":PHASE,"status":status,"checks":checks,"errors":problems,
            "label":"TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE",
            "auditor":"SELF_REVIEW_ONLY; R-10 independent audit outstanding",
            "P1_P2":"HOLD","P3":"NOT_RUN","P4_RT":"BLOCKED",
            "scientific_release":"NOT_AUTHORIZED"})
        try:
            exec_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,
                                              text=True,stderr=subprocess.DEVNULL).strip()
        except Exception:
            exec_sha=None
        all_files={p.name:sha(p) for p in output.iterdir() if p.is_file()}
        manifest={"schema":"POL_XCORR_S0_V1_MANIFEST",
                  "phase":PHASE,"role":"IMPLEMENTER","contract_id":CONTRACT_ID,
                  "timestamp_utc":datetime.now(timezone.utc).isoformat(),
                  "base_git_sha":BASE_SHA,"governance_git_sha":GOV_SHA,
                  "freeze_reference_sha":FREEZE_SHA,
                  "execution_git_sha":exec_sha,
                  "frozen_document_sha256":FROZEN,
                  "input_lock_sha256":FROZEN["config/INPUT_LOCK_v2.json"],
                  "output_file_sha256":all_files,"inputs":inputs,
                  "code_sha256":sha(Path(__file__).resolve()),
                  "environment":{"python":platform.python_version(),
                                 "numpy":np.__version__,"pandas":pd.__version__,
                                 "platform":platform.platform()},
                  "command":sys.argv,"seed_ledger":"S0_NOISE_SEEDS.csv.gz (PCG64 seed 0..199) if produced",
                  "train_test_manifest":"NOT_APPLICABLE; no labels, no training",
                  "solver_config":"NOT_APPLICABLE (synthetic spectral channel)",
                  "source_invariants":"No Full H, labels or historical label-containing feature references loaded",
                  "status":status,"failure_receipts":problems,
                  "auditor":"SELF_REVIEW_ONLY_FREEZE; independent R-10 OPEN",
                  "scientific_verdict":"NOT_ISSUED"}
        save_json(output/"MANIFEST.json",manifest)
        (output/"IMPLEMENTER_REPORT_S0.md").write_text(
            "# POL-XCORR-001 S0 implementer execution receipt\n\n"
            + f"- Status: **{status}**; TECHNICAL_QA_ONLY / SELF_REVIEW_ONLY_FREEZE.\n"
            + f"- Execution SHA: {exec_sha}\n"
            + f"- Contract SHA256: {FROZEN['contracts/EXPERIMENT_CONTRACT_POL-XCORR-001_v1.0.md']}\n"
            + f"- Governance SHA: {GOV_SHA}\n"
            + f"- Frozen inputs: synthetic H(257 bins) + hash-checked historical LoS FLOOR (7,251 TIMELINE); no Full H or labels.\n"
            + f"- Mechanical checks: {json.dumps({k:v['status'] for k,v in checks.items()},ensure_ascii=False)}\n"
            + f"- Errors: {json.dumps(problems,ensure_ascii=False)}\n"
            + "- All old raw H, P0/P0V3, proposer/auditor records, frozen contract/config left unchanged.\n"
            + "- No independent scientific verdict; R-10 missing; P1/P2 remain HOLD. S0 stops after reporting.\n",
            encoding="utf-8"
        )
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root",required=True)
    p.add_argument("--out",required=True,
                   help="New results_s0/run_<GITHUB_RUN_ID> directory; must not exist")
    args=p.parse_args()
    result=run(args)
    print(json.dumps({"status":result,"output":str(args.out)}))
    return 0 if result=="TECHNICAL_QA_ONLY_S0_COMPLETE" else 2


if __name__=="__main__":
    raise SystemExit(main())
