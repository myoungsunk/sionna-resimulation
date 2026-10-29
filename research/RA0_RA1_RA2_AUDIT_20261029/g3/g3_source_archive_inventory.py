#!/usr/bin/env python3
"""Manifest-only verification of both original 2026-10-07 Snowball bundles.
No extraction or input mutation. Covers initial and final archives, distinguishes
ray payload *_trace.npz from path receipts *_trace_receipt.json."""
import argparse,datetime,hashlib,json,tarfile
from pathlib import Path
def sha(f):
 h=hashlib.sha256()
 with f.open("rb") as a:
  for b in iter(lambda:a.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument("--out",type=Path,required=True);p.add_argument("archives",nargs="+")
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 r=[]
 for pathname in a.archives:
  f=Path(pathname)
  with tarfile.open(f,"r:gz") as z:
   fs=[m for m in z.getmembers() if m.isfile()]
   trace=[m for m in fs if m.name.endswith("_trace.npz")]
   rec=[m for m in fs if m.name.endswith("_trace_receipt.json")]
   derived=[m for m in fs if m.name.endswith("_trace.npz") and ("/S2/" in m.name or "traces_" in m.name)]
   r.append(dict(archive=str(f),sha256=sha(f),size_bytes=f.stat().st_size,
     total_files=len(fs),raw_trace_files=len(trace),path_trace_receipts=len(rec),G3_relevant_raw_traces=len(derived),
     raw_examples=[m.name for m in trace[:8]],receipts_examples=[m.name for m in rec[:8]]))
 out=dict(status="SOURCE_ARCHIVE_INDEXED",timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
  source_provenance="Original git-backed archives examined without extraction",
  archives=r,all_original_raw_in_archives=sum(x["G3_relevant_raw_traces"] for x in r),
  finding="Other ray data may still exist on source Snowball volume, not included in these archives.",
  self_review_only=True)
 (a.out/"G3_ARCHIVE_INVENTORY.json").write_text(json.dumps(out,indent=2))
 print(json.dumps({"status":out["status"],"inventory":[{"p":x["archive"],"raw":x["raw_trace_files"],"receipts":x["path_trace_receipts"]} for x in r]}))
if __name__=="__main__":main()
