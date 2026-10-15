"""Expanded R5 nonsmooth original-LUT audit: all 4,124 old MAP failures,
then deterministic stratified cell-aware solver pilot (not old success labels).

No GT read. No posterior covariance claim. No R0/LUT/core code changes.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,os,traceback,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from core import map_update
from p3_rf_adapter4 import FrozenLut,R0
from p4_lut_boundary import boundary_report,segment_crossings
from p4_nonsmooth_local import local_nonsmooth_minimize,fixed_objective
from p4_extended_audit import require_audit,digest,P4_SHA,ROOT

ORIG_COMMIT="46d679a32f55cae460d9ed35b4bb944bc48cc4ce"
HERE=Path(__file__).resolve().parent
SEED=20261015

def np_safe(x):
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,np.ndarray):return x.tolist()
    raise TypeError(type(x).__name__)
def write(p,rec):
    Path(p).write_text(json.dumps(rec,indent=2,default=np_safe,allow_nan=False)+"\n")
def load_original(z):
    final_files=[p for p in z.namelist() if p.endswith("/p4_final/P4_FINAL.json")]
    if len(final_files)!=1:raise RuntimeError("P4_FINAL_MISSING_OR_DUPLICATE")
    rec=json.loads(z.read(final_files[0]))
    if not(rec["git_sha"]==ORIG_COMMIT and rec["map_numerically_invalid_updates"]==4124
           and rec["full_total_timepoints"]==14502
           and rec["fixed_technical_PASS"] and not rec["full_MAP_numerical_PASS"]):
        raise RuntimeError("ORIGINAL_P4_RECEIPT_MISMATCH")
    hashes={Path(p).name:s for p,s in rec["source_archive_manifest"].items()
       if "/P4_FAILURE_SNAPSHOTS/" in p}
    entries=[]
    for path in sorted(z.namelist()):
        if "/p4_map/P4_FAILURE_SNAPSHOTS/" not in path or not path.endswith(".json"):
            continue
        raw=z.read(path)
        if hashlib.sha256(raw).hexdigest()!=hashes.get(Path(path).name):
            raise RuntimeError("INDIVIDUAL_ORIGINAL_FAILURE_SHA_MISMATCH:"+path)
        obj=json.loads(raw)
        entries.append({"source_path":path,
                        "source_sha256":hashlib.sha256(raw).hexdigest(),
                        "case":obj["case"],"channel":obj["channel"],
                        "method":obj["method"],"k":int(obj["k"]),
                        "original_status":obj["solver"]["status"],
                        "original_gradient_inf":float(obj["solver"]["gradient_inf"]),
                        "input":obj})
    if len(entries)!=4124:raise RuntimeError("ORIGINAL_FAILURES_NOT_4124")
    return entries,rec

def reconstruct(obj,lut,by_case):
    mu=np.asarray(obj["prior_mu4"],float);P=np.asarray(obj["prior_P4"],float)
    z=np.asarray(obj["z_range_s"],float)
    case=by_case[obj["case"]]
    model=lambda x:lut.model(x,case)
    result=map_update(mu,P,z,model,R0,
      range_first=(obj["method"]=="M4_R"),max_iter=80,gradient_tol=1e-8)
    old=obj["solver"]
    if result.status!=old["status"]:
        raise RuntimeError("ORIGINAL_FAILURE_STATUS_NOT_REPRODUCED")
    if not math.isclose(result.gradient_inf,float(old["gradient_inf"]),
           rel_tol=2e-5,abs_tol=1e-8):
        raise RuntimeError("ORIGINAL_FAILURE_GRAD_NOT_REPRODUCED")
    return mu,P,z,case,model,result

def stage_full(artifact,audit,out):
    require_audit(audit)
    if digest(artifact)!=P4_SHA:raise RuntimeError("ORIGINAL_SOURCE_ZIP_SHA_CHANGED")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    lut=FrozenLut(ROOT)
    manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    by_case={c["id"]:c for c in manifest["cases"]}
    rows=[];errors=[]
    with zipfile.ZipFile(artifact) as z:
        if z.testzip():raise RuntimeError("ORIGINAL_ZIP_CRC_FAIL")
        entries,rec=load_original(z)
        for n,entry in enumerate(entries):
            obj=entry["input"]
            try:
                mu,P,zvec,case,model,r=reconstruct(obj,lut,by_case)
                x=mu+r.prior_delta
                try:
                    br=boundary_report(x,case)
                    near=br["min_grid_distance_deg"]
                    geometry="VALID"
                    near_dim=br["near_knot_dimensions"]
                except ValueError as exc:
                    br=None;near=None;geometry="INVALID:"+str(exc);near_dim=[]
                st={"case":entry["case"],"channel":entry["channel"],
                    "method":entry["method"],"k":entry["k"],
                    "source_path":entry["source_path"],
                    "source_sha256":entry["source_sha256"],
                    "original_status":entry["original_status"],
                    "gradient_inf":float(r.gradient_inf),
                    "reproduced_status":r.status,"geometry_status":geometry,
                    "near_knot_0p001deg":near is not None and near<=.001,
                    "min_grid_distance_deg":near,
                    "near_knot_dimensions":near_dim,
                    "grid_theta_distance_deg":None if br is None else br["grid_distance_deg"]["theta_deg"],
                    "grid_tx_distance_deg":None if br is None else br["grid_distance_deg"]["phi_tx_deg"],
                    "grid_rx_distance_deg":None if br is None else br["grid_distance_deg"]["phi_rx_deg"],
                    "source_failure_model":entry["method"]}
                rows.append(st)
            except Exception as exc:
                errors.append({"source_path":entry["source_path"],
                    "error_type":type(exc).__name__,"reason":str(exc)})
            if (n+1)%250==0:
                progress={"checked":n+1,"reproduced":len(rows),
                         "nonreproduced":len(errors),"last_group":[entry["case"],entry["channel"]]}
                write(out/"FULL_PROGRESS.json",progress)
                print("EXTENDED_FULL_PROGRESS "+json.dumps(progress),flush=True)
        if len(rows)!=4124 or errors:
            outrec={"status":"FULL_ORIGINAL_REPLAY_FAILED",
                    "reproduced":len(rows),"errors":errors[:80],
                    "original":4124,"scientific_PASS":False}
            write(out/"FULL_GEOMETRY_FINAL.json",outrec)
            raise RuntimeError("ORIGINAL_FAILURE_REPLAY_NOT_REPRODUCIBLE:"+str(len(errors)))
    strata=collections.defaultdict(list)
    for r in rows:strata[(r["case"],r["channel"],r["method"],r["original_status"])].append(r)
    grouprows=[]
    for key,subset in sorted(strata.items()):
        near=[x["min_grid_distance_deg"] for x in subset if x["min_grid_distance_deg"] is not None]
        grouprows.append({"group":list(key),"n":len(subset),
            "near_0p001":sum(r["near_knot_0p001deg"] for r in subset),
            "nearest_grid_distance_median_deg":float(np.median(near)) if near else None,
            "geometry_invalid":sum(r["geometry_status"]!="VALID" for r in subset)})
    full={
        "schema":"R5_P4_4124_ORIGINAL_FAILURE_GEOMETRY_V1",
        "status":"COMPLETE_4124_REPRODUCED",
        "run_id":os.getenv("GITHUB_RUN_ID"),
        "git_sha":os.getenv("GITHUB_SHA"),
        "source_P4_artifact_sha256":P4_SHA,
        "full_source_population":4124,
        "reproduced":len(rows),"nonreproduced":0,
        "near_0p001":sum(x["near_knot_0p001deg"] for x in rows),
        "near_0p01":sum(x["min_grid_distance_deg"] is not None and x["min_grid_distance_deg"]<=.01 for x in rows),
        "near_0p1":sum(x["min_grid_distance_deg"] is not None and x["min_grid_distance_deg"]<=.1 for x in rows),
        "by_status":dict(collections.Counter(x["original_status"] for x in rows)),
        "by_group_status":grouprows if False else grouprows,
        "geometry_invalid":sum(x["geometry_status"]!="VALID" for x in rows),
        "warning":"LUT-knot proximity measures association, not independently proven causal mechanism.",
        "scientific_PASS":False,
        "time_utc":datetime.now(timezone.utc).isoformat()}
    write(out/"FULL_GEOMETRY_FINAL.json",full)
    write(out/"FULL_GEOMETRY_CASES.json",rows)
    print("R5_FULL_GEOMETRY "+json.dumps({k:full[k] for k in
      ("status","reproduced","near_0p001","near_0p01","near_0p1",
       "geometry_invalid","by_status")}),flush=True)
    return 0

def stratified_selection(rows):
    # Exact preregistered deterministic selection: 6 from each of 28
    # case×channel×start-method strata. Two closest, two farthest from
    # any LUT knot, two SHA-ranked; add original historical 20 controls.
    strata=collections.defaultdict(list)
    for r in rows:
        strata[(r["case"],r["channel"],r["method"])].append(r)
    selection={};selection_reasons=collections.defaultdict(set)
    for group,rs in sorted(strata.items()):
        valid=[r for r in rs if r["min_grid_distance_deg"] is not None]
        valid.sort(key=lambda r:(r["min_grid_distance_deg"],r["source_sha256"]))
        ranked=sorted(rs,key=lambda r:hashlib.sha256(
            (str(SEED)+r["source_sha256"]).encode()).hexdigest())
        candidates=valid[:2]+list(reversed(valid[-2:]))+ranked
        chosen=set()
        for v in candidates:
            if v["source_path"] not in chosen:
                chosen.add(v["source_path"])
                selection[v["source_path"]]=v
                selection_reasons[v["source_path"]].add("KNOT_EXTREME_OR_HASH")
            if len(chosen)==6:break
        if len(chosen)!=6:raise RuntimeError("STRATUM_HAS_LESS_THAN_SIX:"+str(group))
    # Historical 20 consists of one first failed case per case/channel,
    # first 3 MAX_ITERATIONS and first 3 tiny gradient controls as in D4.
    historical={};first_group=set();nmax=ntiny=0
    for r in sorted(rows,key=lambda r:r["source_path"]):
        k=(r["case"],r["channel"])
        if k not in first_group:
            historical[r["source_path"]]=r;first_group.add(k)
    for r in sorted(rows,key=lambda r:r["source_path"]):
        if r["original_status"]=="MAX_ITERATIONS" and nmax<3:
            historical[r["source_path"]]=r;nmax+=1
        if r["gradient_inf"]<1e-6 and ntiny<3:
            historical[r["source_path"]]=r;ntiny+=1
    for path,r in historical.items():
        selection[path]=r
        selection_reasons[path].add("HISTORICAL_CONTROL")
    return [dict(row,selection_reason=sorted(selection_reasons[p])) for p,row in sorted(selection.items())],{
        "strata":len(strata),"six_per_stratum":len(strata)*6,
        "historical_controls_unique":len(historical),
        "unique_validation_inputs":len(selection),
        "selection_seed":SEED,
        "note":"Selection intentionally mixes extremes and deterministic SHA-ranked examples. Not prevalence estimator."}

def stage_stratified(artifact,audit,full_dir,out):
    require_audit(audit)
    if digest(artifact)!=P4_SHA:raise RuntimeError("ORIGINAL_SOURCE_ZIP_SHA_CHANGED")
    geometry=json.loads((Path(full_dir)/"FULL_GEOMETRY_FINAL.json").read_text())
    if geometry["status"]!="COMPLETE_4124_REPRODUCED" or geometry["git_sha"]!=os.getenv("GITHUB_SHA"):
        raise RuntimeError("FULL_REPRODUCTION_NOT_COMPLETE")
    rows=json.loads((Path(full_dir)/"FULL_GEOMETRY_CASES.json").read_text())
    selected,selection_contract=stratified_selection(rows)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    write(out/"SELECTION_CONTRACT.json",
          {"contract":selection_contract,"source_case_sha256":[r["source_sha256"] for r in selected]})
    manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    by_case={c["id"]:c for c in manifest["cases"]}
    lut=FrozenLut(ROOT)
    cases=[];counts=collections.Counter();strategy=collections.Counter()
    with zipfile.ZipFile(artifact) as z:
        for index,entry in enumerate(selected):
            f=entry["source_path"]
            raw=z.read(f)
            if hashlib.sha256(raw).hexdigest()!=entry["source_sha256"]:
                raise RuntimeError("SELECTED_ORIGINAL_SNAPSHOT_MISMATCH")
            obj=json.loads(raw)
            mu,P,zvec,case,model,r=reconstruct(obj,lut,by_case)
            initial=mu+r.prior_delta
            cost,grad,Lp=fixed_objective(mu,P,zvec,model)
            y0=np.linalg.solve(Lp,r.prior_delta)
            c0=cost(y0)
            try:
                candidate=local_nonsmooth_minimize(mu,P,zvec,model,
                      warm_delta=r.prior_delta,kink_case=case,
                      maxfev=24000)
                candidate_x=candidate.pop("candidate_x")
                delta=candidate.pop("posterior_delta")
                y=np.linalg.solve(Lp,delta)
                delta_J=cost(y)-c0
                if not (math.isfinite(delta_J) and delta_J<=0.):
                    raise RuntimeError("STRICT_ORIGINAL_OBJECTIVE_NONINCREASING_VIOLATED")
                if abs(candidate["J_delta"]-delta_J)>1e-9:
                    raise RuntimeError("CANDIDATE_INTERNAL_COST_NOT_SAME_OBJECTIVE")
                status=candidate["terminal_status"]
                strategy[candidate["candidate_strategy"]]+=1
                result={
                    "source_path":f,"source_sha256":entry["source_sha256"],
                    "case":obj["case"],"channel":obj["channel"],"method":obj["method"],
                    "k":obj["k"],"old_status":r.status,
                    "original_cost":float(c0),
                    "new_cost":float(cost(y)),
                    "delta_J_vs_original_failed":float(delta_J),
                    "knot_distance_orig_deg":entry["min_grid_distance_deg"],
                    "new_terminal_status":status,
                    "strategy":candidate["candidate_strategy"],
                    "original_smooth_gradient_at_new":candidate["original_smooth_gradient_inf"],
                    "probe":candidate["probe"],
                    "clarke_hull_proxy":candidate["clarke_hull_proxy"],
                    "explicit_boundary_candidates":candidate.get("explicit_boundary_candidates",0),
                    "boundary_detector":candidate.get("boundary_detector"),
                    "diagnostic":candidate,
                    "scientific_PASS":False}
            except Exception as exc:
                result={"source_path":f,"source_sha256":entry["source_sha256"],
                   "case":obj["case"],"channel":obj["channel"],"method":obj["method"],
                   "k":obj["k"],"old_status":r.status,
                   "new_terminal_status":"DIAGNOSTIC_ERROR",
                   "exception":type(exc).__name__+":"+str(exc),"scientific_PASS":False}
                status="DIAGNOSTIC_ERROR"
            cases.append(result);counts[status]+=1
            write(out/(f"CASE_{index:04d}.json"),result)
            if (index+1)%10==0 or index+1==len(selected):
                receipt={"done":index+1,"total":len(selected),
                         "statuses":dict(counts),"strategies":dict(strategy)}
                write(out/"STRATIFIED_PROGRESS.json",receipt)
                print("R5_EXTENDED_PILOT_PROGRESS "+json.dumps(receipt),flush=True)
    strict_violations=[v for v in cases if v.get("delta_J_vs_original_failed",0.)>0]
    if strict_violations:raise RuntimeError("STRICT_OBJECTIVE_INCREASE")
    final={
       "schema":"R5_P4_EXTENDED_NONSMOOTH_PILOT_V1",
       "status":"STRATIFIED_DIAGNOSTIC_COMPLETE",
       "source_original_P4_git_sha":ORIG_COMMIT,
       "source_original_P4_artifact_sha256":P4_SHA,
       "git_sha":os.getenv("GITHUB_SHA"),
       "selection_contract":selection_contract,
       "tested":len(selected),
       "new_statuses":dict(counts),
       "strategies":dict(strategy),
       "strict_no_objective_increase":len(strict_violations)==0,
       "new_smooth_gradient_atol_1e-8":sum(
         x.get("original_smooth_gradient_at_new",math.inf)<=1e-8 for x in cases),
       "observational_likelihood_unchanged":True,
       "original_R4_P4_4124_INVALID_UNCHANGED":True,
       "covariance_not_validated":True,
       "scientific_PASS":False,
       "note":"Approximate directional/Clarke sampled candidate, not proof of 4D nonsmooth stationarity.",
       "sample_rows":[{k:v.get(k) for k in (
           "case","channel","method","k","old_status","new_terminal_status",
           "knot_distance_orig_deg","delta_J_vs_original_failed","strategy")}
           for v in cases],
       "time_utc":datetime.now(timezone.utc).isoformat()}
    write(out/"STRATIFIED_FINAL.json",final)
    print("R5_EXTENDED_FINAL "+json.dumps({k:final[k] for k in
        ("status","tested","new_statuses","strategies",
          "strict_no_objective_increase","new_smooth_gradient_atol_1e-8")}),flush=True)
    return 0 if counts["DIAGNOSTIC_ERROR"]==0 else 3

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--phase",required=True,choices=("full-geometry","stratified-solver"))
    for key in ("artifact","audit","out"):p.add_argument("--"+key,required=True)
    p.add_argument("--full-geometry-dir")
    args=p.parse_args()
    if args.phase=="full-geometry":
        raise SystemExit(stage_full(args.artifact,args.audit,args.out))
    raise SystemExit(stage_stratified(args.artifact,args.audit,args.full_geometry_dir,args.out))
