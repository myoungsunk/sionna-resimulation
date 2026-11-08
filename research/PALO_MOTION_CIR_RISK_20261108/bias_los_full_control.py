#!/usr/bin/env python3
"""PALO S4 bias LoS-vs-Full same-source, same-motion diagnostic. No new estimation."""
from __future__ import annotations
import base64, csv, hashlib, io, json, os, time, urllib.request
from pathlib import Path
import numpy as np

REPO="myoungsunk/sionna-resimulation"
REF="8894353b10f790746f32d8d82159213aad9c82a7"
ROOT="research/POL_HEADING_RESEARCH_20261107/inputs/original_run"
GAP="research/PALO_GAP_STUDY_20261107/results/trajectories"
OUT=Path("control_outputs");OUT.mkdir(exist_ok=True)
AUDIT=[]
DEG=180/np.pi
BIAS={"B0":0.0,"L0":.01,"L1":.05,"L2":.2}
def get(path):
    last=None
    for attempt in range(4):
        try:
            req=urllib.request.Request(f"https://raw.githubusercontent.com/{REPO}/{REF}/{path}",headers={"User-Agent":"PALO-CONTROL-QA"})
            with urllib.request.urlopen(req,timeout=100) as r:b=r.read()
            if b.startswith(b"version https://git-lfs.github.com/spec/v1"):raise RuntimeError("LFS_POINTER")
            AUDIT.append({"path":path,"sha256":hashlib.sha256(b).hexdigest(),"bytes":len(b)})
            return {k:z[k].copy() for z in [np.load(io.BytesIO(b),allow_pickle=False)] for k in z.files}
        except Exception as e:
            last=e
            if "LFS_POINTER" in str(e):raise
            time.sleep(attempt+1)
    raise RuntimeError(f"FETCH_FAILED {path}: {last}")
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def rms(x):return float(np.sqrt(np.mean(np.asarray(x)**2)))
def run():
    rows=[]
    t=None;truth=None;max_full_diff=0.;max_mask_diff=0
    for channel in ("los","full"):
      for lv,btrue in BIAS.items():
        r=get(f"{ROOT}/results/replay/R2_aB_m0_{channel}_{lv}_seed0_recursive.npz")
        inp=get(f"{ROOT}/verified_inputs/R2_aB_m0_{channel}_seed0_ONE_STEP.npz")
        x=np.asarray(r["estimate"][:,3,:],float)
        P=np.asarray(r["covariance"][:,3,:,:],float)
        NIS=np.asarray(r["nis"][:,3],float)
        status=np.asarray(r["status"][:,3])
        gt=np.asarray(inp["truth_for_offline_scoring_only"],float)
        ts=np.asarray(inp["t_s"],float)
        if t is None:t=ts.copy();truth=gt.copy()
        assert ts.shape==(979,) and gt.shape==(979,3) and x.shape==(979,4) and P.shape==(979,4,4)
        assert np.array_equal(ts,t) and np.max(abs(gt-truth))<1e-12
        assert np.isfinite(x).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
        if channel=="full":
            prev=get(f"{GAP}/baseline_{lv}_s4.npz")
            dx=np.max(abs(x-prev["X"])); dp=np.max(abs(P-prev["P"]))
            max_full_diff=max(max_full_diff,float(dx),float(dp))
            assert dx<1e-7 and dp<1e-8,(lv,dx,dp)
            assert np.array_equal((status=="APPLIED"),prev["accepted"])
        sel=t>=40
        eb=(x[sel,3]*DEG-btrue)
        vb=P[sel,3,3]*DEG**2
        epsi=wrap(x[sel,2]-gt[sel,2])*DEG
        vp=P[sel,2,2]*DEG**2
        rows.append(dict(channel=channel,level=lv,n=int(sel.sum()),truth_b_deg_s=btrue,
           bias_mean_deg_s=float(np.mean(x[sel,3]*DEG)),
           bias_mae_deg_s=float(np.mean(abs(eb))),bias_rmse_deg_s=rms(eb),
           bias_sigma_rms_deg_s=rms(np.sqrt(vb)),bias95=float(np.mean(eb**2<=3.841458820694124*vb)),
           heading_rmse_deg=rms(epsi),heading_sigma_rms_deg=rms(np.sqrt(vp)),
           heading95=float(np.mean(epsi**2<=3.841458820694124*vp)),
           reject=int(np.count_nonzero(status[sel]=="REJECT"))))
    with (OUT/"bias_los_full_comparison.csv").open("w",newline="") as f:
      w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={"status":"PASS_S4_FULL_PARITY_LOS_FULL_COMPARISON","input_commit":REF,
            "n_conditions":len(rows),"max_full_parity_diff":max_full_diff,
            "rows":rows,
            "note":"Same R2 noise/position; LoS vs Full RF only; bias attribution still non-causal across unknown model mismatch. No new filter."}
    (OUT/"BIAS_CONTROL_QA.json").write_text(json.dumps(result,indent=2,allow_nan=False))
    (OUT/"INPUT_SHA256.json").write_text(json.dumps(AUDIT,indent=2))
    print(json.dumps({"qa":result["status"],"max_diff":max_full_diff,
          "bias95":{lv:{ch:next(r for r in rows if r["level"]==lv and r["channel"]==ch)["bias95"] for ch in ("los","full")} for lv in BIAS}},indent=2))
    return result
def publish():
    token=os.environ.get("GITHUB_TOKEN");branch=os.environ.get("TARGET_BRANCH")
    if not token or not branch:return
    baseurl=f"https://api.github.com/repos/{REPO}"
    def api(path,method="GET",payload=None):
        b=None if payload is None else json.dumps(payload).encode()
        head={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"PALO-CONTROL"}
        if b:head["Content-Type"]="application/json"
        req=urllib.request.Request(baseurl+path,data=b,headers=head,method=method)
        with urllib.request.urlopen(req,timeout=90) as v:return json.load(v)
    sha=api("/git/ref/heads/"+branch.replace("/","%2F"))["object"]["sha"]
    if sha!=os.environ.get("GITHUB_SHA"):raise RuntimeError("CONCURRENT_HEAD_CHANGED")
    parent=api("/git/commits/"+sha); trees=[]
    prefix=f"research/PALO_MOTION_CIR_RISK_20261108/bias_control/{os.getenv('GITHUB_RUN_ID','local')}"
    for file in OUT.iterdir():
        if file.is_file():
            b=api("/git/blobs","POST",{"content":base64.b64encode(file.read_bytes()).decode(),"encoding":"base64"})
            trees.append({"path":prefix+"/"+file.name,"mode":"100644","type":"blob","sha":b["sha"]})
    tr=api("/git/trees","POST",{"base_tree":parent["tree"]["sha"],"tree":trees})
    commit=api("/git/commits","POST",{"message":"Add independent LoS/Full S4 gyro-bias covariance comparison and QA", "tree":tr["sha"],"parents":[sha]})
    api("/git/refs/heads/"+branch.replace("/","%2F"),"PATCH",{"sha":commit["sha"],"force":False})
    print("PUBLISHED_BIAS_CONTROL",commit["sha"])
if __name__=="__main__":
    run();publish()
