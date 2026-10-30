#!/usr/bin/env python3
"""RA5-I3 same-scene FFD LoS complex noise + adjacent-tap Jacobians:
conditional Fisher of s_next given s_first, all in the SAME generative world.
No Full-H Jacobian, no independent physical scene or hardware noise calibration.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np
from raw_tap_covariance import noise_trials
from tap_jacobian_adapter import adapter

T2=np.array([[1.,0.],[-1.,1.]])
def req(ok,msg):
    if not ok:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def dump(p,records):
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    src=pathlib.Path(args.mbvar_code).resolve()
    sys.path.insert(0,str(src))
    import world
    q=np.array([[3.,7.,0.],[3.5,7.,0.],[5.,7.,0.],
                [6.,7.5,0.],[7.,7.5,0.],[8.,7.5,0.]])
    X=np.c_[q,np.zeros(len(q))]
    taps=world.taps_of(X,"A")
    z,J=adapter(world,X,"A",taps)
    M=world.model()
    hs,dh,*_=M.spectrum(X,world.spec("A"),True)
    freq=np.asarray(M.freqs)
    req(hs.shape==(len(X),257,2) and J.shape==(len(X),3,4),"ERR_FFD_SPECTRUM_LAYOUT")
    rows=[]
    for i in range(len(X)):
        H=np.asarray(hs[i],complex)
        for snr in (-5.,5.,20.):
            for jitter in (0.,150.):
                seed=int(hashlib.sha256(f"RA5-I3|{i}|{snr}|{jitter}|20261030".encode()).hexdigest()[:15],16)
                result=noise_trials(H,freq,snr,jitter,.3,args.draw,seed)
                R=np.array(result["cov_matrix_raw"])[1:3,1:3]
                Js=J[i,1:3,:]
                rt=T2@R@T2.T;jt=T2@Js
                eig=np.linalg.eigvalsh(R)
                entry=dict(pose_i=i,pose_x=float(X[i,0]),pose_y=float(X[i,1]),
                  tap_clean=int(taps[i]),snr_db=snr,jitter_ps=jitter,n_draw=args.draw,
                  clean_s0=float(z[i,1]),clean_s1=float(z[i,2]),
                  jac_s0_psi=float(Js[0,2]),jac_s1_psi=float(Js[1,2]),
                  jac_ds_psi=float(jt[1,2]),var_s0=float(R[0,0]),
                  cov_s0_s1=float(R[0,1]),var_s1=float(R[1,1]),
                  same_packet_correlation=float(R[0,1]/math.sqrt(max(1e-300,R[0,0]*R[1,1]))),
                  n_tap_flips=result["tap_flip_n"],physical_model="FFD_LOS_PLUS_ASSUMED_CFR_NOISE",
                  full_3x3_cov_rank=result["covariance_rank"],full_3x3_information_supported=False,
                  conditional_I_supported=False)
                if eig[0]>1e-12 and np.linalg.cond(R)<1e10 and R[0,0]>1e-12:
                    S=float(R[1,1]-R[1,0]**2/R[0,0])
                    if S>1e-12:
                        I=Js.T@np.linalg.solve(R,Js)
                        Ialt=jt.T@np.linalg.solve(rt,jt)
                        Jcond=Js[1]-R[1,0]/R[0,0]*Js[0]
                        delta=np.outer(Jcond,Jcond)/S
                        I0=np.outer(Js[0],Js[0])/R[0,0]
                        rel=float(np.linalg.norm(I-Ialt)/max(1.,np.linalg.norm(I)))
                        rel2=float(np.linalg.norm(I-I0-delta)/max(1.,np.linalg.norm(I)))
                        req(rel<1e-9 and rel2<1e-9,"ERR_CONDITIONAL_FISHER_EQUIVALENCE "+str((rel,rel2)))
                        evals=np.linalg.eigvalsh(delta)
                        req(evals[0]>-1e-8,"ERR_NONPSD_ADDITIONAL_INFORMATION")
                        entry.update(conditional_I_supported=True,
                          var_s1_given_s0=S,
                          extra_heading_data_fisher=float(delta[2,2]),
                          baseline_heading_data_fisher=float(I0[2,2]),
                          incremental_information_trace=float(np.trace(delta)),
                          conditional_jac_norm=float(np.linalg.norm(Jcond)),
                          I_equivalence_relative=rel,conditional_decomposition_relative=rel2,
                          nuisance_pose_marginal_information="NOT_COMPUTED",
                          online_feature_available="SIMULATED_ONLY")
                rows.append(entry)
        print("RA5_I3_POSE "+json.dumps(dict(i=i,n=len(rows))),flush=True)
    dump(out/"RA5_FFD_SAME_SCENE_CONDITIONAL_INFO.csv",rows)
    count=sum(r["conditional_I_supported"] for r in rows)
    qa=dict(status="PASS_SAME_SCENE_CONDITIONAL_INFORMATION_DIAGNOSTIC" if count else "BLOCKED_SINGULAR_R_S0_S1",
      n_poses=len(X),n_snr=3,n_jitter=2,n_cells=len(rows),n_conditional_fisher_fullrank=count,
      n_information_blocked=len(rows)-count,source_world_sha256=sha(src/"world.py"),
      conditional_information_status="LOCAL_LINEAR_GAUSSIAN_WITH_KNOWN_GENERATOR",
      true_multipath_noise_calibration="NOT_ESTABLISHED",
      four_state_vs_five_state_full_filter="NOT_RUN",scene_generalization="NOT_TESTED",
      r_quantized_range_in_full_R="SINGULAR_POSSIBLE",
      completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      independent_auditor=False,science_release=False)
    (out/"RA5_FFD_CONDITIONAL_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_I3_FINAL "+json.dumps(qa),flush=True)
    if not count:raise RuntimeError("ERR_NO_VALID_CONDITIONAL_FISHER")
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--mbvar-code",required=True)
    p.add_argument("--out",required=True);p.add_argument("--draw",type=int,default=768)
    a=p.parse_args();req(a.draw>=200,"ERR_DRAW");main(a)
