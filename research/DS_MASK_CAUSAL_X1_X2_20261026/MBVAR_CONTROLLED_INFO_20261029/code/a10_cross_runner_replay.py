"""A010 draft-only, archived DEV2 K1/K2 two-runner solver replay.

The replay is deliberately NOT a scientific run: it never opens DEV3,
HOLDOUT2/reserve, or RT. Both runners consume exactly the original 2026-11-01
A010-P0 GEN canonical ZIP. Implementer-level mechanical reproducibility is
not an independent scientific/auditor sign-off.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

import a10_canonical as CAN
import a10_validation as AV

EXP = Path(__file__).resolve().parent.parent
GEN = EXP / "results/P2_A010P0_GEN_run_41269011836"
FORENSIC_CASES = ("K1", "K2")
GOVERNANCE_SHA = "250d617ad89a4105fa1af546cc83ceed9de98f42"
CONTRACT_SHA = "68d73bd22bf467625559f3092433f250cbe91cb2fef011f92151975975b00f34"
RUN_REQUEST_SHA = "9e6b8bd72f9e935315eecdfd0c38c42f18db58f535c1596dbbfe391db383b77b"
EXPECTED_SOURCE_INPUT_SHA = CAN.CANON_SHA
STATE_SCALES_DREF = (.02, .02, np.deg2rad(.25), np.deg2rad(.01))
NUMERIC_LIMITS = dict(state_dref=1e-6, cost_chi2=1e-6,
                      C10_natural_rel=1e-3, C10_cond_log10=1e-3,
                      NEES4_rel=1e-3)


def stop(msg):
    raise SystemExit(msg)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_json(path, obj):
    Path(path).write_text(json.dumps(obj, sort_keys=True, indent=2,
                                     allow_nan=False, default=str) + "\n")


def guard_archive():
    """The archive is a pre-existing DEV2 forensic receipt, NOT a fresh draw."""
    import contract_lock as CL
    import manifest as MF
    run_request = EXP / "RUN_REQUEST.json"
    if file_sha(run_request) != RUN_REQUEST_SHA:
        stop("ERR_A010_FORENSIC_RUN_REQUEST_CHANGED")
    request = json.loads(run_request.read_text())
    if (request.get("phase") != "P2_A010P0_ABL" or
            request.get("contract_id") != "MBVAR-INFO-001" or
            request.get("governance_git_sha") != GOVERNANCE_SHA or
            request.get("amendments", [])[-1:] != ["AMENDMENT-010-P0"]):
        stop("ERR_A010_FORENSIC_REQUEST_SCOPE")
    if CL.amendment_lock("AMENDMENT-010") is not None:
        stop("ERR_A010_SCIENCE_AMENDMENT_IS_NOT_DRAFT")
    if MF.sha256_file(MF.CONTRACT) != CONTRACT_SHA:
        stop("ERR_A010_FROZEN_CONTRACT_CHANGED")
    manfile = GEN / "MANIFEST.json"
    src = json.loads(manfile.read_text())
    if (src.get("contract_sha256") != CONTRACT_SHA or
            src.get("governance_git_sha") != GOVERNANCE_SHA or
            src.get("amendment") != "AMENDMENT-010-P0" or
            src.get("sub_phase") != "P2_A010P0_GEN" or
            src.get("execution_status") != "PASS"):
        stop("ERR_A010_GEN_PROVENANCE")
    for name in ("A010_CANONICAL_INPUTS.zip", "A010_INPUT_CANONICAL_SHA.csv",
                 "A010_LHALF_WORLDPOSE_V2.npy", "A010_GENERATOR_FACTOR_LOCK.json"):
        if file_sha(GEN / name) != src["output_sha256"].get(name):
            stop("ERR_A010_GEN_OUTPUT_HASH " + name)
    if file_sha(GEN / "A010_CANONICAL_INPUTS.zip") != EXPECTED_SOURCE_INPUT_SHA:
        stop("ERR_A010_CANONICAL_ZIP_CHANGED")
    canonical = CAN.read_forensic_bundle(GEN / "A010_CANONICAL_INPUTS.zip")
    ledger = CAN.audit_array_ledger(canonical, GEN / "A010_INPUT_CANONICAL_SHA.csv")
    if not ledger["pass"] or ledger["checked"] != 48:
        stop("ERR_A010_CANONICAL_LEDGER")
    CAN.load_frozen_factor(GEN / "A010_LHALF_WORLDPOSE_V2.npy")
    return src, canonical, dict(
        source_manifest_sha256=file_sha(manfile),
        frozen_input_zip_sha256=file_sha(GEN / "A010_CANONICAL_INPUTS.zip"),
        array_ledger_sha256=file_sha(GEN / "A010_INPUT_CANONICAL_SHA.csv"),
        frozen_factor_sha256=file_sha(GEN / "A010_LHALF_WORLDPOSE_V2.npy"),
        contract_sha256=CONTRACT_SHA,
        run_request_sha256=RUN_REQUEST_SHA,
        array_ledger_checked=ledger["checked"])


def environment():
    cpu_model = ""
    try:
        info = subprocess.check_output(["lscpu"], text=True)
        cpu_model = next((l.split(":", 1)[1].strip() for l in info.splitlines()
                          if l.startswith("Model name:")), "")
    except Exception:
        pass
    try:
        b = np.show_config(mode="dicts").get("Build Dependencies", {}).get("blas", {})
        blas = {k: b.get(k) for k in ("name", "version", "openblas configuration")}
    except Exception:
        blas = {}
    return dict(cpu_model=cpu_model, system=platform.platform(),
                machine=platform.machine(), python=sys.version.split()[0],
                numpy=np.__version__, blas=blas,
                threads={k: os.environ.get(k) for k in
                         ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
                runner_name=os.environ.get("RUNNER_NAME"),
                runner_os=os.environ.get("RUNNER_OS"),
                github_run_id=os.environ.get("GITHUB_RUN_ID"),
                github_job=os.environ.get("GITHUB_JOB"),
                github_run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"))


def boot_id():
    f = Path("/proc/sys/kernel/random/boot_id")
    return f.read_text().strip() if f.exists() else ""


def _all_close_exact_source(actual, source, label):
    a, b = np.asarray(actual), np.asarray(source)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        stop("ERR_A010_GEOMETRY_SCHEMA " + label)
    scale = max(float(np.max(np.abs(b))), 1.0)
    if float(np.max(np.abs(a-b))) > 1e-10 * scale:
        stop("ERR_A010_GEOMETRY_REGEN_MISMATCH " + label)


def run_case(cid, source, setup):
    """The only estimator input object has no truth, true covariance or labels."""
    import a10_p0 as P0
    import c3v5 as C3
    import filters as FL
    import info_core as IC
    import s1v5 as T
    import s1_mc as M
    import world as Wd

    if cid not in FORENSIC_CASES:
        stop("ERR_A010_OUTSIDE_ARCHIVED_DEV2_CASE_SCOPE")
    f, role, cell, seed, arm = P0.CASES[cid]
    if (f, role, cell, seed, arm) != {
            "K1": (10, "LOW", "TIME_1", 2, "ORACLE_CORR_BATCH"),
            "K2": (11, "REV60", "TIME_HIGH_5", 0, "ORACLE_CORR_BATCH")}[cid]:
        stop("ERR_A010_FORENSIC_CASE_MAP_CHANGED")
    est = CAN.estimator_only(source, cid)
    est_shas = {name: CAN.sha_array(arr) for name, arr in est.items()}
    w0 = setup["wins"][role]
    truth = {x: source[f"{cid}|{x}"] for x in CAN.TRUTH_ONLY}
    _all_close_exact_source(w0["poses"], truth["poses"], "poses/" + cid)
    _all_close_exact_source(w0["Xtrue"], truth["Xtrue"], "Xtrue/" + cid)
    _all_close_exact_source(w0["ds"], truth["ds_true"], "ds/" + cid)
    _all_close_exact_source(w0["dth"], truth["dth_true"], "dth/" + cid)
    _all_close_exact_source(w0["dts"], est["dts"], "dt/" + cid)
    if not np.array_equal(w0["taps"], est["taps"]):
        stop("ERR_A010_CANONICAL_TAP_MISMATCH " + cid)
    w = dict(w0, Xtrue=truth["Xtrue"].copy(), poses=truth["poses"].copy(),
             taps=est["taps"].copy(), dts=est["dts"].copy())
    inp = {n:est[n].copy() for n in ("z", "x0", "ds_m", "gy_m")}
    inp["vn"] = np.c_[est["ds_m"] - truth["ds_true"],
                      est["gy_m"] - truth["dth_true"]]
    Sm = est["Sigma_model"].copy()
    key = (f, role, cell, seed, arm)
    raw, Xprime, solver_info, thp = T.eval_batch(w, arm, Sm, inp, key)
    if any(CAN.sha_array(est[k]) != val for k, val in est_shas.items()):
        stop("ERR_A010_MUTATED_FROZEN_INPUT " + cid)
    # As in C3V5: every truth-free start receives the same F2 polishing.
    z, x0, ds_m, gy_m, dts = (est[n] for n in ("z", "x0", "ds_m", "gy_m", "dts"))
    hb = lambda X, taps=est["taps"]: Wd.h_H_tap(X, "A", taps)
    mu = np.zeros_like(z)
    sd = np.sqrt(np.diag(M.P0))
    starts = {f"psi{k:+d}": (np.r_[x0[:2], FL.wrap(x0[2]+k*sd[2]), x0[3]],
                           np.zeros_like(z)) for k in FL.MS_K}
    starts["x+1"] = (x0+np.r_[sd[0], 0, 0, 0], np.zeros_like(z))
    starts["y+1"] = (x0+np.r_[0, sd[1], 0, 0], np.zeros_like(z))
    sol = {"E": (float(raw["cost"]), Xprime)}
    for name, start in starts.items():
        _, _, obj = FL.batch_map_v2(hb, z, mu, Sm, ds_m, gy_m, dts,
                                    x0, M.P0, theta0=start)
        theta, _, _ = T.polish(hb, z, Sm, ds_m, gy_m, dts, x0, obj["theta"],
                               T.key_seed("DIAG_POLISH", f, role, cell, seed, arm, name))
        Lm, L0, qv = T.B3._mats(Sm, ds_m, dts)
        cost, states = FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m,
                                     gy_m, dts, theta[0], theta[1], jac=False)
        sol[name] = (float(cost), states)
    mode = C3.mode_ambiguity(sol)
    if len(sol) != 10:
        stop("ERR_A010_MODE_START_GRID_MISMATCH")
    # The scorer alone accesses Xtrue. The canonical full Sigma_true is never
    # passed to the non-oracle solver, including the ORACLE_CORR_BATCH arm
    # (whose Sigma_model is a stored synthetic oracle reference).
    C10 = AV.c10_diagnostics(raw)
    if not C10["pass_"]:
        stop("ERR_A010_FORENSIC_NONSPD_C10 " + cid)
    Pe = AV.c10_matrix(raw)
    e = truth["Xtrue"][-1] - Xprime[-1]
    e[2] = float(FL.wrap(e[2]))
    rot = IC.rotation_rt(truth["Xtrue"][-1], Wd.ANCHORS["A"])
    er = rot @ e
    nees_independent = float(er @ np.linalg.solve(Pe, er))
    if abs(nees_independent - float(raw["nees4_C10"])) > 1e-8 * max(1.0, abs(nees_independent)):
        stop("ERR_A010_REDERIVED_NEES4 " + cid)
    result = dict(case=cid, field=f, role=role, cell=cell, sensor_seed=seed, arm=arm,
                  cost=float(raw["cost"]), cost_E=float(raw["cost_E"]),
                  class_v31=str(raw["class_v31"]), ms_best_k=int(raw["ms_best_k"]),
                  n_alt_ambiguous=int(mode["n_alt_ambiguous"]),
                  alt_ambiguous_starts=str(mode["alt_ambiguous_starts"]),
                  max_alt_dref_within_1chi2=float(mode["max_alt_dref_within_1chi2"]),
                  nees4_C10=float(raw["nees4_C10"]),
                  nees4_independent=nees_independent,
                  solver_status=str(solver_info["status"]),
                  **{f"xend_{j}":float(raw[f"xend_{j}"]) for j in range(4)},
                  **{f"C10rot_{i}{j}":float(raw[f"C10rot_{i}{j}"])
                     for i in range(4) for j in range(i,4)})
    return result, dict(case=cid, original_estimator_input_sha256=est_shas,
                        truth_only_sha256={k:CAN.sha_array(v) for k,v in truth.items()},
                        estimator_input_bytes_unchanged=True, full_C10_spd=True)


def replay(output, replica):
    if (replica not in ("a", "b") or
            os.environ.get("GITHUB_ACTIONS") != "true" or
            os.environ.get("MBVAR_A010_DEV2_PREFLIGHT") != "1"):
        stop("ERR_A010_REPLAY_SCOPE_REQUIRES_ISOLATED_ACTIONS")
    sha = os.environ.get("GITHUB_SHA", "")
    if len(sha) != 40:
        stop("ERR_A010_REPLAY_MISSING_SOURCE_COMMIT")
    unique_vm = boot_id()
    if not unique_vm:
        stop("ERR_A010_RUNNER_BOOT_ID_UNAVAILABLE")
    import a10_p0 as P0
    import s0v2 as S0
    import s1v2 as V
    import manifest as MF
    source_manifest, canon, hashes = guard_archive()
    lock = P0.lock_p0()
    S = V.setup(lock)
    rows, input_evidence = [], []
    start = time.monotonic()
    for cid in FORENSIC_CASES:
        row, evidence = run_case(cid, canon, S)
        rows.append(row)
        input_evidence.append(evidence)
        print("A010_TWO_RUNNER_CASE", cid, row["cost"], row["class_v31"],
              row["n_alt_ambiguous"], flush=True)
    record = dict(schema="A010_DEV2_2RUNNER_REPLAY_V1",
                  contract_id="MBVAR-INFO-001", role="IMPLEMENTER",
                  science_status="SCIENCE_DRAFT", science_release_allowed=False,
                  allowed_cases=list(FORENSIC_CASES),
                  source_git_sha=sha,
                  governance_git_sha=GOVERNANCE_SHA,
                  contract_sha256=CONTRACT_SHA,
                  run_request_sha256=RUN_REQUEST_SHA,
                  input_sha256=hashes["frozen_input_zip_sha256"],
                  manifest_sha256=hashes["source_manifest_sha256"],
                  archive=hashes,
                  source_code_sha256=MF.code_hashes(),
                  runner_id="|".join((os.environ.get("RUNNER_NAME", ""),
                                       os.environ.get("GITHUB_JOB", ""),
                                       replica, unique_vm)),
                  runner_boot_id=unique_vm, runner_replica=replica,
                  environment=environment(), elapsed_seconds=round(time.monotonic()-start, 1),
                  input_evidence=input_evidence, rows=rows,
                  integrity=True, scientific_verdict="NOT_EVALUATED",
                  independent_auditor_signed=False, dev3="NO-GO",
                  holdout2="NO-GO", rt="NO-GO")
    output = Path(output);output.mkdir(parents=True,exist_ok=True)
    safe_json(output/"REPLAY_RECEIPT.json",record)
    print("A010_REPLAY_WRITTEN",replica,sha,"K1,K2",flush=True)
    return 0


def compare(a_path, b_path, output):
    a_path, b_path, output = Path(a_path), Path(b_path), Path(output)
    a=json.loads(a_path.read_text());b=json.loads(b_path.read_text())
    required=("schema","allowed_cases","archive","source_code_sha256",
              "contract_id","contract_sha256","governance_git_sha",
              "run_request_sha256","runner_boot_id","input_evidence",
              "science_status","science_release_allowed","rows",
              "runner_id","source_git_sha","input_sha256","manifest_sha256")
    if any(k not in d for d in (a,b) for k in required):
        stop("ERR_A010_CROSS_RUNNER_RECEIPT_MISSING_METADATA")
    if any(a[k]!=b[k] for k in
           ("schema","allowed_cases","archive","source_code_sha256",
            "contract_id","contract_sha256","governance_git_sha",
            "run_request_sha256","input_evidence","science_status",
            "source_git_sha","input_sha256","manifest_sha256")):
        stop("ERR_A010_CROSS_RUNNER_SOURCE_OR_INPUT_MISMATCH")
    if a["allowed_cases"]!=list(FORENSIC_CASES) or a["input_sha256"]!=EXPECTED_SOURCE_INPUT_SHA:
        stop("ERR_A010_CROSS_RUNNER_CASE_SCOPE")
    if a["runner_replica"]!="a" or b["runner_replica"]!="b":
        stop("ERR_A010_CROSS_RUNNER_REPLICA_ORDER")
    if not a["runner_boot_id"] or a["runner_boot_id"]==b["runner_boot_id"]:
        stop("ERR_A010_TWO_DISTINCT_RUNNER_VM_NOT_PROVED")
    if any(d.get("science_release_allowed") is not False or
           d.get("independent_auditor_signed") is not False for d in (a,b)):
        stop("ERR_A010_CROSS_RUNNER_SCIENCE_AUTHORITY")
    # Mechanical component: existing strict comparator from the implementation.
    numerical=AV.validate_two_runner_solver_receipts(
        a,b,state_tol=NUMERIC_LIMITS["state_dref"],
        cost_tol=NUMERIC_LIMITS["cost_chi2"],
        cov_tol=NUMERIC_LIMITS["C10_natural_rel"],
        cond_log_tol=NUMERIC_LIMITS["C10_cond_log10"])
    # Additional independent case-level fields that comparator does not handle.
    x={r["case"]:r for r in a["rows"]};y={r["case"]:r for r in b["rows"]}
    if sorted(x)!=list(FORENSIC_CASES) or sorted(y)!=list(FORENSIC_CASES):
        stop("ERR_A010_CROSS_RUNNER_CASE_SET")
    detail=[]
    for cid in FORENSIC_CASES:
        u,v=x[cid],y[cid]
        same=(u["ms_best_k"]==v["ms_best_k"] and
              u["solver_status"]==v["solver_status"] and
              u["alt_ambiguous_starts"]==v["alt_ambiguous_starts"] and
              abs(u["cost_E"]-v["cost_E"])<=NUMERIC_LIMITS["cost_chi2"] and
              abs(u["nees4_independent"]-v["nees4_independent"])<=
                  NUMERIC_LIMITS["NEES4_rel"]*max(abs(u["nees4_independent"]),1e-300))
        if not same:
            stop("ERR_A010_CROSS_RUNNER_BESTSTART_MODE_OR_SCORING "+cid)
        detail.append(dict(case=cid, same_class=True,
                           same_best_start=True, same_mode_starts=True,
                           nees4_independently_derived=True))
    if not numerical["pass_"]:
        stop("ERR_A010_CROSS_RUNNER_NUMERIC "+json.dumps(numerical))
    report=dict(schema="A010_DEV2_2RUNNER_COMPARE_V1",status="TECHNICAL_REPLAY_PASS",
                scientific_verdict="NOT_EVALUATED",independent_auditor_signed=False,
                science_freeze_allowed=False,dev3="NO-GO",holdout2="NO-GO",rt="NO-GO",
                source_git_sha=a["source_git_sha"],input_sha256=a["input_sha256"],
                archive_source_manifest_sha256=a["manifest_sha256"],
                comparable_environment=a["environment"]==b["environment"],
                distinct_linux_boot_ids=True,runner_ids=numerical["runner_ids"],
                numerical=numerical,extra_checks=detail,
                source_receipts_sha256={
                    "a":file_sha(a_path),"b":file_sha(b_path)},
                limitations=[
                    "archived DEV2 forensic keys K1/K2 only, not full S1V5/C3V5",
                    "two GitHub hosted isolated jobs; not proof of different CPU models",
                    "same implementation and math helper reused, not an independent auditor",
                    "near-minimum mode diagnostic is not unique MAP proof",
                    "no DEV3, no HOLDOUT2 or physical RT"
                ])
    output.mkdir(parents=True,exist_ok=True)
    safe_json(output/"TWO_RUNNER_COMPARISON.json",report)
    print("A010_TWO_RUNNER_TECHNICAL_REPLAY_PASS",numerical["n_rows"],
          a["source_git_sha"],flush=True)
    return 0


def main(argv=None):
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("replay")
    r.add_argument("--out",required=True)
    r.add_argument("--replica",choices=["a","b"],required=True)
    c=sub.add_parser("compare")
    c.add_argument("--a",required=True);c.add_argument("--b",required=True)
    c.add_argument("--out",required=True)
    args=p.parse_args(argv)
    if args.cmd=="replay":
        return replay(args.out,args.replica)
    return compare(args.a,args.b,args.out)


if __name__=="__main__":
    raise SystemExit(main())
