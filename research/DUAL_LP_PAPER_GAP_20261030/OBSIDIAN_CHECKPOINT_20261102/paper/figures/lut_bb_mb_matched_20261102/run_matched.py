"""DLP-LUT-BB-MB-MATCHED-001: locked paired replay; canonical DG.run unchanged."""
from pathlib import Path
import sys,os,json,time,datetime,platform,traceback,hashlib
import numpy as np,pandas as pd
OUT=Path(__file__).resolve().parent;FIG=OUT.parent;PREV=FIG/'distance_lut_mbvar_20261102_v3';FIX=FIG/'lut_pole_fix_20261102_v3'
sys.path[:0]=[str(PREV),str(FIX),str(FIG/'lut_observer_swap_20261102')]
import replay_observer_swap as A
from distance_lut import DistanceLut
from pole_regularized_lut import PoleRegularizedLut
DG=A.DG;ARMS={'BB_ORIG':('BB','orig'),'MB_VAR':('MB','var')}
def dump(n,v):
    p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def diff(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def sourcepath(c,b,arm):return A.REC/f'results/traces/{c}__{b}__{arm}__self.npz'
def tick():A.stop_check()

def parity(X,P,L,ref):
    r=dict(X_max=diff(X,ref['X']),P_max=diff(P,ref['PX']),R_max=diff(L['Ru'],ref['Ru']),used_mismatch=int(np.count_nonzero(L['used']!=ref['used'])))
    assert r['X_max']<1e-10 and r['P_max']<1e-10 and r['R_max']<1e-12 and r['used_mismatch']==0,r
    for k in ['xp','Pp','hx','nu','HPH','S','nis']:assert np.allclose(L[k],ref[k],rtol=0,atol=1e-10),k
    return r

def recipe(D,arm,mu,R,rho,gate='self'):
    assert arm in ARMS and gate=='self','WRONG_ARM_OR_GATE'
    bg,mode=ARMS[arm];assert np.array_equal(mu,D['mu'][bg]),'WRONG_DONOR_OR_MEAN'
    expected=D['R'].copy()
    if mode=='var':expected[:,1,1]+=np.interp(rho,DG.HAND[0],DG.HAND[1])**2
    assert np.allclose(R,expected,rtol=0,atol=1e-14),'WRONG_R_RULE'

def diagnostics(D,arm,X,P,L,model):
    bg,mode=ARMS[arm];h,J=model.batch(L['xp'],D['spec']);n=len(X)
    fd_errors=[]
    for axis in range(3):
        plus=L['xp'].copy();minus=plus.copy();plus[:,axis]+=1e-7;minus[:,axis]-=1e-7
        hp,_=model.batch(plus,D['spec']);hm,_=model.batch(minus,D['spec'])
        err=np.max(abs((hp-hm)/2e-7-J[:,:,axis]),axis=1);fd_errors.append(err)
        assert err.max()<2e-5,('ACTUAL_PRIOR_FD',D['case'],D['bias'],arm,axis,float(err.max()))
    rho=np.linalg.norm(np.vstack([D['x0'][:2],X[:-1,:2]])-D['anchor'],axis=1);sigma=np.interp(rho,DG.HAND[0],DG.HAND[1])
    recipe(D,arm,D['mu'][bg],L['Ru'],rho)
    assert np.array_equal(L['used'],L['nis']<=DG.GATE)
    assert diff(h,L['hx'])<1e-12 and diff(D['z']-h-D['mu'][bg],L['nu'])<1e-12
    HPH=J@L['Pp']@J.transpose(0,2,1);S=HPH+L['Ru'];S=.5*(S+S.transpose(0,2,1))
    assert diff(HPH,L['HPH'])<1e-10 and diff(S,L['S'])<1e-10
    K=np.linalg.solve(S,J@L['Pp']).transpose(0,2,1)
    nis=np.einsum('ni,ni->n',L['nu'],np.linalg.solve(S,L['nu'][...,None])[...,0]);assert diff(nis,L['nis'])<1e-10
    xx=L['xp']+np.einsum('nij,nj->ni',K,L['nu']);xx[:,2]=DG.wrap(xx[:,2])
    B=np.eye(4)[None]-K@J;PP=B@L['Pp']@B.transpose(0,2,1)+K@L['Ru']@K.transpose(0,2,1);PP=.5*(PP+PP.transpose(0,2,1))
    xx[~L['used']]=L['xp'][~L['used']];PP[~L['used']]=L['Pp'][~L['used']]
    assert diff(xx,X)<1e-10 and diff(PP,P)<1e-10
    assert np.linalg.eigvalsh(P).min()>0 and np.linalg.eigvalsh(L['Pp']).min()>0
    frame=dict(case=np.repeat(D['case'],n),bias=np.repeat(D['bias'],n),arm=np.repeat(arm,n),k=np.arange(n),pose_id=D['pose_id'],t_s=D['t'],scored=D['t']>=30-1e-9,used=L['used'],rho_previous_posterior_m=rho,sigma_lookup=sigma,ds_m=D['ds'],gyro_rad=D['gy'],dt_s=D['dt'],nis=L['nis'],fd_max_abs=np.max(fd_errors,axis=0))
    arrays=dict(X=X,P=P,xp=L['xp'],Pp=L['Pp'],h=h,J=J,HPH=HPH,S=S,K_candidate=K,K_applied=K*L['used'][:,None,None],nu=L['nu'],R_used=L['Ru'],R_base=D['R'],mu=D['mu'][bg],z=D['z'])
    for name,value in arrays.items():
        for idx in np.ndindex(value.shape[1:]):frame[name+'_'+'_'.join(map(str,idx))]=value[(slice(None),)+idx]
    qa=dict(case=D['case'],bias=D['bias'],arm=arm,actual_prior_fd_max=float(np.max(fd_errors)),h_error=diff(h,L['hx']),HPH_error=diff(HPH,L['HPH']),S_error=diff(S,L['S']),NIS_error=diff(nis,L['nis']),update_X_error=diff(xx,X),Joseph_P_error=diff(PP,P),min_P_eigenvalue=float(np.linalg.eigvalsh(P).min()),gate_rule_exact=True,R_rule_verified=True)
    return J,K,rho,sigma,pd.DataFrame(frame),qa

def save_trace(D,arm,X,P,L,J,K,rho,sigma):
    np.savez_compressed(OUT/'traces'/f'{D["case"]}__{D["bias"]}__{arm}__self.npz',X=X,PX=P,J=J,K_candidate=K,K_applied=K*L['used'][:,None,None],rho_lookup=rho,sigma_lookup=sigma,t=D['t'],pose_id=D['pose_id'],gt=D['gt'],z=D['z'],mu=D['mu'][ARMS[arm][0]],base_R=D['R'],ds=D['ds'],gy=D['gy'],dt=D['dt'],x0=D['x0'],P0=D['P0'],**L)

def negative_tests(D,trace):
    failures=[]
    def reject(name,f):
        try:f()
        except AssertionError as e:failures.append(dict(name=name,detected=True,error=str(e)))
        else:raise AssertionError('NEGATIVE_TEST_NOT_DETECTED '+name)
    rho=trace['rho_lookup'];mu=D['mu']['BB'];R=D['R']
    reject('BB_zero_mean_not_allowed',lambda:recipe(D,'BB_ORIG',np.zeros_like(mu),R,rho))
    reject('BB_fixed_R0_not_allowed',lambda:recipe(D,'BB_ORIG',mu,np.broadcast_to(A.R0,R.shape),rho))
    reject('BB_using_MB_donor_not_allowed',lambda:recipe(D,'BB_ORIG',D['mu']['MB'],R,rho))
    reject('MB_variance_omitted',lambda:recipe(D,'MB_VAR',D['mu']['MB'],R,rho))
    reject('fixed_gate_substitution',lambda:recipe(D,'BB_ORIG',mu,R,rho,gate='fixed'))
    wrong=mu.copy();wrong[0,0]+=.001;reject('mean_mutation',lambda:recipe(D,'BB_ORIG',wrong,R,rho))
    def flipped_gate():
        used=trace['used'].copy();used[0]=~used[0];assert np.array_equal(used,trace['nis']<=DG.GATE),'WRONG_SELF_MASK'
    reject('self_gate_mask_mutation',flipped_gate)
    return failures

def main():
    contract_path=OUT/'CONTRACT_BB_MB_DISTANCE_LUT.json';C=json.loads(contract_path.read_text(encoding='utf-8'))
    expected=(OUT/'CONTRACT_SHA256.txt').read_text(encoding='utf-8').split()[0];assert A.sha(contract_path)==expected and C['status']=='FROZEN_EXECUTION_AUTHORIZED'
    lock=C['input_hashes'];assert all(A.sha(p)==h for p,h in lock.items())
    assert not (OUT/'RUN_MANIFEST.json').exists(),'APPEND_ONLY'
    run=dict(contract_id=C['contract_id'],contract_sha256=expected,status='RUNNING',managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'),thread_id=os.environ.get('MANAGED_PROCESS_THREAD_ID'),command=sys.argv,python=sys.version,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform(),pid=os.getpid(),base_git_sha=C['base_git_sha'],governance=C['governance'],started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),implementation_sha256=A.sha(__file__),input_hashes=lock)
    dump('RUN_MANIFEST.json',run);(OUT/'traces').mkdir();data={};v0=[]
    source=DG.C.base_model();historical=pd.read_csv(A.REC/'results/tables/RECURSIVE_144_LOGICAL_SCORES.csv')
    # V0: archived packet namespace is CONTROL pose_id/time, NOT raw H-row indexing.
    for case in C['cases']:
      control=DG.C.load_control(case,'B0')
      assert np.unique(control['pose_id']).size==len(control['t_s']) and np.all(np.diff(control['t_s'])>0)
      for bias in C['biases']:
        D=A.make_data(case,bias);D['pose_id']=control['pose_id'].copy();data[case,bias]=D
        assert np.array_equal(D['t'],control['t_s']) and np.array_equal(D['gt'],control['truth_scoring_only'])
        assert np.array_equal(D['mu']['BB'][:,1],D['mu']['MB'][:,1]) and not np.array_equal(D['mu']['BB'][:,0],D['mu']['MB'][:,0])
        nscore=int(np.count_nonzero(D['t']>=30-1e-9));assert nscore==C['expected_score_counts'][case[:2]]
        v0.append(dict(case=case,bias=bias,n=len(D['t']),n_score=nscore,pose_unique=True,time_increasing=True,BB_mu_sha256=hashlib.sha256(D['mu']['BB'].tobytes()).hexdigest(),MB_mu_sha256=hashlib.sha256(D['mu']['MB'].tobytes()).hexdigest(),s_mean_exactly_same=True,range_mean_different=True,z_sha256=hashlib.sha256(D['z'].tobytes()).hexdigest()))
    assert sum(r['n_score'] for r in v0)==10744;pd.DataFrame(v0).to_csv(OUT/'V0_INPUT_KEY_DONOR_12.csv',index=False)
    reference=[];source_scores=[]
    for case in C['cases']:
      for bias in C['biases']:
        D=data[case,bias];pair=dict(case=case,bias=bias)
        for arm,(bg,mode) in ARMS.items():
            tick();X,P,L=DG.run(D,bg,mode,'self',model=source)
            with np.load(sourcepath(case,bias,arm)) as ref:r=parity(X,P,L,ref)
            score,_=A.score(D,X,P,L,'SourceFFD',arm);source_scores.append(dict(arm=arm,**score))
            old=historical[(historical.case==case)&(historical.bias==bias)&(historical.arm==arm)&(historical.gate=='self')];assert len(old)==1
            for key in ['head_rmse','head_bias','xy_rmse_cm','nees_xy','head_cov95','xy_cov95']:
                assert np.isclose(score[key],old.iloc[0][key],atol=1e-9,rtol=1e-10),(case,bias,arm,key)
            pair.update({arm+'_'+k:v for k,v in r.items()})
            print('SOURCE_PARITY_PASS',case,bias,arm,flush=True)
        reference.append(pair)
    pd.DataFrame(reference).to_csv(OUT/'PARITY_SOURCE_REFERENCE_12.csv',index=False);pd.DataFrame(source_scores).to_csv(OUT/'SOURCE_REFERENCE_SCORE_24.csv',index=False)
    dump('V0_GATE.json',dict(status='PASS',source_reference_recursions=24,source_pair_parity=12,key_checks=12))
    # V1: exact existing code, same cache values; adding nodes never changes old keys.
    base=A.FrozenLut(A.OLD);model=DistanceLut(base,source.banks)
    with np.load(PREV/'DISTANCE_CORRECTION_NODES.npz') as cache:
        assert cache['height_m']==2.2 and cache['grid_deg']==2
        for key,delta,sa,s10 in zip(cache['keys'],cache['delta_s'],cache['s_actual'],cache['s_10m']):
            key=tuple(map(int,key));value=(float(delta),float(sa),float(s10))
            if key in model.base.s.cache:assert np.array_equal(model.base.s.cache[key],value),'NODE_VALUE_DRIFT'
            model.base.s.cache[key]=value
    oldcap=np.load(PREV/'DISTANCE_CAP_COEFFICIENTS.npz');assert np.array_equal(model.lut.coeff,oldcap['coeff'])
    off=DistanceLut(base,source.banks,enabled=False);fixed=PoleRegularizedLut(base);offdiff=[]
    for case in C['cases']:
      for bias in C['biases']:
        with np.load(PREV/f'{case}_{bias}_MB_VAR_DISTANCE_LUT.npz') as trace:
            ho,jo=off.batch(trace['xp'],data[case,bias]['spec']);hf,jf=fixed.batch(trace['xp'],data[case,bias]['spec'])
            offdiff.append(dict(case=case,bias=bias,h_max=diff(ho,hf),J_max=diff(jo,jf)));assert np.array_equal(ho,hf) and np.array_equal(jo,jf)
    pd.DataFrame(offdiff).to_csv(OUT/'PARITY_DISABLED_DISTANCE_HJ_12.csv',index=False)
    results={};parity_rows=[];scores=[];packets=[];qalog=[]
    # V1 MB12 are the MB half of the primary24, not an extra duplicate execution.
    for case in C['cases']:
      for bias in C['biases']:
        D=data[case,bias];tick();X,P,L=DG.run(D,'MB','var','self',model=model)
        with np.load(PREV/f'{case}_{bias}_MB_VAR_DISTANCE_LUT.npz') as ref:
            record=parity(X,P,L,ref);record.update(case=case,bias=bias)
            for key,want in [('z',D['z']),('mu',D['mu']['MB']),('base_R',D['R']),('ds',D['ds']),('gy',D['gy']),('dt',D['dt']),('x0',D['x0']),('P0',D['P0']),('t',D['t']),('gt',D['gt'])]:assert np.array_equal(ref[key],want),key
        parity_rows.append(record);results[case,bias,'MB_VAR']=(X,P,L)
        J,K,rho,sigma,frame,qa=diagnostics(D,'MB_VAR',X,P,L,model);save_trace(D,'MB_VAR',X,P,L,J,K,rho,sigma)
        score,_=A.score(D,X,P,L,'LUT_distance','MB_VAR');scores.append(dict(arm='MB_VAR',**score));packets.append(frame);qalog.append(qa)
        print('DISTANCE_MB_PARITY_PASS',case,bias,flush=True)
    pd.DataFrame(parity_rows).to_csv(OUT/'PARITY_DISTANCE_MB_12.csv',index=False);dump('V1_GATE.json',dict(status='PASS',MB_replays=12,off_model_hJ_exact=True))
    for case in C['cases']:
      for bias in C['biases']:
        tick();D=data[case,bias];X,P,L=DG.run(D,'BB','orig','self',model=model);results[case,bias,'BB_ORIG']=(X,P,L)
        J,K,rho,sigma,frame,qa=diagnostics(D,'BB_ORIG',X,P,L,model);save_trace(D,'BB_ORIG',X,P,L,J,K,rho,sigma)
        score,_=A.score(D,X,P,L,'LUT_distance','BB_ORIG');scores.append(dict(arm='BB_ORIG',**score));packets.append(frame);qalog.append(qa)
        print('DISTANCE_BB_DONE',case,bias,'head',score['head_rmse'],'XYcm',score['xy_rmse_cm'],flush=True)
    # Off-line first divergence; no extra filter runs.
    first=[];events=[]
    for case in C['cases']:
      for bias in C['biases']:
        D=data[case,bias];xb,pb,lb=results[case,bias,'BB_ORIG'];xm,pm,lm=results[case,bias,'MB_VAR'];gidx=np.flatnonzero(lb['used']!=lm['used']);xidx=np.flatnonzero(np.max(abs(xb-xm),axis=1)>1e-10);pidx=np.flatnonzero(np.max(abs(pb-pm),axis=(1,2))>1e-10)
        r=dict(case=case,bias=bias,gate_mismatch_all=len(gidx),gate_mismatch_scored=int(np.count_nonzero((lb['used']!=lm['used'])&(D['t']>=30-1e-9))))
        for label,idx in [('state',xidx),('P',pidx),('gate',gidx)]:
          r['first_'+label+'_k']=int(idx[0]) if len(idx) else None;r['first_'+label+'_t_s']=float(D['t'][idx[0]]) if len(idx) else None
        ks=sorted(set(int(a[0]) for a in [xidx,pidx,gidx] if len(a)));detail={}
        for k in ks:
          for kk in sorted(set([max(0,k-1),k])):
            for arm in ARMS:
              with np.load(OUT/'traces'/f'{case}__{bias}__{arm}__self.npz') as z:
                detail[f'event{k}_packet{kk}_{arm}']={key:z[key][kk].tolist() for key in ['X','PX','xp','Pp','Ru','nu','J','K_candidate','K_applied','S','nis','used','hx']}
        r['event_detail_json']=json.dumps(detail,separators=(',',':'));first.append(r)
    pd.DataFrame(first).to_csv(OUT/'FIRST_DIVERGENCE_12.csv',index=False)
    df=pd.DataFrame(scores);assert len(df)==24 and not df.duplicated(['case','bias','arm']).any();df.to_csv(OUT/'FULL_SCORE_24.csv',index=False)
    packet=pd.concat(packets,ignore_index=True);assert not packet.duplicated(['case','bias','arm','pose_id','t_s']).any();packet.to_csv(OUT/'PACKET_DIAGNOSTICS.csv.gz',index=False)
    pd.DataFrame(qalog).to_csv(OUT/'UPDATE_QA_24.csv',index=False)
    with np.load(OUT/'traces/R2_aB_m0__B0__BB_ORIG__self.npz') as z:neg=negative_tests(data[A.CASES[0],'B0'],z)
    dump('FAILURES_AND_NEGATIVE_TESTS.json',dict(failures=[],negative_tests=neg,negative_test_full_recursions=0))
    model.base.s.save(OUT/'DISTANCE_NODE_CACHE_USED.npz')
    assert all(A.sha(p)==h for p,h in lock.items()) and A.sha(contract_path)==expected
    run.update(status='COMPLETED_TECHNICAL_SELF_QA',actual_recursions=dict(Source_reference=24,Distance_MB=12,Distance_BB=12),input_hashes_unchanged=True,gate_success=['V0','V1','V2'],finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());dump('RUN_MANIFEST.json',run)
    dump('FINAL_SELF_QA.json',dict(technical_status='PASS_WITHIN_EXECUTED_SCOPE',independent_audit='PENDING_SEPARATE_ACTOR',model_adoption=False,conditions=12,LUT_recursive_runs=24,Source_validation_runs=24,full_score_rows=24,packet_rows=len(packet),input_hashes_unchanged=True,V3='PENDING_REPORT',max_update_error=float(max(q['update_X_error'] for q in qalog)),max_Joseph_error=float(max(q['Joseph_P_error'] for q in qalog))))
    print('PAIRED24_AND_SOURCE24_COMPLETE',flush=True)
if __name__=='__main__':
    try:main()
    except BaseException as exc:
        dump('FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));raise
