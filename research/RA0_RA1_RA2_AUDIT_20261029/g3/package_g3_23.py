#!/usr/bin/env python3
"""Package exactly 23 original G3 trace pairs. Read only, fail closed."""
from __future__ import annotations
import hashlib,json,pathlib,sys,zipfile
def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def main(root,lock):
 root=pathlib.Path(root);lock=pathlib.Path(lock)
 config=json.loads(lock.read_text()); entries=config["items"]
 if len(entries)!=23 or sum(int(x["expected_n_strict_paths"]) for x in entries)!=25:
  raise SystemExit("ERR_LOCK_NOT_23_POS_25_RAYS")
 files=[];errors=[]
 for item in entries:
  rel=pathlib.Path(item["original_relpath"])
  if not str(rel).startswith("results/S2/traces_") or not rel.name.endswith("_trace.npz"):
   errors.append("ERR_PATH "+str(rel));continue
  candidates=[root/rel,root/rel.relative_to("results/S2"),root/"S2"/rel.relative_to("results/S2")]
  p=next((x for x in candidates if x.is_file()),None)
  if p is None:errors.append("MISSING "+str(rel));continue
  q=p.with_name(p.name.replace("_trace.npz","_trace_receipt.json"))
  if not q.is_file():errors.append("MISSING_RECEIPT "+str(q));continue
  qhash=sha(q)
  if qhash!=item["expected_original_receipt_sha256"]:
   errors.append("ERR_RECEIPT_SHA "+str(q));continue
  files.append((p,str(rel),item))
  files.append((q,str(rel).replace("_trace.npz","_trace_receipt.json"),item))
 if errors:
  print(json.dumps({"status":"BLOCKED_MISSING_OR_MISMATCH","issues":errors},indent=2));raise SystemExit(2)
 out=pathlib.Path.cwd()/"G3_ORIGINAL_23_TRACE_PAIRS.zip"
 manifest=dict(status="SOURCE_ORIGINAL_CANDIDATE_NOT_YET_H_PARITY_VERIFIED",n_raw=23,n_receipts=23,
  n_ray_historic_strict=25,items=[dict(path=arc,sha256=sha(p),size=p.stat().st_size) for p,arc,_ in files],
  caution="Raw NPZ hashes were not archived in the original public manifest: provenance requires H reconstruction parity and receipt SHA crosscheck.")
 with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
  for f,arc,_ in files:z.write(f,arcname=arc)
  z.writestr("G3_REQUESTED_SOURCE_MANIFEST.json",json.dumps(manifest,indent=2))
 print(json.dumps(dict(zip=str(out),size=out.stat().st_size,sha256=sha(out),n_files=46,manifest=manifest["status"])))
if __name__=="__main__":
 if len(sys.argv)!=3:raise SystemExit("USAGE: package_g3_23.py ORIGINAL_JOB_ROOT G3_23_ORIGINAL_SOURCE_LOCK.json")
 main(*sys.argv[1:])
