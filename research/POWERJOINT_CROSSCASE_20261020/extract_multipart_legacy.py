#!/usr/bin/env python3
"""Stream immutable R4/R5 multipart release .tar.gz without extra 5GB reassembled copy.
Extract only per-case 257-freq Full/LoS complex H, Pose, firstpath, QA and timeline metadata.
NO new electromagnetic calculation, no time-alignment/Heading PASS.
"""
import sys,io,pathlib,tarfile,json,hashlib,re
source=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);case=sys.argv[3]
out.mkdir(parents=True,exist_ok=True)
parts=sorted(source.glob(f"{case}.tar.gz.part*"));assert len(parts)>=2,[str(x) for x in parts]
class Stream:
 def __init__(self,ps):self.ps=iter(ps);self.fd=None;self.hash=hashlib.sha256();self.size=0
 def read(self,n=-1):
  if n<0:n=8*1024*1024
  arr=bytearray()
  while len(arr)<n:
   if self.fd is None:
    try:self.fd=next(self.ps).open("rb")
    except StopIteration:break
   v=self.fd.read(n-len(arr))
   if not v:self.fd.close();self.fd=None;continue
   arr+=v
  self.hash.update(arr);self.size+=len(arr)
  return bytes(arr)
 def close(self):
  if self.fd:self.fd.close()
stream=Stream(parts);kept=[];members=0;used=0
with tarfile.open(fileobj=stream,mode="r|gz") as archive:
 for m in archive:
  members+=1
  if not m.isfile():continue
  base=pathlib.PurePosixPath(m.name).name.lower()
  interesting=(base in {"h_full.npy","h_direct_los.npy","h_analytic_direct.npy","radio_pose.csv","first_path.csv","route_pose.csv","scene_metadata.json","run_manifest.json","qa_receipt.json","pose_mapping.csv","fp_summary.csv","full_plan.json","source_manifest.json"} or
              re.search(r"(catalog|mapping|timeline|manifest|receipt|t10|pose_ids)",base) and base.endswith((".json",".csv",".txt")))
  if not interesting or m.size>70_000_000 or used+m.size>420_000_000:continue
  fd=archive.extractfile(m)
  if fd is None:continue
  b=fd.read()
  dst=(out/"data"/m.name).resolve();assert dst.is_relative_to(out.resolve()) and '..' not in pathlib.PurePosixPath(m.name).parts
  dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b);used+=len(b)
  kept.append({"name":m.name,"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()})
report={"case":case,"multipart_source":[{"name":x.name,"size":x.stat().st_size} for x in parts],"archive_concat_bytes_seen":stream.size,"archive_concat_sha256":stream.hash.hexdigest(),"members_scanned":members,"kept":kept,"bytes_kept":used,"status":"EXTRACTED_FOR_SCIENCE_REVIEW_NOT_YET_PARITY_CHECKED"}
(out/"SOURCE_RELEASE_SUBSET_RECEIPT.json").write_text(json.dumps(report,indent=2)+"\n")
print("LEGACY_STREAM_DONE",case,"members",members,"kept",len(kept),"bytes",used,flush=True)
