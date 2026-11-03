import pathlib,json,hashlib,subprocess
root=pathlib.Path("D:/codex/MBVAR_PRR_001_20261103")
out=root/"research/MBVAR_PRR_001_20261103/A0_R3_REFIT"
src=pathlib.Path("D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2")
lock=json.loads((out/"TRAINING_LOCK.json").read_text())
bad=[]
for path,h in lock["source_hash"].items():
 data=(src/path).read_bytes()
 sha=hashlib.sha256(data).hexdigest()
 oid=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
 target=subprocess.check_output(["git","-C",str(root),"rev-parse",lock["source"]+":"+path]).decode().strip()
 if sha!=h or oid!=target:bad.append(path)
print(json.dumps(dict(source_items=len(lock["source_hash"]),mismatches=bad,training_lock_sha256=hashlib.sha256((out/"TRAINING_LOCK.json").read_bytes()).hexdigest(),amendment_sha256=hashlib.sha256((out/"AMENDMENT.md").read_bytes()).hexdigest()),indent=2))
