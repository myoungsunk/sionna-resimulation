#!/usr/bin/env python3
"""Frozen original-23 G3 ray forensic + source H parity + hypothetical H sensitivity.
Read-only original data. Strict 5e-14s, relaxed 2e-13s, class tie 1e-13s.
NO correction of original trace or H; NO RT regeneration. SELF_REVIEW_ONLY.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path
import zipfile

import numpy as np
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.paths import _classes, path_residuals, TIE_S
from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, tag_of
from qclean_uwb.features.reflection_attribution import image_delays

C0 = 299792458.0
STRICT = 5e-14
RELAXED = 2e-13
ZIP_SHA = "4f625c84172fecd7539273eb8d19c841fd2eb204b61d9062a3b901cca6dc4a62"
BANK_SHA = {"LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
            "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"}
H_SHA = {"R2_aB": "b3b4c61e23286b86c78b6e87f5b9b5358121cbde7717bae73e5650cc900b546c",
         "R4_aA": "73cfc35ded71b0114d3b15d2a50dba4a804b377d7b3b2b37aafe11c628c83956",
         "R4_aB": "30743ca017615bbfede78a8350739262a756d47ac2213c60b08eb109cebfe1b0",
         "R5_aA": "026a2c5ebb17916633f74d767ec8675f9358c93f8a4ee0df465733838ec89f80",
         "R5_aB": "a4858372414f81156b25fde2e14d57fc0e1a3f987782a5b268dbdf14bcf174b3"}
ROOT = Path("results/DRIVE_SIM_20261007")
BLOCK = ROOT / "POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
HERE = Path(__file__).resolve().parent
DELIVERY = HERE / "original_source_delivery_20261029"
PLANES = {"floor": (2, 0.), "ceiling": (2, 2.7), "wall_y_neg": (1, -1.2),
          "wall_y_pos": (1, 1.2), "end_x_min": (0, 0.), "end_x_max": (0, 20.)}

def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()

def sha_file(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def image_candidates(tx, rx):
    # Independent geometric implementation, equal to the source image-method candidate table.
    tab = {(): float(np.linalg.norm(tx - rx)) / C0}
    for depth in (1, 2, 3):
        for seq in itertools.product(PLANES, repeat=depth):
            if any(a == b for a, b in zip(seq, seq[1:])):
                continue
            img = np.array(rx, dtype=float)
            for name in reversed(seq):
                ax, val = PLANES[name]
                img[ax] = 2 * val - img[ax]
            tab[seq] = float(np.linalg.norm(tx - img)) / C0
    return tab

def observation(h, freqs):
    # Reproduce the archived native first-path detector; this is not a new detector.
    n = len(freqs)
    require(h.shape == (n, 2, 2), "ERR_H_OBS_SHAPE")
    win = .5 - .5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))
    padded = np.zeros((4*n, 2), dtype=complex)
    padded[:n] = h[:, :, 0] * win[:, None]
    cir = np.fft.ifft(padded, axis=0) * n
    mag = np.abs(cir)
    port = int(np.argmax(np.max(mag, axis=0)))
    tap = int(np.flatnonzero(mag[:, port] >= .3 * mag[:, port].max())[0])
    pp = np.abs(cir[tap])**2
    require(float(pp.sum()) > 0, "ERR_OBS_ZERO_POWER")
    return dict(tap=tap, port=port,
                r_m=float(tap * C0 / (4*n*(freqs[1]-freqs[0]))),
                s=float((pp[0]-pp[1])/pp.sum()))

def emit_csv(path, rows):
    require(bool(rows), "ERR_EMPTY_CSV_" + path.name)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def main(out_dir, bank_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    original_zip = DELIVERY / "G3_ORIGINAL_23_TRACE_PAIRS.zip"
    require(sha_file(original_zip) == ZIP_SHA, "ERR_ZIP_SHA")
    lock = json.loads((HERE / "G3_23_ORIGINAL_SOURCE_LOCK.json").read_text())
    require(len(lock["items"]) == 23 and TIE_S == 1e-13, "ERR_FROZEN_CONTRACT")
    with zipfile.ZipFile(original_zip) as z:
        require(z.testzip() is None, "ERR_ZIP_CRC")
        manifest = json.loads(z.read("G3_REQUESTED_SOURCE_MANIFEST.json"))
        expected = {i["path"]:i for i in manifest["items"]}
        require(len(expected) == 46 and set(z.namelist()) == set(expected)|{"G3_REQUESTED_SOURCE_MANIFEST.json"}, "ERR_ZIP_MEMBERS")
        for p, item in expected.items():
            b = z.read(p)
            require(sha_bytes(b) == item["sha256"] and len(b) == item["size"], "ERR_RAW_FILE_SHA " + p)
        sources = {}
        for item in lock["items"]:
            case, tag, p = item["case"], item["tag"], item["original_relpath"]
            receipt_path = p.replace("_trace.npz", "_trace_receipt.json")
            receipt_raw = z.read(receipt_path)
            require(sha_bytes(receipt_raw) == item["expected_original_receipt_sha256"], "ERR_HIST_RECEIPT_SHA " + case + tag)
            receipt = json.loads(receipt_raw)
            raw_npz = z.read(p)
            with np.load(io.BytesIO(raw_npz), allow_pickle=False) as d:
                trace = {k: d[k] for k in d.files}
            trace["status"] = str(trace["status"].item())
            require(trace["status"] == receipt["status"] == "OK", "ERR_TRACE_STATUS " + case+tag)
            tau = np.asarray(trace["tau"], dtype=float)
            require(len(tau) == int(receipt["n_paths"]) and tau.ndim == 1 and np.isfinite(tau).all(), "ERR_TRACE_TAU " + case+tag)
            require(trace["jones"].shape == (receipt["n_nodes"], len(tau), 3, 3) and np.isfinite(trace["jones"]).all(), "ERR_JONES " + case+tag)
            require(trace["ang"].shape == (4,len(tau)) and trace["present"].shape == (receipt["n_nodes"],len(tau)), "ERR_SHAPES " + case+tag)
            require(float(trace["x"]) == receipt["x"] and float(trace["y"]) == receipt["y"] and tag_of(receipt["x"],receipt["y"]) == tag, "ERR_COORD " + case+tag)
            require(int(trace["unmatched"]) == int(receipt["unmatched_paths"]) == int(item["expected_n_strict_paths"]), "ERR_RECEIPT_UNMATCHED " + case+tag)
            sources[(case,tag)] = (trace, receipt, sha_bytes(raw_npz), item["expected_original_receipt_sha256"])
    require(len(sources) == 23, "ERR_NOT_23")

    bank = []
    for name in ("LP_plus45_bank.npz","LP_minus45_bank.npz"):
        f = Path(bank_dir) / name
        require(sha_file(f) == BANK_SHA[name], "ERR_BANK_SHA " + name)
        with np.load(f,allow_pickle=False) as d:
            bank.append(P.Bank({k:d[k] for k in d.files}))
    require(len(bank[0].freqs_hz) == 257 and np.array_equal(bank[0].freqs_hz,bank[1].freqs_hz), "ERR_BANK_FREQ")
    freqs = bank[0].freqs_hz

    poses = {}
    for route in ("R2","R4","R5"):
        pos = json.loads((ROOT / "S1/routes" / ("rf_poses_"+route+".json")).read_text())
        require(all(int(x["pose_id"]) == i for i,x in enumerate(pos)), "ERR_POSE_IDS_" + route)
        poses[route] = pos
    ledger = list(csv.DictReader((HERE / "G3_48_H_ROW_CONDITIONAL_SCOPE.csv").open()))
    scoped = {(r["route_anchor"],r["trace_tag"]):int(r["pose_id"]) for r in ledger}
    require(set(scoped) == set(sources)|{("R2_aA","x3.7036_y-0.5204")}, "ERR_POSE_SCOPE")

    rows=[]; parity=[]; sensitivity=[]
    h_cache={}
    for case in sorted(H_SHA):
        h_file = BLOCK / "FULL_RF" / ("H_"+case+"_m0.npy")
        require(sha_file(h_file) == H_SHA[case], "ERR_FROZEN_H_SHA "+case)
        h = np.load(h_file, mmap_mode="r",allow_pickle=False)
        expect_n = {"R2":1303,"R4":922,"R5":1883}[case[:2]]
        require(h.shape == (expect_n,257,2,2), "ERR_H_SHAPE "+case)
        h_cache[case]=h
    for (case,tag),(trace,receipt,raw_sha,receipt_sha) in sorted(sources.items()):
        tau = np.asarray(trace["tau"],float)
        tx = np.array([4. if case.endswith("aA") else 10.,0.,2.65])
        rx = np.array([float(trace["x"]),float(trace["y"]),.45])
        independent = image_candidates(tx,rx)
        project = image_delays(tx,rx,20.,1.2,2.7)
        require(set(independent) == set(project) and max(abs(independent[s]-project[s]) for s in project)<1e-21, "ERR_IMAGE_METHOD_PARITY "+case+tag)
        image_names=list(independent)
        image_taus=np.array([independent[s] for s in image_names])
        classes, class_names = _classes(project)
        source_res, source_pick, _, _ = path_residuals(tau,tx,rx,20.,1.2,2.7)
        class_pick = np.abs(tau[:,None]-classes[None,:]).argmin(axis=1)
        raw_pick = np.abs(tau[:,None]-image_taus[None,:]).argmin(axis=1)
        raw_res = np.abs(tau-image_taus[raw_pick])
        require(np.allclose(source_res,np.abs(tau-classes[class_pick]),rtol=0,atol=1e-22), "ERR_CLASS_RES_PARITY "+case+tag)
        bad = np.flatnonzero(source_res > STRICT)
        require(len(bad) == int(receipt["unmatched_paths"]), "ERR_ORIG_G3_REPRO "+case+tag)
        require(not np.any(source_res > RELAXED), "ERR_RELAXED_G3_UNEXPECTED "+case+tag)

        pose_id = scoped[(case,tag)]
        pose = poses[case[:2]][pose_id]
        require(tag_of(pose["x"],pose["y"]) == tag, "ERR_POSE_TAG "+case+tag)
        require(abs(float(pose["x"])-rx[0])<1e-7 and abs(float(pose["y"])-rx[1])<1e-7, "ERR_TRACE_POSE "+case+tag)
        base = h_cache[case][pose_id]
        yaw = float(pose["yaw_body_deg"])
        replay = h_for_antenna_yaws(trace,bank,[yaw])[0]
        max_abs = float(np.max(np.abs(replay-base)))
        max_rel = max_abs/max(float(np.max(np.abs(base))),1e-30)
        l2_rel = float(np.linalg.norm(replay-base)/max(np.linalg.norm(base),1e-30))
        require(max_rel <= 5e-9 and l2_rel <= 5e-9, "ERR_H_SOURCE_NO_PARITY "+case+tag+" rel="+str(max_rel))
        parity.append(dict(case=case,tag=tag,pose_id=pose_id,n_paths=len(tau),n_nodes=int(receipt["n_nodes"]),n_bad=len(bad),
                           original_npz_sha256=raw_sha,receipt_sha256=receipt_sha,stored_H_sha256=H_SHA[case],
                           original_H_max_abs=max_abs,original_H_relative_max=max_rel,original_H_relative_l2=l2_rel))
        patched_trace = dict(trace);patched_tau=np.array(tau,copy=True)
        for i in bad:
            use=int(raw_pick[i])
            patched_tau[i]=image_taus[use]
            seq=image_names[use]
            cseq=class_names[int(class_pick[i])]
            ulp=float(abs(np.spacing(np.float32(tau[i]))))
            delta_u=float(raw_res[i]);delta_c=float(source_res[i])
            category = "TIE_CLASS_ARTIFACT" if delta_u<=STRICT else "UNMERGED_STRICT_EXCESS_UNRESOLVED"
            rows.append(dict(case=case,tag=tag,pose_id=pose_id,ray_index=int(i),n_paths=len(tau),
                  tau_source_dtype=str(np.asarray(trace["tau"]).dtype),tau_source_s=float(tau[i]),
                  image_nearest_s=float(image_taus[use]),image_best_sequence=">".join(seq) if seq else "LOS",
                  image_class_nearest_s=float(classes[int(class_pick[i])]),image_best_class=cseq,
                  residual_unmerged_s=delta_u,residual_merged_s=delta_c,
                  residual_float32_ulp_s=ulp,unmerged_residual_in_ulp=float(delta_u/max(ulp,1e-30)),
                  source_tau_float32_roundtrip_s=abs(float(tau[i])-float(np.float32(tau[i]))),
                  image_float32_last_cast_s=abs(float(image_taus[use])-float(np.float32(image_taus[use]))),
                  image_to_class_rep_s=abs(float(image_taus[use])-float(classes[int(class_pick[i])])),
                  strict_unmerged_pass=bool(delta_u<=STRICT),strict_merged_pass=False,
                  label=category,original_npz_sha256=raw_sha))
        patched_trace["tau"]=patched_tau
        hyp=h_for_antenna_yaws(patched_trace,bank,[yaw])[0]
        d=hyp-replay
        obs0=observation(base,freqs);obs1=observation(base+d,freqs)
        ds=float(obs1["s"]-obs0["s"]);dr=float(obs1["r_m"]-obs0["r_m"])
        sensitivity.append(dict(case=case,tag=tag,pose_id=pose_id,n_bad=len(bad),
               hypothetical_adjustment="all G3-bad tau -> nearest UNMERGED image delay, not a physical fix",
               h_rel_l2=float(np.linalg.norm(d)/max(np.linalg.norm(base),1e-30)),
               h_rel_max=float(np.max(np.abs(d))/max(np.max(np.abs(base)),1e-30)),
               h_max_abs=float(np.max(np.abs(d))),ds=ds,dr_m=dr,
               tap_before=obs0["tap"],tap_after=obs1["tap"],port_before=obs0["port"],port_after=obs1["port"],
               s_before=obs0["s"],s_after=obs1["s"],r_before_m=obs0["r_m"],r_after_m=obs1["r_m"],
               packet_r_s_tolerance_pass=(abs(ds)<=1e-12 and abs(dr)<=1e-9),
               original_H_rel_max=max_rel))
        print("STATION "+json.dumps({"case":case,"tag":tag,"n_bad":len(bad),"pose_id":pose_id,"h_parity":max_rel,"dH_hyp_rel_l2":sensitivity[-1]["h_rel_l2"],"ds_hyp":ds,"dr_hyp_m":dr},separators=(",",":")),flush=True)
    require(len(rows)==25 and len(parity)==23 and len(sensitivity)==23,"ERR_EXPECTED_COUNTS")
    counts=dict(collections.Counter(r["label"] for r in rows))
    summary=dict(status="TECHNICAL_SOURCE_PARITY_COMPLETE_NOT_PHYSICAL_GROUND_TRUTH",
        zip_sha256=ZIP_SHA,source_head=os.getenv("GITHUB_SHA","UNKNOWN"),
        code_sha256=sha_file(Path(__file__)),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        n_source_npz=23,n_original_receipts=23,n_strict_merged_excess=25,
        n_h_source_reconstructed=23,
        original_g3_strict_s=STRICT,original_g3_relaxed_s=RELAXED,original_class_tie_s=TIE_S,
        category_counts=counts,per_case_counts=dict(collections.Counter(r["case"] for r in rows)),
        n_unmerged_excess=sum(r["residual_unmerged_s"]>STRICT for r in rows),
        max_unmerged_s=max(r["residual_unmerged_s"] for r in rows),
        max_merged_s=max(r["residual_merged_s"] for r in rows),
        max_H_source_parity_relative=max(x["original_H_relative_max"] for x in parity),
        max_hyp_H_rel_l2=max(x["h_rel_l2"] for x in sensitivity),
        max_hyp_abs_ds=max(abs(x["ds"]) for x in sensitivity),
        max_hyp_abs_dr_m=max(abs(x["dr_m"]) for x in sensitivity),
        n_hyp_first_tap_changed=sum(x["tap_before"]!=x["tap_after"] for x in sensitivity),
        n_hyp_port_changed=sum(x["port_before"]!=x["port_after"] for x in sensitivity),
        n_hyp_packet_outside_tolerance=sum(not x["packet_r_s_tolerance_pass"] for x in sensitivity),
        # TECHNICAL REPRODUCTION != PHYSICAL CORRECTNESS
        strict_g3_verdict="FAIL_REPRODUCED",
        H_source_lineage="23/23 SHA-locked saved H rows reconstructed with original Jones and bank",
        H_physical_validity="NOT_DETERMINED_BY_SOURCE_PARITY",
        modification_to_source=False,RT_regenerated=False,BB_MB_reexecuted=False,
        science_release=False,independent_auditor=False,
        note="Hypothetical counterfactual image-delay change is NOT validated physical correction; missing bounce-vertex/Sionna internal precision evidence may limit physical attribution.")
    emit_csv(out/"G3_25_RAY_LEDGER.csv",rows)
    emit_csv(out/"G3_23_H_PARITY.csv",parity)
    emit_csv(out/"G3_23_H_HYPOTHETICAL_SENSITIVITY.csv",sensitivity)
    (out/"G3_AUDIT_QA.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n")
    (out/"G3_RAY_LEDGER.json").write_text(json.dumps(rows,indent=2,ensure_ascii=False)+"\n")
    print("G3_FINAL_SUMMARY "+json.dumps(summary,separators=(",",":"),ensure_ascii=False),flush=True)
    for row in rows:
        print("G3_RAY "+json.dumps({k:row[k] for k in ("case","tag","ray_index","label","residual_unmerged_s","residual_merged_s","image_best_sequence","image_best_class","unmerged_residual_in_ulp")},separators=(",",":")),flush=True)

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--bank-dir",type=Path,required=True)
    args=ap.parse_args()
    main(args.out,args.bank_dir)
