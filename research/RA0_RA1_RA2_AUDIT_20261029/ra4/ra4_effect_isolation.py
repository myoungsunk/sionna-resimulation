#!/usr/bin/env python3
"""RA4 retrospective 2(mean) x 3(variance) x 2(gate) factorial experiment.
Preserves original data and historic results. Does not claim online deployability.
"""
from __future__ import annotations
import csv, hashlib, json, math, os, pathlib, sys, time
import numpy as np

HERE=pathlib.Path(__file__).resolve()
BASE=HERE.parents[2]/"DS_MASK_CAUSAL_X1_X2_20261026"
sys.path.insert(0,str(BASE/"pol_bias_model"))
sys.path.insert(0,str(BASE/"reflect_model"))
import exp_pb as E
import common as C
from core import predict, wrap

CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0")
LEVELS=("B0","L0","L1","L2")
MEANS=("BB","MB")
VARS=("NONE","LEGACY","PRIOR")
GATES=("BASE_FIXED","SELF_NIS")
THRESH=9.210340371976184
HISTORIC_SOURCE="9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"

def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def run_arm(D,mu,model,variance,gate):
    assert variance in VARS and gate in GATES
    n=len(D["t"]);x=D["x0"].copy();P=D["P0"].copy();a=D["anchor"]
    X=np.empty((n,4)); PX=np.empty((n,4,4)); mask=np.zeros(n,bool)
    sigma=np.empty(n); nis=np.full(n,np.nan);mask_orig=D["acc"]
    for k in range(n):
        legacy=E.sig(math.hypot(x[0]-a[0],x[1]-a[1]))
        if k:
            ds=float(D["ds"][k]);gy=float(D["gy"][k]);dt=float(D["dt"][k])
            q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
            x,P,_,_=predict(x,P,ds,gy,dt,q)
        prior=E.sig(math.hypot(x[0]-a[0],x[1]-a[1]))
        sg=legacy if variance=="LEGACY" else (prior if variance=="PRIOR" else 0.)
        sigma[k]=sg
        doobs=(bool(mask_orig[k]) if gate=="BASE_FIXED" else bool(np.isfinite(D["z"][k]).all()))
        if doobs:
            h,H=model.batch(x[None],D["spec"]);h=h[0];H=H[0]
            Rk=D["R"][k].copy()
            if variance!="NONE":Rk[1,1]+=sg**2
            v=D["z"][k]-h-mu[k]
            S=H@P@H.T+Rk;S=.5*(S+S.T)
            if not np.all(np.isfinite(S)) or not np.all(np.isfinite(v)):
                raise RuntimeError("ERR_NONFINITE_INNOV "+str((k,variance,gate)))
            value=float(v@np.linalg.solve(S,v))
            nis[k]=value
            accept=(value<=THRESH if gate=="SELF_NIS" else True)
            if accept:
                K=np.linalg.solve(S,H@P).T
                y=x+K@v;y[2]=wrap(y[2])
                A=np.eye(4)-K@H
                Pn=A@P@A.T+K@Rk@K.T
                x=y;P=.5*(Pn+Pn.T)
                mask[k]=True
        X[k]=x;PX[k]=P
    return X,PX,mask,sigma,nis

def csv_dump(path,records):
    cols=list(records[0]) if records else []
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(records)

def make_D(case,level,model):
    ref=C.load_control(case,"B0")
    jb,jm=ref["jb"],ref["jm"];spec=C.CASES[case]
    t=ref["t_s"];truth=ref["truth_scoring_only"]
    z=ref["nu"][:,jb]+ref["h"][:,jb]+ref["mu"][:,jb]
    ds,gy,dt,x0=E.build_controls(t,truth[:,:3],level)
    acc=E.gated_mask(z,ref["mu"][:,jb],ref["R"][:,jb],ds,gy,dt,
      np.r_[x0,0.],ref["Pprior"][0,jb],spec,model)
    if level in ("B0","L2"):
        record=C.load_control(case,level)
        if np.count_nonzero(acc!=record["acc"][:,jb].astype(bool)):
            raise RuntimeError("ERR_ARCHIVED_GATE_PARITY "+case+"/"+level)
    hg,_=model.batch(np.c_[truth[:,:3],np.zeros(len(t))],spec)
    D=dict(t=t,gt=truth,z=z,R=ref["R"][:,jb],acc=acc,ds=ds,gy=gy,dt=dt,
       x0=np.r_[x0,0.],P0=ref["Pprior"][0,jb],spec=spec,
       anchor=np.asarray(spec["anchor"][:2]),hg=hg)
    return D,{"BB":ref["mu"][:,jb],"MB":ref["mu"][:,jm]}

def fmt_result(D,X,P,mask,sg,nis,case,level,mean,var,gate):
    score=E.scores(D,X,P)
    if any(not np.isfinite(score[k]) for k in ("head_rmse","xy_rmse_cm","head_z_rms","nees_xy")):
        raise RuntimeError("ERR_NONFINITE_SCORE "+str((case,level,mean,var,gate)))
    return dict(case=case,bias=level,mean=mean,variance=var,gate=gate,
      arm=f"{mean}_"+("ORIG" if var=="NONE" else "VAR_"+var),
      n_packets=int(len(D["t"])),n_accepted=int(mask.sum()),n_base_accepted=int(D["acc"].sum()),
      n_mask_flips_from_base=int(np.count_nonzero(mask!=D["acc"])),
      head_rmse_deg=score["head_rmse"],xy_rmse_cm=score["xy_rmse_cm"],
      head_bias_deg=score["head_bias"],head_z_rms=score["head_z_rms"],xy_nees=score["nees_xy"],
      head_cov95=score["head_cov95"],xy_cov95=score["xy_cov95"],
      n_nis_finite=int(np.count_nonzero(np.isfinite(nis))),
      nis_mean=float(np.nanmean(nis)) if np.any(np.isfinite(nis)) else None,
      mean_sigma=float(np.mean(sg)),max_sigma=float(np.max(sg)))

def contrasts(rows):
    lookup={(r["case"],r["bias"],r["mean"],r["variance"],r["gate"]):r for r in rows}
    effects=[];gates=[]
    for case in CASES:
      for bias in LEVELS:
        for gate in GATES:
          for semantic in ("LEGACY","PRIOR"):
            def Y(mean,var,met):
              return lookup[(case,bias,mean,var,gate)][met]
            for met in ("head_rmse_deg","xy_rmse_cm"):
              y00=Y("BB","NONE",met);y10=Y("MB","NONE",met);y01=Y("BB",semantic,met);y11=Y("MB",semantic,met)
              rec=dict(case=case,bias=bias,gate=gate,semantic=semantic,metric=met,
                y00=y00,y10=y10,y01=y01,y11=y11,
                effect_mean_only=y10-y00,effect_var_only=y01-y00,
                effect_combined=y11-y00,effect_var_given_mean=y11-y10,
                effect_mean_given_var=y11-y01,interaction=y11-y10-y01+y00)
              assert abs(rec["interaction"]-((y11-y10)-(y01-y00)))<1e-9
              assert abs(rec["effect_combined"]-(rec["effect_mean_only"]+rec["effect_var_given_mean"]))<1e-9
              effects.append(rec)
        for mean in MEANS:
          for variance in VARS:
            rf=lookup[(case,bias,mean,variance,"BASE_FIXED")]
            rs=lookup[(case,bias,mean,variance,"SELF_NIS")]
            gates.append(dict(case=case,bias=bias,mean=mean,variance=variance,
              d_head_self_minus_base=rs["head_rmse_deg"]-rf["head_rmse_deg"],
              d_xy_self_minus_base=rs["xy_rmse_cm"]-rf["xy_rmse_cm"],
              delta_n_accepted=rs["n_accepted"]-rf["n_accepted"],
              self_n_mask_flips_from_base=rs["n_mask_flips_from_base"]))
    return effects,gates,lookup

def main():
    out=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path("ra4_out")
    out.mkdir(parents=True,exist_ok=True)
    model=C.base_model()
    entries=[];parity=[];start=time.monotonic()
    for case in CASES:
      for level in LEVELS:
        D,mus=make_D(case,level,model)
        for mean in MEANS:
          mu=mus[mean]
          for variance in VARS:
            for gate in GATES:
              X,P,mask,sg,nis=run_arm(D,mu,model,variance,gate)
              if gate=="BASE_FIXED" and variance in ("NONE","LEGACY"):
                Xo,Po,_,_=E.run(D,mu,{"mode":"orig" if variance=="NONE" else "var"},model)
                dx=float(np.max(np.abs(X-Xo)));dp=float(np.max(np.abs(P-Po)))
                if dx>1e-10 or dp>1e-10 or np.any(mask!=D["acc"]):
                    raise RuntimeError(f"ERR_HISTORIC_PARITY {case}/{level}/{mean}/{variance} dx={dx} dp={dp}")
                parity.append(dict(case=case,bias=level,mean=mean,variance=variance,
                                   state_max_abs=dx,cov_max_abs=dp,mask_mismatch=0))
              if mean=="BB" and variance=="NONE" and gate=="SELF_NIS" and np.any(mask!=D["acc"]):
                raise RuntimeError("ERR_BASE_SELF_GATE "+case+"/"+level)
              entries.append(fmt_result(D,X,P,mask,sg,nis,case,level,mean,variance,gate))
      print(json.dumps({"completed_case":case,"rows":len([r for r in entries if r["case"]==case]),"elapsed_s":round(time.monotonic()-start,2)}),flush=True)
    effects,gates,lut=contrasts(entries)
    assert len(entries)==336 and len(parity)==112 and len(effects)==224 and len(gates)==168
    def counts(variance,gate):
      rs=[]
      for c in CASES:
       for b in LEVELS:
        target=lut[(c,b,"MB",variance,gate)]
        base=lut[(c,b,"BB","NONE",gate)]
        rs.append((target["head_rmse_deg"]<base["head_rmse_deg"],
                   target["xy_rmse_cm"]<base["xy_rmse_cm"]))
      return dict(head=sum(x[0] for x in rs),xy=sum(x[1] for x in rs),both=sum(x[0] and x[1] for x in rs))
    totals={f"{v}/{g}":counts(v,g) for v in VARS for g in GATES}
    if totals["LEGACY/BASE_FIXED"]!=dict(head=23,xy=20,both=19):
      raise RuntimeError("ERR_HISTORIC_COUNT_PARITY "+str(totals["LEGACY/BASE_FIXED"]))
    csv_dump(out/"RA4_336_ARMS.csv",entries)
    csv_dump(out/"RA4_224_INTERACTIONS.csv",effects)
    csv_dump(out/"RA4_168_GATE_CONTRASTS.csv",gates)
    csv_dump(out/"RA4_112_PARITY.csv",parity)
    qa=dict(status="TECHNICAL_RETROSPECTIVE_COMPLETE",source_commit=HISTORIC_SOURCE,
            n_armsgate=len(entries),n_factor_rows=len(effects),n_gate_pairs=len(gates),
            n_source_parity_rows=len(parity),full_state_P_parity_max=max(max(p["state_max_abs"],p["cov_max_abs"]) for p in parity),
            counts_vs_BB_ORIG=totals,
            source_hashes={"exp_pb":sha(BASE/"pol_bias_model/exp_pb.py"),
                           "common":sha(BASE/"reflect_model/common.py"),
                           "ra4_script":sha(HERE)},
            input_lock=(C.ROOT/"out/INPUT_LOCK.sha256").read_text() if (C.ROOT/"out/INPUT_LOCK.sha256").exists() else "MISSING",
            unique_rf_case_count=7,not_independent_bias_levels=True,
            no_original_input_changed=True,physical_G3_25_raw_unresolved=True,
            science_release=False,self_review_only=True)
    (out/"RA4_QA.json").write_text(json.dumps(qa,indent=2))
    print(json.dumps(dict(status=qa["status"],counts=totals,elapsed_s=round(time.monotonic()-start,2),n_arm=len(entries))))
if __name__=="__main__":main()
