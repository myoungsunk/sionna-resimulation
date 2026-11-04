"""Read-only C2 committed-binding audit; hashes and Git/LFS metadata only."""
import hashlib,io,json,re,subprocess,sys
from pathlib import Path
R=Path("D:/codex/MBVAR_PRR_001_20261103")
P="research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001"
C=R/P
COMMIT="9eb2dc4b4c4beac62a9324d5808984eb5a3291dd"
BRANCH="refs/heads/proposal/mbvar-physical-causality-preflight-20261104"
EXTRA="research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/CURRENT_EXECUTION_STATUS_KO.md"
def git(*a): return subprocess.check_output(["git","-C",str(R),*a])
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for x in iter(lambda:f.read(1048576),b""): h.update(x)
    return h.hexdigest()
def load(p): return json.loads(p.read_bytes())
assert git("rev-parse","--show-toplevel").decode().strip().replace("\\","/")==str(R)
url=git("remote","get-url","origin").decode().strip()
assert url=="https://github.com/myoungsunk/sionna-resimulation.git"
remote=git("ls-remote","origin",BRANCH).decode().split()
assert remote==[COMMIT,BRANCH]
raw=load(C/"RAW_PUBLICATION_RECEIPT.json")
for old in ("c0b82a54f04e02b9fb6bcac163885c0ffd16326c","f8d093953812e2d88b443d91cfda778fb05e549e","6a414a4b910156647a5d64f09397554335db5f84",raw["commit"]):
    assert subprocess.run(["git","-C",str(R),"merge-base","--is-ancestor",old,COMMIT],capture_output=True).returncode==0,old
changes=git("diff","--name-only","c0b82a54f04e02b9fb6bcac163885c0ffd16326c",COMMIT).decode().splitlines()
assert all(p.startswith(P+"/") or p==EXTRA for p in changes)
final_changes=git("diff-tree","--no-commit-id","--name-only","-r",COMMIT).decode().splitlines()
assert len(final_changes)==12 and all(p.startswith(P+"/") for p in final_changes)
tree=git("ls-tree","-r","-z",COMMIT,"--",P).split(b"\0")
entries={}
for record in tree:
    if not record: continue
    head,path=record.split(b"\t",1); mode,kind,oid=head.split()
    assert kind==b"blob"
    entries[path.decode()]=(oid.decode(),mode.decode())
assert entries
batch=subprocess.run(["git","-C",str(R),"cat-file","--batch"],input=("\n".join(x[0] for x in entries.values())+"\n").encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
stream=io.BytesIO(batch.stdout)
payload={}; blobs={}; lfs=0; ordinary=0; payload_bytes=0
for path,(oid,mode) in entries.items():
    h=stream.readline().split(); assert h[0].decode()==oid and h[1]==b"blob"
    data=stream.read(int(h[2])); assert stream.read(1)==b"\n"
    local=R/path; assert local.is_file(),path
    blobs[path]=data
    pointer=re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n",data)
    if pointer:
        digest=pointer[1].decode(); size=int(pointer[2])
        assert local.stat().st_size==size,(path,"LFS size")
        assert sha(local)==digest,(path,"LFS sha")
        payload[path]=digest; lfs+=1; payload_bytes+=size
    else:
        actual=local.read_bytes()
        assert actual==data,(path,"Git bytes")
        payload[path]=hashlib.sha256(actual).hexdigest(); ordinary+=1
assert stream.read()==b""
receipt=load(C/"audit/C2_RESULT_AUDIT_RESULT.json")
assert sha(C/"audit/C2_RESULT_AUDIT_RESULT.json")=="b75b64a3c6293cdf36e88a2d90ff5639a9c739aceddcd594a9aea1766af78167"
assert receipt["decision"]=="ACCEPT"
dev=load(C/"audit/C2_DEV_RESULT_AUDIT_RESULT.json")
assert sha(C/"audit/C2_DEV_RESULT_AUDIT_RESULT.json")==receipt["accepted_DEV_audit_sha256"]=="ea4af6f8aa2cd79928bf4a94aaea7d72a24d6c1d17dc2a84ee7d6c41978c0f6c"
for auditfile,packetfile in (("C2_RESULT_AUDIT_RESULT.json","C2_RESULT_AUDIT_RECEIPT_BYTES_RESULT.json"),("C2_DEV_RESULT_AUDIT_RESULT.json","C2_DEV_RECEIPT_BYTES_RESULT.json")):
    actual=(C/"audit"/auditfile).read_bytes()
    assert b"\r" not in actual
    packet=load(C/"audit"/packetfile)
    assert any(isinstance(s,str) and s.encode("utf8")==actual for s in packet.values())
    assert packet["sha256"]==hashlib.sha256(actual).hexdigest()
for f,digest in receipt["phase_artifact_and_report_sha256"].items():
    assert payload[P+"/"+f]==digest,(f,"audited report/index")
indexed=0; phase_counts={}
for phase in ("DEV_001","REMAINING_001"):
    index=load(C/phase/"ARTIFACT_HASHES.json")
    assert payload[P+"/"+phase+"/ARTIFACT_HASHES.json"]==receipt["phase_artifact_and_report_sha256"][phase+"/ARTIFACT_HASHES.json"]
    for f,digest in index.items():
        assert payload[P+"/"+phase+"/"+f]==digest,(phase,f,"audited artifact")
        indexed+=1
    phase_counts[phase]=len(index)
    prov=receipt["phase_provenance"][phase]
    for f,digest in (("MANIFEST.json",prov["manifest_sha256"]),):
        assert payload[P+"/"+phase+"/"+f]==digest
    runname="RUN_RESULT_DEV.json" if phase=="DEV_001" else "RUN_RESULT_REMAINING.json"
    goname="GO_DEV.json" if phase=="DEV_001" else "GO_REMAINING.json"
    assert payload[P+"/"+runname]==prov["run_result_sha256"]
    assert payload[P+"/"+goname]==prov["GO_sha256"]
    go=load(C/goname)
    assert go["schema"]=="C2_GO_V1" and go["decision"]=="GO"
    assert go["bindings_sha256"]==receipt["bindings_sha256"]
assert load(C/"GO_REMAINING.json")["prerequisite_sha256"]==receipt["accepted_DEV_audit_sha256"]
bound=receipt["bindings_sha256"]; assert len(bound)==12
for f,digest in bound.items():
    local=(C/f).resolve()
    rel=local.relative_to(R).as_posix()
    if rel not in blobs:
        data=git("show",COMMIT+":"+rel)
        assert data==local.read_bytes() and hashlib.sha256(data).hexdigest()==digest
    else: assert payload[rel]==digest
verifiers={"DEV":("INDEPENDENT_DEV_VERIFIER.py","C2_DEV_VERIFIER_SOURCE_RESULT.json"),"REMAINING":("INDEPENDENT_REMAINING_VERIFIER.py","C2_REMAINING_VERIFIER_SOURCE_RESULT.json"),"REPORT":("INDEPENDENT_REPORT_VERIFIER.py","C2_REPORT_VERIFIER_SOURCE_RESULT.json")}
for key,(script,packetfile) in verifiers.items():
    actual=(C/"audit"/script).read_bytes()
    digest=receipt["independent_verifier_sha256"][key]
    assert hashlib.sha256(actual).hexdigest()==digest and b"\r" not in actual
    packet=load(C/"audit"/packetfile)
    assert packet["source"].encode("utf8")==actual and packet["sha256"]==digest
report_result=load(C/"audit/C2_REPORT_INDEPENDENT_RESULT.json")
assert report_result["decision"]=="ACCEPT" and report_result["phase_artifact_and_report_sha256"]==receipt["phase_artifact_and_report_sha256"]
numeric=load(C/"audit/C2_REMAINING_INDEPENDENT_RESULT.json")
assert numeric["decision"]=="ACCEPT" and numeric["artifact_hashes_sha256"]==receipt["phase_artifact_and_report_sha256"]["REMAINING_001/ARTIFACT_HASHES.json"]
for name,expected in (("DEV_001",dev),("REMAINING_001",numeric)):
    assert load(C/name/"MANIFEST.json")["bindings_sha256"]==bound
stage=load(C/"STAGE_COMPLETION.json")
assert stage["status"]=="RESULT_AND_REPORT_AUDIT_ACCEPT_PUBLICATION_PENDING"
assert stage["counts"]==receipt["counts"] and stage["result_audit_sha256"]==sha(C/"audit/C2_RESULT_AUDIT_RESULT.json")
assert stage["C3_runs"]==0 and stage["existing_14_poses_and_C0B_reruns"]==0
assert stage["adoption"]=="NO_GO" and stage["real_time"]=="HOLD"
audit=(C/"audit/RESULT_AUDIT_KO.md").read_text(encoding="utf8")
assert "ACCEPT" in audit and "전수 h/H 재평가라고 부르지 않는다" in audit
assert "NO-GO" in audit and "HOLD" in audit and "C3 승인이 아니다" in audit
assert receipt["publication_status"]=="Separate prospective committed-binding audit; not asserted here"
# This root status is an older timestamped progress note, scheduled for final update.
assert git("show",COMMIT+":"+EXTRA)==(R/EXTRA).read_bytes()
raw_changes=git("diff-tree","--no-commit-id","--name-only","-r",raw["commit"]).decode().splitlines()
assert len(raw_changes)==raw["paths"]==968
assert all(p.startswith(P+"/") for p in raw_changes)
raw_lfs=sum(bool(re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n",blobs[p])) for p in raw_changes)
assert raw_lfs==raw["LFS_objects"]==950
manager=raw["manager"]["processes"]; assert len(manager)==1
m=manager[0]
assert m["state"]=="exited" and m["exit_code"]==0 and m["termination"]=="natural" and m["ref_count"]==0
assert all(o["ownership"]=="released" for o in m["owners"])
assert m["actual_process"]["state"]==m["actual_supervisor"]["state"]==m["job"]["state"]=="absent"
logs=Path(m["log_dir"])
out=(logs/"stdout.log").read_text(encoding="utf8")
err=(logs/"stderr.log").read_text(encoding="utf8")
assert raw["commit"]+" files 968 lfs 950" in out
assert "To "+url in err and BRANCH.removeprefix("refs/heads/") in err
assert "error:" not in err.lower() and "fatal:" not in err.lower()
result={"decision":"ACCEPT","scope":"C2_COMMITTED_BINDINGS_AND_PUBLICATION","commit":COMMIT,"remote":url,"branch":BRANCH,"remote_head_verified":True,"raw_publication_commit":raw["commit"],"counts":{"phase_paths":len(entries),"regular_Git_blobs":ordinary,"LFS_pointers_and_local_payloads":lfs,"LFS_payload_bytes":payload_bytes,"indexed_scientific_artifacts":indexed,"phase_index_entries":phase_counts,"GO_bindings":len(bound),"independent_verifier_sources":3,"canonical_result_receipts":2,"final_commit_paths":len(final_changes),"raw_publication_paths":len(raw_changes),"raw_publication_LFS_objects":raw_lfs},"result_audit_sha256":sha(C/"audit/C2_RESULT_AUDIT_RESULT.json"),"phase_artifact_and_report_sha256":receipt["phase_artifact_and_report_sha256"],"stage_completion_sha256":sha(C/"STAGE_COMPLETION.json"),"result_audit_report_sha256":sha(C/"audit/RESULT_AUDIT_KO.md"),"raw_publication_receipt_sha256":sha(C/"RAW_PUBLICATION_RECEIPT.json"),"findings":["All committed phase files match local bytes; every LFS pointer oid and size matches the independently audited local payload","All indexed scientific artifacts,12GO bindings,3exactLF verifiers,canonicalDEV/final receipts and reports are connected","Only C2 additions and the timestamped global progress-status document changed since the code-GO revision; earlier scientific stages unchanged","Stage status correctly separates result/report ACCEPT from publication pending"],"publication_limit":"Remote LFS payloads were not downloaded again; evidence is committed pointer oid/size, actual verified local payload hashes, published remote branch ancestry and successful managed upload/push receipt","scientific_reexecution":0,"model_initializations":0,"new_GO":False,"C3_GO":False,"adoption":"NO_GO","real_time":"HOLD","mandatory_corrections":[]}
print("C2_PUBLICATION_AUDIT_RESULT "+json.dumps(result,sort_keys=True))
