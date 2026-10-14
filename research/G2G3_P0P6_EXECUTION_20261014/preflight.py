#!/usr/bin/env python3
"""P0/P1 audit first; P2 prerequisite decision. No false G2/G3 performance PASS."""
from __future__ import annotations
import argparse,csv,hashlib,json,math,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=R/"outputs/g2g3_p0p6"
H3="research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d"
BF="research/G2G3_BF_STAGED_20261014"
INPUTS={
"original_g3":f"{H3}/h3_offline.py",
"original_R0_contract":f"{H3}/CONTRACT.json",
"original_stage4_partial":f"{H3}/STAGE4_SMOKE_01/SMOKE_PARTIAL.csv",
"g3_tilted_method":f"{BF}/tilted_g3.py",
"g2g3_prior_contract":f"{BF}/CONTRACT.json",
"bf_history":f"{BF}/EXECUTION_SUMMARY.json"
}
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
 return h.hexdigest()
def write(name,d):
 OUT.mkdir(parents=True,exist_ok=True)
 p=OUT/name
 if p.exists():raise FileExistsError("output immutable "+str(p))
 p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False))
def run(stage):
 OUT.mkdir(parents=True,exist_ok=True)
 review=json.loads((HERE/"APPROVAL.json").read_text())
 contract=json.loads((HERE/"CONTRACT.json").read_text())
 receipt=dict(stage=stage,execution_sha=subprocess.check_output(["git","rev-parse","HEAD"],cwd=R,text=True).strip(),
  execute=False,calculation="NOT_EVALUATED",hypothesis="NOT_EVALUATED",scientific_claim="NOT_EVALUATED",
  audited_code_matches_execution_sha=False,source_sha256={},previous_evidence={},findings=[])
 try:
  if review["run_decision"]!="GO_WITH_CLAIM_LIMITATION" or stage not in review["authorized_stages"]:
   raise RuntimeError("HARD_EXECUTION_BLOCK: no audited approval for stage")
  for name,expected in review["source_git_blobs"].items():
   p=R/name
   if subprocess.check_output(["git","hash-object",str(p)],text=True).strip()!=expected:
    raise RuntimeError("HARD_EXECUTION_BLOCK: source Git blob "+name)
   receipt["source_sha256"][name]=sha(p)
  prior=contract["frozen_git_blobs"]
  for name,expected in prior.items():
   p=R/name
   if not p.is_file():raise RuntimeError("HARD_EXECUTION_BLOCK: missing frozen file "+name)
   observed=subprocess.check_output(["git","hash-object",str(p)],text=True).strip()
   if observed!=expected:raise RuntimeError("HARD_EXECUTION_BLOCK: frozen blob "+name)
   receipt["previous_evidence"][name]=dict(blob=observed,sha256=sha(p))
  receipt["audited_code_matches_execution_sha"]=True
  if stage=="P0":
   report=json.loads((R/INPUTS["bf_history"]).read_text())
   if report["D"]["calculation"]!="PASS_NUMERICAL_CROSSCHECK_ONE_CASE":
    raise RuntimeError("HARD_EXECUTION_BLOCK: claimed prior numeric source differs")
   if report["E1"]["execution"]!="PASS":raise RuntimeError("HARD_EXECUTION_BLOCK: prior G3 scoring source missing")
   receipt.update(execute=True,calculation="PASS_FROZEN_PROVENANCE",hypothesis="PRIOR_SINGLE_CELL_REUSE_VERIFIED",
    scientific_claim="CLAIM_BLOCK_UNCALIBRATED_ORIGINAL_MODELS",
    previous_D_max_TV=report["D"]["largest_cross_method_TV"],
    previous_E1_G3_error_deg=report["E1"]["G3_converged_abs_heading_error_deg"])
  elif stage=="P1":
   prior=json.loads((OUT/"P0.json").read_text())
   if not prior["execute"]:raise RuntimeError("HARD_EXECUTION_BLOCK: P0 not valid")
   source=(R/INPUTS["original_g3"]).read_text()
   required=("def integrated_logfun(", "def range_update(","def model(", "def wrapped_logprior(")
   if any(key not in source for key in required):raise RuntimeError("HARD_EXECUTION_BLOCK: expected H3 APIs absent")
   if "if y*y/S>c.GATE_1D_99" not in source:raise RuntimeError("HARD_EXECUTION_BLOCK: original gate changed")
   frozen=json.loads((R/INPUTS["bf_history"]).read_text())
   receipt.update(execute=True,calculation="PASS_STATIC_API_AND_FACTORIZATION_PREREQUISITES",
      hypothesis="P1_ORIGINAL_R0_AND_TILTED_INTEGRATOR_COMPATIBLE_AT_FROZEN_CELL_ONLY",
      scientific_claim="CLAIM_BLOCK_NO_NEW_FULL_SIGNED_SENSOR_AND_DR_FAULT_MODEL",
      findings=[dict(severity="CLAIM_BLOCK",scope="B2 transfer",
           reason="Office TX0 observed CIR and original H3 two-port ratio S/Range have not been source-parity mapped; do not substitute B2 as original H3 likelihood."),
           dict(severity="CLAIM_BLOCK",scope="G2/G3",
           reason="Exact G2 and G3 algebra reused from previous toy identity; new full 3state posterior not implemented.")])
  elif stage=="P2":
   prior=json.loads((OUT/"P1.json").read_text())
   if not prior["execute"]:raise RuntimeError("HARD_EXECUTION_BLOCK: P1 failed")
   csvp=R/INPUTS["original_stage4_partial"]
   with csvp.open(newline="",encoding="utf-8-sig") as f:
    rows=[r for r in csv.DictReader(f)
     if r["case"]=="R2_aA_m0" and r["condition"]=="gyro_bias" and int(r["level"])==2
     and int(r["seed"])==0 and r["channel"]=="los" and r["range_model"]=="B_OLD"
     and int(r["sample"])==978]
   types={r["method"]:r for r in rows}
   if not {"G0","G1","G2H","G2X"}.issubset(types):
    raise RuntimeError("HARD_EXECUTION_BLOCK: frozen original Stage4 methods missing")
   report=json.loads((R/INPUTS["bf_history"]).read_text())
   if float(report["D"]["largest_cross_method_TV"])>.001 or report["D"]["max_relative_evidence_diff"]>.005:
    raise RuntimeError("CASE_RESULT_INVALID: previous D numeric acceptance changed")
   receipt.update(execute=True,calculation="REUSED_VERIFIED_SINGLE_CELL_ONLY",
    hypothesis="TILTED_G3_SINGLE_CELL_NUMERICAL_CONVERGENCE_SUPPORTED",
    scientific_claim="CLAIM_BLOCK_NOT_FULL_NONLINEAR_G2G3",
    frozen_single_cell=dict(original_g3_TV=report["D"]["old_GH_TV"],
     tilted_max_TV=report["D"]["largest_cross_method_TV"],
     G3_heading_error_deg=report["E1"]["G3_converged_abs_heading_error_deg"],
     G2X_heading_error_deg=report["E1"]["G2X_abs_heading_error_deg"],
     original_G2X_gate=types["G2X"]["range_gate"]),
    blockers=[dict(severity="CLAIM_BLOCK",scope="P3-P6 adoption",reason="There is no audited new physical signed RF/DR-fault 3state joint update; cannot infer C4 probability reliability or pose covariance from toy radial proofs.")])
  else:raise ValueError(stage)
 except Exception as exc:
  receipt["findings"].append(dict(severity="HARD_EXECUTION_BLOCK",reason=str(exc),affected_stage=stage))
  receipt["execute"]=False
 finally:
  write(stage+".json",receipt)
  print("P_STAGED_RESULT",stage,receipt["execute"],receipt["calculation"],receipt["scientific_claim"],flush=True)
 return 0 if receipt["execute"] else 2
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("stage",choices=["P0","P1","P2"]);args=a.parse_args()
 raise SystemExit(run(args.stage))
