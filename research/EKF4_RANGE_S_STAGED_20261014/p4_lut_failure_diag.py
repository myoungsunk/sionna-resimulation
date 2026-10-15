"""Read-only 20-case independent LUT-knot and MAP descent diagnosis after audit.

Source model is unchanged from original R4 P4; no parameter changes,
no alternative estimator, no truth access and no completion promotion.
"""
from __future__ import annotations
import argparse,hashlib,json,math,os,zipfile,collections,traceback
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from p3_rf_adapter4 import FrozenLut,R0
from core import map_update
from p4_lut_diag_audit import ORIGINAL_COMMIT,ARTIFACT_SHA,hashes,ROOT,HERE

def sha_file(p):return hashes(Path(p))[1]
def wrap_deg(x):return (x+180.)%360.-180.
def cell_geometry(x,case):
    ax,ay,az=case["anchor"]
    u,v=x[0]-ax,x[1]-ay
    rho=math.hypot(u,v)
    theta=math.degrees(math.atan2(rho,az-case["robot_z_m"]))
    tx=math.degrees(math.atan2(-v,u))
    rx=wrap_deg(math.degrees(math.atan2(-v,-u))-math.degrees(x[2])-case["mount_deg"])
    vals={"theta_deg":theta,"phi_tx_deg":tx,"phi_rx_deg":rx}
    vals.update({name+"_nearest_grid_distance_deg":abs((value/2)-round(value/2))*2
                for name,value in list(vals.items())})
    vals["min_grid_distance_deg"]=min(v for k,v in vals.items() if k.endswith("_nearest_grid_distance_deg"))
    return vals

def gradient_model(x,case,lut):
    _,H=lut.model(x,case)
    errs={};jumps={}
    for epsilon in (1e-4,1e-5,1e-6):
        for j,label in enumerate(("x_m","y_m","yaw_rad")):
            xp=x.copy();xm=x.copy();xp[j]+=epsilon;xm[j]-=epsilon
            h=lut.model(x,case)[0][1]
            hp=lut.model(xp,case)[0][1]
            hm=lut.model(xm,case)[0][1]
            central=(hp-hm)/(2*epsilon)
            right=(hp-h)/epsilon
            left=(h-hm)/epsilon
            errs[f"{label}_eps{epsilon:g}"]=abs(central-H[1,j])
            jumps[f"{label}_eps{epsilon:g}"]=abs(right-left)
    return errs,jumps

def stationarity(y,mu,P,z,lut,case):
    Lp,Lr=np.linalg.cholesky(P),np.linalg.cholesky(R0)
    def ev(yy):
        delta=Lp@yy
        h,H=lut.model(mu+delta,case)
        v=np.linalg.solve(Lr,z-h);B=np.linalg.solve(Lr,H@Lp)
        return .5*float(yy@yy+v@v),yy-B.T@v,np.eye(len(y))+B.T@B
    c,g,A=ev(y)
    step=np.linalg.solve(A,-g)
    candidates=[]
    for t in (1.,.5,.25,.125,.0625,.015625):
        cc,gg,_=ev(y+t*step)
        candidates.append({"fraction":t,"cost_diff":cc-c,
                           "grad_new_inf":float(np.max(abs(gg)))})
    return {"gradient_inf":float(np.max(abs(g))),
            "directional_slope":float(g@step),
            "gn_step_norm_inf":float(np.max(abs(step))),
            "candidate_grid":candidates}

def run(artifact,audit,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    audit_data=json.loads(Path(audit).read_text())
    if (audit_data.get("decision")!="GO"
        or audit_data.get("git_sha")!=os.getenv("GITHUB_SHA")):
        raise RuntimeError("DIAGNOSTIC_PREAUDIT_NOT_GO")
    for name,sha in audit_data["source_sha256"].items():
        p=ROOT/name if "/" in name else (HERE/name)
        if name=="workflow":p=ROOT/".github/workflows/ekf4-r4-p4-lut-rootcause.yml"
        if sha_file(p)!=sha:raise RuntimeError("DIAGNOSTIC_SOURCE_MISMATCH:"+name)
    if sha_file(artifact)!=ARTIFACT_SHA:
        raise RuntimeError("P4_ARTIFACT_SHA_CHANGED")
    manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    by_case={c["id"]:c for c in manifest["cases"]}
    details=[];type_counts=collections.Counter();first_by_group={};maximum=[];tiny=[]
    with zipfile.ZipFile(artifact) as z:
        if z.testzip() is not None:raise RuntimeError("P4_ARCHIVE_ZIP_CRC_BAD")
        finnames=[x for x in z.namelist() if x.endswith("/p4_final/P4_FINAL.json")]
        if len(finnames)!=1:raise RuntimeError("P4_FINAL_MISSING")
        final=json.loads(z.read(finnames[0]))
        if not(final["git_sha"]==ORIGINAL_COMMIT and final["map_numerically_invalid_updates"]==4124
            and final["fixed_technical_PASS"] and final["exit_code"]==0):
            raise RuntimeError("ORIGINAL_FINAL_VERDICT_MISMATCH")
        source_hash={Path(k).name:v for k,v in final["source_archive_manifest"].items()
                     if "/P4_FAILURE_SNAPSHOTS/" in k}
        entries=[]
        for name in z.namelist():
            if "/p4_map/P4_FAILURE_SNAPSHOTS/" not in name or not name.endswith(".json"):continue
            data=z.read(name)
            if hashlib.sha256(data).hexdigest()!=source_hash.get(Path(name).name):
                raise RuntimeError("P4_CASE_PROVENANCE_MISMATCH:"+name)
            obj=json.loads(data)
            case=(obj["case"],obj["channel"])
            entry={"name":name,"case":case,"json":obj}
            entries.append(entry)
            d=obj["solver"]
            type_counts[d["status"]]+=1
            if case not in first_by_group:first_by_group[case]=entry
            if d["status"]=="MAX_ITERATIONS" and len(maximum)<3:maximum.append(entry)
            if d.get("gradient_inf",999) < 1e-6 and len(tiny)<3:tiny.append(entry)
        if len(entries)!=4124:raise RuntimeError("MISSING_FAILURES_IN_ORIGINAL_ARTIFACT")
        used={}
        for e in [*first_by_group.values(),*maximum,*tiny]:
            used[e["name"]]=e
        lut=FrozenLut(ROOT)
        for i,e in enumerate(used.values()):
            d=e["json"];case=by_case[d["case"]]
            mu=np.asarray(d["prior_mu4"],float)
            P=np.asarray(d["prior_P4"],float)
            zvec=np.asarray(d["z_range_s"],float)
            r=map_update(mu,P,zvec,lambda v:lut.model(v,case),R0,
                         range_first=(d["method"]=="M4_R"),
                         max_iter=80,gradient_tol=1e-8)
            old=d["solver"]
            if r.status!=old["status"] or not math.isclose(r.gradient_inf,old["gradient_inf"],rel_tol=1e-6,abs_tol=1e-10):
                raise RuntimeError("FROZEN_FAILURE_REPLAY_NOT_REPRODUCED:"+e["name"])
            final_state=mu+r.prior_delta
            y=np.linalg.solve(np.linalg.cholesky(P),r.prior_delta)
            geometry=cell_geometry(final_state,case)
            jac_errors,jumps=gradient_model(final_state,case,lut)
            steps=stationarity(y,mu,P,zvec,lut,case)
            rec={
                "case":d["case"],"channel":d["channel"],"k":d["k"],
                "method":d["method"],"old_status":old["status"],
                "new_status":r.status,"old_grad_inf":old["gradient_inf"],
                "new_grad_inf":r.gradient_inf,
                "old_iteration":old["iterations"],"new_iteration":r.iterations,
                "source_failure_json_sha256":hashlib.sha256(
                    z.read(e["name"])).hexdigest(),
                "geometry":geometry,
                "analytic_vs_central_gradient_max":max(jac_errors.values()),
                "one_sided_derivative_jump_max":max(jumps.values()),
                "jacobian_numerical_errors":jac_errors,
                "one_sided_gradient_jumps":jumps,
                "local_GN_checks":steps,
                "interpretation_scope":"local LUT interpolation and solver numerical evidence; not a change to science results"}
            details.append(rec)
            (out/f"DIAGNOSTIC_{i:02d}.json").write_text(json.dumps(rec,indent=2)+"\n")
            print("P4_D4_CASE "+json.dumps({
              k:rec[k] for k in ("case","channel","k","method","new_status",
                "new_grad_inf","analytic_vs_central_gradient_max","one_sided_derivative_jump_max")}),flush=True)
    summary={"schema":"P4_D4_AUDITED_NUMERICAL_DIAGNOSTIC_V1",
        "original_run_id":38658117256,"source_commit":ORIGINAL_COMMIT,
        "artifact_zip_sha256":ARTIFACT_SHA,
        "diagnostic_git_sha":os.getenv("GITHUB_SHA"),
        "preaudit_sha256":sha_file(audit),
        "original_failures":len(entries),
        "original_failure_types":dict(type_counts),
        "sample_cases_tested":len(details),
        "all_sample_statuses_reproduced":True,
        "near_grid_knot_under_0p001deg":sum(x["geometry"]["min_grid_distance_deg"]<=.001 for x in details),
        "derivative_one_sided_jump_gt_1e-3":sum(x["one_sided_derivative_jump_max"]>.001 for x in details),
        "central_derivative_mismatch_gt_1e-3":sum(x["analytic_vs_central_gradient_max"]>.001 for x in details),
        "some_local_GN_step_cost_decreased":sum(any(c["cost_diff"]<0 for c in x["local_GN_checks"]["candidate_grid"]) for x in details),
        "rows":[{k:x[k] for k in ("case","channel","k","method","new_status","new_grad_inf",
                                 "analytic_vs_central_gradient_max","one_sided_derivative_jump_max")}
                |{"min_lut_knot_distance_deg":x["geometry"]["min_grid_distance_deg"],
                 "gn_any_improving_step":any(c["cost_diff"]<0 for c in x["local_GN_checks"]["candidate_grid"])}
                for x in details],
        "status":"DIAGNOSTIC_COMPLETED","scientific_PASS":False,
        "observations_are_same_frozen_R0":True,"model_changed":False,
        "time_utc":datetime.now(timezone.utc).isoformat()}
    def numpy_safe(v):
        if isinstance(v,np.generic):return v.item()
        if isinstance(v,np.ndarray):return v.tolist()
        raise TypeError(type(v).__name__)
    (out/"P4_D4_FINAL.json").write_text(json.dumps(summary,indent=2,default=numpy_safe)+"\\n")
    print("P4_D4_FINAL "+json.dumps({k:summary[k] for k in
       ("status","original_failures","original_failure_types","sample_cases_tested",
        "all_sample_statuses_reproduced","near_grid_knot_under_0p001deg",
        "derivative_one_sided_jump_gt_1e-3","central_derivative_mismatch_gt_1e-3",
        "some_local_GN_step_cost_decreased")}),flush=True)
    return 0

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifact",required=True,type=Path)
    p.add_argument("--audit",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    raise SystemExit(run(a.artifact,a.audit,a.out))
