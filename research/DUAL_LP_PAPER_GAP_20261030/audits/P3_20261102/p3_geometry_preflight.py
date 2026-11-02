#!/usr/bin/env python3
"""P3 proposer-locked anchor geometry & input preflight; no new SourceFFD H or RT.

Independent raw-byte verification, geometry, sample selection and 3x2 range
Jacobian central finite differences. One already-seen Corridor scene only.
This fresh arithmetic lives on a distinct GitHub runner, but is authored in
the same chat as proposer: never claim independent human/agent audit.
"""
from __future__ import annotations
import csv,hashlib,json,math,os,pathlib,platform,subprocess,sys,traceback,datetime,time
import numpy as np

ROOT=pathlib.Path.cwd()
P3=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P3_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
P2R=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/runs/P2_FROZEN_RANGE_ONLY_41315429738"
BANK=pathlib.Path(os.environ.get("DLP_P3_BANK_DIR","/tmp/dlp_p3_banks"))
OUT=pathlib.Path(os.environ.get("DLP_P3_PREFLIGHT_OUT","/tmp/dlp_p3_preflight"));OUT.mkdir(parents=True,exist_ok=True)
t0=time.monotonic();checks={};errors=[];stats={};pilot={}
CFG_SHA="49658dc5532e990a9f8bc0968f96b46ce236167244762cbc817092ff34ce3fc8"
SPEC_SHA="24a5e0581c86a8b99659ebbea30b456fb79b6f4e88ee31860db04df85fafb588"
TOL_SHA="11a4adcdf15e7e884b4290e55b8e997b069ce9c8897902b0c41ca47983899b72"

def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def J(p):return json.loads(pathlib.Path(p).read_text("utf-8"))
def gate(key,ok,note,measure=None):
    checks[key]={"status":"PASS" if ok else "FAIL","note":str(note)}
    if measure is not None: checks[key]["measured"]=measure
    if not ok:errors.append({"key":key,"reason":str(note),"measured":measure})
    print("P3_PREFLIGHT",key,checks[key]["status"],str(measure)[:250],flush=True)
def ensure(ok,msg):
    if not ok:raise RuntimeError(msg)
def read_timeline(path):
    with open(path,newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def sample_pilot(rows,anchors):
    n=len(rows)
    keys=[0,1,n//8,n//4,n//2,3*n//4,7*n//8,n-2,n-1]
    xy=np.array([[float(r["x"]),float(r["y"])] for r in rows])
    for xyz in anchors.values():
        i=int(np.argmin(np.sum((xy-np.array(xyz[:2]))**2,axis=1)))
        keys.append(i)
    keys.append(int(np.argmax(abs(xy[:,1]))))
    return sorted(set(keys))

def audit():
    cfg=J(P3/"P3_CONFIG_LOCK.json")
    tol=J(P3/"P3_NUMERIC_TOLERANCES.json")
    receipt=J(P3/"P3_PROPOSER_LOCK_RECEIPT_V2.json")
    ensure(cfg["phase"]=="P3_NONCOLLINEAR_THIRD_ANCHOR_GEOMETRY_AND_SOURCE_DIRECT_LOS_CANARY","P3_SCOPE_CHANGED")
    correct={"P3_CONFIG_LOCK.json":CFG_SHA,"P3_EXPERIMENT_CONTRACT_PROPOSER_LOCKED.md":SPEC_SHA,
             "P3_NUMERIC_TOLERANCES.json":TOL_SHA}
    mismatch=[name for name,d in correct.items() if sha(P3/name)!=d]
    ensure(receipt["sha256_self_test_abc"]=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","BAD_SELFTEST_RECEIPT")
    ensure(len(receipt["files"])==3 and all(x["sha256"]==correct[x["name"]] for x in receipt["files"]),"BAD_P3_RECEIPT_V2")
    gate("A00_LOCK",not mismatch and len(tol["tests"])==13,"P3 proposer V2 SHA and 13 thresholds fixed before source pilot",{"mismatch":mismatch})
    ensure(not mismatch,"P3_LOCK_INVALID")
    qa=J(P2R/"P2_POSTRUN_QA.json");rec=J(P2R/"P2_RECOVERY_RECEIPT.json")
    expected=cfg["source_p2"]
    p2zip=P2R/"P2_ALL_28_TRACES_IMMUTABLE.zip"
    ok=(qa["status"]=="PASS" and qa["score_rows"]==84 and not qa["failures"] and
        rec["trace_npz_count"]==28 and rec["original_scorer_status"]=="PASS" and
        rec["archive_sha256"]==expected["original_28_traces_archive_sha256"] and
        p2zip.exists() and sha(p2zip)==rec["archive_sha256"])
    gate("A01_PARENT_P2",ok,"P2 recovered SHA-pinned original 28 NPZ and 84 stats, one scene",{"zip_sha":sha(p2zip) if p2zip.exists() else None})
    ensure(ok,"P2_NOT_VERIFIED")
    inp=J(P1/"P1_INPUT_LOCK.json")
    failed=[]
    for a in inp["base_assets"]:
        path=ROOT/a["path"]
        if not path.is_file() or sha(path)!=a["sha256"] or path.stat().st_size!=a["bytes"]:
            failed.append(a["path"])
    gate("A02_C0_INPUTS",len(inp["base_assets"])==39 and not failed,
         "39 original C0 asset actual bytes SHA match, no substitution",{"failed":failed[:4],"asset_count":len(inp["base_assets"])})
    ensure(not failed,"P3_C0_HASH_INVALID")
    p0=J(ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json")
    original={tuple(round(float(t),5) for t in c["anchor"]) for c in p0["cases"]}
    anchors={"A":cfg["scene"]["existing_anchors"]["A"],"B":cfg["scene"]["existing_anchors"]["B"],
             "C":cfg["scene"]["proposed_third"]["xyz_m"]}
    a=np.array(anchors["A"]);b=np.array(anchors["B"]);c=np.array(anchors["C"])
    area=float(.5*abs(np.cross((b-a)[:2],(c-a)[:2])))
    room=cfg["scene"]["room_xyz_m"]
    wall_margin=float(min(c[1]-room["y"][0],room["y"][1]-c[1]))
    within=all(room[k][0]+(1e-12 if k!="z" else 0)<c[i]<room[k][1] for i,k in enumerate(("x","y","z")))
    anchors_correct=len(original)==2 and (16.,.8,2.65) not in original and all(v[1]==0 for v in original)
    triangle=area>=1 and wall_margin>=.3 and abs(c[2]-2.65)<=1e-12 and within
    gate("A03_THIRD_GEOMETRY",anchors_correct and triangle and cfg["scene"]["candidate_count"]==1,
       "C new noncollinear anchor, physically in 20x2.4x2.7 corridor",
       {"C":c.tolist(),"triangle_area_m2":area,"min_y_wall_margin_m":wall_margin,
        "locked_original_anchors":sorted(map(list,original)),"n_candidates":cfg["scene"]["candidate_count"]})
    ensure(anchors_correct and triangle,"P3_GEOMETRY_INVALID")
    banks=[]
    for ref in inp["ffd_bank_source"]["banks"]:
        got=list(BANK.rglob(ref["filename"]))
        if len(got)!=1 or sha(got[0])!=ref["sha256"] or got[0].stat().st_size!=ref["bytes"]:
            failed.append(ref["filename"])
        else:banks.append((ref,got[0]))
    gsha=subprocess.check_output(["git","hash-object","research/FFD_P0P3_20261016/source_model.py"],text=True).strip()
    bank_ok=len(banks)==2 and not failed and gsha==cfg["source_p1"]["source_model_blob"]
    gate("A04_FFD_BANKS",bank_ok,"2 original FFD NPZ real bytes and source model exact Git blob",
         {"banks":[{"name":x["filename"],"sha256":sha(p)} for x,p in banks],"source_blob":gsha})
    ensure(bank_ok,"BANK_HASH_INVALID")
    timeline_lookup={}
    for route,expected_n in (("R2",979),("R4",742),("R5",1415)):
        a=next(z for z in inp["base_assets"] if z["kind"]=="TIMELINE_TNONE" and ("timeline_"+route+"_") in z["path"])
        v=read_timeline(ROOT/a["path"])
        ensure(len(v)==expected_n,"ROUTE_TIMELINE_COUNT_DIFFER:"+route)
        ids=np.array([int(x["pose_id"]) for x in v]);ts=np.array([float(x["t_s"]) for x in v])
        ensure(len(set(ids.tolist()))==len(ids) and np.all(np.diff(ts)>0),"INVALID_TIME_KEYS:"+route)
        # Assert every original sample pose index is truly available in original
        # A-side case, never fabricate a third channel or resample space/time.
        casename=f"{route}_aA_m0"
        refcase=next(z for z in inp["primary_cases"] if z["case_id"]==casename)
        samples=J(ROOT/refcase["samples_path"])
        xyerr=0.;yawerr=0
        for x in v:
            refsample=samples[int(x["pose_id"])]
            xyerr=max(xyerr,abs(float(x["x"])-refsample["x"]),abs(float(x["y"])-refsample["y"]))
            delta=(float(x["yaw_body_deg"])-refsample["yaw_body_deg"]+180)%360-180
            yawerr=max(yawerr,abs(delta))
        ensure(xyerr<=1e-6 and yawerr<=1e-6,"TIMELINE_GT_NOT_ORIGINAL:"+route)
        timeline_lookup[route]=v
    gate("A05_3136_TIMELINE",True,"R2 R4 R5 original 3136 unique-route timeline samples, exact C0 IDs/poses")
    minsv=1e300;rank_bad=[];rank_2old=0;max_fd=0.;pilot_all=[];line_bad=[]
    for route,rows in timeline_lookup.items():
        xs=np.array([float(r["x"]) for r in rows]);ys=np.array([float(r["y"]) for r in rows])
        n=len(xs);H=np.empty((n,3,2));d3=np.empty((n,3))
        for j,point in enumerate(anchors.values()):
            ax,ay,az=point;dd=np.sqrt((xs-ax)**2+(ys-ay)**2+(.45-az)**2)
            d3[:,j]=dd;H[:,j,0]=(xs-ax)/dd;H[:,j,1]=(ys-ay)/dd
        sv=np.linalg.svd(H,compute_uv=False)
        minsv=min(minsv,float(sv[:,-1].min()))
        if (sv[:,-1]<=1e-9).any():rank_bad.append((route,np.where(sv[:,-1]<=1e-9)[0][:8].tolist()))
        rank_2old+=int(np.count_nonzero(np.linalg.svd(H[:,:2,:],compute_uv=False)[:,-1]<1e-10))
        idx=sample_pilot(rows,anchors)
        p=[]
        for k in idx:
            row=rows[k];pose=int(row["pose_id"])
            xyz=np.array([float(row["x"]),float(row["y"]),.45],float)
            for aid,pt in anchors.items():
                u=np.array(pt,float)
                for tt in np.linspace(0,1,11):
                    test=(1-tt)*xyz+tt*u
                    if (test[0]<room["x"][0]-1e-10 or test[0]>room["x"][1]+1e-10 or
                        test[1]<room["y"][0]-1e-10 or test[1]>room["y"][1]+1e-10 or
                        test[2]<room["z"][0]-1e-10 or test[2]>room["z"][1]+1e-10):
                        line_bad.append((route,pose,aid,float(tt)))
                # Central finite difference on distance, independent from array H.
                for j in (0,1):
                    plus=xyz.copy();minus=xyz.copy();plus[j]+=1e-6;minus[j]-=1e-6
                    fd=(np.linalg.norm(plus-u)-np.linalg.norm(minus-u))/(2e-6)
                    max_fd=max(max_fd,abs(fd-H[k,list(anchors).index(aid),j]))
            p.append({"pose_id":pose,"timeline_row_index":k,"t_s":float(row["t_s"]),
                      "x_m":float(row["x"]),"y_m":float(row["y"]),
                      "yaw_body_deg":float(row["yaw_body_deg"]),
                      "sample_type":"original_C0_Tnone_geometry_selected_before_new_C_H"})
        pilot[route]=p;pilot_all+=p
        stats[route]={"timeline_n":len(rows),"pilot_n":len(p),"min_singular_xy_range_H_ABC":float(sv[:,-1].min()),
                      "pct_abc_singular_min_below_0p05":float(np.mean(sv[:,-1]<.05)),
                      "original_AB_rank_deficient_samples":int(np.count_nonzero(np.linalg.svd(H[:,:2,:],compute_uv=False)[:,-1]<1e-10)),
                      "pilot_pose_ids":[int(t["pose_id"]) for t in p]}
    gate("A06_GEO_RANK_FD",not rank_bad and minsv>1e-9 and max_fd<=1e-8,
         "3anchor range XY H rank2 across all 3136 original distinct route steps; FD consistent",
         {"min_singular":minsv,"max_fd_abs":max_fd,"old_AB_rank_deficient_count":rank_2old,"rank_fail":rank_bad[:4]})
    gate("A07_PILOT_AND_PRISM",not line_bad and len(pilot_all)>=27 and all(9<=len(p)<=13 for p in pilot.values()),
         "original deterministic pilot pose keys, all direct line rays within empty rectangular prism",
         {"pilot_n":len(pilot_all),"per_route":{r:len(v) for r,v in pilot.items()},"blocked_empty_prism_rays":line_bad[:10]})
    ensure(not rank_bad and not line_bad and max_fd<=1e-8,"THIRD_GEOMETRY_CANNOT_FREEZE")
    gate("A08_NO_RT_OR_FABRICATED_SYNC",
         not cfg["pilot"]["synchronized_measured_third_anchor_packets"] and
         not cfg["pilot"]["anchor_c_observed_native_los_h_available"] and
         not cfg["resource_policy"]["new_raytrace_budget_approved"],
         "Original locked C0 has no C H or physical multi-anchor synchronized packet; P3 is source-only canary",
         {"real_rt_path_count":None,"source_only_direct_geometric_path_count_assumed":1,
          "measured_C_packets":0,"independent_scene_count":1})
    outplan={"schema":"DLP_P3_PRE_FROZEN_OUTCOME_BLIND_PILOT_SELECTION_V1","plan_source":"original_Tnone_only",
       "source_audit_run":os.environ.get("GITHUB_RUN_ID"),
       "source_three_anchor_xyz":{k:list(map(float,v)) for k,v in anchors.items()},
       "routes":pilot,"n_pilot_pose":len(pilot_all),
       "status":"PLANNED_NOT_NEW_RF","scene_independent_count":1,
       "third_C_original_RF":"MISSING_C0_NATIVE","timeline_is_measurement_sync_evidence":False,
       "selection_algorithm":cfg["pilot"]["selection_algorithm"]}
    (OUT/"P3_FROZEN_PILOT_SELECTION_PLAN.json").write_text(json.dumps(outplan,indent=2,ensure_ascii=False)+"\n")
    stats["overall"]={"pilot_n":len(pilot_all),"time_steps_n":sum(len(x) for x in timeline_lookup.values()),
       "min_xy_range_jacobian_singular_value":minsv,
       "max_FD_distance_error":max_fd,"triangle_area_m2":area,
       "AB_rank_deficient_n":rank_2old,
       "new_C_real_raytraced_packet_n":0,"RT_native_path_count":"NOT_RUN"}
if __name__=="__main__":
    try:audit()
    except BaseException as ex:
        errors.append({"key":"AUDIT_EXCEPTION","reason":repr(ex),"traceback":traceback.format_exc()})
        print("P3_PREFLIGHT_EXCEPTION",repr(ex),traceback.format_exc(),flush=True)
    verdict="ACCEPT_SOURCE_CANARY_WITH_BOUNDARIES" if not errors and len(checks)==9 else "BLOCKED_EVIDENCE"
    receipt={"schema":"DLP_P3_PRE_RUN_MATH_INPUT_GEOMETRY_AUDIT_V1",
       "status":verdict,"contract_id":"DLP-EKF-GAPS-001/P3-V1",
       "locked_config_sha256":CFG_SHA,"locked_contract_sha256":SPEC_SHA,
       "locked_tolerances_sha256":TOL_SHA,"actual_GitHub_runner":os.environ.get("GITHUB_RUN_ID"),
       "git_sha":os.environ.get("GITHUB_SHA"),"code_sha256":sha(__file__),
       "checks":checks,"errors":errors,"statistics":stats,
       "actor":"GPT-6 wrote proposer and audit, separate Linux runner for computation only",
       "independent_human_or_agent_peer_review":False,
       "scope":"geometry and provenance preaudit only; SourceFFD C new pilot H NOT_RUN, no native RT",
       "elapsed_sec":time.monotonic()-t0,"numpy":np.__version__,
       "utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    (OUT/"P3_PRE_RUN_AUDIT.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("P3_PREFLIGHT_FINAL",verdict,"checks",len(checks),"errors",len(errors),flush=True)
    sys.exit(0 if not errors and len(checks)==9 else 1)
