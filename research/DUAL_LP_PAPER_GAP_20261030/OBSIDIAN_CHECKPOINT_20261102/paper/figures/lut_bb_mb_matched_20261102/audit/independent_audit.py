"""Separate-actor read-only verification. Does not invoke a filter recursion."""
from pathlib import Path
import json, hashlib, datetime, sys, math, traceback
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
OUT=HERE.parent; PREV=OUT.parent/'distance_lut_mbvar_20261102_v3'
REC=Path('C:/Users/Myoungsun Kim/dlp1102/DualLP_Physics_Link_Validation_20261101')
EXPECTED='faec09c6b775346ec9e0889529f7c53218ddabaef8b586067f2a0ab8ce85192d'
CASE=['R2_aB_m0','R4_aB_m0','R5_aB_m0']; BIAS=['B0','L0','L1','L2']; ARMS=['BB_ORIG','MB_VAR']
GATE=9.210340371976184
THRESH=[3.841458820694124,5.991464547107979,7.814727903251179]
checks=[]; facts=[]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(name,test,**detail):
    checks.append(dict(check=name,passed=bool(test),**detail))
    if not test:raise AssertionError((name,detail))
def err(a,b):return float(np.max(np.abs(np.asarray(a)-np.asarray(b))))
def near(name,a,b,tol=1e-10):
    v=err(a,b);check(name,v<tol,max_abs=v,threshold=tol);return v
def wrap(a):return np.arctan2(np.sin(a),np.cos(a))
def independent_scores(z,gt,t):
    mask=t>=30-1e-9;e=gt[:,:3]-z['X'][:,:3];e[:,2]=wrap(e[:,2]);P=z['PX']
    nh=e[:,2]**2/P[:,2,2]
    nx=np.sum(e[:,:2]*np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0],axis=1)
    n3=np.sum(e*np.linalg.solve(P[:,:3,:3],e[...,None])[...,0],axis=1)
    return dict(n_score=int(mask.sum()),n_total=len(t),n_used=int(z['used'].sum()),n_used_score=int(z['used'][mask].sum()),
      head_rmse=float(np.rad2deg(np.sqrt(np.mean(e[mask,2]**2)))),head_bias=float(np.rad2deg(e[mask,2].mean())),
      xy_rmse_cm=float(100*np.sqrt(np.mean(np.sum(e[mask,:2]**2,axis=1)))),
      nees_heading=float(nh[mask].mean()),nees_xy=float(nx[mask].mean()),nees_pose=float(n3[mask].mean()),
      head_cov95=float(np.mean(nh[mask]<1.96**2)),xy_cov95=float(np.mean(nx[mask]<5.991)),pose_cov95=float(np.mean(n3[mask]<THRESH[2])),
      heading_coverage95_exact=float(np.mean(nh[mask]<THRESH[0])),xy_coverage95_exact=float(np.mean(nx[mask]<THRESH[1])),
      heading_threshold_sensitive_points=int(np.count_nonzero(mask&((nh<1.96**2)!=(nh<THRESH[0])))),
      xy_threshold_sensitive_points=int(np.count_nonzero(mask&((nx<5.991)!=(nx<THRESH[1])))))

def independent_prediction(z):
    x=np.vstack([z['x0'],z['X'][:-1]]);P=np.concatenate([z['P0'][None],z['PX'][:-1]])
    a=z['gy']-x[:,3]*z['dt'];c=np.sinc(a/(2*np.pi));small=np.abs(a)<1e-4
    dc=np.empty(len(a));dc[small]=-a[small]/12+a[small]**3/480-a[small]**5/53760
    h=a[~small]/2;dc[~small]=(h*np.cos(h)-np.sin(h))/(2*h*h)
    phi=x[:,2]+a/2;u=np.stack([np.cos(phi),np.sin(phi)],axis=1);up=np.stack([-u[:,1],u[:,0]],axis=1)
    d=z['ds'][:,None]*c[:,None]*u;v=z['ds'][:,None]*(dc[:,None]*u+c[:,None]*up/2)
    y=x.copy();y[:,:2]+=d;y[:,2]=wrap(x[:,2]+a)
    n=len(a);F=np.broadcast_to(np.eye(4),(n,4,4)).copy();F[:,:2,2]=np.stack([-d[:,1],d[:,0]],axis=1)
    F[:,:2,3]=-z['dt'][:,None]*v;F[:,2,3]=-z['dt']
    G=np.zeros((n,4,3));G[:,:2,0]=c[:,None]*u;G[:,:2,1]=v;G[:,2,1]=1;G[:,3,2]=1
    q=np.zeros((n,3,3));q[:,0,0]=2e-5*np.abs(z['ds']);q[:,1,1]=np.deg2rad(.015)**2*z['dt']
    pp=F@P@F.transpose(0,2,1)+G@q@G.transpose(0,2,1);pp=(pp+pp.transpose(0,2,1))/2
    y[0]=z['x0'];pp[0]=z['P0']
    near('independent prediction state',y,z['xp']);near('independent prediction covariance',pp,z['Pp'])

def verify_packet_math(z,arm):
    independent_prediction(z)
    rho=np.linalg.norm(np.vstack([z['x0'][:2],z['X'][:-1,:2]])-np.array([10.,0.]),axis=1)
    sigma=np.interp(rho,[0,1.5,3,6,10],[.011,.02,.05,.12,.24]);near('rho previous posterior',rho,z['rho_lookup']);near('sigma interpolation',sigma,z['sigma_lookup'])
    R=z['base_R'].copy()
    if arm=='MB_VAR':R[:,1,1]+=sigma**2
    near('correct original or adaptive R',R,z['Ru'],1e-12)
    J=z['J'];P=z['Pp'];v=z['z']-z['hx']-z['mu'];near('innovation',v,z['nu'])
    hph=np.einsum('nai,nij,nbj->nab',J,P,J);S=hph+R;S=(S+S.transpose(0,2,1))/2
    near('HPH',hph,z['HPH']);near('S',S,z['S'])
    nis=np.sum(v*np.linalg.solve(S,v[...,None])[...,0],axis=1);near('NIS',nis,z['nis'])
    check('self gate exact',np.array_equal(z['used'],nis<=GATE))
    K=P@J.transpose(0,2,1)@np.linalg.inv(S);near('candidate gain',K,z['K_candidate'])
    near('applied gain',K*z['used'][:,None,None],z['K_applied'])
    xx=z['xp']+np.einsum('nij,nj->ni',K,v);xx[:,2]=wrap(xx[:,2]);B=np.eye(4)[None]-K@J
    pp=B@P@B.transpose(0,2,1)+K@R@K.transpose(0,2,1);pp=(pp+pp.transpose(0,2,1))/2
    xx[~z['used']]=z['xp'][~z['used']];pp[~z['used']]=P[~z['used']]
    near('posterior state',xx,z['X']);near('Joseph covariance',pp,z['PX'])
    near('posterior symmetry',z['PX'],z['PX'].transpose(0,2,1))
    mineig=float(np.linalg.eigvalsh(z['PX']).min());check('posterior SPD',mineig>0,min_eigenvalue=mineig)

def main():
    contract=OUT/'CONTRACT_BB_MB_DISTANCE_LUT.json';check('contract frozen hash',sha(contract)==EXPECTED)
    C=json.loads(contract.read_text(encoding='utf-8'));check('all 237 input locks',all(sha(p)==v for p,v in C['input_hashes'].items()),files=len(C['input_hashes']))
    scores=pd.read_csv(OUT/'FULL_SCORE_24.csv');source=pd.read_csv(OUT/'SOURCE_REFERENCE_SCORE_24.csv')
    check('24 unique paired score rows',len(scores)==24 and not scores.duplicated(['case','bias','arm']).any())
    check('24 unique source score rows',len(source)==24 and not source.duplicated(['case','bias','arm']).any())
    run=json.loads((OUT/'RUN_MANIFEST.json').read_text(encoding='utf-8'))
    check('run complete and linked',run['status']=='COMPLETED_TECHNICAL_SELF_QA' and run['contract_sha256']==EXPECTED)
    selfqa=pd.read_csv(OUT/'UPDATE_QA_24.csv');check('all prior FD tested',len(selfqa)==24 and selfqa.actual_prior_fd_max.max()<2e-5,max_abs=float(selfqa.actual_prior_fd_max.max()))
    independent=[];source_independent=[];div=[];sensitivity=[];arrays={}
    for case in CASE:
      control=np.load(REC/f'recovered/inputs/traces/{case}_B0_CONTROL.npz');names=list(control['names']);jb=names.index('OFF_BB');jm=names.index('OFF_MB')
      t=control['t_s'];gt=control['truth_scoring_only'];zraw=control['nu'][:,jb]+control['h'][:,jb]+control['mu'][:,jb]
      for bias in BIAS:
        for arm in ARMS:
          with np.load(OUT/'traces'/f'{case}__{bias}__{arm}__self.npz') as zz:z={k:zz[k] for k in zz.files}
          arrays[case,bias,arm]=z
          for name,want in [('t',t),('pose_id',control['pose_id']),('gt',gt),('z',zraw),('base_R',control['R'][:,jb]),('P0',control['Pprior'][0,jb]),('mu',control['mu'][:,jb if arm=='BB_ORIG' else jm])]:
            check('exact frozen input '+name,np.array_equal(z[name],want))
          check('all finite arrays',all(np.isfinite(z[k]).all() for k in z))
          verify_packet_math(z,arm)
          if arm=='MB_VAR':
            with np.load(PREV/f'{case}_{bias}_MB_VAR_DISTANCE_LUT.npz') as prior:
              for name in ['X','PX','Ru','used','xp','Pp','J']:check('old distance MB exact '+name,np.array_equal(z[name],prior[name]))
          row=independent_scores(z,gt,t);ref=scores[(scores.case==case)&(scores.bias==bias)&(scores.arm==arm)].iloc[0]
          for k in ref.index.intersection(row):near('independent score '+k,row[k],ref[k],1e-9)
          independent.append(dict(case=case,bias=bias,arm=arm,**row))
          sensitivity.append(dict(case=case,bias=bias,arm=arm,heading_points=row['heading_threshold_sensitive_points'],xy_points=row['xy_threshold_sensitive_points']))
          with np.load(REC/f'results/traces/{case}__{bias}__{arm}__self.npz') as archive:
            sr=independent_scores(archive,gt,t)
            archive_prediction={k:archive[k] for k in ['X','PX','xp','Pp']}
            archive_prediction.update({k:z[k] for k in ['ds','gy','dt','x0','P0']})
            independent_prediction(archive_prediction)
            near('Source raw z reconstruction',archive['nu']+archive['hx']+z['mu'],zraw)
          sref=source[(source.case==case)&(source.bias==bias)&(source.arm==arm)].iloc[0]
          for k in sref.index.intersection(sr):near('independent Source archived score '+k,sr[k],sref[k],1e-9)
          source_independent.append(dict(case=case,bias=bias,arm=arm,**sr))
        bb=arrays[case,bias,'BB_ORIG'];mb=arrays[case,bias,'MB_VAR']
        for k in ['ds','gy','dt','x0','P0','z','base_R','gt','t','pose_id']:check('BB MB controlled '+k,np.array_equal(bb[k],mb[k]))
        check('same polarization mean',np.array_equal(bb['mu'][:,1],mb['mu'][:,1]))
        def first(mask):
            a=np.flatnonzero(mask);return None if not len(a) else int(a[0])
        div.append(dict(case=case,bias=bias,first_state_k=first(np.max(abs(bb['X']-mb['X']),axis=1)>1e-10),first_P_k=first(np.max(abs(bb['PX']-mb['PX']),axis=(1,2))>1e-10),first_gate_k=first(bb['used']!=mb['used']),gate_mismatch_all=int(np.count_nonzero(bb['used']!=mb['used']))))
    ind=pd.DataFrame(independent);src=pd.DataFrame(source_independent)
    ind.to_csv(HERE/'RECOMPUTED_DISTANCE_SCORE_24.csv',index=False);src.to_csv(HERE/'RECOMPUTED_SOURCE_SCORE_24.csv',index=False)
    pd.DataFrame(sensitivity).to_csv(HERE/'COVERAGE_THRESHOLD_SENSITIVITY_24.csv',index=False)
    fd=pd.read_csv(OUT/'FIRST_DIVERGENCE_12.csv')
    for d in div:
      ref=fd[(fd.case==d['case'])&(fd.bias==d['bias'])].iloc[0]
      for k in ['first_state_k','first_P_k','first_gate_k','gate_mismatch_all']:
        check('first divergence '+k,(pd.isna(ref[k]) and d[k] is None) or ref[k]==d[k])
    pd.DataFrame(div).to_csv(HERE/'RECOMPUTED_FIRST_DIVERGENCE_12.csv',index=False)
    counts={}
    for label,frame in [('distance_LUT',ind),('SourceFFD',src)]:
      wide=frame.pivot(index=['case','bias'],columns='arm',values=['head_rmse','xy_rmse_cm'])
      counts[label]={}
      for metric in ['head_rmse','xy_rmse_cm']:
        delta=wide[metric,'BB_ORIG']-wide[metric,'MB_VAR'];counts[label][metric]=dict(improved=int((delta>1e-10).sum()),worsened=int((delta< -1e-10).sum()),tied=int((abs(delta)<=1e-10).sum()))
    paired=pd.read_csv(OUT/'PAIRED_BB_MB_12.csv');check('paired ledger 12 unique',len(paired)==12 and not paired.duplicated(['case','bias']).any())
    exact=pd.read_csv(OUT/'FULL_SCORE_CONTRACT_COVERAGE_24.csv')
    for _,r in ind.iterrows():
      match=exact[(exact.case==r.case)&(exact.bias==r.bias)&(exact.arm==r.arm)].iloc[0]
      for a,b in [('heading_coverage95_exact','head_cov95_contract_chi2'),('xy_coverage95_exact','xy_cov95_contract_chi2'),('pose_cov95','pose_cov95_contract_chi2')]:near('exact contractual coverage '+b,r[a],match[b],1e-12)
    for _,r in paired.iterrows():
      bb=ind[(ind.case==r.case)&(ind.bias==r.bias)&(ind.arm=='BB_ORIG')].iloc[0]
      mb=ind[(ind.case==r.case)&(ind.bias==r.bias)&(ind.arm=='MB_VAR')].iloc[0]
      for m in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95','head_bias','n_used','n_used_score','n_score','n_total']:
        near('paired raw BB '+m,r[m+'_BB'],bb[m],1e-9);near('paired raw MB '+m,r[m+'_MB'],mb[m],1e-9);near('paired delta '+m,r[m+'_delta_MB_minus_BB'],mb[m]-bb[m],1e-9)
      for m in ['head_rmse','xy_rmse_cm']:
        near('paired reduction percent '+m,r[m+'_reduction_pct'],100*(1-mb[m]/bb[m]),1e-9)
        outcome='IMPROVED' if bb[m]-mb[m]>1e-10 else ('WORSENED' if bb[m]-mb[m]< -1e-10 else 'TIE')
        check('paired outcome '+m,r[m+'_outcome']==outcome)
    clarify=json.loads((OUT/'CONTRACT_CLARIFICATION.json').read_text(encoding='utf-8'))
    check('coverage definition resolved transparently',clarify['frozen_contract_unchanged'] and not clarify['filter_or_threshold_changes'])
    neg=json.loads((OUT/'FAILURES_AND_NEGATIVE_TESTS.json').read_text(encoding='utf-8'))
    check('7 negative fixtures rejected',len(neg['negative_tests'])==7 and all(r['detected'] for r in neg['negative_tests']))
    parity=pd.read_csv(OUT/'PARITY_SOURCE_REFERENCE_12.csv');check('Source parity ledger 12',len(parity)==12)
    for col in parity.columns:
      if col.endswith(('_X_max','_P_max','_R_max','_used_mismatch')):check('Source parity values '+col,float(parity[col].max())< (1e-12 if col.endswith('_R_max') else 1e-10),max_abs=float(parity[col].max()))
    packet=pd.read_csv(OUT/'PACKET_DIAGNOSTICS.csv.gz',usecols=['case','bias','arm','pose_id','t_s','fd_max_abs'])
    check('every packet FD finite and within threshold',len(packet)==sum(r['n_total'] for r in independent) and np.isfinite(packet.fd_max_abs).all() and packet.fd_max_abs.max()<2e-5,packet_count=len(packet))
    outputs=json.loads((OUT/'OUTPUT_MANIFEST.json').read_text(encoding='utf-8'))['files']
    check('output manifest hashes',all(sha(OUT/p)==h for p,h in outputs.items()),files=len(outputs))
    mixed=any(counts['distance_LUT'][m]['worsened']>0 for m in counts['distance_LUT'])
    doc=dict(question_id=C['contract_id'],actor='/root/independent_audit',role='AUDITOR separate subagent',verdict='ACCEPT',scope='Frozen synthetic-distance-LUT paired BB_ORIG/self versus MB_VAR/self replay, 12 repeated conditions in one environment; no adoption',
      independent_full_filter_runs=0,independent_rescored_distance_traces=24,independent_rescored_source_archives=24,input_lock_count=len(C['input_hashes']),contract_sha256=EXPECTED,base_git_commit=C['base_git_sha'],
      governance=C['governance'],script_sha256=sha(__file__),python=sys.version,numpy=np.__version__,pandas=pd.__version__,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      audited_output_manifest_sha256=sha(OUT/'OUTPUT_MANIFEST.json'),audited_output_files=outputs,audited_scope='All files explicitly listed in parent OUTPUT_MANIFEST.json at audit; later delivery envelope/log-copy additions are outside this hash ledger, not implicitly audited.',
      checks=checks,improvement_counts=counts,coverage_threshold_sensitive_points=int(sum(r['heading_points']+r['xy_points'] for r in sensitivity)),
      findings=[dict(id='COVERAGE-DEFINITION-01',severity='minor reporting',description='Historical head_cov95 uses |e/sigma|<1.96 and xy_cov95 uses NEES<5.991; contract exact chi-square cutoffs differ slightly. Exact coverage supplied separately and verified against independent recomputation. No change to filters/RMSE/NEES.',resolved=True,resolution='Separate exact contractual coverage ledger and transparent CONTRACT_CLARIFICATION.json preserve original history and frozen contract.')],
      limitations=['No independent environment or RF realization; biases share one sensor seed.','Synthetic LUT derives from the same verified FFD bank, not measured calibration.','BB to MB changes mean, variance, and consequent self gate jointly; no pure-component causal attribution.','Source parity state traces are independently rescored archived traces; actual replay parity uses frozen parent execution ledger, not a second independent filter rerun.','Observer actual-prior finite differences independently code-reviewed and complete evidence checked; no second full observer sweep.'],scientific_claim_status='MIXED' if mixed else 'SUPPORTED_WITHIN_FROZEN_SCENARIO',adopted=False)
    (HERE/'INDEPENDENT_AUDIT.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    text=['# 독립 감사 — DLP-LUT-BB-MB-MATCHED-001','',f"판정: {doc['verdict']}. 감사 actor는 /root/independent_audit이며 구현자와 별도 하위 에이전트이다.",'',
      f"거리 LUT 24 trace와 보존 SourceFFD 24 trace의 Heading·XY·NEES·coverage를 원자료에서 독립 재집계했다. 총 {len(checks)}개 검사를 통과했다. 추가 필터 재생은 수행하지 않았다.",'',
      '동결 계약/237개 입력 해시, 출력 manifest, 이전 MB12 trace의 X/P/R/used/J 완전 일치, 원 donor/관측/초기화, 직전 posterior 거리 분산, 동역학과 과정공분산, innovation·gain·NIS·self gate·Joseph 갱신, 양의 정부호와 최초 divergence를 확인했다. 전체 packet 수치미분 기록이 동결 기준을 통과했으며 수치미분 검사는 코드를 별도로 검토했다.','',
      f"새 LUT 개선/악화 집계: {json.dumps(counts['distance_LUT'],ensure_ascii=False)}. Source 참조 집계: {json.dumps(counts['SourceFFD'],ensure_ascii=False)}.",'',
      '발견한 coverage 정의 차이는 해소됐다. 보존 역사 기준(1.96/5.991)은 유지하고 정확한 계약 χ² coverage를 별도 ledger에 제공했으며 독립 재계산과 일치한다. 필터나 동결 계약은 변경되지 않았다.','',
      f"과학 결과: {doc['scientific_claim_status']}. 한 환경·한 RF realization·동일 seed의 결합 개입 비교에만 수용한다. 작은 NEES를 일관성 입증으로 보지 않는다. 성능 차이를 평균/분산/gate의 순수 기여율로 분해할 수 없고 실측 전이·일반 성능 우위를 주장할 수 없다. 모델/원고 채택은 수행하지 않았다.",'',
      '실행 자체의 Source 상태 재현은 보존 trace와 구현자 실행의 동결 parity ledger를 확인했으며 독립적인 두 번째 필터 구현/재실행은 하지 않았다. 감사 코드와 세부 검사는 INDEPENDENT_AUDIT.json 및 independent_audit.py에 기록했다.']
    (HERE/'INDEPENDENT_AUDIT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps(dict(verdict=doc['verdict'],checks=len(checks),counts=counts,coverage_sensitive=doc['coverage_threshold_sensitive_points']),ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        (HERE/'AUDIT_FAILURE.json').write_text(json.dumps(dict(error=repr(exc),traceback=traceback.format_exc(),checks=checks),indent=2),encoding='utf-8');raise
