"""Read-only pre-execution audit for strict interpretation of completed R5 panel."""
import ast,argparse,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORKFLOW=ROOT/".github/workflows/ekf4-r5-panel-reconcile.yml"
PANEL_SHA="b9c1b1af65aa7ded34b331d6d775fc06721fa8e46abb3c96d3f3ec157bb57ffd"
THREE_SHA="66b74f1cc2d82a4a6acff6faf6bf27fbd414722bca29ddb187f2f5f0aa3cfde9"
def digest(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def run(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 errs=[];hashes={}
 try:
  if os.getenv("GITHUB_ACTIONS")!="true" or subprocess.check_output(
      ["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()!=os.getenv("GITHUB_SHA"):
   errs.append("RUNNING_OUTSIDE_EXACT_GITHUB_ACTIONS")
  for name in ("p4_panel_reconcile_audit.py","p4_panel_reconcile.py"):
   p=HERE/name
   ast.parse(p.read_text(),filename=name)
   hashes[str(p.relative_to(ROOT))]=digest(p)
  wf=WORKFLOW.read_text()
  if not(wf.find("p4_panel_reconcile_audit.py --out") <
         wf.find("p4_panel_reconcile.py --panel")):errs.append("AUDIT_NOT_FIRST")
  if not("actions: read" in wf and "set -euo pipefail" in wf
         and "if: always()" in wf and PANEL_SHA in wf and THREE_SHA in wf):
   errs.append("ARTIFACT_PROVENANCE_MISSING")
  hashes[str(WORKFLOW.relative_to(ROOT))]=digest(WORKFLOW)
 except Exception as e:errs.append("AUDIT_ERROR:"+repr(e))
 rec={"schema":"R5_EXPANDED_RESULTS_INTERPRETATION_AUDIT_V1",
    "source_SHA":os.getenv("GITHUB_SHA"),"sources":hashes,
    "panel_SHA256":PANEL_SHA,"three_SHA256":THREE_SHA,
    "decision":"GO" if not errs else "HOLD","fatal":errs,
    "scientific_PASS":False}
 (out/"AUDIT.json").write_text(json.dumps(rec,indent=2)+"\n")
 print("R5_RECONCILE_AUDIT "+json.dumps({"decision":rec["decision"],"fatal":errs}),flush=True)
 return 0 if not errs else 2
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--out",required=True)
 a=p.parse_args();raise SystemExit(run(a.out))
