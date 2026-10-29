#!/usr/bin/env python3
"""RA5-3/5: real archived FFD Jacobian geometry with controlled covariance,
plus structural 4+1-state observability and nuisance marginalization.
No calibrated real temporal process covariance: method/identifiability diagnostics only.
"""
import csv,datetime,json,math,os,pathlib,sys
import numpy as np
HERE=pathlib.Path(__file__).resolve()
sys.path.insert(0,str(HERE.parents[1]/"ra4"))
import ra4_effect_isolation as A

def req(b,msg):
    if not b:raise RuntimeError(msg)
def dump(file,rows):
    with file.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sym(x):return .5*(x+x.T)

def main(out):
    out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True)
    model=A.C.base_model()
    scales4=np.diag([.1,.1,math.radians(5),math.radians(.2)])
    scales5=np.diag([.1,.1,math.radians(5),math.radians(.2),.1])
    source=[];factor=[];obs=[]
    for case in A.CASES:
        ref=A.C.load_control(case,"B0");jb=ref["jb"]
        gt=np.asarray(ref["truth_scoring_only"],float)
        t=np.asarray(ref["t_s"],float)
        n=len(t);req(n>100,"ERR_EMPTY_GT")
        ds,gy,dt,x0=A.E.build_controls(t,gt[:,:3],"B0")
        spec=A.C.CASES[case]
        k1=int(round((n-1)*.25));k2=int(round((n-1)*.75))
        states=np.column_stack([gt[[k1,k2],:3],np.zeros(2)])
        hh,J=model.batch(states,spec);J=np.asarray(J)
        req(J.shape==(2,2,4),"ERR_FFD_J_SHAPE")
        Rbase=np.asarray(ref["R"][k1,jb],float)
        P0=np.asarray(ref["Pprior"][0,jb],float)
        req(np.linalg.eigvalsh(Rbase).min()>0 and np.linalg.eigvalsh(P0).min()>0,"ERR_BAD_PRIOR_R")
        for gi,k in enumerate((k1,k2)):
            H=J[gi]
            for noise,fac in (("HALF",.5),("DOUBLE",2.)):
                R=Rbase*fac
                I=H.T@np.linalg.solve(R,H)
                eigen=np.linalg.eigvalsh(sym(scales4@I@scales4))
                Ppost=np.linalg.inv(np.linalg.inv(P0)+I)
                # Marginalize nuisance b_s using specified synthetic prior.
                H5=np.pad(H,((0,0),(0,1)))
                H5[1,4]=1.
                I5=H5.T@np.linalg.solve(R,H5)
                Ipose=I5[:4,:4];Ixb=I5[:4,4];Ibb=float(I5[4,4]+100.)
                Ieff=sym(Ipose-np.outer(Ixb,Ixb)/Ibb)
                req(np.linalg.eigvalsh(Ieff).min()>-1e-8,"ERR_NUISANCE_SCHUR")
                factor.append(dict(case=case,geometry="FIXED_POSE_Q25" if gi==0 else "FIXED_POSE_Q75",
                    pose_id=k,noise_factor=fac,noise_arm=noise,
                    geometry_selection="TIME_QUARTILES_NOT_OUTCOME_SELECTED",
                    sigma_source="ARCHIVED_R0_K_Q25",sigma_physical_intervention="SYNTHETIC_SCALE_ONLY",
                    heading_fisher=float(I[2,2]),pose_fisher_trace=float(np.trace(I)),
                    normalized_nonzero_fisher_min=float(eigen[-2]),
                    normalized_fisher_max=float(eigen[-1]),
                    heading_post_sd_rad=float(np.sqrt(Ppost[2,2])),
                    nuisance_marginal_heading_fisher=float(Ieff[2,2]),
                    raw_r_s_R_correlation=float(R[0,1]/math.sqrt(R[0,0]*R[1,1]))))
        for frac in (.1,.45,.8):
            start=int(round((n-41)*frac)); stop=start+40
            traj=np.column_stack([gt[start:stop,:3],np.zeros(40)])
            _,Hseries=model.batch(traj,spec)
            req(np.asarray(Hseries).shape==(40,2,4),"ERR_H_SERIES")
            Phi=np.eye(5);W=np.zeros((5,5))
            for offset,k in enumerate(range(start,stop)):
                if offset:
                    xprev=np.r_[gt[k-1,:3],0.]
                    ds0,gy0,dt0=float(ds[k]),float(gy[k]),float(dt[k])
                    Q=np.diag([2e-5*abs(ds0),math.radians(.015)**2*dt0,0])
                    F=A.predict(xprev,np.eye(4),ds0,gy0,dt0,Q)[2]
                    F5=np.eye(5);F5[:4,:4]=F
                    Phi=F5@Phi
                H5=np.pad(np.asarray(Hseries[offset],float),((0,0),(0,1)))
                H5[1,4]=1.
                v=H5@Phi
                R=np.asarray(ref["R"][k,jb],float)
                req(np.linalg.eigvalsh(R).min()>0,"ERR_MODEL_R_PSD")
                W+=v.T@np.linalg.solve(R,v)
            W=sym(W)
            eig=np.linalg.eigvalsh(sym(scales5@W@scales5))
            rank=int(np.sum(eig>max(1e-9,float(eig[-1])*1e-8)))
            for sigma_b in (.02,.1,.5):
                Pb=np.diag([.1**2,.1**2,math.radians(5)**2,
                            math.radians(.2)**2,sigma_b**2])
                Ppost=np.linalg.inv(np.linalg.inv(Pb)+W)
                corr=float(Ppost[2,4]/np.sqrt(Ppost[2,2]*Ppost[4,4]))
                Imarg=sym(W[:4,:4]-np.outer(W[:4,4],W[4,:4])/(W[4,4]+1/sigma_b**2))
                obs.append(dict(case=case,window_start=start,window_end=stop-1,
                     window_s=float(t[stop-1]-t[start]),assumed_b_prior_std=sigma_b,
                     assumption="CONSTANT_B_S_WITHIN_WINDOW",
                     normalized_gramian_rank=rank,normalized_gramian_eig_min=float(eig[0]),
                     normalized_gramian_eig_max=float(eig[-1]),
                     normalized_gramian_condition=float(eig[-1]/max(eig[0],1e-30)),
                     yaw_b_posterior_corr=corr,heading_marginal_info=float(Imarg[2,2]),
                     heading_raw_info=float(W[2,2]),
                     physically_identifiable="NOT_PROVEN_FIELD_TIME_AND_RWHITE_QB_UNCALIBRATED"))
        source.append(dict(case=case,n_packet=n,source_code=A.HISTORIC_SOURCE,
            geometry_sample_1=k1,geometry_sample_2=k2,n_gramian_windows=3))
        print("RA5_P35_CASE "+json.dumps(source[-1]),flush=True)
    req(len(factor)==28 and len(obs)==63 and len(source)==7,"ERR_P35_ROWS")
    dump(out/"RA5_P3_J_SIGMA_FACTORIAL.csv",factor)
    dump(out/"RA5_P5_OBSERVABILITY.csv",obs)
    dump(out/"RA5_P35_SOURCE_ROWS.csv",source)
    qa=dict(status="PASS_P3_P5_CONTROLLED_DIAGNOSTICS_ONLY",
       n_routing_cases=7,n_JxSigma_cells=len(factor),n_gramian_rows=len(obs),
       p3_intervention="REAL_ARCHIVED_LOS_J_SYNTHETIC_0.5_2X_SAME_R_PRIOR",
       p5_assumed_nuisance_model="CONSTANT_B_WITHIN_40_PACKET_WINDOW",
       p5_white_colored_covariance_separation="BLOCKED_NOT_IDENTIFIED",
       p5_physical_validity="NOT_ESTABLISHED",
       independent_scenes=1,external_holdout="NONE",
       first_packet_RMSE="NOT_TESTED",filter_4vs5="BLOCKED_COVARIANCE",
       self_review_only=True,science_release=False,
       created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_P35_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_P35_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "ra5_p35_out")
