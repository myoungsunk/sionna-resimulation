"""Exact 3 anomalous R5 candidate tests: original-J round-trip cost semantics."""
import argparse,hashlib,io,json,math,os,zipfile
from pathlib import Path
import numpy as np
from core import map_update
from p3_rf_adapter4 import FrozenLut,R0
from p4_nonsmooth_local import local_nonsmooth_minimize,fixed_objective
from p4_roundtrip_preaudit import ROOT,HERE,P4_ARCHIVE_SHA,sha
TARGETS=[
 ("R2_aA_m45","los",868,"M4_P"),
 ("R4_aB_m0","full",365,"M4_R"),
 ("R4_aB_m0","los",455,"M4_R")
]
def run(artifact,audit,out):
    receipt=json.loads(Path(audit).read_text())
    if receipt["decision"]!="GO" or receipt["git_sha"]!=os.getenv("GITHUB_SHA"):
        raise RuntimeError("PREAUDIT_NOT_GO")
    for path,expected in receipt["source_sha256"].items():
        if sha(ROOT/path)!=expected:raise RuntimeError("SOURCE_CHANGED:"+path)
    if sha(artifact)!=P4_ARCHIVE_SHA:raise RuntimeError("ARCHIVE_SHA_MISMATCH")
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    lut=FrozenLut(ROOT)
    m=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    metas={c["id"]:c for c in m["cases"]}
    results=[]
    with zipfile.ZipFile(artifact) as z:
        if z.testzip():raise RuntimeError("ZIP_CRC_ERROR")
        for case,ch,k,method in TARGETS:
            name=f"_temp/p4_map/P4_FAILURE_SNAPSHOTS/{case}_{ch}_k{k:04d}_{method}.json"
            entry=[x for x in z.namelist() if x.endswith(name)]
            if len(entry)!=1:raise RuntimeError("FIXTURE_NOT_UNIQUE")
            source=json.loads(z.read(entry[0]))
            mu=np.asarray(source["prior_mu4"],float)
            P=np.asarray(source["prior_P4"],float)
            zraw=np.asarray(source["z_range_s"],float)
            obj=lambda x:lut.model(x,metas[case])
            old=map_update(mu,P,zraw,obj,R0,
                    range_first=(method=="M4_R"),max_iter=80,gradient_tol=1e-8)
            if old.status!=source["solver"]["status"]:
                raise RuntimeError("FROZEN_ORIGINAL_FAILURE_NOT_REPRODUCIBLE")
            cost,grad,Lp=fixed_objective(mu,P,zraw,obj)
            original_y=np.linalg.solve(Lp,old.prior_delta)
            c0=cost(original_y)
            candidate=local_nonsmooth_minimize(mu,P,zraw,obj,
                     warm_delta=old.prior_delta,kink_case=metas[case])
            delta=np.asarray(candidate["posterior_delta"])
            cand_x=np.asarray(candidate["candidate_x"])
            reconstructed_y=np.linalg.solve(Lp,delta)
            x_restored_y=np.linalg.solve(Lp,cand_x-mu)
            dc_y=cost(reconstructed_y)-c0
            dc_x=cost(x_restored_y)-c0
            internal=float(candidate["J_final"]-candidate["J_initial"])
            margin=32*np.finfo(float).eps*max(1.,abs(c0))
            row={"case":case,"channel":ch,"k":k,"method":method,
                 "original_status":old.status,"candidate_status":candidate["terminal_status"],
                 "candidate_strategy":candidate["candidate_strategy"],
                 "original_J":float(c0),"reported_J_initial":candidate["J_initial"],
                 "reported_J_final":candidate["J_final"],"reported_J_delta":candidate["J_delta"],
                 "internally_recomputed_delta_J":internal,
                 "roundtrip_state_reconstructed_delta_J":float(dc_y),
                 "physical_x_reconstructed_delta_J":float(dc_x),
                 "roundtrip_cost_discrepancy":float(dc_y-internal),
                 "delta_roundtrip_y_norm_inf":float(np.max(abs(original_y-reconstructed_y))),
                 "cost_uncertainty_32eps":float(margin),
                 "candidate_verified_only_under_internal_coordinates": bool(
                     candidate["J_delta"]<=0 and dc_y>0),
                 "source_failure_sha256":hashlib.sha256(z.read(entry[0])).hexdigest()}
            results.append(row)
            print("R5_ROUNDTRIP_CASE "+json.dumps(row),flush=True)
            (out/f"{case}_{ch}_{k}_{method}.json").write_text(json.dumps(row,indent=2)+"\n")
    summ={"schema":"R5_ROUNDTRIP_GUARD_DIAGNOSTIC_V1",
          "status":"FIXED_SOURCE_REEVALUATION_COMPLETE",
          "source_git_sha":os.getenv("GITHUB_SHA"),
          "strict_violations":sum(x["roundtrip_state_reconstructed_delta_J"]>0 for x in results),
          "cases":results,"scientific_PASS":False,
          "note":"Numerical finite precision representability only; no original R4 result modified."}
    (out/"ROUNDTRIP_FINAL.json").write_text(json.dumps(summ,indent=2)+"\n")
    return 0
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for n in ("artifact","audit","out"):p.add_argument("--"+n,required=True)
    a=p.parse_args();raise SystemExit(run(a.artifact,a.audit,a.out))
