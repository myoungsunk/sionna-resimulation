"""Independent C2 report-only verifier: no model initialization or production math.
Run after the accepted immutable numerical audit. Decimal output is compared at
the precision printed in each table; numeric CSV keeps frozen 1e-10 atol/rtol.
"""
import csv, hashlib, io, json, math, re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
C = Path("D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001")
LOG = Path("C:/Users/Myoungsun Kim/.codex/managed-processes/runs/2a377317-6c46-460f-8a2d-eb7df5bd13e7")
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_bytes())
lines=(LOG/"stdout.log").read_text(encoding="utf8").splitlines()
num=[json.loads(s.split(" ",1)[1]) for s in lines if s.startswith("C2_REMAINING_INDEPENDENT_RESULT ")]
assert len(num)==1 and num[0]["decision"]=="ACCEPT"
assert (LOG/"stderr.log").read_bytes()==b""
num=num[0]
expected_index={"DEV_001":"343e3d6e70e2bdd79989ec232a57089c47e5310d4857bce824688d1b26ded828","REMAINING_001":num["artifact_hashes_sha256"]}
rows=[]; phases={}
for phase,n in (("DEV_001",132),("REMAINING_001",2508)):
    p=C/phase
    assert sha(p/"ARTIFACT_HASHES.json")==expected_index[phase]
    index=load(p/"ARTIFACT_HASHES.json")
    assert sha(p/"TRAJECTORY_SUMMARY.json")==index["TRAJECTORY_SUMMARY.json"]
    part=load(p/"TRAJECTORY_SUMMARY.json"); assert len(part)==n
    assert load(p/"MANIFEST.json")["status"]=="NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT"
    rows.extend(part)
    phases[phase]={"manifest_sha256":sha(p/"MANIFEST.json"),"artifact_hashes_sha256":sha(p/"ARTIFACT_HASHES.json")}
keycols=("route","bias","window","mode","arm")
keys=[tuple(r[k] for k in ("route","bias","seed","window","mode","arm")) for r in rows]
assert len(keys)==len(set(keys))==2640
groups=defaultdict(list)
for r in rows: groups[tuple(r[k] for k in keycols)].append(r)
assert len(groups)==132
for g in groups.values(): assert sorted(r["seed"] for r in g)==list(range(10,30))
metadata={"seed","first_index","suffix_rows","primary_rows","start_s","end_s"}
fields=set()
for r in rows:
    for k,v in r.items():
        if k in metadata or k.startswith("first_"): continue
        if isinstance(v,(int,float)) and not isinstance(v,bool): fields.add(k)
        elif v is None and k.startswith(("primary_","delta_primary_","own_minus_fixed_","I_","FF_I_","delta_I_")) and not k.endswith(("_available","_actual_packets","_unavailable_reason")):
            fields.add(k)
expected={}
for key,g in groups.items():
    d={}
    for f in sorted(fields):
        vals=sorted(r[f] for r in g if r[f] is not None)
        assert all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in vals)
        n=len(vals); d[f+"_n"]=n
        if n:
            median=vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2
            d.update({f+"_median":median,f+"_min":vals[0],f+"_max":vals[-1]})
        else: d.update({f+"_median":None,f+"_min":None,f+"_max":None})
    expected[key]=d
reader=csv.DictReader(io.StringIO((C/"AGGREGATE_SUMMARY.csv").read_text(encoding="utf8")))
csvfields=reader.fieldnames; aggregate=list(reader)
assert len(aggregate)==132
assert set(csvfields)==set(keycols)|{"seeds"}|set(next(iter(expected.values())))
assert len(csvfields)==len(set(csvfields))
seen=set(); checks=0; empty=0; mx=0.0
for row in aggregate:
    key=tuple(row[k] for k in keycols); assert key in expected and key not in seen; seen.add(key)
    assert row["seeds"]=="20"
    for f,v in expected[key].items():
        got=row[f]; checks+=1
        if v is None:
            assert got==""; empty+=1
        elif f.endswith("_n"): assert int(got)==v and float(got)==v
        else:
            got=float(got); err=abs(got-v); mx=max(mx,err)
            assert math.isfinite(got) and err<=1e-10+1e-10*abs(v),(key,f,got,v)
assert seen==set(expected)
info=load(C/"REPORT_INPUTS.json")
assert info=={"phases":phases,"trajectories":2640,"groups":132,"seeds":list(range(10,30))}
display_checks=0; display_max=0.0
def printed(token,value):
    global display_checks,display_max
    dec=Decimal(token); unit=Decimal(10)**dec.as_tuple().exponent
    err=abs(float(dec)-value); display_max=max(display_max,err); display_checks+=1
    assert err<=float(abs(unit))/2+max(1e-18,math.ulp(value)*2),(token,value,err,unit)
report=(C/"RESULTS_KO.md").read_text(encoding="utf8")
table=[s.strip("|").split("|") for s in report.splitlines() if re.match(r"^\|R[245]\|",s)]
assert len(table)==44
seen4=set()
for r in table:
    assert len(r)==7
    key4=tuple(r[:4]); assert key4 not in seen4; seen4.add(key4)
    for j,arm in enumerate(("LF","FL","LL")):
        key=key4+(arm,)
        tokens=re.fullmatch(r"([+-]\d+\.\d+) \[([+-]\d+\.\d+), ([+-]\d+\.\d+)\]",r[4+j])
        assert tokens
        for token,stat in zip(tokens.groups(),("median","min","max")):
            printed(token,expected[key]["delta_primary_heading_deg_rmse_"+stat])
assert seen4=={k[:4] for k in expected}
interpretation=(C/"INTERPRETATION_KO.md").read_text(encoding="utf8")
it=[s.strip("|").split("|") for s in interpretation.splitlines() if re.match(r"^\|R[45] ",s)]
assert len(it)==4
metrics=("delta_primary_heading_deg_rmse","delta_primary_xy_m_rmse","delta_primary_NEES3_mean","delta_primary_NEES4_mean","delta_primary_Ppsi_rad2_mean","delta_primary_heading95_mean","delta_primary_XY95_mean")
selected=set()
for r in it:
    assert len(r)==9
    label,bias=r[:2]
    if label=="R4 hot33 편파만 FL": key=("R4",bias,"hot33","own","FL")
    elif label=="R5 hot79 양쪽 LL": key=("R5",bias,"hot79","own","LL")
    else: raise AssertionError(label)
    assert key not in selected; selected.add(key)
    for token,metric in zip(r[2:],metrics): printed(token,expected[key][metric+"_median"])
assert selected=={(route,bias,w,"own",arm) for route,w,arm in (("R4","hot33","FL"),("R5","hot79","LL")) for bias in ("B0","L2")}
# Numeric values in the two prose examples, independently keyed.
for start,window,arm,route in (("R4 hot33에서는","hot33","LF","R4"),("R2 hot525에서는","hot525","FL","R2")):
    prose=[s for s in interpretation.splitlines() if s.startswith(start)]
    assert len(prose)==1
    tokens=re.findall(r"[+-]\d+\.\d+",prose[0]); assert len(tokens)==4
    for token,key in zip(tokens,((route,bias,window,mode,arm) for mode in ("fixed","own") for bias in ("B0","L2"))):
        printed(token,expected[key]["delta_primary_heading_deg_rmse_median"])
# Confirm each limited directional claim and the retained counterexamples.
for bias in ("B0","L2"):
    d=expected[("R4",bias,"hot33","own","FL")]
    assert d["delta_primary_heading_deg_rmse_median"]<0 and d["delta_primary_xy_m_rmse_median"]>0 and d["delta_primary_XY95_mean_median"]<0
    d=expected[("R5",bias,"hot79","own","LL")]
    assert all(d[f+"_median"]>0 for f in metrics[:4])
    assert d["delta_primary_Ppsi_rad2_mean_median"]<0
    assert d["delta_primary_heading_deg_rmse_min"]<0<d["delta_primary_heading_deg_rmse_max"]
    assert d["delta_primary_xy_m_rmse_min"]<0<d["delta_primary_xy_m_rmse_max"]
# The static claim audit independently reads the prose; these are guard assertions
# preserving the explicit scope statements, not substitutes for semantic review.
for text in (report,interpretation):
    assert "NO-GO" in text and "HOLD" in text and "C3" in text
assert "독립 RF 표본이나 새 잠금 평가로 해석하지 않는다" in report
assert "Fisher 정보량이 아니다" in report and "물리 LoS 정답으로 대체 해석하지 않는다" in report
assert "실제 벽 제거의 Heading 인과효과" in interpretation and "입증하지 않는다" in interpretation
files=("DEV_001/ARTIFACT_HASHES.json","REMAINING_001/ARTIFACT_HASHES.json","RESULTS_KO.md","AGGREGATE_SUMMARY.csv","REPORT_INPUTS.json","INTERPRETATION_KO.md","report.py")
out={"decision":"ACCEPT","scope":"C2_REPORT_ONLY_ALL_132_GROUPS","counts":{"trajectory_summaries":2640,"groups":132,"seeds_per_group":20,"aggregate_columns":len(csvfields),"numeric_fields":len(fields),"aggregate_cells_checked":checks,"NA_cells":empty,"heading_table_rows":44,"interpretation_table_rows":4,"printed_numeric_cells_checked":display_checks},"max_aggregate_numeric_error":mx,"max_display_rounding_error":display_max,"display_rule":"Half a unit in the last printed decimal; CSV frozen 1e-10 atol/rtol unchanged","phase_artifact_and_report_sha256":{f:sha(C/f) for f in files},"numerical_audit_stdout_sha256":sha(LOG/"stdout.log"),"numerical_audit_stderr_sha256":sha(LOG/"stderr.log"),"production_math_calls":0,"observer_initializations":0,"scientific_reexecutions":0,"claim_review":"Conditional offline component interventions; heading/XY/covariance/NEES tradeoffs and per-seed counterexamples retained; no wall-removal, physical-LoS equivalence, RF independence, policy/adoption or C3 claim"}
print("C2_REPORT_INDEPENDENT_RESULT "+json.dumps(out,ensure_ascii=False,sort_keys=True))
