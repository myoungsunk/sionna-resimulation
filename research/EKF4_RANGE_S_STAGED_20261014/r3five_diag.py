"""Reproduce and diagnose exactly five ORIGINAL R3 P2 invalid model updates.

Consumes *only* authenticated immutable artifact 11892566974 from run
38562146793. Calls the original map_update without modification and traces
its actual accepted/rejected trials; independently evaluates the identical
fixed-prior mathematical cost and gradient in mpmath 80-digit arithmetic.

Research diagnostics only, not a replacement estimator or P2 rerun.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import traceback
import zipfile

import mpmath as mp
import numpy as np
import core
import solver_r3
from core import SyntheticRF

HERE = Path(__file__).resolve().parent
SOURCE_RUN_ID = 38562146793
SOURCE_COMMIT = "2547f147ea347563a186a886bd25a543871825f3"
ZIP_SHA = "931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4"
TOL = 1e-8
mp.mp.dps = 80


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def mfloat(x):
    f = float(x)
    a, b = f.as_integer_ratio()
    return mp.mpf(a) / mp.mpf(b)


def mmatrix(a):
    arr = np.asarray(a)
    if arr.ndim == 1:
        return mp.matrix([mfloat(x) for x in arr])
    return mp.matrix([[mfloat(x) for x in row] for row in arr])


def fnum(v):
    try:
        return float(v)
    except (OverflowError, ValueError):
        return None


def model_mp(x):
    dx = x[0] + 2
    dy = x[1] - 3
    rho = mp.sqrt(dx*dx + dy*dy + mfloat(1.3)**2)
    q = dx*dx + dy*dy
    sq = mp.sqrt(q)
    r = rho
    s = mfloat(0.8)*mp.sin(x[2]) + mfloat(0.15)*dy/sq
    H = mp.matrix(2, len(x))
    H[0, 0], H[0, 1] = dx/rho, dy/rho
    H[1, 0] = -mfloat(0.15)*dx*dy/(q*sq)
    H[1, 1] = mfloat(0.15)*dx*dx/(q*sq)
    H[1, 2] = mfloat(0.8)*mp.cos(x[2])
    return mp.matrix([r,s]), H


class MPObjective:
    """Fixed-prior whitened objective with independent mp implementation."""
    def __init__(self, mu, P, z, R):
        self.mu = mmatrix(mu)
        self.Lp = mmatrix(np.linalg.cholesky(P))
        self.Lr = mmatrix(np.linalg.cholesky(R))
        self.z = mmatrix(z)
        self.n = len(mu)

    def eval(self, y, gradient=True):
        x = self.mu + self.Lp*y
        if abs(x[2]-self.mu[2]) >= mp.pi:
            raise ValueError("outside local yaw chart")
        h, H = model_mp(x)
        v = mp.lu_solve(self.Lr, self.z-h)
        # mpmath lu_solve expects a vector RHS; here H*Lp is 2-by-n.
        # A high-precision matrix inverse (2x2) handles the multi-RHS case.
        B = (self.Lr ** -1) * (H*self.Lp)
        cost = mp.fsum([*(y[i]*y[i] for i in range(self.n)),
                        *(v[i]*v[i] for i in range(len(v)))])/2
        if not gradient:
            return cost
        g = y - B.T*v
        return cost, g

    def hessian(self, y):
        # Differentiate the independently implemented *true* gradient,
        # not the original double Gauss-Newton matrix.
        n = self.n
        H = mp.matrix(n,n)
        for j in range(n):
            for i in range(n):
                def component(t):
                    v = mp.matrix(y)
                    v[j] = t
                    return self.eval(v)[1][i]
                H[i,j] = mp.diff(component, y[j])
        return (H+H.T)/2


def fmt_mp(x):
    return mp.nstr(x, 24)


def load_member(zf, suffix, starts=None):
    matches = [x for x in zf.namelist() if x.endswith(suffix)
               and (starts is None or x.startswith(starts))]
    if len(matches) != 1:
        raise RuntimeError("ZIP_MEMBER_MISMATCH " + suffix + " " + str(matches[:8]))
    return matches[0], zf.read(matches[0])


def extract_failure(zf, base, item):
    trial = int(item["trial"])
    cell_dir = (f"{base}trials/{item['path']}/{item['true_bias_dps']}/"
                f"{trial:03d}/{item['model']}/")
    pjson, raw_json = load_member(zf, cell_dir+"FAILURE.json")
    pnpz, raw_npz = load_member(zf, cell_dir+"FAILED_STEP.npz")
    payload = json.loads(raw_json)
    with np.load(io.BytesIO(raw_npz), allow_pickle=False) as ar:
        snapshot = {key: np.array(ar[key]) for key in ar.files}
    return {"record": item, "original": payload, "npz": snapshot,
            "source_json": pjson, "source_npz": pnpz,
            "source_hashes": {"FAILURE.json":sha_bytes(raw_json),
                              "FAILED_STEP.npz":sha_bytes(raw_npz)}}


def capture_replay(mu,P,z,R):
    """Monkeypatch ONLY for instrumentation; original algorithm is called."""
    events = []
    exact_calls = []
    orig_int = core.integrated_descent
    orig_newton = core.exact_newton_direction

    def wrapped_int(evaluate, y, d, c0, g0, c1, g1, info):
        result = orig_int(evaluate,y,d,c0,g0,c1,g1,info)
        events.append({"y": y.copy(), "d": d.copy(), "c0":float(c0),
                       "c1":float(c1), "g0":g0.copy(), "g1":g1.copy(),
                       "info":info.copy(), "integrated_accept":result is not None,
                       "evaluate":evaluate})
        return result

    def wrapped_newton(evaluate,y,g):
        direction = orig_newton(evaluate,y,g)
        exact_calls.append({"y":y.copy(),"direction":None if direction is None
                            else direction.copy()})
        return direction

    core.integrated_descent = wrapped_int
    core.exact_newton_direction = wrapped_newton
    try:
        result = core.map_update(mu,P,z,SyntheticRF(),R,
                                 range_first=True,max_iter=80,gradient_tol=TOL)
    finally:
        core.integrated_descent = orig_int
        core.exact_newton_direction = orig_newton
    return result,events,exact_calls


def high_precision_analysis(events, calls, result, mu, P, z, R):
    obj=MPObjective(mu,P,z,R)
    Lp=np.linalg.cholesky(P)
    # The instrumented y is the actual production solver coordinate,
    # unlike a re-solved rounded prior_delta.
    if events:
        last_y=events[-1]["y"]
        final_events=[x for x in events if np.array_equal(x["y"],last_y)]
        evaluate=events[-1]["evaluate"]
    else:
        last_y=np.linalg.solve(Lp,result.prior_delta)
        final_events=[]
        evaluate=None
    y=mmatrix(last_y)
    c_mp,g_mp=obj.eval(y)
    grad_mp_inf=max(abs(q) for q in g_mp)
    hessian=obj.hessian(y)
    hnp=np.array(hessian.tolist(),dtype=float)
    eig=np.linalg.eigvalsh(hnp)
    grad_float=math.nan
    if evaluate:
        _,gg,ii=evaluate(last_y)
        grad_float=float(np.max(np.abs(gg)))
        gn_dir=np.linalg.solve(ii,-gg)
    else:
        gn_dir=None
    true_direction=None
    if min(eig)>0 and np.linalg.cond(hnp)<1e12:
        true_direction=np.array([fnum(q) for q in mp.lu_solve(hessian,-g_mp)],
                                dtype=float)
    actual_exact=[a["direction"] for a in calls if np.array_equal(a["y"],last_y)]
    fallback_direction=actual_exact[-1] if actual_exact else None
    trial_rows=[]
    candidates=[]
    for name,direction in (("GAUSS_NEWTON",gn_dir),
                           ("R3_EXACT_NEWTON",fallback_direction),
                           ("MP_EXACT_NEWTON",true_direction)):
        if direction is None:
            continue
        slope=float(np.dot(np.asarray([fnum(v) for v in g_mp]),direction))
        for j in range(25):
            t=2.0**(-j)
            d=direction*t
            ymp=y+mmatrix(d)
            try:
                mp_delta=obj.eval(ymp,gradient=False)-c_mp
                grad_mp_new=obj.eval(ymp)[1]
                gd_new=max(abs(q) for q in grad_mp_new)
            except ValueError:
                mp_delta=mp.nan
                gd_new=mp.nan
            if evaluate is not None:
                cf,gf,_=evaluate(last_y+d)
                c0f,g0f,_=evaluate(last_y)
                float_diff=fnum(cf-c0f)
                float_direct=solver_r3.resolved_armijo(c0f,cf,t*float(np.dot(g0f,direction))) if np.isfinite(cf) else False
                float_grad_new=fnum(np.max(np.abs(gf))) if gf is not None else None
            else:
                float_diff=None;float_direct=False;float_grad_new=None
            record={"direction":name,"j":j,"step_fraction":t,
                    "step_norm_inf":fnum(np.linalg.norm(d,np.inf)),
                    "directional_mp_slope":slope,
                    "mp_delta_J":fmt_mp(mp_delta),"mp_delta_J_float":fnum(mp_delta),
                    "mp_gradient_new_inf":fmt_mp(gd_new),
                    "float64_delta_J":float_diff,
                    "float64_new_gradient_inf":float_grad_new,
                    "R3_direct_accept":bool(float_direct)}
            trial_rows.append(record)
            if mp.isfinite(mp_delta) and mp_delta < 0:
                candidates.append(record)
    # Root search is analysis only: no modified result is deployed.
    ym=mp.matrix(y)
    iteration_rows=[]
    solved=False
    if min(eig)>0 and np.linalg.cond(hnp)<1e12:
        for i in range(8):
            cc, gg=obj.eval(ym)
            norm=max(abs(x) for x in gg)
            iteration_rows.append({"iteration":i,"mp_gradient_inf":fmt_mp(norm),
                                   "mp_cost_difference_from_failed":fmt_mp(cc-c_mp)})
            if norm<mp.mpf("1e-35"):
                solved=True
                break
            hh=obj.hessian(ym)
            try:
                step=mp.lu_solve(hh,-gg)
            except (ValueError,ZeroDivisionError):
                break
            if max(abs(x) for x in step)>mp.mpf("0.1"):
                break
            ym+=step
    root_cost,root_grad=obj.eval(ym)
    root_mpinfty=max(abs(v) for v in root_grad)
    root_float = None
    if evaluate is not None:
        yy=np.asarray([fnum(a) for a in ym])
        root_c,root_g,_=evaluate(yy)
        if root_g is not None:
            root_float=float(np.max(np.abs(root_g)))
    last_step_rejections=[{"d_norm_inf":fnum(np.linalg.norm(row["d"],np.inf)),
                           "direct_delta":row["c1"]-row["c0"],
                           "integrated_accept":row["integrated_accept"],
                           "float_gradient_new_inf":float(np.max(np.abs(row["g1"])))}
                          for row in final_events]
    root_near=np.linalg.norm(np.asarray([fnum(a-b) for a,b in zip(ym,y)]),np.inf)
    descended=any(r["direction"] in ("GAUSS_NEWTON","R3_EXACT_NEWTON")
                  for r in candidates)
    mp_mismatch=(grad_mp_inf<=mfloat(TOL) and result.gradient_inf>TOL)
    if mp_mismatch:
        classification="FLOAT64_GRADIENT_FALSE_NONSTATIONARITY"
    elif descended and result.status!="CONVERGED":
        classification="REJECTED_VERIFIABLE_MP_DESCENT"
    elif solved and root_near<1e-4 and root_mpinfty<mfloat(TOL):
        classification="NEARBY_STATIONARY_ROOT_WITHOUT_VERIFIED_ACCEPTANCE"
    else:
        classification="UNRESOLVED_NOT_PROVEN_TRUE_STALL"
    analysis={
        "status":result.status,
        "classification":classification,
        "production_gradient_inf":result.gradient_inf,
        "actual_double_gradient_inf_at_final_iterate":grad_float,
        "independent_mp_gradient_inf":fmt_mp(grad_mp_inf),
        "mp_float_gradient_inf_gap":fnum(abs(grad_mp_inf-mfloat(grad_float))) if math.isfinite(grad_float) else None,
        "mp_cost":fmt_mp(c_mp),
        "exact_Hessian_eigenvalues_float":eig.tolist(),
        "exact_Hessian_condition_number":fnum(np.linalg.cond(hnp)),
        "GN_direction_available":gn_dir is not None,
        "R3_exact_fallback_called":bool(actual_exact),
        "R3_exact_direction_available":fallback_direction is not None,
        "mp_exact_direction_available":true_direction is not None,
        "last_iteration_integral_rejections":len(final_events),
        "total_integrated_candidates_all_iterations":len(events),
        "integrated_accepts_all_iterations":sum(e["integrated_accept"] for e in events),
        "last_rejection_examples":last_step_rejections[-6:],
        "mp_negative_descent_candidate_count":len(candidates),
        "mp_negative_descent_by_direction":{direction:sum(r["direction"]==direction for r in candidates)
                                  for direction in ("GAUSS_NEWTON","R3_EXACT_NEWTON","MP_EXACT_NEWTON")},
        "mp_stationary_root_solved":solved,
        "mp_root_gradient_inf":fmt_mp(root_mpinfty),
        "mp_root_cost_change":fmt_mp(root_cost-c_mp),
        "mp_root_distance_y_inf":root_near,
        "float_gradient_at_mp_root":root_float,
        "mp_root_trace":iteration_rows,
    }
    return analysis,trial_rows


def diagnose(item, zf,base):
    inp=extract_failure(zf,base,item)
    s=inp["npz"]
    original=inp["original"]
    mu,P,z,R=(s["prior_x"],s["prior_P"],s["z"],s["R"])
    assert int(original["step"])>=0
    assert original["solver_status"] in ("NUMERICALLY_STALLED","LINE_SEARCH_FAILED","MAX_ITERATIONS")
    result,events,calls=capture_replay(mu,P,z,R)
    if result.status != original["solver_status"]:
        raise RuntimeError("NONREPRODUCIBLE_STATUS " + str(item) + " " + str(result.status))
    if abs(result.gradient_inf-float(original["gradient_inf"]))>5e-11:
        raise RuntimeError("NONREPRODUCIBLE_GRADIENT " + str(item))
    if not np.allclose(result.prior_delta,s["prior_delta"],rtol=0,atol=1e-10):
        raise RuntimeError("NONREPRODUCIBLE_TERMINAL_STATE " + str(item))
    if len(result.history)!=len(original["history"]):
        raise RuntimeError("NONREPRODUCIBLE_ITERATION_HISTORY " + str(item))
    independent,trace=high_precision_analysis(events,calls,result,mu,P,z,R)
    return {"cell":item,
            "source":{"run_id":SOURCE_RUN_ID,"commit":SOURCE_COMMIT,
                      "fixture_json":inp["source_json"],"fixture_npz":inp["source_npz"],
                      "original_fixture_hashes":inp["source_hashes"],
                      "original_final_status":original["solver_status"],
                      "original_final_gradient":original["gradient_inf"],
                      "failure_step":original["step"],"failure_time_s":original["t_s"]},
            "reproduced":{"status":result.status,"iterations":result.iterations,
                           "gradient_inf":result.gradient_inf,
                           "cost":result.cost,
                           "terminal_delta":result.prior_delta.tolist(),
                           "history_last":result.history[-1] if result.history else {}},
            "numeric":independent,"candidate_grid":trace}


def run(artifact,audit_path,out):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    receipt=json.loads(Path(audit_path).read_text())
    if receipt["decision"]!="GO" or receipt["git_sha"]!=os.environ.get("GITHUB_SHA"):
        raise RuntimeError("PRE_EXECUTION_AUDIT_NOT_GO")
    for name,expected in receipt["source_sha256"].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError("SOURCE_CHANGED_AFTER_AUDIT "+name)
    blob=Path(artifact).read_bytes()
    if sha_bytes(blob)!=ZIP_SHA:
        raise RuntimeError("ORIGINAL_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        if zf.testzip() is not None:
            raise RuntimeError("ZIP_CRC_MISMATCH")
        path,raw=load_member(zf,"/p2_preflight/CASE_INVALID.json")
        failures=json.loads(raw)
        base=path[:-len("CASE_INVALID.json")]
        final_path,raw_fin=load_member(zf,"/p2_preflight/FINAL.json")
        final=json.loads(raw_fin)
        if not(len(failures)==5 and final["invalid_model_cases"]==5
               and final["commit"]==SOURCE_COMMIT
               and final["run_id"]==str(SOURCE_RUN_ID)
               and final["phase"]=="preflight"
               and final["exit_code"]==3):
            raise RuntimeError("SOURCE_FAILURE_COUNT_OR_PROVENANCE_MISMATCH")
        uniq={(x["path"],x["true_bias_dps"],x["trial"],x["model"]) for x in failures}
        if len(uniq)!=5:
            raise RuntimeError("DUPLICATE_FAILURE_KEYS")
        cases=[]
        for idx,item in enumerate(failures):
            print("R3_FIVE_CASE_BEGIN",idx,json.dumps(item),flush=True)
            result=diagnose(item,zf,base)
            cases.append(result)
            (out/f"CASE_{idx+1}.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
            summary={"cell":item, "source_step":result["source"]["failure_step"],
                     "reproduced":result["reproduced"]["status"],
                     "classification":result["numeric"]["classification"],
                     "mp_gradient":result["numeric"]["independent_mp_gradient_inf"],
                     "mp_descent_candidates":result["numeric"]["mp_negative_descent_by_direction"]}
            print("R3_FIVE_CASE_RESULT "+json.dumps(summary,ensure_ascii=False),flush=True)
    index={"schema":"R3_FIVE_FIXED_FAILURE_INDEPENDENT_NUMERIC_V1",
           "source_run_id":SOURCE_RUN_ID,"source_commit":SOURCE_COMMIT,
           "original_artifact_id":11892566974,"original_zip_sha256":ZIP_SHA,
           "diagnostic_git_sha":os.getenv("GITHUB_SHA"),
           "audit_sha256":sha_bytes(Path(audit_path).read_bytes()),
           "cases":len(cases),"all_five_status_reproduced":len(cases)==5,
           "results":[{"cell":c["cell"],"step":c["source"]["failure_step"],
                       "status":c["reproduced"]["status"],
                       "classification":c["numeric"]["classification"],
                       "fp_mismatch":c["numeric"]["mp_float_gradient_inf_gap"],
                       "mp_decrease_counts":c["numeric"]["mp_negative_descent_by_direction"],
                       "mp_root_gradient_inf":c["numeric"]["mp_root_gradient_inf"],
                       "float_gradient_at_mp_root":c["numeric"]["float_gradient_at_mp_root"]}
                      for c in cases],
           "limitations":["mpmath uses original FLOAT64 prior Cholesky factors with 80-digit evaluation",
                          "finite high-precision line-search grid, not global optimality proof",
                          "no scientific P2 data, seed, model, or source solver changes",
                          "5 failed models are not 5 statistically independent RF scenes"],
           "scientific_PASS":False,"time_utc":datetime.now(timezone.utc).isoformat()}
    (out/"DIAGNOSTIC_INDEX.json").write_text(json.dumps(index,indent=2,ensure_ascii=False)+"\n")
    print("R3_FIVE_FINAL "+json.dumps(index,ensure_ascii=False),flush=True)
    return 0


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        raise SystemExit(run(a.artifact,a.audit,a.out))
    except Exception:
        print("R3_FIVE_DIAGNOSTIC_ERROR\n"+traceback.format_exc(),flush=True)
        raise
