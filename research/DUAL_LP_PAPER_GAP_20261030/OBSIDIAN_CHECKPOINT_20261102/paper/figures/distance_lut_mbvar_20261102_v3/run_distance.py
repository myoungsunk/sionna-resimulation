from pathlib import Path
import sys,os,json,datetime,platform,time,traceback
import numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent; FIX=OUT.parent/'lut_pole_fix_20261102_v3'
sys.path[:0]=[str(FIX),str(OUT.parent/'lut_observer_swap_20261102')]
import replay_observer_swap as A
from pole_regularized_lut import PoleRegularizedLut
from distance_lut import DistanceLut
DG=A.DG
def dump(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def math_gate(model,base,source):
    # Off inherited grid knots, including pole and both repaired joins.
    rows=[]; joins=[]; limits=[]; vals=[]; sp=DG.C.CASES[A.CASES[0]]
    for theta in [0.,.1,.5,.999,1.,1.001,1.5,1.999,2.,2.001,4.001,40.001,76.001]:
      for psi in [-167.37,-42.63,17.31,112.77]:
       for alpha in [13.71,102.83]:
        rho=2.2*np.tan(np.radians(theta)); x=np.array([10+rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.radians(psi),0.])
        h,j=model.model(x,sp); hb,jb=base.model(x,sp)
        assert np.array_equal(h[:1],hb[:1]) and np.array_equal(j[:1],jb[:1]);vals.append(h[1])
        for a in range(3):
            xp=x.copy();xm=x.copy();xp[a]+=1e-7;xm[a]-=1e-7
            fd=(model.model(xp,sp)[0]-model.model(xm,sp)[0])/2e-7
            rows.append(dict(theta_deg=theta,psi_deg=psi,alpha_deg=alpha,axis=a,max_abs_error=float(abs(fd-j[:,a]).max())))
    for theta in [1.,2.]:
      for psi in [-167.37,-42.63,17.31,112.77]:
        def at(th):
            r=2.2*np.tan(np.radians(th));return model.model(np.array([10+.8*r,.6*r,np.radians(psi),0.]),sp)
        h0,j0=at(theta-1e-7);h1,j1=at(theta+1e-7)
        joins.append(dict(theta=theta,h_jump=float(abs(h0-h1).max()),J_jump=float(abs(j0-j1).max())))
    for psi in [-167.37,-42.63,17.31,112.77]:
      ss=[]; jj=[]
      for alpha in np.arange(0,360,10):
        x=np.array([10.,0.,np.radians(psi),0.]);h,j=model.model(x,sp);ss.append(h[1]);jj.append(np.linalg.norm(j[1,:2]))
      limits.append(dict(psi_deg=psi,s_range=float(np.ptp(ss)),Jxy_max=float(max(jj))))
    # Direct node values and independent analytic SourceFFD implementation agree.
    nodes=[]
    for i in [1,2,10,20,30,38]:
      for j,k in [(17,32),(83,114),(141,167)]:
        theta=2*i;alpha=180-2*j;psi=alpha+180-(-180+2*k);rho=2.2*np.tan(np.radians(theta))
        x=np.array([[10+rho*np.cos(np.radians(alpha)),rho*np.sin(np.radians(alpha)),np.radians(psi),0.]])
        h,J=source.batch(x,sp);direct=model.base.s.raw([(i,j,k)])[0]
        htab=model.model(x[0],sp)[0][1]
        # At theta>=2 the sum is original scalar + (actual - direct10).
        s10=model.base.s.raw([(i,j,k)],10.)[0]
        nodes.append(dict(i=i,j=j,k=k,direct_vs_Source=float(abs(direct-h[0,1])),original_vs_direct10=float(abs(base.s[i,j,k]-s10)),table_vs_source=float(abs(htab-h[0,1]))))
    fd=pd.DataFrame(rows);join=pd.DataFrame(joins);node=pd.DataFrame(nodes)
    fd.to_csv(OUT/'PRECHECK_FD.csv',index=False);join.to_csv(OUT/'PRECHECK_JOINS.csv',index=False);node.to_csv(OUT/'PRECHECK_NODES.csv',index=False)
    check=dict(fd_max=float(fd.max_abs_error.max()),join_h_max=float(join.h_jump.max()),join_J_max=float(join.J_jump.max()),pole_range_max=max(v['s_range'] for v in limits),pole_Jxy_max=max(v['Jxy_max'] for v in limits),direct_Source_max=float(node.direct_vs_Source.max()),original_direct10_max=float(node.original_vs_direct10.max()),sample_s_min=float(min(vals)),sample_s_max=float(max(vals)))
    dump('MATH_GATE.json',check)
    assert check['fd_max']<2e-5 and check['join_h_max']<1e-6 and check['join_J_max']<1e-4
    assert check['pole_range_max']==0 and check['pole_Jxy_max']<5
    assert check['direct_Source_max']<1e-9 and check['original_direct10_max']<1e-6
    assert min(vals)>=-1-1e-6 and max(vals)<=1+1e-6
    print('MATH_GATE_PASS',check,flush=True)

def main():
    assert not (OUT/'CONTRACT.json').exists(),'DO_NOT_OVERWRITE'
    prior=json.loads((FIX/'CONTRACT.json').read_text(encoding='utf-8')); locked=dict(prior['input_hashes'])
    for c in A.CASES:
      for b in A.BIASES:
        for p in [FIX/f'{c}_{b}_PROPOSED_MB_VAR_LUT_fixed.npz',A.refpath(c,b,'PROPOSED_MB_VAR')]:locked[str(p)]=A.sha(p)
    partial=list((OUT.parent/'distance_lut_mbvar_20261102_v2').glob('*_MB_VAR_DISTANCE_LUT.npz'))
    for p in [Path(__file__),OUT/'distance_lut.py',FIX/'pole_regularized_lut.py',FIX/'ALL_SCORES_108.csv',*partial]:locked[str(p)]=A.sha(p)
    assert all(A.sha(p)==h for p,h in locked.items())
    dump('CONTRACT.json',dict(question_id='DLP-ANCHORB-DISTANCE-LUT-MBVAR-20261102',roles='PROPOSER then IMPLEMENTER then self-check; not independent',source_identity=prior['source_identity'],declared_source_commit=prior['declared_source_commit'],input_hashes=locked,cases=A.CASES,biases=A.BIASES,stage='PROPOSED_MB_VAR',expected_new_runs=12,expected_baseline_parity=12,
      intervention='On unchanged 2deg scalar grid, add delta_s(theta,tx,rx)=s_direct(height/cos(theta))-s_direct(10m), same verified FFD banks and unchanged Hann/IFFT/first-path chain. Height fixed 2.2m. Same 1/2deg Cartesian pole procedure on corrected 2/4deg rings; trilinear derivative and geometry chain rule include distance effect. Range h/H unchanged.',
      table_implementation='Deterministic lazy node generation and persistent sparse table; model function at each node independent of RF, ground truth, bias, donor, time or previous trajectory. Direct generator only at grid nodes; no SourceFFD online h/H replacement. Not a fully materialized real-time deployment benchmark.',failed_predecessor='Sibling distance_lut_mbvar_20261102 failed cp949 decoding of UTF8 parent contract before contract creation, table generation or filter execution. Preserved; explicit UTF8 read and interpreter mode only, no model change.',
      optimization='v2 partial execution intentionally cancelled because set-dict_keys difference copies full cache per corner. v3 replaces ONLY cache membership lookup; same values and sorted missing-node order. All completed v2 paths will be compared to new values. Math and thresholds unchanged; v2 partial files/logs/cancel preserved.',
      domain='Anchor B height2.2m mount0; theta<88deg; fail outside rather than extrapolate 90deg infinity',controls=prior['controls'],adaptive_rule=prior['adaptive_rule'],score=prior['score'],thresholds=dict(fd_abs=2e-5,join_h=1e-6,join_J=1e-4,pole_Jxy=5,node_source=1e-9,node_original=1e-6,X_parity=1e-10,P_parity=1e-10,R_parity=1e-12),
      gate_order='input hashes -> synthetic math tests -> all12 disabled-distance baseline parity -> 12 new runs -> actual-prior finite difference and controlled-input checks -> score',fixed_before_results=True,performance_tuning=False,allowed_claim='Paired observer distance intervention in one scene/seed, no mean/variance refit; improvement not guaranteed; cannot claim calibrated NEES or adoption',python=sys.version,numpy=np.__version__,platform=platform.platform(),managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'),thread_id=os.environ.get('MANAGED_PROCESS_THREAD_ID'),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    source=DG.C.base_model();base=A.FrozenLut(A.OLD)
    print('BUILD_CORRECTED_POLE_RINGS',flush=True);model=DistanceLut(base,source.banks)
    np.savez_compressed(OUT/'DISTANCE_CAP_COEFFICIENTS.npz',coeff=model.lut.coeff,psi_deg=model.lut.psi,fit_residual=model.lut.fit_residual)
    math_gate(model,base,source)
    # Turning only the distance intervention off must recover the prior fixed LUT.
    off=DistanceLut(base,source.banks,enabled=False);parity=[];data={}
    for c in A.CASES:
      for b in A.BIASES:
        A.stop_check();D,bg,mode=A.arm_data(A.make_data(c,b),'PROPOSED_MB_VAR');data[c,b]=(D,bg,mode)
        X,P,L=DG.run(D,bg,mode,'self',model=off)
        with np.load(FIX/f'{c}_{b}_PROPOSED_MB_VAR_LUT_fixed.npz') as r:
            rec=dict(case=c,bias=b,X_max=float(abs(X-r['X']).max()),P_max=float(abs(P-r['PX']).max()),R_max=float(abs(L['Ru']-r['Ru']).max()),gate_mismatch=int(np.count_nonzero(L['used']!=r['used'])))
            for k in ['xp','Pp','nu','S','HPH','hx','nis']:assert np.allclose(L[k],r[k],rtol=1e-10,atol=1e-10,equal_nan=True)
        assert rec['X_max']<1e-10 and rec['P_max']<1e-10 and rec['R_max']<1e-12 and rec['gate_mismatch']==0
        parity.append(rec);print('BASELINE_PASS',c,b,flush=True)
    pd.DataFrame(parity).to_csv(OUT/'BASELINE_PARITY_12.csv',index=False);dump('BASELINE_GATE.json',dict(status='PASS',conditions=12))
    rows=[];packets=[];actualfd=[];effects=[];statecheck=[];optimization_parity=[]
    previous=pd.read_csv(FIX/'ALL_SCORES_108.csv')
    for c in A.CASES:
      for b in A.BIASES:
        A.stop_check();D,bg,mode=data[c,b];start=time.perf_counter();X,P,L=DG.run(D,bg,mode,'self',model=model)
        h,J=model.batch(L['xp'],D['spec']);assert np.allclose(h,L['hx'],rtol=0,atol=1e-12)
        assert np.allclose(J@L['Pp']@J.transpose(0,2,1),L['HPH'],rtol=1e-8,atol=1e-9)
        assert np.array_equal(L['nis']<=DG.GATE,L['used'])
        rho=np.linalg.norm(np.vstack([D['x0'][:2],X[:-1,:2]])-D['anchor'],axis=1);sg=np.interp(rho,DG.HAND[0],DG.HAND[1]);er=D['R'].copy();er[:,1,1]+=sg**2
        assert np.allclose(er,L['Ru'],rtol=0,atol=1e-14)
        # All used priors, not just low-error or accepted samples.
        for k,x in enumerate(L['xp']):
          for a in range(3):
            xp=x.copy();xm=x.copy();xp[a]+=1e-7;xm[a]-=1e-7
            fd=(model.model(xp,D['spec'])[0]-model.model(xm,D['spec'])[0])/2e-7;err=float(abs(fd-J[k,:,a]).max())
            actualfd.append(dict(case=c,bias=b,k=k,axis=a,max_abs_error=err));assert err<2e-5,(c,b,k,a,err)
        np.savez_compressed(OUT/f'{c}_{b}_MB_VAR_DISTANCE_LUT.npz',X=X,PX=P,J=J,t=D['t'],gt=D['gt'],z=D['z'],mu=D['mu'][bg],base_R=D['R'],ds=D['ds'],gy=D['gy'],dt=D['dt'],x0=D['x0'],P0=D['P0'],rho_lookup=rho,sigma_lookup=sg,**L)
        oldpath=OUT.parent/'distance_lut_mbvar_20261102_v2'/f'{c}_{b}_MB_VAR_DISTANCE_LUT.npz'
        if oldpath.exists():
          with np.load(oldpath) as ref:
            rec=dict(case=c,bias=b,X_max=float(abs(X-ref['X']).max()),P_max=float(abs(P-ref['PX']).max()),R_max=float(abs(L['Ru']-ref['Ru']).max()),gate_mismatch=int(np.count_nonzero(L['used']!=ref['used'])))
            assert rec['X_max']==rec['P_max']==rec['R_max']==rec['gate_mismatch']==0
            optimization_parity.append(rec)
        r,p=A.score(D,X,P,L,'LUT_distance','PROPOSED_MB_VAR');rows.append(r);packets.append(p)
        for ob,path in [('LUT_fixed',FIX/f'{c}_{b}_PROPOSED_MB_VAR_LUT_fixed.npz'),('SourceFFD',A.refpath(c,b,'PROPOSED_MB_VAR'))]:
          with np.load(path) as ref:
            r,p=A.score(D,ref['X'],ref['PX'],ref,ob,'PROPOSED_MB_VAR');rows.append(r);packets.append(p)
            old=previous[(previous.case==c)&(previous.bias==b)&(previous.observer==ob)&(previous.stage=='PROPOSED_MB_VAR')].iloc[0]
            for key in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose']:assert np.isclose(r[key],old[key],rtol=1e-10,atol=1e-9)
            effects.append(dict(case=c,bias=b,reference=ob,gate_mismatch=int(np.count_nonzero(L['used']!=ref['used'])),R_max=float(abs(L['Ru']-ref['Ru']).max())))
            if ob=='LUT_fixed':
                for key in ['t','gt','z','mu','base_R','ds','gy','dt','x0','P0']:
                    expected=D['mu'][bg] if key=='mu' else D['R'] if key=='base_R' else D[key]
                    assert np.array_equal(ref[key],expected),key
                hs,js=model.batch(ref['xp'],D['spec']);ss,_=source.batch(ref['xp'],D['spec']);hf=ref['hx']
                statecheck.append(dict(case=c,bias=b,same_fixed_prior_s_RMS_fixed_source=float(np.sqrt(np.mean((hf[:,1]-ss[:,1])**2))),same_fixed_prior_s_RMS_distance_source=float(np.sqrt(np.mean((hs[:,1]-ss[:,1])**2)))))
        pd.DataFrame(rows).to_csv(OUT/'ALL_SCORES_36.csv',index=False)
        print('DISTANCE_DONE',c,b,'seconds',round(time.perf_counter()-start,2),'heading',rows[-3]['head_rmse'],'XYcm',rows[-3]['xy_rmse_cm'],'NEES3',rows[-3]['nees_pose'],flush=True)
    df=pd.DataFrame(rows);assert len(df)==36 and not df.duplicated(['case','bias','observer']).any()
    pd.concat(packets,ignore_index=True).to_csv(OUT/'PACKET_ERRORS_AND_NEES.csv.gz',index=False)
    pd.DataFrame(actualfd).to_csv(OUT/'ACTUAL_PRIOR_FD.csv',index=False);pd.DataFrame(effects).to_csv(OUT/'GATE_R_EFFECTS.csv',index=False);pd.DataFrame(statecheck).to_csv(OUT/'SAME_STATE_MODEL_CHECK.csv',index=False)
    pd.DataFrame(optimization_parity).to_csv(OUT/'CACHE_OPTIMIZATION_PARITY.csv',index=False);assert len(optimization_parity)==len(partial)
    model.base.s.save(OUT/'DISTANCE_CORRECTION_NODES.npz')
    assert all(A.sha(p)==h for p,h in locked.items())
    dump('RESULT_CHECKS.json',dict(status='EXECUTION_AND_SELF_CHECK_COMPLETED',new_runs=12,baseline_parity=12,score_rows=36,scored_observers=3,source_archived_reused=True,input_hashes_unchanged=True,all_P_positive_definite=True,controls_exact=True,adaptive_previous_posterior_R_verified=True,actual_fd_samples=len(actualfd),actual_fd_max=max(r['max_abs_error'] for r in actualfd),sparse_table_nodes=len(model.base.s.cache),independent_audit=False,adopted=False,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print('ALL_12_DISTANCE_MBVAR_COMPLETED',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        dump('FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc()));raise
