import json,tarfile,sys
from pathlib import Path
from orchestrate import ledger,safe_extract,sha,dump
work=Path(sys.argv[1]);downloads=Path(sys.argv[2])
inventory=json.loads((work/"inventory.json").read_text());seen={}
canary_status=[]
for i in ["canary",0,1,2,3]:
 archive=downloads/f"shard_{i}.tar.gz"
 if not archive.exists():continue
 checksum=json.loads(Path(str(archive)+".sha256.json").read_text())
 assert sha(archive)==checksum["sha256"]
 safe_extract(archive,downloads/"verified")
 directory=downloads/"verified"/f"output_{i}"
 for name,h in json.loads((directory/"OUTPUT_SHA256.json").read_text()).items():
  assert sha(directory/name)==h
 statuses=json.loads((directory/"STATUS.json").read_text())
 assert len(statuses)==(4 if i=="canary" else 77)
 expected={r["task_id"] for r in json.loads((work/f"shard_{i}.json").read_text())}
 assert len({r["task_id"] for r in statuses})==len(statuses)
 assert {r["task_id"] for r in statuses}==expected
 for row in statuses:
  if row["status"]=="PASS_TECHNICAL":
   assert row["calls"]==257
   folders=list((directory/row["task_id"]).glob("*/bins"))
   assert len(folders)==1
   assert {x.name for x in folders[0].glob("*.npz")}=={f"{j:03d}.npz" for j in range(257)}
   assert (folders[0].parent/"RAW_H.npz").is_file()
   assert (folders[0].parent/"FIRST_PATH.npz").is_file()
 if i=="canary":
  canary_status=statuses
  continue
 for row in statuses:
  assert row["task_id"] not in seen
  seen[row["task_id"]]=row
assert set(seen).issubset(set(inventory["pending"]))
allkeys=[]
for row in ledger():
 task=row["task_id"]
 if task in seen:result=seen[task]
 elif task in inventory["pending"]:
  result=dict(task_id=task,status="NOT_RUN_OR_INTERRUPTED",calls=None)
 else:
  assert task in inventory["reused"]
  result=dict(task_id=task,status="SKIP_VALIDATED",calls=0,raw=inventory["reused"][task])
 allkeys.append(result)
assert len(allkeys)==400
complete=len(canary_status)==4 and all(r["status"]=="PASS_TECHNICAL" and r["calls"]==257 for r in canary_status) and all(r["status"] in ("PASS_TECHNICAL","SKIP_VALIDATED") for r in allkeys)
if complete:assert sum(r["calls"] for r in allkeys)==79156
dump(downloads/"ALL_KEYS.json",allkeys)
dump(downloads/"CANARY_STATUS.json",canary_status)
dump(downloads/"FINAL_QA.json",dict(status="PASS_TECHNICAL_SELF_CHECK" if complete else "INCOMPLETE",registered=400,new=308,reused=92,recorded_calls=sum(r["calls"] or 0 for r in allkeys+canary_status),missing_call_counts=any(r["calls"] is None for r in allkeys)))
handoff=downloads/"handoff.tar.gz"
with tarfile.open(handoff,"w:gz") as out:
 for name in ["ALL_KEYS.json","FINAL_QA.json","CANARY_STATUS.json"]:
  out.add(downloads/name,arcname=name)
 for i in ["canary",0,1,2,3]:
  for suffix in [".tar.gz",".tar.gz.sha256.json"]:
   name=f"shard_{i}"+suffix
   if (downloads/name).exists():out.add(downloads/name,arcname="new/"+name)
 for group in ["B0","B1","SM1a","G3"]:
  out.add(work/(group+".tar.gz"),arcname="reused/"+group+".tar.gz")
 out.add(work/"inputs.tar.gz",arcname="inputs.tar.gz")
dump(downloads/"HANDOFF_SHA256.json",dict(sha256=sha(handoff),bytes=handoff.stat().st_size))
