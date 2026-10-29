#!/usr/bin/env python3
"""One-ray counterfactual using original stored Jones, original FFD, original H.
Not a replacement for Sionna rerun or physical ground truth; read-only numerical sensitivity.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,math,os,sys
from pathlib import Path
import numpy as np
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.drivesim.rf_store import load_trace,h_for_antenna_yaws,tag_of
from qclean_uwb.features.reflection_attribution import image_delays

C0=299792458.0
BANK_SHA={
 "LP_plus45_bank.npz":"b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
 "LP_minus45_bank.npz":"39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}
H_SHA={"0":"1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51",
       "45":"dd0264c1d004d78ff0f0d39f5f0c613b084ea89ad558ac448ecbfd0b3e177ea1"}
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def observation(H,freq):
    H=np.asarray(H)
    z=H[:,:,0]
    n=len(freq)
    assert z.shape==(n,2)
    w=0.5-0.5*np.cos(2.*np.pi*np.arange(n)/(n-1))
    pad=np.zeros((4*n,2),complex)
    pad[:n]=z*w[:,None]
    cir=np.fft.ifft(pad,axis=0)*n
    mag=np.abs(cir)
    strongest=int(np.argmax(mag.max(axis=0)))
    u=mag[:,strongest]
    ix=int(np.flatnonzero(u>=0.3*u.max())[0])
    pp=np.abs(cir[ix,:])**2
    s=float((pp[0]-pp[1])/pp.sum()) if pp.sum()>0 else float('nan')
    r=float(ix*C0/(4*n*(freq[1]-freq[0])))
    return dict(first_tap=ix,range_m=r,s=s,port_used=strongest,powers=pp.tolist())
def main():
    ap=argparse.ArgumentParser()
    for key in ("bank_dir","trace","poses","h_dir","out"):ap.add_argument("--"+key,required=True,type=Path)
    q=ap.parse_args();q.out.mkdir(parents=True,exist_ok=True)
    bank=[]
    for name,digest in BANK_SHA.items():
        p=q.bank_dir/name
        if not p.exists() or sha(p)!=digest:raise RuntimeError(f"ERR_BANK_SHA {name}")
        with np.load(p,allow_pickle=False) as z:
            bank.append(P.Bank({x:z[x] for x in z.files}))
    assert np.array_equal(bank[0].freqs_hz,bank[1].freqs_hz)
    freqs=bank[0].freqs_hz
    with np.load(q.trace,allow_pickle=False) as z:raw={k:z[k] for k in z.files}
    raw["status"]=str(raw["status"])
    assert raw["status"]=="OK"
    pos=json.loads(q.poses.read_text());pose=pos[915]
    assert tag_of(pose["x"],pose["y"])=="x3.7036_y-0.5204"
    assert abs(float(raw["x"])-float(pose["x"]))<1e-8 and abs(float(raw["y"])-float(pose["y"]))<1e-8
    tau0=np.asarray(raw["tau"],float)
    assert len(tau0)==63
    target=62
    ideal=image_delays(np.array([4.,0.,2.65]),np.array([float(raw["x"]),float(raw["y"]),.45]),20.,1.2,2.7)[("end_x_max","end_x_min","end_x_max")]
    assert abs(float(tau0[target])-ideal)-5.1090357159952736e-14<1e-19
    raw_alt=dict(raw);raw_alt["tau"]=np.array(tau0,copy=True);raw_alt["tau"][target]=ideal
    results=[]
    for mount in (0,45):
        fp=q.h_dir/("H_R2_aA_m"+str(mount)+".npy")
        if sha(fp)!=H_SHA[str(mount)]:raise RuntimeError(f"ERR_H_HASH {fp}")
        ref=np.load(fp,mmap_mode="r",allow_pickle=False)[915]
        yaw=float(pose["yaw_body_deg"])+mount
        replay=h_for_antenna_yaws(raw,bank,[yaw])[0]
        patched=h_for_antenna_yaws(raw_alt,bank,[yaw])[0]
        diff_source=replay-ref
        max_relative_source=float(np.max(np.abs(diff_source))/np.maximum(np.max(np.abs(ref)),1e-30))
        if max_relative_source>5e-9:
            raise RuntimeError(f"BLOCKED_H_SOURCE_NO_PARITY mount={mount},relative={max_relative_source}")
        d=patched-replay
        obs0=observation(ref,freqs);obs1=observation(ref+d,freqs)
        change_r=abs(obs1["range_m"]-obs0["range_m"])
        change_s=abs(obs1["s"]-obs0["s"])
        results.append(dict(mount_deg=mount,pose_id=915,raw_h_sha256=H_SHA[str(mount)],stored_H_reconstruction_max_abs=float(np.max(np.abs(diff_source))),
                            stored_H_reconstruction_rel=max_relative_source,
                            hypothetical_ideal_image_delta_tau_s=float(ideal-tau0[target]),
                            max_abs_dH=float(np.max(np.abs(d))),h_rel_max=float(np.max(np.abs(d))/np.max(np.abs(ref))),
                            h_rel_l2=float(np.linalg.norm(d)/np.linalg.norm(ref)),
                            original_observation=obs0,hypothetical_observation=obs1,
                            abs_ds=change_s,abs_dr_m=change_r,
                            FIRST_PATH_SWITCH=bool(obs1["first_tap"]!=obs0["first_tap"]),
                            packet_tolerance_s_1e_minus_12=bool(change_s<=1e-12),
                            packet_tolerance_r_1e_minus_9m=bool(change_r<=1e-9)))
    out=dict(status="COUNTERFACTUAL_ONE_RAY_COMPLETED",input_trace_sha256=sha(q.trace),pose_sha256=sha(q.poses),
             bank_sha256=BANK_SHA,source_H_SHA256=H_SHA,
             original_tau_s=float(tau0[target]),hypothetical_ideal_image_tau_s=float(ideal),
             unaffected_source_H_files="Existing source H is not modified, only a hypothetical delta is calculated.",
             upstream_scope="R2_aA ray 62, pose_id 915 only; not the 25 other G3 strict failures",
             consequence="No gate/class-label correction changes H; only a hypothetical physical tau correction could change H.",
             provenance="Self-review numerical sensitivity, not independent Sionna physical validation.",
             utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),cases=results)
    (q.out/"R2_A_H_COUNTERFACTUAL.json").write_text(json.dumps(out,indent=2))
    print(json.dumps({"status":out["status"],"outcomes":[{"mount":x["mount_deg"],"h_rel_l2":x["h_rel_l2"],"max_ds":x["abs_ds"],"dr_m":x["abs_dr_m"],"parity_rel":x["stored_H_reconstruction_rel"]} for x in results]}))
if __name__=="__main__":main()
