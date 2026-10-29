#!/usr/bin/env python3
"""At first MB_VAR self-vs-fixed gate flip, hold MB_VAR predicted prior fixed.
Counterfactual 2x2 local NIS: BB/MB mean x NONE/VAR covariance.
NOT actual full BB trajectory NIS; no source data altered.
"""
import csv,json,math,pathlib,sys
import numpy as np
import ra4_effect_isolation as A
from a4_first_packet_probe import prior
CASES=("R5_aA_m0","R4_aB_m0","R2_aA_m45")
def main(out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    model=A.C.base_model();rows=[];checks=[]
    for case in CASES:
        D,mus=A.make_D(case,"B0",model)
        for semantic in ("LEGACY","PRIOR"):
            f=A.run_arm(D,mus["MB"],model,semantic,"BASE_FIXED")
            s=A.run_arm(D,mus["MB"],model,semantic,"SELF_NIS")
            bad=np.flatnonzero(f[2]!=s[2])
            if not len(bad):continue
            k=int(bad[0]);x,P=prior(D,f[0],f[1],k);xx,PP=prior(D,s[0],s[1],k)
            assert np.max(np.abs(x-xx))<1e-10 and np.max(np.abs(P-PP))<1e-10
            h,H=model.batch(x[None],D["spec"]);h=h[0];H=H[0]
            rho_p=math.hypot(*(x[:2]-D["anchor"]))
            rho_prev=math.hypot(*((D["x0"][:2] if k==0 else f[0][k-1,:2])-D["anchor"]))
            sigma=A.E.sig(rho_prev if semantic=="LEGACY" else rho_p)
            assert abs(sigma-f[3][k])<1e-12
            group=[]
            for mean,mu in mus.items():
                for variance in ("NONE",semantic):
                    R=D["R"][k].copy()
                    if variance!="NONE":R[1,1]+=sigma*sigma
                    v=D["z"][k]-h-mu[k]
                    S=H@P@H.T+R;S=.5*(S+S.T)
                    NIS=float(v@np.linalg.solve(S,v))
                    K=np.linalg.solve(S,H@P).T
                    rec=dict(case=case,semantic=semantic,packet=k,time_s=float(D["t"][k]),
                             mean=mean,variance=variance,
                             first_fixed_accept=bool(f[2][k]),first_self_accept=bool(s[2][k]),
                             rho_prev_post=rho_prev,rho_current_prior=rho_p,sigma=sigma,
                             Rss=float(R[1,1]),Rrs=float(R[0,1]),NIS=NIS,
                             NIS_accept=bool(NIS<=A.THRESH),K_norm=float(np.linalg.norm(K)),
                             innovation_r=float(v[0]),innovation_s=float(v[1]))
                    rows.append(rec);group.append(rec)
            assert len(group)==4
            n={r["mean"]+"_"+("VAR" if r["variance"]!="NONE" else "ORIG"):r["NIS"] for r in group}
            checks.append(dict(case=case,semantic=semantic,packet=k,
                               NIS_BB=n["BB_ORIG"],NIS_MB=n["MB_ORIG"],
                               NIS_BB_VAR=n["BB_VAR"],NIS_MB_VAR=n["MB_VAR"],
                               combined_mean_effect=n["MB_ORIG"]-n["BB_ORIG"],
                               combined_variance_effect=n["BB_VAR"]-n["BB_ORIG"],
                               interaction=n["MB_VAR"]-n["MB_ORIG"]-n["BB_VAR"]+n["BB_ORIG"],
                               baseline_mask=bool(D["acc"][k])))
            print("A4_SHADOW "+json.dumps(checks[-1],ensure_ascii=False),flush=True)
    with (out/"A4_MATCHED_PRIOR_NIS_2X2.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (out/"A4_NIS_CONTRASTS.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
    qa=dict(status="PASS_SHADOW_2X2_FIRST_FLIP",n_cases=len(CASES),n_rows=len(rows),
            n_contrasts=len(checks),same_prior_all_arms=True,
            boundary="Local same-MB_VAR-prior NIS only; not full recursive BB counterfactual, nor causal fraction of final RMSE.",
            self_review_only=True,source_mutation=False)
    (out/"A4_SHADOW_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("A4_SHADOW_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "a4_shadow_out")
