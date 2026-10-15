"""R4 P4 failure archive: audit-bound 20-case non-smooth local solver pilot.

The unchanged original MAP failures are reproduced first; local Powell +
sampled Clarke hull validates a distinct NONSMOOTH status, never fabricated
original smooth-gradient success. Every original failed input is immutable.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,zipfile
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from core import map_update
from p3_rf_adapter4 import FrozenLut,R0
from p4_nonsmooth_local import local_nonsmooth_minimize,fixed_objective
from p4_nonsmooth_audit import ZIP_SHA,verify
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ORIGINAL_COMMIT="46d679a32f55cae460d9ed35b4bb944bc48cc4ce"

def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for part in iter(lambda:f.read(1<<20),b""):h.update(part)
 return h.hexdigest()

def main(artifact,audit,out):
 verify(audit)
 if sha_file(artifact)!=ZIP_SHA:
  raise RuntimeError("P4_FROZEN_FAILURE_ARCHIVE_CHANGED")
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 manifest=json.loads((ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
 cmeta={c["id"]:c for c in manifest["cases"]}
 lut=FrozenLut(ROOT)
 cases=[];before={}
 with zipfile.ZipFile(artifact) as z:
  if z.testzip():raise RuntimeError("ZIP_CRC_ERROR")
  finals=[n for n in z.namelist() if n.endswith("/p4_final/P4_FINAL.json")]
  if len(finals)!=1:raise RuntimeError("P4_ORIGINAL_FINAL_UNIQUE_REQUIRED")
  rec=json.loads(z.read(finals[0]))
  if not(rec["git_sha"]==ORIGINAL_COMMIT
         and rec["map_numerically_invalid_updates"]==4124
         and not rec["full_MAP_numerical_PASS"]):
   raise RuntimeError("P4_ORIGINAL_FAILURE_CONTRACT_CHANGED")
  sources={Path(p).name:h for p,h in rec["source_archive_manifest"].items()
           if "/P4_FAILURE_SNAPSHOTS/" in p}
  entries=[]
  for name in z.namelist():
   if "/p4_map/P4_FAILURE_SNAPSHOTS/" not in name or not name.endswith(".json"):
    continue
   b=z.read(name)
   if hashlib.sha256(b).hexdigest()!=sources.get(Path(name).name):
    raise RuntimeError("FROZEN_FAILURE_JSON_HASH_MISMATCH:"+name)
   e=json.loads(b); entries.append((name,e))
  if len(entries)!=4124:
   raise RuntimeError("FAILURE_POPULATION_NOT_FULL")
  bygroup={}
  maxiter=[];tiny=[]
  for name,e in entries:
   key=(e["case"],e["channel"])
   bygroup.setdefault(key,(name,e))
   if e["solver"]["status"]=="MAX_ITERATIONS" and len(maxiter)<3:
    maxiter.append((name,e))
   if e["solver"]["gradient_inf"]<1e-6 and len(tiny)<3:
    tiny.append((name,e))
  selected={}
  for name,e in [*bygroup.values(),*maxiter,*tiny]:
   selected[name]=e
  if not len(selected)==20:
   raise RuntimeError("EXPECTED_EXACT_20_CASES_BUT_"+str(len(selected)))
  for number,(name,e) in enumerate(selected.items()):
   mu=np.asarray(e["prior_mu4"],float)
   P=np.asarray(e["prior_P4"],float)
   raw=np.asarray(e["z_range_s"],float)
   c=cmeta[e["case"]]
   model=lambda x,case=c:lut.model(x,case)
   old=map_update(mu,P,raw,model,R0,
       range_first=(e["method"]=="M4_R"),
       max_iter=80,gradient_tol=1e-8)
   if old.status!=e["solver"]["status"] or not np.isclose(
       old.gradient_inf,float(e["solver"]["gradient_inf"]),atol=1e-9,rtol=0):
    raise RuntimeError("OLD_FAILED_INPUT_NOT_REPRODUCIBLE:"+name)
   cost,grad,Lp=fixed_objective(mu,P,raw,model)
   old_y=np.linalg.solve(Lp,old.prior_delta)
   old_cost=cost(old_y)
   if abs(old_cost-old.cost)>2e-10:
    raise RuntimeError("ORIGINAL_SAME_OBJECTIVE_VIOLATION")
   solved=local_nonsmooth_minimize(mu,P,raw,model,
       warm_delta=old.prior_delta,kink_case=c)
   newx=solved.pop("candidate_x")
   newdelta=solved.pop("posterior_delta")
   if len(newx)!=4 or not np.isfinite(newx).all():
    raise RuntimeError("NEW_SOLVER_NONFINITE")
   if solved["J_delta"]>0.:
    raise RuntimeError("NONSMMOOTH_OBJECTIVE_ROSE_IN_PILOT:"+name)
   detail={"case":e["case"],"channel":e["channel"],"k":e["k"],
       "t_s":e["t_s"],"method":e["method"],
       "original_status":old.status,
       "original_gradient_inf":old.gradient_inf,
       "original_cost":old.cost,
       "original_cost_independent":old_cost,
       "new_x":newx.tolist(),"new_prior_delta":newdelta.tolist(),
       "original_source_failure_sha256":sources[Path(name).name],
       **solved}
   (out/f"CASE_{number:02d}.json").write_text(json.dumps(detail,indent=2)+"\n")
   cases.append(detail)
   print("P4_NONSMOOTH_CASE "+json.dumps({k:detail[k] for k in
     ("case","channel","k","method","original_status","terminal_status",
      "J_delta","original_smooth_gradient_inf","powell_nfev")}),flush=True)
 status_counts={stat:sum(d["terminal_status"]==stat for d in cases)
                for stat in sorted({v["terminal_status"] for v in cases})}
 final={"schema":"P4_R4_NONSMOOTH_FROZEN_20_CASE_PILOT_V1",
   "original_source_commit":ORIGINAL_COMMIT,
   "git_sha":os.environ["GITHUB_SHA"],"run_id":os.getenv("GITHUB_RUN_ID"),
   "original_archive_sha256":ZIP_SHA,
   "original_invalid_population":len(entries),
   "sample_count":len(cases),
   "statuses":status_counts,
   "cost_nonincreasing":sum(d["J_delta"]<=0. for d in cases),
   "probe_nonnegative_cases":sum(d["probe"]["negative_beyond_1e_minus_5"]==0 for d in cases),
   "clarke_hull_small_cases":sum(d["clarke_hull_proxy"].get("norm") is not None
       and d["clarke_hull_proxy"]["norm"]<=1e-3 for d in cases),
   "old_smooth_converged":sum(d["original_smooth_gradient_inf"]<=1e-8 for d in cases),
   "original_optimizer_unchanged":True,"objective_unchanged":True,
   "no_silent_success_conversion":True,
   "scientific_PASS":False,
   "status":"PILOT_COMPLETED_WITH_SCOPED_LOCAL_CANDIDATES",
   "limitations":["Non-smooth Clarke proxy sampled, not exhaustive"],
   "cases":[{k:r[k] for k in ("case","channel","k","method","original_status",
       "terminal_status","J_delta","original_smooth_gradient_inf")} for r in cases],
   "finished_utc":datetime.now(timezone.utc).isoformat()}
 (out/"FINAL.json").write_text(json.dumps(final,indent=2)+"\n")
 print("P4_NONSMOOTH_FINAL "+json.dumps({k:final[k] for k in
  ("status","sample_count","statuses","cost_nonincreasing",
   "probe_nonnegative_cases","clarke_hull_small_cases",
   "old_smooth_converged")}),flush=True)
 return 0
if __name__=="__main__":
 p=argparse.ArgumentParser()
 for n in ("artifact","audit","out"):p.add_argument("--"+n,required=True)
 a=p.parse_args();raise SystemExit(main(a.artifact,a.audit,a.out))
