"""Offline alignment and rolling-information diagnostics; no filter replay."""
from pathlib import Path
import os,sys,json,hashlib,datetime,traceback
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import numpy as np
import pandas as pd
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
SRC=Path(r'D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849/p2')
CASES=['R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0'];PRIMARY=CASES[:3]
B=-.5315983906250129;CHECKS=[]
def dump(n,d):(ROOT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def event(msg):print(msg,flush=True)
def check(name,a,b,tol):
    err=float(np.max(abs(np.asarray(a)-np.asarray(b))));CHECKS.append(dict(name=name,max_abs=err,tolerance=tol,pass_check=err<=tol));assert err<=tol,(name,err)
def stop():
    f=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if f and Path(f).exists():raise RuntimeError('MANAGED_STOP')
def uncertainty(I,u):
    eig=np.linalg.eigvalsh(I);valid=eig[0]>max(1e-12,eig[-1]*1e-10)
    return (float(np.sqrt(u@np.linalg.solve(I,u))),float(eig[-1]/eig[0]),True) if valid else (np.inf,np.inf,False)

def main():
    assert not (ROOT/'INPUT_LOCK.json').exists()
    mp=SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json';manifest=json.loads(mp.read_text());cases={x['id']:x for x in manifest['cases']}
    files=[mp,Path(__file__),ROOT/'PROTOCOL.md',ROOT/'DEFINITIONS.md',BASE/'pass_rs_azimuth/P2_PASSES_GT.csv',SRC/'research/FFD_P0P3_20261016/source_model.py',SRC/'research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py']
    files += [BASE/'e1_e4/E1'/f'{c}_{b}.npz' for c in CASES for b in ['B0','L2']]
    lock=[dict(path=str(p.resolve()),sha256=sha(p),bytes=p.stat().st_size) for p in files]
    dump('INPUT_LOCK.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline='a6315bbbca54aa9c7d8ae4ab26183d8d94b51ec9',files=lock,command=sys.argv))
    passes=pd.read_csv(BASE/'pass_rs_azimuth/P2_PASSES_GT.csv');align=[];roll=[];summ=[];diagnostics=[]
    for cid in CASES:
        a=np.array(cases[cid]['anchor'])[:2];height=cases[cid]['anchor'][2]-cases[cid]['robot_z_m']
        for bias in ['B0','L2']:
            stop();z=np.load(BASE/'e1_e4/E1'/f'{cid}_{bias}.npz');t=np.round(z['t_s'],8);truth=z['truth_scoring_only'];dg=np.linalg.norm(truth[:,:2]-a,axis=1)
            for arm,aname in [('BB','A0'),('MB','A1')]:
                j=list(z['names']).index(aname);x=z['x'][:,j,:2];pr=z['prior'][:,j,:2];acc=z['acc'][:,j];nu=z['nu'][:,j];H=z['H'][:,j];R=z['R'][:,j];d=np.linalg.norm(pr-a,axis=1);rr=np.sqrt(d*d+height*height)
                check(cid+bias+arm+'_range_model',z['h'][:,j,0],rr+B,1e-12)
                check(cid+bias+arm+'_range_gradient',H[:,0,:2],(pr-a)/rr[:,None],1e-12)
                near=d<2;starts=np.flatnonzero(near&~np.r_[False,near[:-1]]);ends=np.flatnonzero(near&~np.r_[near[1:],False])
                ps=passes[(passes.case==cid)&(passes.bias==bias)]
                for p in ps.itertuples():
                    which=[(i,k) for i,k in zip(starts,ends) if t[i]<=p.min_d_time_s<=t[k]]
                    if not which:
                        diagnostics.append(dict(case=cid,bias=bias,arm=arm,pass_id=p.pass_id,result='NO_EST_EPISODE'));continue
                    ei,ej=which[0]
                    for pre in [5,10,20]:
                        for post in [5,10,20]:
                            stop();lo=max(t[0],t[ei]-pre);hi=min(t[-1],t[ej]+post);idx=np.flatnonzero((t>=lo)&(t<=hi));k0,k1=idx[0],idx[-1];used=idx[acc[idx]]
                            q=x[used]-x[k0];target=z['nu'][used,j,0]+z['h'][used,j,0];sd=np.sqrt(R[used,0,0]);origin=x[k0]
                            def fun(v):return (np.sqrt(np.sum((q+v-a)**2,axis=1)+height*height)+B-target)/sd
                            def jac(v):
                                u=q+v-a;r=np.sqrt(np.sum(u*u,axis=1)+height*height)
                                return u/r[:,None]/sd[:,None]
                            offsets=[(0,0)]+[(v,0) for v in [-2,-.5,.5,2]]+[(0,v) for v in [-2,-.5,.5,2]]
                            sols=[least_squares(fun,origin+np.array(off),jac=jac,loss='huber',f_scale=1.345,max_nfev=1000,ftol=1e-11,xtol=1e-11,gtol=1e-11) for off in offsets]
                            success=[s for s in sols if s.success and np.isfinite(s.cost)];best=min(success or sols,key=lambda s:s.cost)
                            uend=x[k1]-x[k0]+best.x-a;uend/=np.linalg.norm(uend);ut=np.array([-uend[1],uend[0]])
                            ug=truth[k1,:2]-a;ug/=np.linalg.norm(ug);utg=np.array([-ug[1],ug[0]])
                            residual=fun(best.x);J=jac(best.x);w=np.minimum(1.,1.345/np.maximum(abs(residual),1e-300));I=J.T@(w[:,None]*J)
                            sigma,cond,valid=uncertainty(I,ut);sigmag,_,_=uncertainty(I,utg)
                            before=float(utg@(x[k1]-truth[k1,:2])*100);after=float(utg@(x[k1]-x[k0]+best.x-truth[k1,:2])*100)
                            red=1-abs(after)/abs(before) if abs(before)>=.1 else np.nan
                            matches=[s for s in success if s.cost<=best.cost+max(1e-8,1e-6*abs(best.cost))]
                            spread=max([float(np.linalg.norm(s.x-best.x)*100) for s in matches] or [np.nan])
                            common=dict(case=cid,bias=bias,arm=arm,pass_id=p.pass_id,T_pre=pre,T_post=post,n_range=len(used),window_start_s=t[k0],window_end_s=t[k1],actual_pre_s=t[ei]-t[k0],actual_post_s=t[k1]-t[ej],dx_cm=float((best.x-origin)[0]*100),dy_cm=float((best.x-origin)[1]*100),dtheta_deg=0.,et_filter_end_cm=before,et_aligned_end_cm=after,reduction=red)
                            eligible=bool(len(used)>=30 and valid and best.success and np.isfinite(red))
                            align.append(dict(**common,dof=2,sigma_dt_cm=sigma*100,sigma_dt_gt_cm=sigmag*100,cond=cond,rank=int(np.linalg.matrix_rank(I)),cost=best.cost,optimality=best.optimality,solver_success=bool(best.success),near_tie_spread_cm=spread,eligible=eligible,pass_goal=bool(eligible and red>=.5 and sigma*100<3),result='VALID' if eligible else 'NA'))
                            # The rotational gauge is analytic, independent of optimizer quality.
                            q90=np.column_stack([-q[:,1],q[:,0]]);J3=np.column_stack([J,np.einsum('ni,ni->n',J,q90)]);I3=J3.T@(w[:,None]*J3)
                            d0=best.x-a;null=np.r_[-d0[1],d0[0],1.]
                            check('3d_gauge_null',J3@null,np.zeros(len(q)),1e-10)
                            xy=q+best.x-a;angle=.1;rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
                            check('rotation_range_invariant',np.sum((xy@rot.T)**2,axis=1),np.sum(xy*xy,axis=1),1e-10)
                            eig=np.linalg.eigvalsh(I3);rank=int(np.count_nonzero(eig>max(1e-12,eig[-1]*1e-10)));assert rank<=2
                            align.append(dict(**common,dof=3,sigma_dt_cm=np.inf,sigma_dt_gt_cm=np.inf,cond=np.inf,rank=rank,cost=best.cost,optimality=np.nan,solver_success=False,near_tie_spread_cm=np.nan,eligible=False,pass_goal=False,result='UNIDENTIFIABLE_ROTATION'))
                event(f'M3-pre {cid} {bias} {arm} complete')
                # Window-constant translation information and fixed endpoint tangent.
                h=H[:,0,:2];info=np.einsum('ni,nj->nij',h,h)/R[:,0,0,None,None]*acc[:,None,None]
                updates=np.einsum('nij,nj->ni',z['K'][:,j,:2],nu)*acc[:,None]
                ci=np.concatenate([np.zeros((1,2,2)),np.cumsum(info,axis=0)]);cu=np.vstack([np.zeros(2),np.cumsum(updates,axis=0)])
                ur=(pr-a)/d[:,None];uts=np.column_stack([-ur[:,1],ur[:,0]])
                for T in [5,10,20]:
                    local=[]
                    for k in np.flatnonzero((t>=30)&(t-t[0]>=T)):
                        left=np.searchsorted(t,round(float(t[k]-T),8),side='right');I=ci[k+1]-ci[left];st=float(uts[k]@(cu[k+1]-cu[left]));sigma,cond,valid=uncertainty(I,uts[k]);grp='near' if dg[k]<1.5 else 'mid' if dg[k]<4 else 'far'
                        row=dict(case=cid,bias=bias,arm=arm,T=T,k=int(k),t_s=float(t[k]),grp=grp,S_t_cm=100*st,sigma_t_cm=100*sigma,ratio=abs(st)/sigma if valid else np.nan,cond=cond,valid=valid,n_accepted=int(acc[left:k+1].sum()))
                        local.append(row);roll.append(row)
                    df=pd.DataFrame(local)
                    for grp in ['near','mid','far']:
                        gg=df[df.grp==grp];v=gg.loc[gg.valid,'ratio'];summ.append(dict(case=cid,bias=bias,arm=arm,T=T,grp=grp,n=len(gg),n_valid=len(v),n_singular=int((~gg.valid).sum()),ratio_med=float(v.median()) if len(v)>=30 else np.nan,ratio_p90=float(v.quantile(.9)) if len(v)>=30 else np.nan))
            pd.DataFrame(align).to_csv(ROOT/'M3PRE_ALIGNMENT.csv',index=False,na_rep='NA');pd.DataFrame(summ).to_csv(ROOT/'M2PRE_CONSISTENCY.csv',index=False,na_rep='NA')
    pd.DataFrame(roll).to_csv(ROOT/'M2PRE_PACKETS.csv.gz',index=False,compression='gzip',na_rep='NA');pd.DataFrame(diagnostics).to_csv(ROOT/'M3PRE_EPISODE_DIAGNOSTICS.csv',index=False)
    aa=pd.DataFrame(align);m3=[]
    for pre in [5,10,20]:
        for post in [5,10,20]:
            df=aa[(aa.dof==2)&(aa.arm=='MB')&(aa.T_pre==pre)&(aa.T_post==post)]
            count=0
            for cid in PRIMARY:
                q=df[(df.case==cid)&(df.pass_id==1)];count+=int(len(q)==2 and q.pass_goal.all())
            r5=df[df.case.str.startswith('R5')];robust=len(r5)==12 and bool(r5.pass_goal.all())
            m3.append(dict(T_pre=pre,T_post=post,primary_case_pass_count=count,R5_pass_count=int(r5.pass_goal.sum()),R5_expected_count=12,R5_all_pass=robust,GO=bool(count>=2 and robust)))
    mm=pd.DataFrame(summ);m2=[];m2detail=[]
    for T in [5,10,20]:
        count=0
        for cid in PRIMARY:
            pair=[]
            for bias in ['B0','L2']:
                d0=mm[(mm.case==cid)&(mm.bias==bias)&(mm.arm=='MB')&(mm.T==T)].set_index('grp').ratio_med
                rm=d0['near']/d0['mid'] if d0['mid']>0 else np.nan;rf=d0['near']/d0['far'] if d0['far']>0 else np.nan
                ok=bool(rm>=2 and rf>=2);pair.append(ok);m2detail.append(dict(case=cid,bias=bias,T=T,near_mid_ratio=rm,near_far_ratio=rf,GO=ok))
            count+=int(all(pair))
        m2.append(dict(T=T,primary_case_pass_count=count,GO=bool(count>=2)))
    pd.DataFrame(m3).to_csv(ROOT/'M3PRE_DECISIONS.csv',index=False);pd.DataFrame(m2).to_csv(ROOT/'M2PRE_DECISIONS.csv',index=False);pd.DataFrame(m2detail).to_csv(ROOT/'M2PRE_CONTRASTS.csv',index=False,na_rep='NA')
    for f in lock:assert sha(Path(f['path']))==f['sha256'],f['path']
    dump('PRE_CHECKS.json',dict(status='PASS',checks=CHECKS,inputs_unchanged=True,no_filter_replay=True))
    result=dict(M3_pre='GO' if any(x['GO'] for x in m3) else 'NO_GO',M2_pre='GO' if any(x['GO'] for x in m2) else 'NO_GO',M3_alignment_rows=len(align),M2_packet_rows=len(roll))
    dump('PRE_RESULT.json',result);event(json.dumps(result))
if __name__=='__main__':
    try:main()
    except BaseException as e:dump('PRE_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
