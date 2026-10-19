#!/usr/bin/env python3
"""Extract inspectable route-level RF Full/LoS complex arrays and metadata
from an immutable GitHub Release .tar.gz. No sensor/EKF replay, no scientific PASS.
Run in GH Actions with a freshly-downloaded release archive.
"""
import sys, pathlib,tarfile,json,hashlib,re,csv,io,os
root=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True,exist_ok=True)
tag=sys.argv[3];manifest=[];kept=[];maxpayload=230_000_000;used=0
def sha(b):return hashlib.sha256(b).hexdigest()
with tarfile.open(root,"r:gz") as t:
 members=t.getmembers()
 for m in members:
  manifest.append({"name":m.name,"bytes":m.size,"type":m.type.decode(errors="replace") if isinstance(m.type,bytes) else str(m.type)})
 # Preserve an inspectable subset, no large raw ray catalogs by default.
 for m in members:
  if not m.isfile():continue
  base=pathlib.PurePosixPath(m.name).name
  low=m.name.lower()
  essential=(base.endswith(".json") or base.endswith(".csv") or base.endswith(".txt"))
  ch=(bool(re.search(r"(h_full|h_los|h_direct|direct_los|h_[ab]|complex_h)",low)) and low.endswith((".npy",".npz")))
  if not (essential or ch):continue
  if m.size>52_000_000:continue
  if used+m.size>maxpayload:continue
  stream=t.extractfile(m)
  if stream is None:continue
  raw=stream.read()
  target=out/"data"/m.name
  if ".." in target.parts or str(target.resolve()).startswith(str(out.resolve())) is False: raise ValueError("unsafe path")
  target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(raw);used+=len(raw)
  kept.append({"name":m.name,"bytes":len(raw),"sha256":sha(raw),"is_complex_channel_candidate":ch})
summary={"tag":tag,"archive_name":str(root.name),"archive_sha256":sha(root.read_bytes()),"members_count":len(manifest),"extracted_bytes":used,"kept_count":len(kept),"data_science_executed":False,"note":"release case source snapshot; time-series validity and H pairing still to be audited","members":manifest,"extracted":kept}
(out/"ARCHIVE_CONTENTS_AND_SHA.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print("ARCHIVE_INSPECTED",tag,len(manifest),"KEPT",len(kept),"BYTES",used,flush=True)
print("CANDIDATES",[(x["name"],x["bytes"]) for x in kept if x["is_complex_channel_candidate"]],flush=True)
