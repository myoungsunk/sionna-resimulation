#!/usr/bin/env python3
"""Inspect newly regenerated legacy R4/R5 M45 H source and timeline index.
Mapping gate only, NOT same-clock EKF validity.
"""
import pathlib,sys,json,csv,re
import numpy as np
root=pathlib.Path(sys.argv[1]);o=pathlib.Path(sys.argv[2]);o.mkdir(parents=True,exist_ok=True);c=sys.argv[3]
source=list(root.rglob("SOURCE_RELEASE_SUBSET_RECEIPT.json"));assert len(source)==1,source
s=json.loads(source[0].read_text())
pats=["H_FULL.npy","H_DIRECT_LOS.npy","H_ANALYTIC_DIRECT.npy","RADIO_POSE.csv","BATCH_POSES","POSE_MAPPING","MAPPING","T10","TIMELINE"]
files=list(root.rglob("*"));matched=[]
for p in files:
 if not p.is_file():continue
 nm=p.name.upper()
 if not any(q.upper() in nm for q in pats):continue
 row={"file":str(p.relative_to(root)),"bytes":p.stat().st_size}
 if p.suffix==".npy":
  try:
   a=np.load(p,mmap_mode="r",allow_pickle=False);row.update(shape=list(a.shape),dtype=str(a.dtype))
  except Exception as e:row["error"]=repr(e)
 elif p.suffix==".csv":
  try:
   with p.open(newline="") as f:
    r=csv.reader(f);row.update(cols=next(r,[])[:50],row0=next(r,[])[:25])
  except Exception as e:row["error"]=repr(e)
 matched.append(row)
rec={"route":c,"archive_concat_sha256":s["archive_concat_sha256"],"members_scanned":s["members_scanned"],"kept_files":len(s["kept"]),"matching_files":matched,"science_result":"T10_FIRST_VISIT_SOURCE_ONLY_NOT_YET_TIMELINE_CERTIFIED"}
(o/f"{c}_REG_M45_MAPPING_AUDIT.json").write_text(json.dumps(rec,indent=2,ensure_ascii=False))
print("REGEN",c,"files",len(matched),"sample",json.dumps(matched[:15])[:5700])
