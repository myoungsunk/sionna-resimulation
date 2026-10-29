#!/usr/bin/env python3
"""A4 controlled initialization/sensor-stream 2^5 factorial + R5-A first-flip test.
Same archived RF z, mu_M, R0, truth score, model, P0. BASE mask fixed at seed0.
No new independent RF scenes. Synthetic sensor/initialization sensitivity only.
"""
import argparse,csv,datetime,itertools,json,math,os,pathlib,sys
import numpy as np
import ra4_effect_isolation as A

CASES=("R5_aA_m0","R5_aB_m0","R2_aA_m45")
FACTORS=("init_xy_alt","init_heading_alt","gyro_bias_L2",
         "wheel_noise_alt","gyro_noise_alt")
def must(v,m):
    if not v:raise RuntimeError(m)
def maxerr(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def write(path,rows):
    if not rows:return
    keys=sorted(set().union(*(z.keys() for z in rows)))
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def override_run(D,mu,model,policy,overrides):
    n=len(D["t"]);x=D["x0"].copy();P=D["P0"].copy()
    X=np.empty((n,4));PP=np.empty((n,4,4));m=np.zeros(n,bool);sigma=np.zeros(n)
    for k in range(n):
        sg=A.E.sig(math.hypot(x[0]-D["anchor"][0],x[1]-D["anchor"][1]))
        if k:
            ds,gy,dt=[float(D[z][k]) for z in ("ds","gy","dt")]
            Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0])
            x,P,_,_=A.predict(x,P,ds,gy,dt,Q)
        sigma[k]=sg
        doobs=bool(D["acc"][k]) if policy=="BASE_FIXED" else bool(np.isfinite(D["z"][k]).all())
        if k in overrides:doobs=True  # compute K even when BASE originally rejected
        if doobs:
            h,H=model.batch(x[None],D["spec"]);h,H=h[0],H[0]
            R=D["R"][k].copy();R[1,1]+=sg**2
            v=D["z"][k]-h-mu[k]
            S=H@P@H.T+R;S=.5*(S+S.T)
            nis=float(v@np.linalg.solve(S,v))
            allow=bool(nis<=A.THRESH) if policy=="SELF_NIS" else True
            if k in overrides:allow=bool(overrides[k])
            if allow:
                K=np.linalg.solve(S,H@P).T
                y=x+K@v;y[2]=A.wrap(y[2])
                F=np.eye(4)-K@H
                Pn=F@P@F.T+K@R@K.T
                x=y;P=.5*(Pn+Pn.T);m[k]=True
        X[k]=x;PP[k]=P
    return X,PP,m,sigma

def firstflip(D,mus,model,case):
    natural=A.run_arm(D,mus["MB"],model,"LEGACY","SELF_NIS")
    fixed=A.run_arm(D,mus["MB"],model,"LEGACY","BASE_FIXED")
    neutral=override_run(D,mus["MB"],model,"SELF_NIS",{})
    must(max(maxerr(natural[0],neutral[0]),maxerr(natural[1],neutral[1]))<1e-10 and np.array_equal(natural[2],neutral[2]),
        "ERR_COUNTERFACTUAL_IMPLEMENTATION_PARITY")
    flips=np.flatnonzero(natural[2]!=fixed[2])
    must(len(flips)>0,"ERR_NO_FIRST_FLIP")
    k=int(flips[0]);must(bool(natural[2][k]) and not bool(fixed[2][k]),"ERR_EXPECTED_FIRST_EXTRA_ACCEPT")
    # Intervene on ONE packet, then let other NIS decisions follow each path.
    reject=override_run(D,mus["MB"],model,"SELF_NIS",{k:False})
    # Base fixed policy, but force acceptance of this one packet.
    accept_in_fixed=override_run(D,mus["MB"],model,"BASE_FIXED",{k:True})
    chk=override_run(D,mus["MB"],model,"BASE_FIXED",{})
    must(max(maxerr(chk[0],fixed[0]),maxerr(chk[1],fixed[1]))<1e-10 and np.array_equal(chk[2],fixed[2]),
         "ERR_FIXED_COUNTERFACTUAL_PARITY")
    output=[]
    for tag,z in (("SELF_NATURAL",natural),("SELF_FORCE_FIRST_REJECT",reject),
                   ("BASE_FIXED",fixed),("BASE_FORCE_FIRST_ACCEPT",accept_in_fixed)):
        met=A.E.scores(D,z[0],z[1])
        output.append(dict(case=case,first_flip_packet=k,first_time_s=float(D["t"][k]),
           arm=tag,head_deg=met["head_rmse"],xy_cm=met["xy_rmse_cm"],
           head_z_rms=met["head_z_rms"],xy_nees=met["nees_xy"],
           head_cov95=met["head_cov95"],xy_cov95=met["xy_cov95"],
           n_accepted=int(z[2].sum()),n_mask_diff_to_self=int(np.count_nonzero(z[2]!=natural[2])),
           n_mask_diff_to_base=int(np.count_nonzero(z[2]!=fixed[2])),
           intervention_is_one_packet=True))
    return output
def main(case,out):
    must(case in CASES,"ERR_INVALID_CASE");out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    model=A.C.base_model();D,mus=A.make_D(case,"B0",model)
    t=D["t"];gt=D["gt"]
    c0=A.E.build_controls(t,gt[:,:3],"B0",seed=0)
    cwheel=A.E.build_controls(t,gt[:,:3],"B0",seed=101)
    cgyro=A.E.build_controls(t,gt[:,:3],"B0",seed=102)
    cxy=A.E.build_controls(t,gt[:,:3],"B0",seed=103)
    ch=A.E.build_controls(t,gt[:,:3],"B0",seed=104)
    base_ds,base_gy,dt,base_x0=c0
    must(maxerr(base_ds,D["ds"])<1e-12 and maxerr(base_gy,D["gy"])<1e-12 and maxerr(np.r_[base_x0,0],D["x0"])<1e-12,
         "ERR_NATIVE_BASE_SENSOR_PARITY")
    for c in (cwheel,cgyro,cxy,ch):
        must(maxerr(c[2],dt)<1e-12,"ERR_SENSOR_TIME_ALIGNMENT")
    rows=[]
    for combo in itertools.product((0,1),repeat=5):
        flag=dict(zip(FACTORS,combo))
        d=dict(D)
        xx=np.asarray(base_x0).copy()
        if flag["init_xy_alt"]:xx[:2]=cxy[3][:2]
        if flag["init_heading_alt"]:xx[2]=ch[3][2]
        d["x0"]=np.r_[xx,0.]
        d["ds"]=cwheel[0] if flag["wheel_noise_alt"] else base_ds
        d["gy"]=(cgyro[1] if flag["gyro_noise_alt"] else base_gy)+math.radians(.2*flag["gyro_bias_L2"])*dt
        d["dt"]=dt
        # R0,z,mu/P0 and historical seed0 baseline mask intentionally never changed.
        for gate in ("BASE_FIXED","SELF_NIS"):
            v=A.run_arm(d,mus["MB"],model,"LEGACY",gate)
            met=A.E.scores(d,v[0],v[1])
            rows.append(dict(case=case,**flag,gate=gate,
                head_deg=met["head_rmse"],xy_cm=met["xy_rmse_cm"],
                head_z_rms=met["head_z_rms"],xy_nees=met["nees_xy"],
                head_cov95=met["head_cov95"],xy_cov95=met["xy_cov95"],
                n_accepted=int(v[2].sum()),n_mask_flips_to_original=int(np.count_nonzero(v[2]!=D["acc"])),
                same_RF_packet=True,same_R_mu=True,same_P0=True,
                fixed_original_base_mask=True,dx0_xy_m=float(np.linalg.norm(xx[:2]-base_x0[:2])),
                dx0_heading_rad=float(A.wrap(xx[2]-base_x0[2])),
                gyro_bias_deg_s=float(.2*flag["gyro_bias_L2"]),
                # wheel noise intervention also changes Q because Q depends on abs(ds).
                wheel_noise_includes_Q_change=bool(flag["wheel_noise_alt"])))
    must(len(rows)==64,"ERR_FACTORIAL_COUNT")
    toggles=firstflip(D,mus,model,case) if case=="R5_aA_m0" else []
    write(out/"A4_SENSOR_INIT_32X2.csv",rows)
    write(out/"A4_FIRST_FLIP_ONE_PACKET.csv",toggles)
    qa=dict(status="PASS_A4_FACTORIAL_TECHNICAL",case=case,n_full_factorial=32,
       n_gate_arms=len(rows),n_first_packet_counterfactual=len(toggles),
       factors=FACTORS,initial_seed=0,alternative_seeds=[101,102,103,104],
       sensor_variant="B0_BIAS_ONLY_AND_INDEPENDENT_SEED_STREAMS",
       policy_invariance="ORIGINAL_BASE_MASK_FROZEN; SELF_NIS_SEPARATE",
       wheel_noise_factor_also_changes_Q=True,
       new_RF_scenes=False,new_truth_labels=False,
       self_review_only=True,science_release=False,
       recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"A4_FACTORIAL_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("A4_FACTORIAL_FINAL "+json.dumps(qa),flush=True)
    for o in toggles:print("A4_FIRST_FLIP_COUNTERFACTUAL "+json.dumps(o),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--case",required=True);p.add_argument("--out",required=True);a=p.parse_args();main(a.case,a.out)
