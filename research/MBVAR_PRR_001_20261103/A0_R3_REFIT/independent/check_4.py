import pathlib,hashlib,json,numpy as np
r=pathlib.Path("D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103")
p=r/"A0_R3_REFIT";cache=pathlib.Path("D:/codex/MBVAR_PRR_001_20261103_inputs")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
c=json.loads((p/"CONTRACT_LOCK.json").read_bytes());lock=json.loads((p/"INPUT_LOCK.json").read_bytes());receipt=json.loads((p/"LOCK_RECEIPT.json").read_bytes())
bad=[]
for name,h in receipt.items():
 if sha(p/name)!=h:bad.append(name)
for name,h in lock["component_hashes"].items():
 if sha(r/name)!=h:bad.append(name)
for name,h in c["decision_rules"]["document_hashes"].items():
 if sha(r/name)!=h:bad.append(name)
refs=json.loads((p/"F64_REFERENCE.json").read_bytes())
traces=[]
for key,v in refs.items():
 path=cache/"F64_R3_REFERENCE"/(key+".npz")
 with np.load(path,allow_pickle=False) as z:
  traces.append(dict(key=key,n=len(z["pose_id"]),unique_ids=len(np.unique(z["pose_id"])),bytes_match=sha(path)==v["trace_sha256"],dtypes={k:str(z[k].dtype) for k in z.files},nonfinite={k:int((~np.isfinite(z[k])).sum()) for k in z.files if z[k].dtype.kind in "fc"}))
print(json.dumps(dict(hash_mismatches=bad,receipt=receipt,traces=traces),indent=2))
