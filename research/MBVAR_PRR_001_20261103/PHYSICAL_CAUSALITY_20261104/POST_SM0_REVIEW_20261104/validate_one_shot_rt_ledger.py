#!/usr/bin/env python3
"""Pure-stdlib, NO RT import. Independently rebuild complete missing RT key set.

Inputs: original Tnone CSV from immutable Git source, PR35 fixed G3 PLAN/GO
from pinned separate checkout, and prepared 400-row ONE_SHOT CSV/JSON.
Fails closed on an omitted, duplicated, extra, shifted or wrong-source key.
"""
from __future__ import annotations
import csv
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE
while not (ROOT/"results").is_dir() and ROOT!=ROOT.parent:
    ROOT=ROOT.parent
TIMELINE_ROOT=ROOT/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS"
G3_ROOT=Path(os.environ.get("MBVAR_G3_ROOT",str(ROOT/"g3_source")))
G3=G3_ROOT/"research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C3/G3_001"
CSV=HERE/"ONE_SHOT_RT_EXTRACTION_LEDGER_20261105.csv"
PLAN=HERE/"ONE_SHOT_RT_EXTRACTION_PLAN_20261105.json"
ORIG_FIXED={"R4":[168,172,173,194,234,500,525,729],
            "R5":[401,465,979,980,982,983],"R2":[525]}
WINDOWS={"R4":[("R4_0_15",0,15),("R4_33_35p2",33,35.2),("R4_59_61",59,61),
               ("R4_99_105p4",99,105.4)],
         "R5":[("R5_79_81",79,81),("R5_92_94",92,94),
               ("R5_132_135",132,135),("R5_195_198",195,198)]}

def must(a,err):
    if not a:raise RuntimeError(err)
def byhash(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(2**20),b""):h.update(b)
    return h.hexdigest()
def original():
    out={}
    for route in ("R2","R4","R5"):
        path=TIMELINE_ROOT/("timeline_"+route+"_Tnone.csv")
        must(path.is_file(),"ERR_MISSING_TNONE_"+route)
        with path.open(newline="") as f:
            records=list(csv.DictReader(f))
        keys={int(r["pose_id"]):r for r in records}
        must(len(keys)==len(records),"ERR_TNONE_DUPLICATE_"+route)
        required={id:{"row":keys[id],"tags":["SM0B_FIXED15"]} for id in ORIG_FIXED[route]}
        for tag,start,end in WINDOWS.get(route,[]):
            for pose_id,row in keys.items():
                t=float(row["t_s"])
                if start-1e-8<=t<=end+1e-8:
                    data=required.setdefault(pose_id,{"row":row,"tags":[]})
                    data["tags"].append("SM1_"+tag)
        out[route]=required
    return out

def validate():
    plan=json.loads(PLAN.read_text())
    with CSV.open(newline="") as f:actual=list(csv.DictReader(f))
    must(len(actual)==400 and plan["expected_task_rows"]==400,"ERR_TOTAL_TASK_COUNT")
    identifiers=[r["task_id"] for r in actual]
    must(len(set(identifiers))==400,"ERR_DUPLICATE_TASK_ID")
    orig=original()
    expected={}
    count=Counter()
    for route in ("R4","R5","R2"):
        for pose_id,data in orig[route].items():
            row=data["row"]
            fixed="SM0B_FIXED15" in data["tags"]
            stage=("B0_CANARY" if route=="R4" and pose_id in (194,234)
                   else "B1_FIXED" if fixed else "SM1_EVENT")
            for mode in ("FULL","NATIVE_LOS"):
                key=f"ORIG6_{route}_B_P{pose_id}_{mode}"
                expected[key]=(route,pose_id,mode,row,data["tags"],stage)
                count[stage]+=1
    must(len(expected)==380,"ERR_ORIGINAL_KEY_COUNT")
    g3_plan=json.loads((G3/"PLAN.json").read_text())
    g3_go=json.loads((G3/"GO_G3_001.json").read_text())
    must(g3_go["decision"]=="GO","ERR_G3_GO_NOT_APPROVED")
    must(g3_go["scope"]=="G3_REMAINING20_RAW_CAPTURE_ONLY","ERR_G3_GO_SCOPE")
    must(len(g3_plan["authorized"])==len(g3_go["authorized"])==20,"ERR_G3_20_MISSING")
    must(g3_plan["repeat_bins"]==[0,128,256],"ERR_REPEAT_BINS_CHANGED")
    authorized={r["id"]:r for r in g3_go["authorized"]}
    must(set(authorized)=={r["id"] for r in g3_plan["authorized"]},"ERR_PLAN_GO_KEYS")
    count["SM2_G3_REMAINING20"]=20
    must(len(orig["R4"])==135 and len(orig["R5"])==54 and len(orig["R2"])==1,"ERR_ORIGINAL_ROUTE_POSES")
    must(count==Counter({"B0_CANARY":4,"B1_FIXED":26,"SM1_EVENT":350,"SM2_G3_REMAINING20":20}),"ERR_STAGE_COUNT")
    for r in actual:
        id=r["task_id"]
        if id in expected:
            route,pose,mode,source,tags,stage=expected.pop(id)
            must(r["source_track"]=="ORIGINAL_6_WALL_CORRIDOR","ERR_ORIGINAL_SOURCE_TRACK")
            must(r["route"]==route+"_B" and r["stage"]==stage,"ERR_ROUTE_OR_STAGE_"+id)
            must(int(r["pose_id"])==pose and r["rf_mode"]==mode,"ERR_ORIGINAL_MODE_"+id)
            must(r["window_tags"]==";".join(tags),"ERR_WINDOW_TAGS_"+id)
            for field,compare in (("t_s","t_s"),("idx","idx"),("x_m","x"),("y_m","y"),("yaw_deg","yaw_body_deg")):
                must(float(r[field])==float(source[compare]),"ERR_POSE_TNONE_VALUE_"+id+"_"+field)
            must(int(r["expected_solver_calls"])==257,"ERR_ORIGINAL_SOLVER_CALL_COUNT")
            must(r["repeat_bin_indices"]=="","ERR_ORIGINAL_REPEAT_UNAUTHORIZED")
        else:
            must(id in authorized,"ERR_EXTRA_OR_UNREGISTERED_KEY_"+id)
            e=authorized.pop(id)
            must(r["stage"]=="SM2_G3_REMAINING20" and
                 r["source_track"]=="SM2_ORIGINAL_SIX_WALL_FIXED_XY_YAW","ERR_G3_SCENE_SOURCE_"+id)
            must(r["yaw_condition_id"]==e["id"] and r["coordinate_id"]==e["coordinate"],"ERR_G3_KEY_"+id)
            must([float(r[x]) for x in ("x_m","y_m","z_m")]==e["xyz"],"ERR_G3_COORD_"+id)
            must(float(r["yaw_deg"])==float(e["yaw_deg"]),"ERR_G3_YAW_"+id)
            must(int(r["expected_solver_calls"])==260,"ERR_G3_CALL_COUNT")
            must(r["repeat_bin_indices"]=="0;128;256","ERR_G3_REPEAT_SET")
            must(r["rf_mode"]=="FULL_WITH_DIRECT_RAY_EXTRACTED","ERR_G3_MODE")
    must(not expected and not authorized,"ERR_MISSING_KEYS")
    calls=sum(int(x["expected_solver_calls"]) for x in actual)
    must(calls==102860 and plan["expected_solver_calls_exact_max"]==calls,"ERR_CALL_BUDGET")
    for k,v in dict(count).items():must(plan["job_counts"][k]==v,"ERR_PLAN_GROUP_"+k)
    must(plan["pr35_yaw_done4_reused_no_compute"] is True,"ERR_G2_DUPLICATE")
    must(plan["original_full_los_tasks"]==380 and plan["g3_remaining_yaw_tasks"]==20,"ERR_PREREGISTERED_SCOPE")
    result=dict(status="ONE_SHOT_RT_READ_ONLY_KEY_LEDGER_PASS",
        source_type="exact original Tnone 3 routes and separate pinned PR35 G3 PLAN/GO",
        n_rows=len(actual),original_pose_count=sum(len(x) for x in orig.values()),
        original_full_los_rows=380,not_yet_verified_g3_rows=20,
        total_max_solver_calls=calls,stage_counts=dict(count),
        csv_sha256=byhash(CSV),plan_sha256=byhash(PLAN),
        raw_H_generated_this_test=False,RT_calls=0)
    print("ONE_SHOT_KEY_LEDGER_STATIC_PASS",json.dumps(result,sort_keys=True))
    out=Path(os.environ.get("MBVAR_ONE_SHOT_QA_OUT","/tmp/ONE_SHOT_KEY_LEDGER_STATIC_QA.json"))
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    return result
if __name__=="__main__":validate()
