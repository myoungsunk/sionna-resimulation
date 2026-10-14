#!/usr/bin/env python3
"""Audited one-cell E pilot: score independently converged original G3 posterior.

Uses archived original G0/G1/G2H/G2X sample results, no new RF filter;
truth enters ONLY after original G3 posterior is loaded/verified. Full G2/G3
and recursive F remain explicitly NOT_RUN. Gate is stdlib-only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/g2g3_e1_pilot"
STAGE4=REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d/STAGE4_SMOKE_01/SMOKE_PARTIAL.csv"
TIMELINE=REPO/"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/INPUTS/timeline_R2_Tnone.csv"
ZIP_SHA="93e41c0b7490ba0a5ddee06d91786ed82dcd919e721d8cdf1ff4b942a7e9f1fa"
D_SHA="ae39d41cf5aa60934a88b7ade93da6d7563a90b18a3752824b2047261c30b7a4"
NPZ_SHA="a02c17e0789355ee55aab0ece4ecd587a1a8a288c9a9427e262a292100047d29"
ARTIFACT=11878356818


def sha(b):return hashlib.sha256(b).hexdigest()


def audit_first():
    OUT.mkdir(parents=True,exist_ok=False)
    approval=json.loads((ROOT/"E1_APPROVAL.json").read_text())
    receipt=dict(
      source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
      audit_id=approval["audit_id"],
      reviewer="assistant; no external human reviewer",
      audited_code_matches_execution_sha=False,run_decision="HOLD",
      source_sha256={},scientific_claim="CLAIM_BLOCK_FULL_G2G3_AND_GENERALIZATION",
    )
    try:
        if approval["review_decision"]!="GO_WITH_CLAIM_LIMITATION":
            raise RuntimeError("Unapproved E pilot")
        for rel,digest in approval["source_git_blobs"].items():
            data=(REPO/rel).read_bytes()
            found=subprocess.check_output(
                ["git","hash-object",str(REPO/rel)],cwd=REPO,text=True).strip()
            if found!=digest:
                raise RuntimeError("HARD_EXECUTION_BLOCK: unexpected original/source blob "+rel)
            receipt["source_sha256"][rel]=sha(data)
        receipt["audited_code_matches_execution_sha"]=True
        receipt["run_decision"]="GO_WITH_CLAIM_LIMITATION"
        ok=0
    except Exception as ex:
        receipt["error"]=str(ex)
        receipt["run_decision"]="HOLD"
        ok=2
    (OUT/"E1_PRE_RUN_AUDIT.json").write_text(
        json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False))
    print("E1_PRE_RUN_AUDIT",receipt["run_decision"],flush=True)
    return ok


def no_redirect():
    class Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):return None
    return urllib.request.build_opener(Stop())


def retrieve_pinned():
    token=os.getenv("GH_TOKEN")
    if not token:raise RuntimeError("HARD_EXECUTION_BLOCK: no permitted Actions read token")
    url="https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/artifacts/"+str(ARTIFACT)+"/zip"
    req=urllib.request.Request(url,headers={
        "Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json",
        "User-Agent":"g2g3-one-cell-audited-evaluation"})
    try:
        resp=no_redirect().open(req,timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code not in (301,302,303,307,308):raise
        redirect=exc.headers["Location"]
        parsed=urllib.parse.urlparse(redirect)
        if parsed.scheme!="https" or not (
          parsed.hostname.endswith(".blob.core.windows.net") or
          parsed.hostname.endswith(".githubusercontent.com")):
            raise RuntimeError("HARD_EXECUTION_BLOCK: unapproved redirect destination")
        resp=urllib.request.urlopen(redirect,timeout=90)
    with resp:
        blob=resp.read(100*1024*1024+1)
    if len(blob)>100*1024*1024 or sha(blob)!=ZIP_SHA:
        raise RuntimeError("HARD_EXECUTION_BLOCK: archive size/SHA mismatch")
    with zipfile.ZipFile(io.BytesIO(blob)) as zz:
        jd=zz.read("outputs/g2g3_bf/D_RESULT.json")
        n=zz.read("outputs/g2g3_bf/D_TILTED_GH_41.npz")
    if sha(jd)!=D_SHA or sha(n)!=NPZ_SHA:
        raise RuntimeError("HARD_EXECUTION_BLOCK: extracted posterior checksum")
    return json.loads(jd),n


def wrap(rad):return (rad+math.pi)%(2*math.pi)-math.pi


def execution():
    receipt=json.loads((OUT/"E1_PRE_RUN_AUDIT.json").read_text())
    if receipt["run_decision"]!="GO_WITH_CLAIM_LIMITATION":
        raise RuntimeError("Missing passing audit")
    for p,s in receipt["source_sha256"].items():
        if sha((REPO/p).read_bytes())!=s:
            raise RuntimeError("Audited source bytes changed")
    report=dict(stage="E1_ONE_CELL",execution="RUNNING",calculation="NOT_EVALUATED",
                scientific_PASS=False,full_E="NOT_RUN",recursive_F="NOT_RUN",
                original_R0_model_only=True,numerical_source_run=38531405523,
                next="STOP")
    try:
        D,packed=retrieve_pinned()
        if (D["actual_G3_reference"]!="PASS_INDEPENDENT_NUMERICAL" or
            D["max_TV"]>.001 or D["max_MAP_delta_deg"]>.1 or
            D["max_relative_evidence"]>.005):
            raise RuntimeError("CASE_RESULT_INVALID: G3 source is not numerically verified")
        import numpy as np
        with np.load(io.BytesIO(packed),allow_pickle=False) as npz:
            angles=np.asarray(npz["angles"],float)
            probs=np.asarray(npz["post"],float)
        if (angles.shape!=(1440,) or probs.shape!=(1440,) or not
            np.isfinite(probs).all() or np.min(probs)<0 or
            abs(float(probs.sum())-1)>1e-10):
            raise RuntimeError("CASE_RESULT_INVALID: posterior shape/normalization")

        with TIMELINE.open(newline="",encoding="utf-8") as f:
            times=[v for v in csv.DictReader(f)]
        tr=next(v for v in times if int(v["pose_id"])==978)
        if abs(float(tr["t_s"])-195.6)>1e-8:
            raise RuntimeError("HARD_EXECUTION_BLOCK: timeline mismatch")
        truth=math.radians(float(tr["yaw_body_deg"]))
        with STAGE4.open(newline="",encoding="utf-8-sig") as f:
            allrows=[v for v in csv.DictReader(f) if
                v["case"]=="R2_aA_m0" and v["condition"]=="gyro_bias" and
                int(v["level"])==2 and int(v["seed"])==0 and
                v["channel"]=="los" and v["range_model"]=="B_OLD" and
                int(v["sample"])==978]
        base={}
        for label in ("G0","G1","G2H","G2X"):
            rows=[v for v in allrows if v["method"]==label]
            if len(rows)!=1:raise RuntimeError("Frozen "+label+" sample missing")
            orig=rows[0]
            v=float(orig["MAP_rad"])
            error=math.degrees(wrap(v-truth))
            if abs(error-float(orig["heading_error_deg"]))>1e-8:
                raise RuntimeError("HARD_EXECUTION_BLOCK: archived error parity "+label)
            base[label]=dict(MAP_deg=math.degrees(v),signed_error_deg=error,
                             abs_error_deg=abs(error),
                             range_gate=orig["range_gate"])
        idx=int(np.argmax(probs))
        g3_map=float(angles[idx])
        g3_error=float(math.degrees(wrap(g3_map-truth)))
        chosen=np.argsort(probs)[::-1]
        k=int(np.searchsorted(np.cumsum(probs[chosen]),.95))+1
        mask=np.zeros(1440,dtype=bool);mask[chosen[:k]]=True
        truth_idx=int(np.argmin(np.abs(np.array([wrap(q-truth) for q in angles]))))
        p5=float(np.sum(probs[np.abs(np.array([wrap(q-truth) for q in angles]))<=math.radians(5)]))
        output=dict(MAP_deg=float(math.degrees(g3_map)),
                    signed_heading_error_deg=g3_error,abs_heading_error_deg=abs(g3_error),
                    hpd95_contains_truth=bool(mask[truth_idx]),
                    hpd95_total_width_deg=k*.25,
                    probability_within_truth_5deg=p5)
        report.update(
            execution="PASS",calculation="PASS_SINGLE_CELL_G3_SCORING",
            hypothesis="CONTRADICTED_G3_ALWAYS_IMPROVES_HEADING" if
                   abs(g3_error)>base["G2X"]["abs_error_deg"] else "SUPPORTED_SINGLE_CELL",
            scientific_claim="CLAIM_BLOCK_NO_GENERAL_POSE_BENEFIT_OR_CALIBRATION",
            truth_yaw_deg=math.degrees(truth),original_methods=base,
            numerical_G3=output,numerical_gate=dict(
                max_TV=D["max_TV"],max_relative_evidence=D["max_relative_evidence"]),
            interpretation="G2X NIS-rejected Range and uses conditional S; G3 joint uses Range. Accuracy difference confounds gate and pose-prior modelling, not sequential-versus-joint Bayesian factorization.",
            next="STOP after this scoped comparison. Require user-confirmed amended DR-fault/signed-RF model and independent calibration before full E/F.")
    except Exception as ex:
        report.update(execution="FAIL_SCOPED",calculation="CASE_RESULT_INVALID",
                      error_type=type(ex).__name__,error=str(ex),traceback=traceback.format_exc())
    finally:
        (OUT/"E1_ONE_CELL_RESULT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
        print("E1_RESULT",json.dumps({k:report.get(k) for k in
            ("execution","calculation","hypothesis","numerical_G3","next")},ensure_ascii=False),flush=True)
    return 0 if report["execution"]=="PASS" else 3


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["audit","run"])
    stage=p.parse_args().action
    if stage=="audit":raise SystemExit(audit_first())
    raise SystemExit(execution())


if __name__=="__main__":main()
