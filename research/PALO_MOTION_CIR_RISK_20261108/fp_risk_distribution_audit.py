#!/usr/bin/env python3
"""Pinned follow-up: severity/FP-spread monotonicity vs true harmful heading action.

No new policy is trained. Offline truth and LoS are ONLY labels. The same 779 RF
frames repeated across four bias conditions and two prior policies are NOT
independent. NIS rejected candidate losses are not realized filter injuries.
"""
from __future__ import annotations
import base64,hashlib,io,json,os,time,urllib.request
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.metrics import roc_auc_score
REPO="myoungsunk/sionna-resimulation"
SOURCE_REF="b7bacb08bfaca9a1765cddd5fff819c45e3ab0d4"
SOURCE_PATH="research/PALO_MOTION_CIR_RISK_20261108/runs/42462035988/matched_motion_cir_frames.csv.gz"
SOURCE_SHA="35264bf410a464e73a5a2b740cade6aa618c44853987b13f8e7ce12645906ac5"
OUT=Path("audit_outputs");OUT.mkdir(exist_ok=True)
def get():
    url=f"https://raw.githubusercontent.com/{REPO}/{SOURCE_REF}/{SOURCE_PATH}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"PALO-Research-QA"}),timeout=90) as r:b=r.read()
            assert len(b)==1296659,(len(b),"bytes")
            assert hashlib.sha256(b).hexdigest()==SOURCE_SHA,"INPUT_SHA_MISMATCH"
            return pd.read_csv(io.BytesIO(b),compression="gzip")
        except Exception:
            if attempt==3:raise
            time.sleep(1+attempt)
def A(y,x):
    if y.sum()==0 or y.sum()==len(y):return None
    return float(roc_auc_score(y,x))
def contiguous(indices):
    v=sorted(int(k) for k in indices)
    if not v:return []
    out=[];st=prev=v[0]
    for k in v[1:]:
        if k==prev+1:prev=k
        else:out.append([st,prev]);st=prev=k
    out.append([st,prev])
    return out
def run():
    df=get()
    assert len(df)==6232
    assert sorted(df.level.unique().tolist())==["B0","L0","L1","L2"]
    assert sorted(df.donor.unique().tolist())==["dr","s4"]
    for (_, _),g in df.groupby(["level","donor"]):
        assert len(g)==779 and (g.k.values==np.arange(200,979)).all()
        assert abs(g.t.iloc[0]-40.)<1e-12
        assert (np.abs(g.oracle_delta_s_full_minus_los)<1.).all()
    d=df.query('level=="B0" and donor=="s4"').sort_values("k").copy()
    d["major_rf"]=d.abs_oracle_delta_s>.1
    d["major_heading"]=d.ref_hed_gain_deg<-.5
    g=d[d.gate_eligible].copy()
    assert d.major_rf.sum()==135 and d.major_heading.sum()==11
    assert g.major_heading.sum()==3 and g.loc[g.major_heading,"k"].tolist()==[483,484,485]
    assert not (d.loc[d.major_heading,"major_rf"]).any()
    assert (g.loc[g.major_heading,"abs_oracle_delta_s"]<.01).all()
    # RF severity -- bins are offline labels, not learned sensor thresholds.
    cats=pd.cut(d.abs_oracle_delta_s,[-1e-12,.02,.05,.1,.2,float("inf")],
        labels=["<=.02",".02-.05",".05-.10",".10-.20",">.20"])
    bins=[]
    for name,sub in d.groupby(cats,observed=True):
        bins.append(dict(rf_delta_bin=str(name),n=len(sub),
            median_abs_full_los_s=float(sub.abs_oracle_delta_s.median()),
            median_fp_spread_13=float(sub.fp_spread_primary.median()),
            median_fp_spread_25=float(sub.fp_spread_wide.median()),
            median_tap_pm2_delta_s=float(sub.delta_s_tap_absmax2.median()),
            candidate_harm_gt05=int(sub.major_heading.sum()),
            nis_eligible_harm_gt05=int((sub.major_heading&sub.gate_eligible).sum())))
    pd.DataFrame(bins).to_csv(OUT/"rf_severity_bins.csv",index=False)
    quantiles=[]
    for feature in ["fp_spread_primary","fp_spread_wide","delta_s_tap_absmax2","abs_Hpsi"]:
        labels=pd.qcut(d[feature],4,labels=["Q1","Q2","Q3","Q4"])
        for q,sub in d.groupby(labels,observed=True):
            quantiles.append(dict(feature=feature,quartile=str(q),n=len(sub),
               lo=float(sub[feature].min()),hi=float(sub[feature].max()),
               median_abs_full_los_s=float(sub.abs_oracle_delta_s.median()),
               rf_delta_gt_01=int(sub.major_rf.sum()),
               rf_delta_gt_01_fraction=float(sub.major_rf.mean()),
               heading_harm_gt_05=int(sub.major_heading.sum()),
               gate_eligible_heading_harm_gt_05=int((sub.major_heading&sub.gate_eligible).sum())))
    pd.DataFrame(quantiles).to_csv(OUT/"fp_and_slope_quartiles.csv",index=False)
    auc=[]
    features=["fp_spread_primary","fp_spread_wide","fp_spread_narrow",
          "fp_spread_diff_primary","fp_jsd_primary","fp_late_fraction",
          "delta_s_tap_absmax2","abs_Hpsi","abs_heading_correction_deg",
          "innovation_abs","abs_delta_s_temporal","abs_oracle_delta_s"]
    for feature in features:
        for label,ss,yy in [("RF_DELTA_GT_0.1_OFFLINE",d,d.major_rf),
                            ("CANDIDATE_HEAD_LOSS_GT_0.5",d,d.major_heading),
                            ("GATE_ELIGIBLE_HEAD_LOSS_GT_0.5",g,g.major_heading)]:
            auc.append(dict(feature=feature,label=label,n=len(ss),positive=int(yy.sum()),
                auc_higher_feature_means_higher_risk=A(yy,ss[feature]),
                spearman_vs_abs_full_los=float(ss[feature].corr(ss.abs_oracle_delta_s,method="spearman")),
                feature_offline_only=(feature=="abs_oracle_delta_s")))
    pd.DataFrame(auc).to_csv(OUT/"auc_target_gate_audit.csv",index=False)
    alarm=[]
    thresholds=[("abs_Hpsi",1.5),("abs_Hpsi",2.0),
       ("abs_heading_correction_deg",.2),("abs_heading_correction_deg",.5),
       ("fp_spread_primary",2.3),("fp_spread_wide",3.5),
       ("innovation_abs",.15)]
    for level in ["B0","L0","L1","L2"]:
        for donor in ["s4","dr"]:
            t=df.query("level==@level and donor==@donor and gate_eligible")
            for feature,cut in thresholds:
                flag=t[feature]>=cut
                harm=t.ref_hed_gain_deg<-.5
                alarm.append(dict(level=level,donor=donor,feature=feature,threshold=cut,
                    eligible=len(t),alarm_count=int(flag.sum()),harmful_gt05=int(harm.sum()),
                    caught_harmful=int((flag&harm).sum()),
                    beneficial_alarm=int((flag&(t.ref_hed_gain_deg>0)).sum()),
                    precision=float(harm[flag].mean()) if flag.any() else None,
                    recall=float((flag&harm).sum()/harm.sum()) if harm.any() else None))
    pd.DataFrame(alarm).to_csv(OUT/"alarm_threshold_cross_state.csv",index=False)
    severity=[]
    for start,sub in [("all_candidates",d),("gate_eligible",g)]:
        for delta in [.05,.1,.2,.5,.75,1.0]:
            harm=sub.ref_hed_gain_deg<=-delta
            severity.append(dict(cohort=start,loss_threshold_deg=delta,n=len(sub),
                count_harm=int(harm.sum()),
                event_stretches=contiguous(sub.loc[harm,"k"].values)))
    (OUT/"severity_events.json").write_text(json.dumps(severity,indent=2))
    d.loc[d.major_heading,["k","t","gate_eligible","nis","abs_Hpsi","innovation_abs",
        "abs_heading_correction_deg","ref_hed_gain_deg",
        "abs_oracle_delta_s","fp_spread_primary","fp_spread_wide",
        "delta_s_tap_absmax2"]].to_csv(OUT/"candidate_harm_event_rows.csv",index=False)
    meta=dict(
       status="EXPLORATORY_SAVED_R2_ANALYSIS_ONLY",source_commit=SOURCE_REF,
       input_file=SOURCE_PATH,input_sha256=SOURCE_SHA,
       physical_frames=779,reused_prior_rows=6232,
       B0_S4_candidate_harm_gt05=int(d.major_heading.sum()),
       B0_S4_actual_gate_eligible_harm_gt05=int(g.major_heading.sum()),
       B0_S4_captured_harm_cluster=[483,485],
       B0_S4_rejected_candidate_harm=int((d.major_heading&~d.gate_eligible).sum()),
       B0_S4_major_rf_delta_gt01=int(d.major_rf.sum()),
       B0_S4_major_rf_and_candidate_harm_gt05=int((d.major_rf&d.major_heading).sum()),
       B0_S4_actual_harm_max_mp_delta=float(g.loc[g.major_heading,"abs_oracle_delta_s"].max()),
       spearman_fp13_to_mp=float(d.fp_spread_primary.corr(d.abs_oracle_delta_s,method="spearman")),
       fp13_auc_mp=A(d.major_rf,d.fp_spread_primary),
       slope_auc_candidate_harm=A(d.major_heading,d.abs_Hpsi),
       accepted_hazard_support_not_independent="3 adjacent frames in a single time-cluster",
       limits=["single trajectory and RF seed","post-hoc threshold performance; no held-out route",
               "RF quality labels require LoS oracle and are unavailable online",
               "zero padded Sionna CIR, not raw 992-tap hardware impulse",
               "AUC 0.908 includes eight rejected candidate outcomes and is not online utility",
               "no new recursive policy or causal attribution"])
    (OUT/"SUMMARY.json").write_text(json.dumps(meta,indent=2))
    manifest={p.name:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in OUT.iterdir() if p.is_file()}
    (OUT/"SHA256.json").write_text(json.dumps(manifest,indent=2))
    print("PALO_GATED_RISK_AUDIT_PASS",json.dumps(meta))
    return meta
def publish():
    token=os.environ.get("GITHUB_TOKEN");branch=os.environ.get("TARGET_BRANCH")
    if not token or not branch:return
    endpoint=f"https://api.github.com/repos/{REPO}"
    def api(p,method="GET",value=None):
        payload=json.dumps(value).encode() if value is not None else None
        hd={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":"2022-11-28","User-Agent":"palo-rf-audit"}
        if payload is not None:hd["Content-Type"]="application/json"
        req=urllib.request.Request(endpoint+p,data=payload,method=method,headers=hd)
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    encoded=branch.replace("/","%2F")
    original=api("/git/ref/heads/"+encoded)["object"]["sha"]
    if original!=os.environ["GITHUB_SHA"]:raise RuntimeError("CONCURRENT_BRANCH_WRITE")
    parent=api("/git/commits/"+original)
    elems=[]
    for file in sorted(OUT.iterdir()):
        if file.is_file():
            b=api("/git/blobs","POST",{"content":base64.b64encode(file.read_bytes()).decode(),"encoding":"base64"})
            elems.append({"path":f"research/PALO_MOTION_CIR_RISK_20261108/risk_detail/{os.environ.get('GITHUB_RUN_ID','local')}/{file.name}",
                "mode":"100644","type":"blob","sha":b["sha"]})
    tree=api("/git/trees","POST",{"base_tree":parent["tree"]["sha"],"tree":elems})
    commit=api("/git/commits","POST",{"message":"Publish PALO gate-aware heading-harm rarity and CIR severity bins; threshold transfer checks",
      "tree":tree["sha"],"parents":[original]})
    api("/git/refs/heads/"+encoded,"PATCH",{"sha":commit["sha"],"force":False})
    print("PALO_RISK_AUDIT_PUBLISHED",commit["sha"])
if __name__=="__main__":
    run();publish()
