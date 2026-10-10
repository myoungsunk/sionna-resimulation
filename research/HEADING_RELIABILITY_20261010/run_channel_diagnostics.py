#!/usr/bin/env python3
"""Exploratory paired-channel diagnostics, not the locked operational heading study.

Offline input is Sionna complex H, but EVERY predictor is computed solely from
per-port amplitude/power CIR. Direct LoS H and true poses are used ONLY for
labels/stratification, never as deployable inference features.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BLOCK = ROOT / "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
FREQS = BLOCK.parent / "freqs_hz.npy"
CASES = ["R2_aA_m0", "R2_aB_m0", "R2_aA_m45",
         "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"]
D_FEATURES = ["delay_rms_mean_ns", "delay_rms_absdiff_ns",
              "early_fraction_mean", "early_fraction_absdiff",
              "rise_time_mean_ns", "peak_over_first_mean"]
P_FEATURES = ["jsd_early16", "shape_l1_early16", "peak_delay_diff_ns",
              "early_fraction_absdiff", "s", "log10_fp_power_sum"]
ALL_FEATURES = sorted(set(D_FEATURES + P_FEATURES))
HEAD_COLS = ["case", "route", "pose_id", "station_group_id", "x", "y",
             "yaw_deg", "distance_m", "s_full", "s_los", "e_MP",
             "range_error_m", "fp_idx_full", "fp_idx_los"] + ALL_FEATURES

def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()

def csv_write(path, records, columns=None):
    if not records:
        path.write_text("", encoding="utf-8")
        return
    columns = columns or list(records[0])
    with path.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        wr.writeheader()
        wr.writerows(records)

def safe_div(x, y):
    return np.divide(x, y, out=np.full_like(x, np.nan, dtype=float),
                     where=np.abs(y) > 1e-200)

def observer(h4, f, chunk=100):
    """Replicate original strongest-RX shared first-path tap (no thermal noise)."""
    out = {}
    n = h4.shape[0]
    power = np.zeros((n,2))
    s = np.full(n,np.nan)
    fp = np.zeros(n,dtype=int)
    range_m = np.zeros(n)
    feat = {k: np.full(n,np.nan) for k in ALL_FEATURES}
    win_h = 0.5-0.5*np.cos(2*np.pi*np.arange(len(f))/(len(f)-1))
    df = float(f[1]-f[0])
    dt = 1.0/(4*len(f)*df)
    for j in range(0,n,chunk):
        sl=slice(j,min(j+chunk,n))
        h = np.asarray(h4[sl,:,:,0],complex)
        pad = np.zeros((len(h),4*len(f),2),dtype=complex)
        pad[:,:len(f)] = h*win_h[None,:,None]
        cir = np.fft.ifft(pad,axis=1)*len(f)
        amp=np.abs(cir)
        peak_branch=amp.max(axis=1).argmax(axis=1)
        strongest=np.take_along_axis(amp,peak_branch[:,None,None],axis=2)[:,:,0]
        peak=strongest.max(axis=1)
        k=(strongest>=0.3*peak[:,None]).argmax(axis=1)
        ix=np.arange(len(h))
        powers=np.abs(cir[ix,k,:])**2
        den=powers.sum(axis=1)
        sq=np.where(den>0,(powers[:,0]-powers[:,1])/np.maximum(den,1e-200),np.nan)
        power[sl]=powers
        s[sl]=sq
        fp[sl]=k
        range_m[sl]=k*dt*299792458.0
        p=amp**2
        for q in range(len(h)):
            k0=int(k[q]); lo=min(len(p[q]),k0+80); lo16=min(len(p[q]),k0+16)
            pp=p[q,k0:lo,:]
            if len(pp)<8:continue
            t=np.arange(len(pp),dtype=float)*dt*1e9
            energy=pp.sum(axis=0)
            mu=np.sum(pp*t[:,None],axis=0)/np.maximum(energy,1e-200)
            rds=np.sqrt(np.maximum(0,np.sum(pp*(t[:,None]-mu)**2,axis=0)/np.maximum(energy,1e-200)))
            early=pp[:8].sum(axis=0)/np.maximum(energy,1e-200)
            ratio=pp.max(axis=0)/np.maximum(p[q,k0,:],1e-200)
            peak_index=pp.argmax(axis=0)
            vec=p[q,k0:lo16,:]
            norm=vec/np.maximum(vec.sum(axis=0),1e-200)[None,:]
            m=np.maximum((norm[:,0]+norm[:,1])*0.5,1e-200)
            jsd=0.5*np.sum(np.where(norm[:,0]>0,norm[:,0]*np.log(np.maximum(norm[:,0],1e-200)/m),0))+0.5*np.sum(np.where(norm[:,1]>0,norm[:,1]*np.log(np.maximum(norm[:,1],1e-200)/m),0))
            rise=[]
            for port in (0,1):
                a=amp[q,:,port]
                pi=int(a.argmax())
                crossings=[int(np.flatnonzero(a[:pi+1]>=fraction*a[pi])[0]) if np.any(a[:pi+1]>=fraction*a[pi]) else pi for fraction in (0.1,0.9)]
                rise.append((crossings[1]-crossings[0])*dt*1e9)
            dct={
                "delay_rms_mean_ns":float(rds.mean()),
                "delay_rms_absdiff_ns":float(abs(rds[0]-rds[1])),
                "early_fraction_mean":float(early.mean()),
                "early_fraction_absdiff":float(abs(early[0]-early[1])),
                "rise_time_mean_ns":float(np.mean(rise)),
                "peak_over_first_mean":float(ratio.mean()),
                "jsd_early16":float(jsd),
                "shape_l1_early16":float(np.sum(abs(norm[:,0]-norm[:,1]))),
                "peak_delay_diff_ns":float(abs(peak_index[0]-peak_index[1])*dt*1e9),
                "s":float(sq[q]),
                "log10_fp_power_sum":float(np.log10(max(den[q],1e-200))),
            }
            for key,value in dct.items():feat[key][j+q]=value
    return dict(s=s,fp=fp,range_m=range_m,features=feat,power=power)

def build_stations(samples):
    groups=[];cur=[0]
    for i in range(1,len(samples)):
        s=samples[i]; t=samples[cur[0]]
        if abs(s["x"]-t["x"])<=1e-7 and abs(s["y"]-t["y"])<=1e-7:cur.append(i)
        else:groups.append(cur);cur=[i]
    groups.append(cur)
    station=np.full(len(samples),-1,int)
    for gi,g in enumerate(groups):
        for j in g:station[j]=gi
    return groups,station

def measures(x, y):
    valid=np.isfinite(x)&np.isfinite(y)
    x=np.asarray(x)[valid];y=np.asarray(y)[valid]
    if len(x)<4 or np.std(x)<1e-14 or np.std(y)<1e-14:return (float("nan"),float("nan"),int(len(x)))
    pear=float(np.corrcoef(x,y)[0,1])
    def rank(v):
        # deterministic average rank for duplicate ties, no scipy dependence
        idx=np.argsort(v,kind="mergesort")
        vv=v[idx]; rr=np.empty(len(vv),dtype=float);i=0
        while i<len(vv):
            j=i+1
            while j<len(vv) and vv[j]==vv[i]:j+=1
            rr[i:j]=(i+j-1)/2
            i=j
        out=np.empty(len(vv),dtype=float);out[idx]=rr
        return out
    rho=float(np.corrcoef(rank(x),rank(y))[0,1])
    return pear,rho,len(x)

def summaries(rows):
    out=[]
    for case in sorted({r["case"] for r in rows}|{"ALL"}):
        data=[r for r in rows if case=="ALL" or r["case"]==case]
        for low,hi,name in [(0,5,"<5"),(5,10,"5-10"),(10,float("inf"),">=10"),(0,float("inf"),"ALL")]:
            a=[r for r in data if low<=r["distance_m"]<hi]
            x=np.asarray([r["e_MP"] for r in a],float)
            z=np.asarray([r["range_error_m"] for r in a],float)
            out.append(dict(case=case,distance_bin=name,n=len(a),
                            s_bias=float(x.mean()) if len(x) else None,
                            s_variance=float(x.var()) if len(x) else None,
                            s_RMS=float(np.sqrt(np.mean(x*x))) if len(x) else None,
                            range_bias_m=float(z.mean()) if len(z) else None,
                            range_variance_m2=float(z.var()) if len(z) else None,
                            range_RMS_m=float(np.sqrt(np.mean(z*z))) if len(z) else None))
    return out

def correlation_report(rows):
    out=[]
    for case in sorted({r["case"] for r in rows}|{"ALL"}):
        a=[r for r in rows if case=="ALL" or r["case"]==case]
        errors=np.array([abs(r["e_MP"]) for r in a],float)
        for k in ALL_FEATURES+["distance_m"]:
            vals=np.array([r[k] for r in a],float)
            v=measures(vals,errors)
            out.append(dict(case=case,feature=k,pearson_abs_eMP=v[0],spearman_abs_eMP=v[1],n=v[2]))
    return out

def proxy_cv(rows, outdir):
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss,roc_auc_score,average_precision_score
    groups=[("BASE_CONSTANT", []),("DISTANCE",["distance_m"]),
            ("DELAY",D_FEATURES),("POLARIZATION",P_FEATURES),
            ("DELAY+POL",sorted(set(D_FEATURES+P_FEATURES))),
            ("DISTANCE+DELAY+POL",["distance_m"]+sorted(set(D_FEATURES+P_FEATURES)))]
    report=[]
    for route in ("R2","R4","R5"):
        tr=[r for r in rows if r["route"]!=route]
        te=[r for r in rows if r["route"]==route]
        ytr=np.array([abs(r["e_MP"])>0.1 for r in tr],int)
        yte=np.array([abs(r["e_MP"])>0.1 for r in te],int)
        for label,feats in groups:
            if len(np.unique(ytr))<2 or not feats:
                proba=np.full(len(te),float(ytr.mean()))
            else:
                xx=np.array([[r.get(k,float("nan")) for k in feats] for r in tr],float)
                xt=np.array([[r.get(k,float("nan")) for k in feats] for r in te],float)
                model=make_pipeline(SimpleImputer(strategy="median",add_indicator=True),
                                    StandardScaler(),LogisticRegression(C=1,max_iter=2000))
                model.fit(xx,ytr)
                proba=model.predict_proba(xt)[:,1]
            report.append(dict(heldout_route=route,model=label,n_test=len(te),
                               prevalence=float(yte.mean()),brier=float(brier_score_loss(yte,proba)),
                               auroc=float(roc_auc_score(yte,proba)) if len(np.unique(yte))>1 else None,
                               auprc=float(average_precision_score(yte,proba)) if len(np.unique(yte))>1 else None,
                               high_conf_false_accept=float(np.mean((proba<0.2)&(yte==1)))))
    csv_write(outdir/"05_EXPLORATORY_CV_Es_PROXY.csv",report)
    return report

def probes(case, rows, station_groups):
    out=[]
    for gi,g in enumerate(station_groups):
        if len(g)<5:continue
        psi=np.array([rows[i]["yaw_deg"] for i in g],float)
        los=np.array([rows[i]["s_los"] for i in g],float)
        ep=np.array([rows[i]["e_MP"] for i in g],float)
        H=np.gradient(los,psi)
        for count,selected in [(1,[0]),(2,[0,2]),(3,[0,2,4])]:
            ix=np.array(selected,int)
            denom=float(np.dot(H[ix],H[ix]))
            if not np.isfinite(denom) or denom<1e-8:
                delta=float("nan");resid=float("nan")
            else:
                delta=float(np.dot(H[ix],ep[ix])/denom)
                resid=float(np.sqrt(np.mean((ep[ix]-H[ix]*delta)**2)))
            out.append(dict(case=case,route=case.split("_")[0],station_group_id=gi,
                       station_x=rows[g[0]]["x"],station_y=rows[g[0]]["y"],
                       probe_count=count,base_pose_id=rows[g[0]]["pose_id"],
                       angles_deg=";".join(str(psi[i]) for i in ix),
                       delta_linear_equiv_deg=delta,shape_residual_RMS=resid,
                       max_abs_slope_per_deg=float(np.max(np.abs(H[ix]))),
                       first_s_abs_mp_error=abs(ep[0]),
                       flagged_slope_low=bool(np.max(np.abs(H[ix]))<0.01)))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--no-classifier",action="store_true")
    args=ap.parse_args();outdir=args.out;outdir.mkdir(parents=True,exist_ok=True)
    status={"study":"EXPLORATORY_MATCHED_CHANNEL_DIAGNOSTIC","executed":False,
            "primary_RF_heading_label":"BLOCKED_BY_ORIGINAL_LUT_AND_V2_PRIOR",
            "actual_heading_accuracy":"NOT_MEASURED",
            "probe_operational_gain":"NOT_MEASURED",
            "oracle_local_apparent_heading_shift":"EXPLORATORY_ONLY",
            "source_code_commit":"codex/post-a23-evidence-20261010 @ 047cce2",
            "cases":[]}
    (outdir/"EXECUTION_STATUS.json").write_text(json.dumps(status,indent=2))
    assert FREQS.exists(),f"Missing {FREQS}"
    freq=np.load(FREQS)
    declared={i["case"]:i for i in json.loads((BLOCK/"CASES.json").read_text())}
    allrows=[]; allprobes=[]
    for case in CASES:
        hpath=BLOCK/"FULL_RF"/f"H_{case}.npy"
        lpath=BLOCK/f"H_LoS_{case}.npy"
        spath=BLOCK/case/"SAMPLES.json"
        for p in (hpath,lpath,spath):
            if not p.exists():raise FileNotFoundError(p)
        rec=declared[case]
        sha_h=sha256(hpath);sha_l=sha256(lpath);sha_s=sha256(spath)
        assert sha_h==rec["input_H_sha256"],(case,"full H SHA mismatch")
        assert sha_l==rec["H_sha256"],(case,"LoS H SHA mismatch")
        assert sha_s==rec["samples_sha256"],(case,"samples SHA mismatch")
        full=np.load(hpath,mmap_mode="r")
        los=np.load(lpath,mmap_mode="r")
        samples=json.loads(spath.read_text())
        assert full.shape==los.shape==(len(samples),257,2,2)
        a=observer(full,freq);b=observer(los,freq)
        print(f"PARITY_INPUT {case} poses={len(samples)} full_sha={sha_h[:12]} los_sha={sha_l[:12]}",flush=True)
        groups,sg=build_stations(samples)
        ax=rec["anchor_xyz"]
        z_rob=rec["robot_z"]
        d=np.sqrt((np.array([v["x"] for v in samples])-ax[0])**2+
                   (np.array([v["y"] for v in samples])-ax[1])**2+(ax[2]-z_rob)**2)
        case_rows=[]
        for j,pose in enumerate(samples):
            row={key:a["features"][key][j] for key in ALL_FEATURES}
            row.update(case=case,route=case.split("_")[0],pose_id=int(pose["pose_id"]),
                      station_group_id=int(sg[j]),x=float(pose["x"]),y=float(pose["y"]),
                      yaw_deg=float(pose["yaw_body_deg"]),distance_m=float(d[j]),
                      s_full=float(a["s"][j]),s_los=float(b["s"][j]),
                      e_MP=float(a["s"][j]-b["s"][j]),
                      range_error_m=float(a["range_m"][j]-d[j]),
                      fp_idx_full=int(a["fp"][j]),fp_idx_los=int(b["fp"][j]))
            case_rows.append(row)
        allrows.extend(case_rows)
        allprobes.extend(probes(case,case_rows,groups))
        status["cases"].append(dict(case=case,n_poses=len(samples),
                                    n_eligible_sweep=sum(len(g)>=5 for g in groups),
                                    full_H_SHA256=sha_h,los_H_SHA256=sha_l))
    csv_write(outdir/"01_CIR_FEATURES_AND_CHANNEL_LABELS_OFFLINE.csv",allrows,HEAD_COLS)
    csv_write(outdir/"02_DISTANCE_BIAS_VARIANCE.csv",summaries(allrows))
    correlations=correlation_report(allrows)
    csv_write(outdir/"03_CORRELATIONS_ABS_S_MISMATCH.csv",correlations)
    csv_write(outdir/"04_PROBE_LOCAL_LINEAR_DIAGNOSTICS.csv",allprobes)
    if not args.no_classifier:
        report=proxy_cv(allrows,outdir)
    else:report=[]
    summary_all=[s for s in summaries(allrows) if s["case"]=="ALL"]
    global_cor=sorted([r for r in correlations if r["case"]=="ALL"],
                      key=lambda r:abs(r["spearman_abs_eMP"]) if math.isfinite(r["spearman_abs_eMP"]) else -1,
                      reverse=True)
    num_groups=len(allprobes)//3
    p1=[r for r in allprobes if r["probe_count"]==1 and np.isfinite(r["delta_linear_equiv_deg"])]
    p3=[r for r in allprobes if r["probe_count"]==3 and np.isfinite(r["delta_linear_equiv_deg"])]
    summary={"total_poses":len(allrows),"n_cases":len(CASES),
             "number_station_case_instances":num_groups,
             "distance_stats_all":summary_all,
             "top_spearman_abs_eMP":global_cor[:15],
             "probe_linear_equivalent_abs_delta_median_deg":
                 {str(n):float(np.median([abs(r["delta_linear_equiv_deg"]) for r in allprobes
                            if r["probe_count"]==n and np.isfinite(r["delta_linear_equiv_deg"])]))
                  for n in [1,2,3]},
             "probe_3point_shape_RMS_median":float(np.median([r["shape_residual_RMS"] for r in p3])) if p3 else None,
             "classifier":report,
             "limitations":["All seven cases share one corridor geometry.",
                            "Full H complex coefficients only used to synthesize amplitude-only CIR.",
                            "Reference outcome is paired full-v-LoS s difference, NOT operational RF-heading accuracy.",
                            "Probe equivalent angles use true-pose-matched LoS curve: oracle local diagnostic.",
                            "No original fixed LUT or v2 prior was used; operational heading study BLOCKED.",
                            "No real hardware CIR availability proven."]}
    (outdir/"SUMMARY.json").write_text(json.dumps(summary,indent=2,allow_nan=False),encoding="utf-8")
    with (outdir/"SUMMARY_KO.md").open("w",encoding="utf-8") as f:
        f.write("# 기존 7케이스 CIR–편파 오차 탐색적 분석\n\n")
        f.write("이 결과는 full H와 동일 pose의 direct LoS H를 비교한 **s 채널 모델 불일치** 분석입니다. sensor-v2의 운용 가능 RF heading 정답이나 NEES를 계산한 결과가 아닙니다.\n\n")
        f.write(f"- 채널 수: {len(CASES)}개, RF pose: {len(allrows)}개, 동일 위치 yaw case-group: {num_groups}개.\n")
        f.write("- 아직 실행되지 않은 primary: fixed LUT 기반 역 heading, v2 prior-assisted heading, 보정된 reliability, 운용 probe gain.\n\n")
        f.write("## 거리별 e_MP 평균 및 분산\n\n| 거리 | 수 | 평균 편향 | 분산 | RMS |\n|---|---:|---:|---:|---:|\n")
        for v in summary_all:
            f.write(f"| {v['distance_bin']} | {v['n']} | {v['s_bias']:.5f} | {v['s_variance']:.5f} | {v['s_RMS']:.5f} |\n")
        f.write("\n## 상관성 (종속변수 = |s_full-s_LoS|)\n\n| 특징 | Pearson | Spearman | n |\n|---|---:|---:|---:|\n")
        for v in global_cor:
            f.write(f"| {v['feature']} | {v['pearson_abs_eMP']:+.4f} | {v['spearman_abs_eMP']:+.4f} | {v['n']} |\n")
        f.write("\n## 1/2/3점 국소 heading 등가오차 (oracle-reference)\n\n")
        for n,v in summary["probe_linear_equivalent_abs_delta_median_deg"].items():
            f.write(f"- {n}점: median |linear equivalent shift| = {v:.3f} deg\n")
        f.write("이 수치를 실제 heading correction 성능이라고 해석하면 안 됩니다. RF prior와 branch 선택이 포함되지 않았습니다.\n")
        if report:
            f.write("\n## 탐색적 e_MP>0.1 분류 (운용 heading reliability 결과 아님)\n\n| held-out route | features | Brier | AUC |\n|---|---|---:|---:|\n")
            for v in report:
                f.write(f"| {v['heldout_route']} | {v['model']} | {v['brier']:.4f} | {v['auroc'] if v['auroc'] is not None else 'NA'} |\n")
    status.update(executed=True,number_poses=len(allrows),probe_groups=num_groups,
                  raw_data_verified=True,covariates_online_possible_but_hardware_unverified=True,
                  report="SUMMARY_KO.md")
    (outdir/"EXECUTION_STATUS.json").write_text(json.dumps(status,indent=2),encoding="utf-8")
    print("SUMMARY_START",flush=True)
    print(json.dumps({k:v for k,v in summary.items() if k!="classifier"},ensure_ascii=False),flush=True)
    print("SUMMARY_END",flush=True)

if __name__=="__main__":
    main()
