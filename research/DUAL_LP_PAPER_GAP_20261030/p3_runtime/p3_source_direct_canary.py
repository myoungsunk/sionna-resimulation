#!/usr/bin/env python3
"""DLP P3 source-only direct-LoS third-anchor canary; NOT NEW NATIVE SIONNA RT.

Run only after immutable SHA-bound P3 source-only FROZEN and exact preflight plan.
39 original pilot poses * A/B/C 3 anchor source spectra = 117 computed rows.
Real original A/B native LoS H used for reference only; C measured/native H
does not exist. No new multipath ray trace, no learned corrections or EKF.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,pathlib,platform,sys,traceback,datetime,time
import numpy as np
ROOT=pathlib.Path.cwd()
LOCK=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P3_20261102"
P1=ROOT/"research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P1_20261101"
BANK=pathlib.Path(os.getenv("DLP_P3_BANK_DIR","/tmp/dlp_p3_banks"))
PREF=pathlib.Path(os.getenv("DLP_P3_PREFLIGHT","/tmp/dlp_p3_verified_preflight"))
OUT=pathlib.Path(os.getenv("DLP_P3_OUT","/tmp/dlp_p3_result"))
OUT.mkdir(parents=True,exist_ok=True)
START=time.monotonic()
C=299792458.
N=257
DF=1950000.
OFFSET=-.5315983906250129
SCENES=1
GATES={};ERR=[];OBS=[];LEDGER=[];SOURCE_H=[];SOURCE_KEYS=[];STAT={}
CONTRACT_SHA="24a5e0581c86a8b99659ebbea30b456fb79b6f4e88ee31860db04df85fafb588"
CFG_SHA="49658dc5532e990a9f8bc0968f96b46ce236167244762cbc817092ff34ce3fc8"
TOL_SHA="11a4adcdf15e7e884b4290e55b8e997b069ce9c8897902b0c41ca47983899b72"
AUDIT_SHA="c658b6e30ff6d5b5011a70333e14b1ddfe93d22406a8adc881b435e57537b202"
PLAN_SHA="efb9c7b1d91b865f143f8fa26fd3defb97eed02e385ee4137062ce336e9a0b61"
A=(4.,0.,2.65);B=(10.,0.,2.65);C3=(16.,.8,2.65)
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
      for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def J(path):return json.loads(pathlib.Path(path).read_text("utf-8"))
def gate(name,passed,note,measure=None):
    GATES[name]={"status":"PASS" if passed else "FAIL","note":str(note)}
    if measure is not None:GATES[name]["measured"]=measure
    print("P3_CANARY_GATE",name,GATES[name]["status"],str(measure)[:300],flush=True)
    if not passed:ERR.append(dict(id=name,reason=str(note),measure=measure))
def require(flag,msg):
    if not bool(flag):raise RuntimeError(msg)
def writetable(path,items,header):
    with pathlib.Path(path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=header,extrasaction="ignore")
        w.writeheader();w.writerows(items)
def independent_observer(h):
    """Independent 257 x 2 first-path observer, not O.observe or Source.batch."""
    h=np.asarray(h)
    require(h.ndim==3 and h.shape[1:]==(N,2),"INVALID_P3_TWO_RX_ONE_TX_H")
    window=.5-.5*np.cos(2*np.pi*np.arange(N)/(N-1))
    cir=np.fft.ifft(h*window[None,:,None],n=4*N,axis=1)*N
    a=np.abs(cir)
    strongest=a.max(axis=1).argmax(axis=1)
    envelope=a[np.arange(len(h)),:,strongest]
    peak=envelope.max(axis=1)
    tap=np.argmax(envelope>=.3*peak[:,None],axis=1)
    z=cir[np.arange(len(h)),tap,:]
    powr=(z*z.conj()).real
    den=powr.sum(axis=1)
    good=np.isfinite(den)&(den>0)&(peak>0)
    s=np.full(len(h),np.nan)
    s[good]=(powr[good,0]-powr[good,1])/den[good]
    r=tap*(C/((4*N)*DF))
    return dict(s=s,r=r,tap=tap,strongest=strongest,valid=good,power=powr)
def load_lock_and_preflight():
    rat=J(LOCK/"P3_FROZEN_SOURCE_ONLY_RATIFICATION.json")
    cfg=J(LOCK/"P3_CONFIG_LOCK.json")
    tol=J(LOCK/"P3_NUMERIC_TOLERANCES.json")
    dig={"P3_EXPERIMENT_CONTRACT_PROPOSER_LOCKED.md":CONTRACT_SHA,
         "P3_CONFIG_LOCK.json":CFG_SHA,"P3_NUMERIC_TOLERANCES.json":TOL_SHA}
    mismatch=[n for n,z in dig.items() if sha(LOCK/n)!=z]
    require(not mismatch,"P3_LOCKED_SCIENCE_SHA_CHANGED:"+str(mismatch))
    require(rat["status"]=="FROZEN_SOURCE_FFD_GEOMETRY_CANARY_ONLY" and
       all(rat["unchanged_proposer_hashes"][n]==d for n,d in dig.items()),
       "P3_RATIFICATION_BAD_OR_CHANGED")
    require(len(tol["tests"])==13 and cfg["scene"]["candidate_count"]==1,
       "P3_FIXED_TESTS_OR_CANDIDATE_CHANGED")
    audrat=rat["auditor_countersignature"]
    require(audrat["audit_sha256"]==AUDIT_SHA and
       audrat["pilot_plan_sha256"]==PLAN_SHA and audrat["auditor_run"]==41389798998,
       "P3_INDEPENDENT_PREFLIGHT_SHA_RATIFICATION_DRIFT")
    aud_file=PREF/"P3_PRE_RUN_AUDIT.json"
    plan_file=PREF/"P3_FROZEN_PILOT_SELECTION_PLAN.json"
    require(sha(aud_file)==AUDIT_SHA and sha(plan_file)==PLAN_SHA,
       "P3_PHYSICAL_PREAUDIT_OR_PLAN_RAW_BYTES_DRIFT")
    aud=J(aud_file);plan=J(plan_file)
    require(aud["status"]=="ACCEPT_SOURCE_CANARY_WITH_BOUNDARIES" and
       len(aud["checks"])==9 and not aud["errors"] and plan["n_pilot_pose"]==39,
       "P3_PREAUDIT_NOT_ACCEPTED")
    locked=J(P1/"P1_INPUT_LOCK.json")
    bad=[]
    for item in locked["base_assets"]:
        path=ROOT/item["path"]
        if not path.is_file() or sha(path)!=item["sha256"] or path.stat().st_size!=item["bytes"]:
            bad.append(item["path"])
    gate("P00_LOCK",not bad and not mismatch and cfg["source_p2"]["run"]==41315429738,
         "Exact P1 C0 physical bytes and frozen proposer plus separate-runner audit source lock",
         {"C0_asset_count":len(locked["base_assets"]),"failed_inputs":bad[:5]})
    require(not bad,"P3_C0_INPUT_SHA_MISSING")
    orig=J(ROOT/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json")
    refs={}
    for r in ("R2","R4","R5"):
        for name in ("A","B"):
            key=r+"_a"+name+"_m0"
            refs[(r,name)]=next(x for x in orig["cases"] if x["id"]==key)
    require(set(plan["routes"])=={"R2","R4","R5"} and
            {k:tuple(v) for k,v in plan["source_three_anchor_xyz"].items()}==
            {"A":A,"B":B,"C":C3},
            "P3_PLAN_GEOMETRY_CHANGED")
    bankpaths=[]
    for item in locked["ffd_bank_source"]["banks"]:
        got=list(BANK.rglob(item["filename"]))
        require(len(got)==1 and got[0].stat().st_size==item["bytes"] and sha(got[0])==item["sha256"],
                "P3_SOURCE_BANK_ACTUAL_BINARY_HASH_CHANGED:"+item["filename"])
        bankpaths.append(got[0])
    dest=ROOT.parent;bn={}
    for item,path in zip(locked["ffd_bank_source"]["banks"],bankpaths):
        tgt=dest/item["filename"]
        require(not tgt.exists() and not tgt.is_symlink(),"P3_FFD_PATH_ALREADY_STAGED")
        tgt.symlink_to(path)
        bn[item["filename"]]=item["sha256"]
    (dest/"BANK_MANIFEST.json").write_text(json.dumps({"npz_sha256":bn}))
    (dest/"ffd_p0p3/out").mkdir(parents=True,exist_ok=True)
    return cfg,rat,plan,aud,locked,refs,orig

def run():
    cfg,rat,plan,audit,locked,refs,orig=load_lock_and_preflight()
    sys.path.insert(0,str(ROOT/"research/FFD_P0P3_20261016"))
    sys.path.insert(0,str(ROOT/"research/EKF4_RANGE_S_STAGED_20261014"))
    import p0_initial
    from source_model import SourceFFD
    src=SourceFFD()
    require(np.array_equal(src.freqs,6250400000.+1950000.*np.arange(N)),
            "SOURCE_FREQUENCY_GRID_NOT_C0")
    gate("P05_REAL_BANK",True,"Verified actual FFD bank, exact 257 bins, no new EM export")
    anchor_map={"A":A,"B":B,"C":C3}
    gate("P02_GEOMETRY",math.isclose(2.4,.5*abs((B[0]-A[0])*(C3[1]-A[1])-
                          (B[1]-A[1])*(C3[0]-A[0])),abs_tol=1e-12),
         "Fixed candidate C noncollinear, triangle 2.4m^2, no posthoc search")
    dims=cfg["scene"]["room_xyz_m"]
    source_max_s_diff=0.;source_max_r_diff=0;source_tap_mismatch=0
    yaw_period_max=0.;nonfinite=0;power_invalid=0
    native_max_H=0.;native_max_s=0.;native_tap_mismatch=0;native_count=0
    offcap_direct_max=0.;offcap_count=0;cap_count=0
    rank_min=float(audit["statistics"]["overall"]["min_xy_range_jacobian_singular_value"])
    count_invalid_prism=0;original_timeline_bad=[];n_rows=0
    for route in ("R2","R4","R5"):
        ps=plan["routes"][route]
        require(len(ps)==13,"P3_OUTCOME_BLIND_POSE_IDS_NOT_13:"+route)
        original_timelines=next(a for a in locked["base_assets"] if a["kind"]=="TIMELINE_TNONE"
                                 and ("timeline_"+route+"_") in a["path"])
        with open(ROOT/original_timelines["path"],newline="") as f:
            timeline={int(r["pose_id"]):r for r in csv.DictReader(f)}
        for q in ps:
            raw=timeline.get(int(q["pose_id"]))
            if (raw is None or abs(float(raw["t_s"])-q["t_s"])>1e-9 or
                abs(float(raw["x"])-q["x_m"])>1e-10 or
                abs(float(raw["y"])-q["y_m"])>1e-10):
                original_timeline_bad.append((route,q["pose_id"]))
        x=np.array([[q["x_m"],q["y_m"],np.deg2rad(q["yaw_body_deg"]),0.]
                    for q in ps],dtype=float)
        xyz=np.column_stack([x[:,:2],np.full(len(x),.45)])
        yaw=np.degrees(x[:,2])
        for aname,anchor in anchor_map.items():
            case=(refs[(route,aname)].copy() if aname in ("A","B") else
                  dict(id=route+"_aC_m0_SOURCE_ONLY",route=route,anchor=list(anchor),mount_deg=0,
                       robot_z_m=.45))
            pred,J,diag=src.batch(x,case,gradient=True,return_diagnostics=True)
            hc=src.physical_h_col(x,case)
            ob=independent_observer(hc)
            require(hc.shape==(len(ps),N,2) and J.shape==(len(ps),2,4),
                    "P3_SOURCE_H_OBSERVER_DIMENSION_ERROR:"+route+aname)
            nonfinite+=int(np.count_nonzero(~np.isfinite(hc).all(axis=(1,2))))
            nonfinite+=int(np.count_nonzero(~np.isfinite(pred).all(axis=1)))
            power_invalid+=int(np.count_nonzero(~ob["valid"]))
            source_max_s_diff=max(source_max_s_diff,float(np.max(abs(pred[:,1]-ob["s"]))))
            source_max_r_diff=max(source_max_r_diff,float(np.max(abs(diag["native_range"]-ob["r"]))))
            source_tap_mismatch+=int(np.count_nonzero(diag["tap"]!=ob["tap"]))
            p=src.batch(x+np.array([0,0,2*np.pi,0]),case,gradient=False,return_diagnostics=True)
            yaw_period_max=max(yaw_period_max,float(np.max(abs(pred[:,1]-p[0][:,1]))))
            direction=xyz-np.asarray(anchor)[None,:]
            dist=np.linalg.norm(direction,axis=1)
            off=np.degrees(np.arctan2(np.hypot(direction[:,0],direction[:,1]),
                                     np.abs(direction[:,2])))
            direct=p0_initial.direct(src.banks,xyz,yaw,list(anchor))
            direct_h=direct[:,:,:,0]
            rel=np.linalg.norm((hc-direct_h).reshape(len(ps),-1),axis=1)/np.maximum(
                np.linalg.norm(direct_h.reshape(len(ps),-1),axis=1),1e-300)
            offcap=off>=.8
            offcap_count+=int(np.count_nonzero(offcap))
            cap_count+=int(np.count_nonzero(~offcap))
            if np.any(offcap):offcap_direct_max=max(offcap_direct_max,float(np.max(rel[offcap])))
            n_href=np.full(len(ps),np.nan)
            ns_ref=np.full(len(ps),np.nan)
            nt_ref=np.full(len(ps),-1,dtype=int)
            if aname in ("A","B"):
                path=ROOT/case["los_path"]
                original_h=np.load(path,mmap_mode="r",allow_pickle=False)
                source_indices=np.asarray([int(q["pose_id"]) for q in ps],dtype=int)
                oh=np.asarray(original_h[source_indices,:,:,0])
                no=independent_observer(oh)
                n_href=np.linalg.norm((oh-hc).reshape(len(ps),-1),axis=1)/np.maximum(
                     np.linalg.norm(oh.reshape(len(ps),-1),axis=1),1e-300)
                ns_ref=abs(no["s"]-pred[:,1])
                nt_ref=no["tap"]
                native_max_H=max(native_max_H,float(np.max(n_href)))
                native_max_s=max(native_max_s,float(np.max(ns_ref)))
                native_tap_mismatch+=int(np.count_nonzero(nt_ref!=diag["tap"]))
                native_count+=len(ps)
            # Independently check all direct ray segments only against original
            # *empty rectangular prism*. Does not guarantee robot body occlusion.
            for i,q in enumerate(ps):
                point=xyz[i]
                for t in np.linspace(0,1,11):
                    pp=point*(1-t)+np.asarray(anchor)*t
                    if not all(dims[k][0]-1e-10<=pp[k2]<=dims[k][1]+1e-10
                         for k2,k in enumerate(("x","y","z"))):
                        count_invalid_prism+=1
                        LEDGER.append(dict(route=route,pose_id=q["pose_id"],anchor=aname,
                                           type="RAY_OUTSIDE_EMPTY_PRISM",note="Geometry not valid"))
            for i,q in enumerate(ps):
                if not ob["valid"][i]:
                    LEDGER.append(dict(route=route,pose_id=q["pose_id"],anchor=aname,
                                       type="INVALID_SOURCE_POWER",note="No finite first-path power"))
                if off[i]<.8:
                    LEDGER.append(dict(route=route,pose_id=q["pose_id"],anchor=aname,
                                       type="NEAR_POLE_SOURCE_ONLY_CAP",note="Direct source FFT comparison marked diagnostic, not native RT"))
                if aname=="C":
                    SOURCE_H.append(hc[i])
                    SOURCE_KEYS.append(dict(source_array_row=len(SOURCE_H)-1,route=route,pose_id=q["pose_id"],
                                       t_s=q["t_s"],channel_class="SOURCE_ONLY_1_RAY_NOT_NATIVE_RT",
                                       anchor="C",tensor_shape="[257,2] one TX +45 two RX +/-45"))
                row=dict(route=route,pose_id=q["pose_id"],timeline_t_s=q["t_s"],
                         anchor_id=aname,x_m=q["x_m"],y_m=q["y_m"],yaw_body_deg=q["yaw_body_deg"],
                         source_case=case["id"],x_anchor_m=anchor[0],y_anchor_m=anchor[1],z_anchor_m=anchor[2],
                         distance_m=float(dist[i]),off_boresight_deg=float(off[i]),
                         full_pose_source="C0_original_Tnone",geometry_direct_path_count_by_definition=1,
                         native_RT_paths_measured="NOT_RUN",physical_THIRD_C_packet_exists=False if aname=="C" else True,
                         h_s_source=float(pred[i,1]),h_r_continuous_m=float(pred[i,0]),
                         first_path_raw_r_m=float(ob["r"][i]),first_path_s_signed=float(ob["s"][i]),
                         first_tap=int(ob["tap"][i]),strong_rx_port=int(ob["strongest"][i]),
                         source_tap=int(diag["tap"][i]),source_first_path_margin=float(diag["fp_margin"][i]),
                         source_analytic_Hs_x=float(J[i,1,0]),source_analytic_Hs_y=float(J[i,1,1]),
                         source_analytic_Hs_psi=float(J[i,1,2]),source_analytic_Hs_bg=float(J[i,1,3]),
                         native_los_present=aname in ("A","B"),
                         native_s_abs_error=float(ns_ref[i]) if aname!="C" else "",
                         native_complex_H_rel_error=float(n_href[i]) if aname!="C" else "",
                         native_tap=int(nt_ref[i]) if aname!="C" else "",
                         offpole_independent_source_H_rel=float(rel[i]) if offcap[i] else "",
                         cap_or_pole_marker="SOURCE_ONLY_NEAR_POLE" if not offcap[i] else "OFF_POLE_VERIFIED",
                         source_detector_s_diff=float(pred[i,1]-ob["s"][i]),
                         source_detector_r_diff=float(diag["native_range"][i]-ob["r"][i]),
                         no_measured_third_RF="C_MISSING" if aname=="C" else "A_B_NATIVE_EXISTS")
                OBS.append(row);n_rows+=1
            print("P3_SOURCE_PILOT",route,aname,"n",len(ps),
                  "native",aname!="C","offpole",int(offcap.sum()),flush=True)
    # Original all-route rank preflight is part of signed pre-run input.
    gate("P01_TIME_POSE",not original_timeline_bad and
         len({(r["route"],r["pose_id"],r["anchor_id"]) for r in OBS})==117,
         "All 39 original timeline pilot IDs map exactly, 3 anchors each",{"bad":original_timeline_bad[:5]})
    gate("P03_LOS_PRISM",count_invalid_prism==0,
         "Every selected ray stays inside the empty C0 corridor prism; no other occluder modeled",
         {"invalid_ray_intersections":count_invalid_prism})
    gate("P04_RANGE_GEOMETRY",rank_min>1e-9 and float(audit["statistics"]["overall"]["max_FD_distance_error"])<=1e-8,
         "Original 3136 timeline 3-anchor XY range geometry full rank and independent FD",
         {"min_singular_value":rank_min,"n_orig_timeline":3136,
          "max_range_jac_fd":audit["statistics"]["overall"]["max_FD_distance_error"]})
    gate("P06_OLD_AB_NATIVE",native_count==78 and native_max_H<=5e-4 and native_max_s<=2e-5 and
         native_tap_mismatch==0,
         "Original 78 A/B pilot Native LoS actual RF H and SourceFFD stay within predeclared engineering parity",
         {"n":native_count,"max_H_rel":native_max_H,"max_s_abs":native_max_s,"tap_mismatch":native_tap_mismatch})
    gate("P07_C_DIRECT_ORACLE",offcap_count>=8 and offcap_direct_max<=1e-9 and nonfinite==0,
         "New C direct-only source FFD and independent vector field match away from the source cap",
         {"n_total_offpole_AB_C":offcap_count,"cap_flagged_all_anchors":cap_count,
          "max_direct_H_rel":offcap_direct_max,"nonfinite":nonfinite})
    gate("P08_R_S_CHAIN",source_max_s_diff<=1e-9 and source_max_r_diff<=1e-9 and
         source_tap_mismatch==0 and power_invalid==0,
         "Independent Hann 257/N-1+1028 FFT strongestRX30% common tap vs pinned SourceFFD for every source-only H",
         {"n":n_rows,"max_s_abs":source_max_s_diff,"max_r_abs_m":source_max_r_diff,
          "tap_mismatch":source_tap_mismatch,"invalid_power":power_invalid})
    gate("P09_CAP_AND_PERIOD",yaw_period_max<=1e-10 and nonfinite==0,
         "Yaw +2π invariance with the fixed new anchor and existing A/B; source near-pole cap explicitly marked",
         {"yaw_period_max_abs_s":yaw_period_max,"near_pole_markers":cap_count})
    gate("P10_ALL_ROWS",n_rows==117 and len(SOURCE_H)==39 and len(SOURCE_KEYS)==39,
         "39 fixed geometry pilot poses × 3 anchors; no omissions; C physical data source-only",
         {"all_rows":n_rows,"new_C_H_257x2_rows":len(SOURCE_H),"ledger_rows":len(LEDGER)})
    gate("P11_RESOURCE",not cfg["resource_policy"]["new_raytrace_budget_approved"] and
         not cfg["pilot"]["anchor_c_observed_native_los_h_available"],
         "No fabricated native C RT paths or synchronized third-anchor packets; P4 not unlocked",
         {"real_C_RT_packets":0,"C_direct_only_pilot_rows":len(SOURCE_H),
          "ratio_future_3tx_to_1tx_resources":3})
    # P12 output complete only after writing table and manifest.
    writetable(OUT/"P3_SOURCE_ONLY_OBSERVER_ROWS.csv",OBS,list(OBS[0]))
    writetable(OUT/"P3_C_SOURCE_ONLY_ARRAY_KEYS.csv",SOURCE_KEYS,list(SOURCE_KEYS[0]))
    writetable(OUT/"P3_BOUNDARY_AND_INVALID_LEDGER.csv",LEDGER,
               ["route","pose_id","anchor","type","note"])
    new_H=np.asarray(SOURCE_H,dtype=np.complex128)
    require(new_H.shape==(39,257,2),"P3_THIRD_SOURCE_H_SHAPE_INVALID")
    np.save(OUT/"P3_C_SOURCE_ONLY_H_39_POSES.npy",new_H,allow_pickle=False)
    # Geometry ledger and provenance separate from any future RF to prevent
    # users treating new synthetic source H as Sionna multipath.
    STAT.update(dict(original_scene="C0_CORRIDOR_ONE_SCENE",original_rf_anchor_ids=["A","B"],
       new_anchor_geometry_C=[16,.8,2.65],new_C_H_type="SOURCE_FFD_DIRECT_1_RAY_NO_NATIVE_SIONNA_RT",
       original_native_A_B_checked=78,n_pilot_pose=39,n_all_source_anchor_rows=117,
       C_new_source_model_H_shape=list(new_H.shape),
       C_original_native_H_count=0,C_native_RT_path_count=None,
       C_synchronized_physical_packet_count=0,
       canary_source_path_count_by_definition=1,
       actual_RT_canary_status="NOT_RUN_SEPARATE_BUDGET_NOT_APPROVED",
       p4_bulk="BLOCKED_MISSING_NATIVE_C_H_AND_CLOCKS",
       A_B_complex_max_relative=native_max_H,A_B_s_max_abs=native_max_s,
       A_B_first_path_mismatch=native_tap_mismatch,
       source_direct_offpole_max_relative=offcap_direct_max,
       independent_source_s_detector_max_abs=source_max_s_diff,
       first_path_mismatches=source_tap_mismatch,
       min_H_3anchor_XY_singular_value=rank_min,
       source_near_pole_cap_markers=cap_count,
       unknown_sync="Original C0 trajectory label alignment only, not measured multianchor clock sync",
       independent_scene_count=SCENES))
    (OUT/"P3_GEOMETRY_AND_SOURCE_SUMMARY.json").write_text(json.dumps(STAT,indent=2,allow_nan=False)+"\n")
    gate("P12_OUTPUT",all((OUT/name).is_file() for name in
         ["P3_SOURCE_ONLY_OBSERVER_ROWS.csv","P3_C_SOURCE_ONLY_ARRAY_KEYS.csv",
          "P3_BOUNDARY_AND_INVALID_LEDGER.csv","P3_C_SOURCE_ONLY_H_39_POSES.npy",
          "P3_GEOMETRY_AND_SOURCE_SUMMARY.json"]),
         "Outputs are reproducible append-only labels and explicit source-only C H")
    # Explicit full P3 source gates T00-T12 represented by P00-P12.
    require(len(GATES)==13,"P3_13_GATES_NOT_COMPLETE")
    return

if __name__=="__main__":
    try:run()
    except BaseException as ex:
       ERR.append(dict(id="RUNNER_EXCEPTION",reason=repr(ex),traceback=traceback.format_exc()))
       print("P3_SOURCE_CANARY_FATAL",repr(ex),traceback.format_exc(),flush=True)
    status="PASS_SOURCE_ONLY_CANARY" if not ERR and len(GATES)==13 else "FAIL_OR_BLOCKED_SOURCE_ONLY"
    result={"schema":"DLP_P3_C0PLUS_SOURCE_ONLY_PHYSICAL_CANARY_V1",
       "contract_id":"DLP-EKF-GAPS-001/P3-V1",
       "science_scope":"SOURCE_FFD_DIRECT_ONLY_NO_NATIVE_RAYTRACING",
       "status":status,
       "native_physical_rt_status":"NOT_RUN_BUDGET_NOT_APPROVED",
       "full_P3_native_rt_claim":"NOT_SUPPORTED",
       "P4_3anchor_replay":"BLOCKED",
       "contract_sha256":CONTRACT_SHA,"config_sha256":CFG_SHA,"tol_sha256":TOL_SHA,
       "exact_audit_sha256":AUDIT_SHA,"exact_pilot_plan_sha256":PLAN_SHA,
       "science_code_sha256":sha(__file__),
       "checks":GATES,"failures":ERR,"summary":STAT,
       "actor":"GPT-6 authored source-only canary, GitHub Actions separate runner",
       "human_independent_review":False,
       "one_original_corridor_scene":True,
       "run_id":os.environ.get("GITHUB_RUN_ID"),"runner_sha":os.environ.get("GITHUB_SHA"),
       "runtime_sec":time.monotonic()-START,"runtime":platform.platform(),
       "numpy_version":np.__version__,
       "allowed_paper_claim":"A new geometrically feasible third anchor can be evaluated using original FFD source-only direct LoS; requires independent Sionna full-H and calibrated synchronization before multianchor efficacy assessment.",
       "forbidden_claims":["third anchor measured packets","native Sionna raytraced path count",
        "Full multipath improvement","3 independent scene environments","P4 filter advantage"]}
    (OUT/"P3_SOURCE_ONLY_EXECUTION_QA.json").write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("P3_SOURCE_CANARY_FINAL",status,"GATES",len(GATES),
          "FAIL",len(ERR),"ROWS",len(OBS),"C_ROWS",len(SOURCE_H),flush=True)
    sys.exit(0 if status=="PASS_SOURCE_ONLY_CANARY" else 1)
