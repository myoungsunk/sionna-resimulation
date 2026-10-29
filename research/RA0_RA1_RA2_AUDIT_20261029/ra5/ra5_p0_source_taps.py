#!/usr/bin/env python3
"""RA5-P0 SHA-locked H/LoS/packet observer and online-tap availability.
7 case sharded. No labels consumed by estimator, truth only for audit/scoring.
"""
import argparse,csv,datetime,gzip,hashlib,json,os,pathlib,sys
import numpy as np

HERE=pathlib.Path(__file__).resolve()
sys.path.insert(0,str(HERE.parents[1]/"ra4"))
sys.path.insert(0,str(HERE.parents[1]/"ra2"))
import ra4_effect_isolation as A
import ra2_readonly_lineage as RA2

C0=299792458.
def must(b,msg):
    if not b:raise RuntimeError(msg)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def observe(H,frequencies):
    n=len(frequencies);df=float(frequencies[1]-frequencies[0])
    must(H.ndim==4 and H.shape[1:]==(n,2,2),"ERR_H_LAYOUT")
    window=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1))
    out=[]
    for a in range(0,len(H),96):
        x=np.asarray(H[a:a+96,:,:,0])
        padded=np.zeros((len(x),4*n,2),complex)
        padded[:,:n]=x*window[None,:,None]
        cir=np.fft.ifft(padded,axis=1)*n
        amp=np.abs(cir)
        port=np.argmax(np.max(amp,axis=1),axis=1)
        pmag=amp[np.arange(len(port)),:,port]
        height=np.max(pmag,axis=1)
        must(np.all(np.isfinite(height)) and np.all(height>0),"ERR_NULL_RF")
        tap=np.argmax(pmag>=.3*height[:,None],axis=1)
        must(np.all(tap+1<4*n),"ERR_TAP_EDGE")
        p0=np.abs(cir[np.arange(len(tap)),tap,:])**2
        p1=np.abs(cir[np.arange(len(tap)),tap+1,:])**2
        den=p0.sum(axis=1);den1=p1.sum(axis=1)
        must(np.all(den>0) and np.all(den1>0),"ERR_ZERO_POL_POWER")
        s0=(p0[:,0]-p0[:,1])/den
        s1=(p1[:,0]-p1[:,1])/den1
        for k in range(len(tap)):
            out.append(dict(tap=int(tap[k]),port=int(port[k]),
                r=float(tap[k]*C0/(4*n*df)),s0=float(s0[k]),
                s1=float(s1[k]),ds1=float(s1[k]-s0[k]),
                fp_power=float(den[k]),adj_power=float(den1[k])))
    must(len(out)==len(H),"ERR_H_ROW_COVERAGE")
    return out

def main(case,out):
    must(case in A.CASES,"ERR_UNDECLARED_CASE")
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    ref=A.C.ROOT
    lockp=pathlib.Path(__file__).resolve().parents[3]/"EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
    # HERE: /research/RA0_RA1_RA2_AUDIT_20261029/ra5/filename.py -> parents[2]=research, not parents[3].
    if not lockp.exists():
        lockp=pathlib.Path(__file__).resolve().parents[2]/"EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
    must(lockp.exists(),"ERR_P0_ORIGINAL_SOURCE_MANIFEST")
    lock=json.loads(lockp.read_text())
    assets={p["path"]:p for p in lock["assets"] if p.get("sha256")}
    row=next(c for c in lock["cases"] if c["id"]==case)
    locations={
      row["full_path"]:ref/"rf"/("H_"+case+".npy"),
      row["los_path"]:ref/"rf"/("H_LoS_"+case+".npy"),
      row["samples_path"]:ref/"rf"/("SAMPLES_"+case+".json"),
    }
    sha_checks=[]
    for original,p in locations.items():
        must(p.is_file(),"ERR_SOURCE_FILE_MISSING "+str(p))
        a=assets[original];digest=sha(p)
        must(digest==a["sha256"] and p.stat().st_size==int(a["bytes"]),
             "ERR_SOURCE_DIGEST "+original+" "+digest)
        sha_checks.append(dict(kind=a["kind"],original_path=original,sha256=digest,bytes=p.stat().st_size))
    control=ref/"traces"/(case+"_B0_CONTROL.npz")
    must(sha(control)==RA2.CONTROL_SHA[case],"ERR_CONTROL_SHA")
    samples=json.loads(locations[row["samples_path"]].read_text())
    must(len(samples)==row["rf_count"] and all(int(s["pose_id"])==i for i,s in enumerate(samples)),"ERR_SAMPLES_POSE_ORDER")
    Hf,Hl,_=A.C.load_rf(case)
    must(tuple(Hf.shape)==tuple(Hl.shape)==tuple(row["H_shape"]),"ERR_H_SHAPE")
    bank=ref/"banks"/"LP_plus45_bank.npz"
    bank_other=ref/"banks"/"LP_minus45_bank.npz"
    must(sha(bank)==A.C.BANK_SHA[bank.name] and sha(bank_other)==A.C.BANK_SHA[bank_other.name],"ERR_BANK_DIGEST")
    with np.load(bank,allow_pickle=False) as b:freqs=np.asarray(b["freqs_hz"])
    must(len(freqs)==257 and np.allclose(np.diff(freqs),freqs[1]-freqs[0],atol=.1),"ERR_FREQ")
    f=observe(Hf,freqs);l=observe(Hl,freqs)
    T=A.C.load_control(case,"B0")
    jb=T["jb"]
    z=T["nu"][:,jb]+T["h"][:,jb]+T["mu"][:,jb]
    t=T["t_s"];gt=T["truth_scoring_only"]
    must(len(t)==RA2.EXPECTED_T[case[:2]] and len(z)==len(t),"ERR_PACKET_COUNT")
    u=np.array([[p["r"],p["s0"]] for p in f[:len(t)]])
    par=np.max(np.abs(u-z),axis=0)
    must(par[0]<=1e-9 and par[1]<=1e-12,"ERR_NATIVE_H_PACKET_PARITY "+str(par))
    must(np.max(np.abs(np.array([[s["x"],s["y"]] for s in samples[:len(t)]])-gt[:,:2]))<5e-6,"ERR_GT_POSE_KEY")
    records=[];switches=0;prev=None
    for i,s in enumerate(samples):
        a=f[i];b=l[i]
        phase="TIMELINE" if i<len(t) else "STATIC_YAW_SWEEP"
        switch=(i>0 and phase=="TIMELINE" and a["tap"]!=prev)
        switches+=int(switch);prev=a["tap"]
        rr=dict(case=case,route=case[:2],anchor=case[4],mount_deg=A.C.CASES[case]["mount_deg"],
           pose_id=i,phase=phase,x=float(s["x"]),y=float(s["y"]),yaw_body_deg=float(s["yaw_body_deg"]),
           t_s=float(t[i]) if phase=="TIMELINE" else "",
           r_full=a["r"],s0_full=a["s0"],s1_full=a["s1"],ds1=a["ds1"],
           r_los=b["r"],s0_los=b["s0"],s1_los=b["s1"],
           e_s_oracle=a["s0"]-b["s0"],e_r_oracle_m=a["r"]-b["r"],
           first_tap=a["tap"],first_tap_los=b["tap"],first_port=a["port"],
           first_port_los=b["port"],tap_switch=bool(switch),first_power=a["fp_power"],
           next_tap_power=a["adj_power"],first_denom_valid=True,
           ds1_online_hardware="CONDITIONAL_ON_RAW_ADJACENT_TAP",
           oracle_online=False)
        records.append(rr)
    p=out/"RA5_P0_RAW_TAPS.csv.gz"
    with gzip.open(p,"wt",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    man=dict(status="PASS_P0_SOURCE_REPLAY_ONLY",case=case,sha_source_manifest=sha(lockp),
       historical_code_sha=A.HISTORIC_SOURCE,control_sha=sha(control),
       source_assets=sha_checks,bank_sha={bank.name:sha(bank),bank_other.name:sha(bank_other)},
       n_all=len(records),n_timeline=len(t),n_auxiliary=len(records)-len(t),
       n_first_tap_switch=switches,max_abs_native_r_m=float(par[0]),
       max_abs_native_s=float(par[1]),fgrid_bins=257,
       measured_delta_t_ns=float(1e9/(4*len(freqs)*(freqs[1]-freqs[0]))),
       raw_h_physical_validity="NOT_PROVEN",scene_independence="ONE_CORRIDOR",
       r_s1_conditional_info="NOT_ESTIMATED",online_ds1="CONDITIONAL",
       oracle_delta_s="SCORING_ONLY",self_review_only=True,
       current_source_sha=os.getenv("GITHUB_SHA","UNKNOWN"),
       time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_P0_MANIFEST.json").write_text(json.dumps(man,indent=2)+"\n")
    print("RA5_P0_FINAL "+json.dumps({k:v for k,v in man.items() if k not in ("source_assets","bank_sha")}),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--case",choices=A.CASES,required=True);ap.add_argument("--out",required=True)
    x=ap.parse_args();main(x.case,x.out)
