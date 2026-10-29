#!/usr/bin/env python3
"""RA5-1 method QA: covariance transforms, duplicate observation, conditional Fisher, MA(1).
No RF-dependent science estimand; all inputs synthetic and explicitly specified.
"""
import csv,datetime,json,math,os,pathlib,sys
import numpy as np

def req(c,msg):
    if not c:raise RuntimeError(msg)
def maxerr(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def update(x,P,H,R,z):
    v=z-H@x
    S=H@P@H.T+R
    K=np.linalg.solve(S,H@P).T
    nx=x+K@v
    A=np.eye(len(x))-K@H
    PP=A@P@A.T+K@R@K.T
    return nx,.5*(PP+PP.T),float(v@np.linalg.solve(S,v)),K
def dump(path,rows):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main(out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    P=np.array([[.04,.003,0,0],[.003,.03,.001,0],[0,.001,.015,.0001],[0,0,.0001,.0003]])
    x=np.array([.4,-.3,.08,.001]);z=np.array([.7,.02,.2])
    J=np.array([[.9,.4,.02,0],[.01,.05,1.7,.02],[-.02,.03,-.7,.03]])
    L=np.array([[.07,0,0],[.01,.05,0],[-.002,.03,.04]])
    R=L@L.T
    eig=np.linalg.eigvalsh(R)
    req(eig.min()>1e-8,"ERR_R_PSD")
    T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,-1.,1.]])
    ya=update(x,P,J,R,z)
    yb=update(x,P,T@J,T@R@T.T,T@z)
    errX=maxerr(ya[0],yb[0]);errP=maxerr(ya[1],yb[1]);errNIS=abs(ya[2]-yb[2])
    req(max(errX,errP,errNIS)<1e-10,"ERR_TWO_TAP_CHANGE_OF_BASIS")
    Ia=J.T@np.linalg.solve(R,J);Ib=(T@J).T@np.linalg.solve(T@R@T.T,T@J)
    req(maxerr(Ia,Ib)<1e-10,"ERR_FISHER_BASIS")

    z0=z[:2];J0=J[:2];R0=R[:2,:2]
    Adup=np.array([[1.,0.],[0.,1.],[0.,1.]])
    Rd=Adup@R0@Adup.T
    y0=update(x,P,J0,R0,z0)
    Sd=Adup@(J0@P@J0.T+R0)@Adup.T
    innovation=Adup@(z0-J0@x)
    Kd=P@J0.T@Adup.T@np.linalg.pinv(Sd,rcond=1e-12)
    xd=x+Kd@innovation;Pd=P-Kd@Adup@J0@P
    errdup=max(maxerr(xd,y0[0]),maxerr(Pd,y0[1]))
    req(errdup<1e-10,"ERR_DUPLICATE_ZERO_INFO")
    Idup=(Adup@J0).T@np.linalg.pinv(Rd,rcond=1e-12)@(Adup@J0)
    I0=J0.T@np.linalg.solve(R0,J0)
    req(maxerr(Idup,I0)<1e-10,"ERR_DUPLICATE_FISHER")
    Iwrong=(Adup@J0).T@np.linalg.solve(np.diag(np.diag(Rd)),Adup@J0)
    false_info=float(np.trace(Iwrong-I0))
    req(false_info>1,"ERR_NEGATIVE_FIXTURE_FAILED_DIAGONAL")

    Rzz=R[:2,:2];Rdz=R[2,:2];Rzd=R[:2,2]
    Rcond=float(R[2,2]-Rdz@np.linalg.solve(Rzz,Rzd))
    Jcond=J[2]-Rdz@np.linalg.solve(Rzz,J[:2])
    add=np.outer(Jcond,Jcond)/Rcond
    req(Rcond>0 and maxerr(Ia,I0+add)<1e-10,"ERR_CONDITIONAL_INCREMENT")
    eig_add=np.linalg.eigvalsh(add)
    req(eig_add.min()>-1e-10,"ERR_CONDITIONAL_INFORMATION_NOT_PSD")
    conditional=dict(conditional_variance=Rcond,delta_fisher_trace=float(np.trace(add)),
       delta_fisher_max_eigen=float(eig_add.max()),delta_fisher_min_eigen=float(eig_add.min()))

    rng=np.random.default_rng(20261029)
    sigma=.3
    noise=rng.normal(size=300000)*sigma
    diff=noise[1:]-noise[:-1]
    variance=float(np.var(diff));lag=float(np.mean((diff[1:]-diff[1:].mean())*(diff[:-1]-diff[:-1].mean())))
    req(abs(variance-2*sigma*sigma)<.005 and abs(lag+sigma*sigma)<.005,
        "ERR_MA1_SAMPLE")
    # Geometry-vs-noise synthetic 2x2, equal time/obs and prior, no physical extrapolation.
    jlow=J0.copy();jlow[1]*=.45
    jhigh=J0.copy();jhigh[1]*=1.7
    rows=[]
    for g,H in (("LOW",jlow),("HIGH",jhigh)):
        for n,Rm in (("LOW",R0*.6),("HIGH",R0*2)):
            I=H.T@np.linalg.solve(Rm,H)
            post=np.linalg.inv(np.linalg.inv(P)+I)
            rows.append(dict(geometry=g,noise=n,fisher_trace=float(np.trace(I)),yaw_fisher=float(I[2,2]),
                post_heading_var=float(post[2,2]),conditional_nuisance="NOT_INCLUDED",science="SYNTHETIC_FIXTURE"))
    dump(out/"RA5_J_SIGMA_SYNTHETIC_2X2.csv",rows)
    # Toy first-stage observability for psi and b_s (dimensionless scaled states).
    Hsame=np.array([[.4,1.],[.4,1.]])
    Hdiv=np.array([[.4,1.],[1.2,1.]])
    gr=[]
    for label,H in (("SAME_GEOMETRY",Hsame),("CHANGED_GEOMETRY",Hdiv)):
        mat=H.T@H
        e=np.linalg.eigvalsh(mat)
        gr.append(dict(design=label,rank=int(np.linalg.matrix_rank(mat,tol=1e-10)),
             eig_min=float(e[0]),eig_max=float(e[-1]),
             empirically_separable=bool(e[0]>1e-10)))
    req(gr[0]["rank"]==1 and gr[1]["rank"]==2,"ERR_OBSERVABILITY_RANK_FIXTURE")
    dump(out/"RA5_OBSERVABILITY_TOY.csv",gr)
    qa=dict(status="PASS_RA5_1_METHOD_ONLY",date_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      norm_four_state=True,synthetic_only=True,transform=dict(X_max=errX,P_max=errP,NIS_abs=errNIS,
        fisher_max=maxerr(Ia,Ib)),duplicate=dict(state_P_max=errdup,fisher_max=maxerr(Idup,I0),
          wrong_diagonal_spurious_fisher_trace=false_info),
      conditional_increment=conditional,ma1=dict(variance=variance,lag1_cov=lag,
        analytic_variance=2*sigma*sigma,analytic_lag1_cov=-sigma*sigma),
      checks=["FULL_COV_BASIS","DUPLICATE_RANK","DIAGONAL_NEGATIVE_FIXTURE",
              "CONDITIONAL_FISHER","MA1","J_SIGMA_2X2","OBSERVABILITY_RANK"],
      actual_RF_covariance="NOT_ESTIMATED",online_feature_data="NOT_CHECKED",
      estimator_R0_R5="NOT_RUN",external_generalization="NOT_RUN",
      independent_auditor=False,science_release=False,current_source_sha=os.getenv("GITHUB_SHA","UNKNOWN"))
    (out/"RA5_P1_MATH_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_P1_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":main(sys.argv[1] if len(sys.argv)>1 else "ra5_math_out")
