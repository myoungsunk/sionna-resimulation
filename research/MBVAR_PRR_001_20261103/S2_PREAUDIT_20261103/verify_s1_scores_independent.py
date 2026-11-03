"""Independent S1 published-score audit (standard library only).
Not an independent raw-trace/Gaussian-update replay.
Does not import implementation score/summary/update helpers or run S2.
"""
import csv,hashlib,json,os,re,statistics,sys
from collections import Counter
from pathlib import Path

R=Path(__file__).resolve().parents[3]
ROOT=R/"research/MBVAR_PRR_001_20261103/S1"
SRC=ROOT/"runs/EVAL_001"
AUD=ROOT/"audit"

def readcsv(path):
    with open(path,newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ensure(v,msg):
    if not v:raise AssertionError(msg)
def median(v):return statistics.median(v)
def quantile90(v):
    v=sorted(v); pos=.9*(len(v)-1);lo=int(pos);frac=pos-lo
    return v[lo]*(1-frac)+v[min(lo+1,len(v)-1)]*frac

scores=readcsv(SRC/"SCORES_PER_SEED.csv")
paired=readcsv(SRC/"PAIRED_SUMMARY.csv")
idx=json.loads((SRC/"TRACE_INDEX.json").read_text())
run=json.loads((SRC/"RUN_MANIFEST.json").read_text())
grant=json.loads((AUD/"GO_S1_LOCKED_EVAL.json").read_text())
r1=(AUD/"R1_S1_INDEPENDENT.md").read_text()
ensure(len(scores)==1600 and len(paired)==320 and len(idx)==320 and run["n"]==320,"table/trace count")
ensure(not (SRC/"FAILURES.jsonl").read_text().strip(),"failure log nonempty")
ensure(run["status"]=="COMPLETE" and run["phase"]=="eval" and run["token"]=="GO_S1_LOCKED_EVAL","phase")
ensure(run["code_commit"]==grant["code_commit"]=="c4f7394842a808b59f3e14f3c5eb985250c0c5cd","frozen code SHA")
ensure(run["contract_sha256"]==grant["contract_sha256"],"locked contract SHA")
ensure(run["input_sha256"]==grant["materialized_sha256"],"locked input SHA")
ensure("S2" in r1 and "HOLD" in r1 and "NO-GO" in r1,"S1 auditor conclusion")
keys=[(s["route"],s["bias"],s["channel"],int(s["seed"]),s["arm"],s["window"]) for s in scores]
ensure(len(set(keys))==len(keys),"duplicate score key")
expect={(r,b,c,k,a,w)
        for r in ("R4","R5") for b in ("B0","L2") for c in ("Full","Native_LoS")
        for k in range(10,30) for a in ("W0","W-d0-DS")
        for w in ("all","initial","primary","near","late")}
ensure(set(keys)==expect,"missing/wrong/future score keys")
indexes={(v["route"],v["bias"],v["channel"],v["seed"],v["arm"]):v for v in idx}
ensure(len(indexes)==320,"duplicate trace index key")
assert all(re.fullmatch(r"[0-9a-f]{64}",v["sha256"]) for v in idx)
assert all(int(v["n"])==(742 if v["route"]=="R4" else 1415) for v in idx)
assert all(Path(v["file"]).name==v["file"] for v in idx)
# GitHub repo publishes LFS pointers for binary traces. Verify metadata ONLY,
# never confuse pointer matching with verification of the original NPZ bytes.
lfs_checked=0
for x in idx:
    f=SRC/x["file"]
    ensure(f.is_file(),"trace pointer missing "+x["file"])
    data=f.read_text(encoding="utf-8")
    if data.startswith("version https://git-lfs.github.com/spec/v1\n"):
        ensure("oid sha256:"+x["sha256"] in data,"LFS pointer oid mismatch")
        lfs_checked+=1
    else:
        # If LFS materializes the payload, content hash can be checked independently.
        ensure(sha(f)==x["sha256"],"raw trace hash mismatch")
ensure(lfs_checked in (0,320),"partial LFS pointer set")
lookup={k:s for k,s in zip(keys,scores)}
lookup_pair={(x["route"],x["bias"],x["channel"],x["window"],x["arm"],x["metric"]):x for x in paired}
fail=[]
cells=[]
for route in ("R4","R5"):
    for bias in ("B0","L2"):
        pairs=[(
           lookup[(route,bias,"Full",seed,"W0","primary")],
           lookup[(route,bias,"Full",seed,"W-d0-DS","primary")])
           for seed in range(10,30)]
        ratios=[float(b["heading_rmse_deg"])/float(a["heading_rmse_deg"]) for a,b in pairs]
        deltas=[float(b["heading_rmse_deg"])-float(a["heading_rmse_deg"]) for a,b in pairs]
        m=median(ratios);p90=quantile90(ratios)
        xyr=median([float(b["xy_rmse_m"])/float(a["xy_rmse_m"]) for a,b in pairs])
        cover=median([float(b["heading_coverage95"]) for a,b in pairs])
        key=(route,bias,"Full","primary","W-d0-DS","heading_rmse_deg")
        published=lookup_pair[key]
        ensure(abs(m-float(published["ratio_median"]))<1e-12,"ratio summary mismatch "+str(key))
        ensure(abs(median(deltas)-float(published["paired_delta_median"]))<1e-12,"paired delta mismatch "+str(key))
        ensure(abs(p90-float(published["ratio_p90"]))<1e-12,"p90 mismatch "+str(key))
        thr=.90 if route=="R4" else 1.05
        verdict="PASS" if m<=thr else "FAIL"
        ensure(verdict=="FAIL","S1 SCIENCE unexpectedly changed, requires new independent review")
        cells.append(dict(route=route,bias=bias,n_seeds=20,primary_heading_ratio=m,
                          primary_heading_ratio_p90=p90,xy_ratio=xyr,median_heading95=cover,
                          improved_seed_count=sum(r<1. for r in ratios),
                          predeclared_threshold=thr,science_verdict=verdict))
        fail.append(verdict)
# Explicit science limitation: R1's raw-trace review was performed by
# a previous independent runner. This audit does NOT repeat the 345,120 updates.
receipt=dict(status="S1_PUBLISHED_SCORES_INDEPENDENTLY_RECOMPUTED",
             adoption="NO_GO",S2_current_authorization="HOLD_PENDING_SEPARATE_APPROVAL",
             audit_scope="independent score CSV arithmetic, manifest/Grant/trace-index and LFS pointer metadata",
             raw_trace_independently_replayed=False,
             trace_payloads_verified_not_just_pointers=(lfs_checked==0),
             lfs_pointer_count=lfs_checked,
             score_rows=len(scores),paired_rows=len(paired),indexed_traces=len(idx),
             scientific_fail_cells=len(fail),
             cells=cells,
             source_sha256={n:sha(SRC/n) for n in ["SCORES_PER_SEED.csv","PAIRED_SUMMARY.csv","RUN_MANIFEST.json","TRACE_INDEX.json"]},
             workflow_sha=os.environ.get("GITHUB_SHA","local"),
             independent_of_production_scoring_helper=True)
out=Path(os.environ.get("AUDIT_OUT","/tmp/mbvar_s1_independent_score_audit.json"))
out.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n")
print(json.dumps(receipt,indent=2,ensure_ascii=False))
