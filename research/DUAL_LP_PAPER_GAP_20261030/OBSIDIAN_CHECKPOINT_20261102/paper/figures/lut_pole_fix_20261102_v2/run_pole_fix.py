"""Frozen-condition 36-arm pole-only rerun, gated on math and old-LUT parity."""
from pathlib import Path
import sys,json,datetime,platform,time,traceback
import numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent/'lut_observer_swap_20261102'))
import replay_observer_swap as A
from pole_regularized_lut import PoleRegularizedLut
DG=A.DG
def dump(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def precheck(fixed,base):
    sp=DG.C.CASES['R5_aB_m0'];rows=[];outside=[];limits=[];joins=[];bounds=[]
    # Deterministic off-knot headings and azimuths; covers pole and both joins.
    for theta in [0,.1,.5,.999,1.,1.001,1.5,1.999,2.,2.001,4.,40.]:
      for psi in [-167.37,-42.63,17.31,112.77]:
       for alpha in [13.71,102.83]:
        rho=2.2*np.tan(np.radians(theta));x=np.array([10+rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.radians(psi),0.])
        h,j=fixed.model(x,sp);hb,jb=base.model(x,sp)
        assert np.array_equal(h[:1],hb[:1]) and np.array_equal(j[:1],jb[:1])
        if theta>=2.001:outside.append(float(max(abs(h-hb).max(),abs(j-jb).max())))
        for a in range(3):
            eps=1e-7;xp=x.copy();xm=x.copy();xp[a]+=eps;xm[a]-=eps
            fd=(fixed.model(xp,sp)[0]-fixed.model(xm,sp)[0])/(2*eps)
            rows.append(dict(theta_deg=theta,psi_deg=psi,alpha_deg=alpha,axis=a,max_abs_error=float(abs(fd-j[:,a]).max())))
    for psi in np.arange(-179.37,180,10):
      for rho in [0.,1e-6,1e-5,.001,.01]:
        values=[];jj=[]
        for alpha in np.arange(0,360,10):
            x=np.array([10+rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.radians(psi),0.])
            h,j=fixed.model(x,sp);values.append(h[1]);jj.append(np.linalg.norm(j[1,:2]))
        limits.append(dict(psi_deg=psi,rho_m=rho,s_range=float(np.ptp(values)),Jxy_max=float(max(jj))))
    for psi in np.arange(-179.37,180,2):
      for theta in [0,.5,1.,1.5,1.9,2.]:
       for alpha in np.arange(0,360,30):
        rho=2.2*np.tan(np.radians(theta));x=np.array([10+rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.radians(psi),0.]);bounds.append(fixed.model(x,sp)[0][1])
    for theta in [1.,2.]:
      for psi in [-167.37,-42.63,17.31,112.77]:
       def at(th):
        rho=2.2*np.tan(np.radians(th));x=np.array([10+rho*.8,rho*.6,np.radians(psi),0.]);return fixed.model(x,sp)
       h0,j0=at(theta-1e-7);h1,j1=at(theta+1e-7)
       joins.append(dict(theta_deg=theta,psi_deg=psi,h_jump=float(abs(h0-h1).max()),J_jump=float(abs(j0-j1).max())))
    fd=pd.DataFrame(rows);lim=pd.DataFrame(limits);join=pd.DataFrame(joins)
    fd.to_csv(OUT/'PRECHECK_FINITE_DIFFERENCES.csv',index=False);lim.to_csv(OUT/'PRECHECK_POLE_LIMIT.csv',index=False);join.to_csv(OUT/'PRECHECK_JOINS.csv',index=False)
    checks=dict(fd_samples=len(fd),fd_max_abs=float(fd.max_abs_error.max()),outside_max_abs=max(outside),pole_exact_max_range=float(lim[lim.rho_m==0].s_range.max()),pole_1um_max_range=float(lim[lim.rho_m==1e-6].s_range.max()),pole_Jxy_max=float(lim.Jxy_max.max()),join_h_max=float(join.h_jump.max()),join_J_max=float(join.J_jump.max()),s_sample_min=float(min(bounds)),s_sample_max=float(max(bounds)),fit_residual_rms=float(np.sqrt(np.mean(fixed.fit_residual**2))))
    dump('PRECHECK_RESULTS.json',checks)
    assert checks['fd_max_abs']<2e-5,checks
    assert checks['outside_max_abs']==0 and checks['pole_exact_max_range']==0
    assert checks['pole_1um_max_range']<1e-5 and checks['pole_Jxy_max']<5
    assert checks['join_h_max']<1e-6 and checks['join_J_max']<1e-4
    assert min(bounds)>=-1-1e-6 and max(bounds)<=1+1e-6
    return checks

def main():
    assert not (OUT/'CONTRACT.json').exists(),'DO_NOT_OVERWRITE'
    old=json.loads((A.OUT/'CONTRACT.json').read_text());assert all(A.sha(p)==h for p,h in old['input_hashes'].items())
    paths=list(old['input_hashes'])+[str(A.OUT/'ALL_SCORES_72.csv'),str(A.OUT/'RESULT_CHECKS.json'),str(__file__),str(OUT/'pole_regularized_lut.py')]
    paths += [str(A.OUT/f'{case}_{bias}_{stage}_LUT.npz') for case in A.CASES for bias in A.BIASES for stage in A.STAGES]
    gov=Path('C:/Users/Myoungsun Kim/.codex/research-governance');paths+=[str(gov/'ROLE_PROPOSER.md')]
    hashes={p:A.sha(p) for p in sorted(set(paths))}
    contract=dict(question_id='DLP-ANCHORB-LUT-POLE-FIX-20261102',roles='PROPOSER then IMPLEMENTER then AUDITOR self-check; not independent',authorization='User requested LUT pole repair and 12-condition rerun with all other settings unchanged',source_identity=old['checkout_status'],declared_source_commit=old['source_declared_original_commit'],evidence_commit=old['source_evidence_commit'],input_hashes=hashes,
      change='Only h_s and H_s at theta<2deg; quadratic Cartesian scalar cap from original LUT rings theta=2,4deg, quintic blend at 1<theta<2 to downward extension of NORMAL original 2..4deg cell; original h/H exactly at theta>=2. No SourceFFD cap/predictions, RF or truth used to fit cap.',
      math='q=(u,v)/(height*tan(2deg)); p=[1,qx,qy,qx²,qx*qy,qy²]; c(heading) fit to 2,4deg frozen rings, periodic linear interpolation at original 2deg heading grid; s_cap=p*c; s=(1-w)*s_cap+w*s_ext; s_ext=s_2+(theta-2)*(s_4-s_2)/2; H includes derivatives of extension and w. w=6z^5-15z^4+10z^3,z=theta-1 in degrees.',
      failed_predecessor='Sibling lut_pole_fix_20261102: failed precheck at theta=2deg because contaminated 0..2deg derivative was blended back in; NO FILTER RUNS; original gates retained, no result-based tuning',
      fixed_before_results=True,not_performance_tuned=True,cases=A.CASES,biases=A.BIASES,stages=A.STAGES,controls=old['controls'],adaptive_rule=old['adaptive_rule'],score=old['score'],expected_new_paths=36,expected_old_lut_parity_paths=36,expected_total_score_rows=108,
      gate_order='math prechecks -> all 36 original-LUT replay parity -> 36 repaired-LUT runs -> actual-state Jacobian and scoring checks',precheck_thresholds=dict(fd_abs=2e-5,outside_exact=0,exact_pole_range=0,pole_1um_range=1e-5,pole_Jxy_max=5,join_h=1e-6,join_J=1e-4,physical_s_tolerance=1e-6),baseline_thresholds=old['validation_thresholds'],allowed_claim='Post-hoc repair on same single scene/seed; observed correction of pole artifact and paired changes only; no independent environment, optimality, calibration or automatic manuscript adoption',python=sys.version,numpy=np.__version__,platform=platform.platform(),managed_run_id=__import__('os').environ.get('MANAGED_PROCESS_RUN_ID'),thread_id=__import__('os').environ.get('MANAGED_PROCESS_THREAD_ID'),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    dump('CONTRACT.json',contract)
    base=A.FrozenLut(A.OLD);fixed=PoleRegularizedLut(base);off=PoleRegularizedLut(base,enabled=False)
    np.savez_compressed(OUT/'CARTESIAN_CAP_COEFFICIENTS.npz',psi_deg=fixed.psi,coeff=fixed.coeff,fit_residual=fixed.fit_residual)
    checks=precheck(fixed,base);print('MATH_GATE_PASS',checks,flush=True)
    data={(c,b):A.make_data(c,b) for c in A.CASES for b in A.BIASES}
    rows=[];packets=[];parity=[];diffs=[];actualfd=[]
    archived=pd.read_csv(A.OUT/'ALL_SCORES_72.csv')
    for c in A.CASES:
     for b in A.BIASES:
      for stage in A.STAGES:
        A.stop_check();D,bg,mode=A.arm_data(data[c,b],stage)
        X,P,L=DG.run(D,bg,mode,'self',model=off)
        with np.load(A.OUT/f'{c}_{b}_{stage}_LUT.npz') as ref:
            dx=float(abs(X-ref['X']).max());dp=float(abs(P-ref['PX']).max());dr=float(np.nanmax(abs(L['Ru']-ref['Ru'])));dm=int(np.count_nonzero(L['used']!=ref['used']))
            assert dx<1e-10 and dp<1e-10 and dr<1e-12 and dm==0,(c,b,stage,dx,dp,dr,dm)
        parity.append(dict(case=c,bias=b,stage=stage,X_max_abs=dx,P_max_abs=dp,R_max_abs=dr,gate_mismatch=dm))
        r,p=A.score(D,X,P,L,'LUT_original',stage);rows.append(r);packets.append(p)
        with np.load(A.refpath(c,b,stage)) as ref:
            r,p=A.score(D,ref['X'],ref['PX'],ref,'SourceFFD',stage)
            for k in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose']:
                v=archived[(archived.case==c)&(archived.bias==b)&(archived.stage==stage)&(archived.observer=='SourceFFD')][k].iloc[0]
                assert np.isclose(r[k],v,rtol=1e-10,atol=1e-9)
            rows.append(r);packets.append(p)
        print('OLD_LUT_PARITY_PASS',c,b,stage,flush=True)
    pd.DataFrame(parity).to_csv(OUT/'ORIGINAL_LUT_BASELINE_PARITY.csv',index=False)
    dump('BASELINE_GATE.json',dict(status='PASS',n_old_lut=36,source_archived_scores_checked=36))
    for c in A.CASES:
     for b in A.BIASES:
      for stage in A.STAGES:
        A.stop_check();D,bg,mode=A.arm_data(data[c,b],stage);X,P,L=DG.run(D,bg,mode,'self',model=fixed)
        h,J=fixed.batch(L['xp'],D['spec']);assert np.allclose(h,L['hx'],atol=1e-12)
        rho=np.linalg.norm(np.vstack([D['x0'][:2],X[:-1,:2]])-D['anchor'],axis=1);sg=np.interp(rho,DG.HAND[0],DG.HAND[1]);er=D['R'].copy()
        if mode=='var':er[:,1,1]+=sg**2
        assert np.allclose(er,L['Ru'],rtol=0,atol=1e-14)
        assert np.array_equal(L['nis']<=DG.GATE,L['used'])
        assert np.allclose(J@L['Pp']@J.transpose(0,2,1),L['HPH'],rtol=1e-8,atol=1e-9)
        height=D['spec']['anchor'][2]-D['spec']['robot_z_m'];theta=np.degrees(np.arctan2(np.linalg.norm(L['xp'][:,:2]-D['anchor'],axis=1),height));changed=theta<2
        hb,jb=A.LutBatch().batch(L['xp'][~changed],D['spec']) if (~changed).any() else (np.empty((0,2)),np.empty((0,2,4)))
        assert np.array_equal(h[~changed],hb) and np.array_equal(J[~changed],jb)
        for k in np.flatnonzero(changed):
          for a in range(3):
            eps=1e-7;xp=L['xp'][k].copy();xm=xp.copy();xp[a]+=eps;xm[a]-=eps
            fd=(fixed.model(xp,D['spec'])[0]-fixed.model(xm,D['spec'])[0])/(2*eps);err=float(abs(fd-J[k,:,a]).max())
            actualfd.append(dict(case=c,bias=b,stage=stage,k=int(k),axis=a,theta_deg=float(theta[k]),max_abs_error=err))
            assert err<2e-5,(c,b,stage,k,a,err)
        with np.load(A.OUT/f'{c}_{b}_{stage}_LUT.npz') as ref:
            gd=int(np.count_nonzero(L['used']!=ref['used']));rd=float(np.nanmax(abs(L['Ru']-ref['Ru'])))
            changes=dict(case=c,bias=b,stage=stage,n_modified_prior=int(changed.sum()),gate_changes_vs_old=gd,R_max_difference_vs_old=rd,X_max_abs_difference_vs_old=float(abs(X-ref['X']).max()))
            if not changed.any():assert np.array_equal(X,ref['X']) and np.array_equal(P,ref['PX'])
        diffs.append(changes)
        np.savez_compressed(OUT/f'{c}_{b}_{stage}_LUT_fixed.npz',X=X,PX=P,J=J,t=D['t'],gt=D['gt'],z=D['z'],mu=D['mu'][bg],base_R=D['R'],ds=D['ds'],gy=D['gy'],dt=D['dt'],x0=D['x0'],P0=D['P0'],rho_lookup=rho,sigma_lookup=sg,theta_prior_deg=theta,**L)
        r,p=A.score(D,X,P,L,'LUT_fixed',stage);rows.append(r);packets.append(p)
        print('FIXED_DONE',c,b,stage,'heading',r['head_rmse'],'XYcm',r['xy_rmse_cm'],'NEES3',r['nees_pose'],flush=True)
    df=pd.DataFrame(rows);assert len(df)==108 and not df.duplicated(['case','bias','stage','observer']).any()
    df.to_csv(OUT/'ALL_SCORES_108.csv',index=False);pd.concat(packets,ignore_index=True).to_csv(OUT/'PACKET_ERRORS_AND_NEES.csv.gz',index=False)
    pd.DataFrame(diffs).to_csv(OUT/'GATE_VARIANCE_AND_CAP_USAGE.csv',index=False);pd.DataFrame(actualfd).to_csv(OUT/'ACTUAL_CAP_PRIOR_FINITE_DIFFERENCES.csv',index=False)
    metrics=['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']
    wide=df.pivot(index=['case','route','bias','stage'],columns='observer',values=metrics);wide.columns=[f'{a}_{b}' for a,b in wide.columns];wide=wide.reset_index();wide.to_csv(OUT/'THREE_OBSERVERS_36.csv',index=False)
    assert all(A.sha(p)==v for p,v in hashes.items())
    dump('RESULT_CHECKS.json',dict(status='EXECUTION_AND_SELF_CHECK_COMPLETED',new_fixed_paths=36,original_lut_parity=36,source_scores_verified=36,metric_rows=108,inputs_unchanged=True,all_P_positive_definite=True,adaptive_rule_verified=True,NEES_solve_Cholesky_verified=True,actual_cap_fd_count=len(actualfd),actual_cap_fd_max_abs=max((r['max_abs_error'] for r in actualfd),default=0),independent_audit=False,adopted=False,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print('ALL_36_FIXED_RUNS_COMPLETE',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException as e:
        dump('FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
