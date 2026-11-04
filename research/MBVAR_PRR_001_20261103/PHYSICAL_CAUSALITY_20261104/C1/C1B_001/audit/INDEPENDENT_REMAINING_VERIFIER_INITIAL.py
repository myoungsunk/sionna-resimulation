"""Independent C1b remaining audit plus full120 report. Read-only.
Checks every stored Full BASE recursion edge for remaining114 conditions with
original locked FFD; reuses accepted DEV6 without rerunning that audit.
Run with original Windows interpreter -X utf8 -B and all BLAS thread variables=1.
"""
import csv, hashlib, importlib.metadata, importlib.util, json, math, os
from pathlib import Path
import platform, subprocess, sys
import numpy as np
from threadpoolctl import threadpool_info

ROOT=Path(r'D:/codex/MBVAR_PRR_001_20261103')
PHYS=ROOT/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104'
HERE=PHYS/'C1/C1B_001'
PARENT=HERE.parent/'C1A_001'
CACHE=Path(r'D:/codex/MBVAR_PRR_001_20261103_inputs/C1B_001')
INPUTS=CACHE.parent/'C1A_001'
OUT=HERE/'REMAINING_001'
ARMS=('FF','LF','FL','LL')
GATE=9.210340371976184
MAX={}
COUNTS=dict(cells=0,priors=0,posterior_rows=0,summary_rows=0,BASE_transition_edges=0,
            BASE_update_edges=0,source_observer_states=0,gate_rows=0)
FLIPS={}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with np.load(p,allow_pickle=False) as z: return dict(z)
def js(p): return json.loads(p.read_bytes())
def check(name, actual, expected, angular=False):
    a,b=np.asarray(actual),np.asarray(expected)
    assert a.shape==b.shape,(name,a.shape,b.shape)
    assert np.isfinite(a).all() and np.isfinite(b).all(),name
    delta=a-b
    if angular: delta=np.arctan2(np.sin(delta),np.cos(delta))
    MAX[name]=max(MAX.get(name,0.),float(np.max(np.abs(delta))))
    assert np.all(np.abs(delta)<=1e-10+1e-10*np.abs(b)),(name,MAX[name])
def exact(name,a,b): assert np.array_equal(a,b),name
def inv2(a):
    aa,bb,cc,dd=np.moveaxis(a.reshape(*a.shape[:-2],4),-1,0)
    determinant=aa*dd-bb*cc
    assert np.isfinite(determinant).all() and np.all(determinant>0)
    return np.stack((dd,-bb,-cc,aa),axis=-1).reshape(a.shape)/determinant[...,None,None]
def wrap(a): return (a+np.pi)%(2*np.pi)-np.pi
def sym(a): return (a+a.swapaxes(-1,-2))*.5
def predict(x,P,ds,gy,dt):
    angle=gy-x[3]*dt
    if abs(angle)<1e-4:
        a2=angle*angle
        c=1-a2/24+a2*a2/1920-a2**3/322560
        dc=-angle/12+angle**3/480-angle**5/53760
    else:
        half=angle*.5
        c=math.sin(half)/half
        dc=(half*math.cos(half)-math.sin(half))/(2*half*half)
    theta=x[2]+angle*.5;u=np.array([math.cos(theta),math.sin(theta)])
    displacement=ds*c*u
    derivative=ds*(dc*u+c*np.array([-u[1],u[0]])*.5)
    y=x.copy();y[:2]+=displacement;y[2]=wrap(y[2]+angle)
    F=np.eye(4);F[:2,2]=[-displacement[1],displacement[0]]
    F[:2,3]=-dt*derivative;F[2,3]=-dt
    G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=derivative;G[2,1]=1.;G[3,2]=1.
    Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
    return y,sym(F@sym(P)@F.T+G@Q@G.T)
def errors(x,truth):
    xy=np.sqrt(np.sum((x[...,:2]-truth[:,None,:2])**2,axis=-1))
    d=x[...,2]-truth[:,None,2]
    yaw=np.abs(np.arctan2(np.sin(d),np.cos(d)))*180/np.pi
    return xy,yaw

assert sys.dont_write_bytecode
plan=js(HERE/'PLAN.json');lock=js(HERE/'INPUT_LOCK.json');go=js(HERE/'GO_REMAINING.json')
assert go['schema']=='C1B_GO_V1' and go['decision']=='GO'
assert go['authorized']==dict(stage='C1b_only',phase='remaining',routes=['R2','R4','R5'],
                            biases=['B0','L2'],seeds=list(range(11,30)),output='REMAINING_001')
bindings=go['bindings_sha256'];assert len(bindings)==11
for n,h in bindings.items():
    assert sha(HERE/n)==h,n
    gitpath=(HERE/n).resolve().relative_to(ROOT).as_posix()
    raw=subprocess.check_output(['git','-C',str(ROOT),'show',
        '577ff8b58d3e2e79c3144e92ea91a15bb272d18c:'+gitpath])
    assert hashlib.sha256(raw).hexdigest()==h,n
env=js(CACHE/'provenance/ENV_LOCK.json')
assert sys.version==env['python'] and platform.platform()==env['os']
assert {k:importlib.metadata.version(k) for k in env['packages']}==env['packages']
assert all(os.environ.get(k)=='1' for k in env['threads'])
pools=threadpool_info();assert pools and all(p['num_threads']==1 for p in pools)
assert sha(Path(sys.executable))==plan['python_executable_sha256']
assert sha(PARENT/'INPUT_LOCK.json')==lock['c1a_input_lock_sha256']
assert sha(PARENT/'audit/C1A_RESULT_AUDIT_RESULT.json')==lock['c1a_result_audit_sha256']
paudit=js(PARENT/'audit/C1A_RESULT_AUDIT_RESULT.json')
assert paudit['decision']=='ACCEPT'
pindex=PARENT/'RESULTS_001/ARTIFACT_HASHES.json'
assert sha(pindex)==paudit['artifact_hashes_sha256'];partifacts=js(pindex)
for n,d in js(PARENT/'INPUT_LOCK.json')['sources'].items():
    assert (INPUTS/n).stat().st_size==d['size'] and sha(INPUTS/n)==d['payload_sha256'],n
for n,d in lock['sources'].items():
    assert (CACHE/n).stat().st_size==d['size'] and sha(CACHE/n)==d['sha256'],n
for d in lock['banks'].values():
    assert Path(d['path']).stat().st_size==d['size'] and sha(Path(d['path']))==d['sha256']
index=js(OUT/'ARTIFACT_HASHES.json')
actual={p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()}
assert actual==set(index)|{'ARTIFACT_HASHES.json'}
for n,h in index.items(): assert sha(OUT/n)==h,n
assert (OUT/'FAILURES.jsonl').read_bytes()==b''
manifest=js(OUT/'MANIFEST.json');run=js(HERE/'RUN_RESULT_REMAINING.json')
assert manifest['status']==run['status']=='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
assert run['result_status']==manifest['status'] and run['exit_code']==0
assert manifest['bindings_sha256']==bindings
assert manifest['go_sha256']==run['go_sha256']==sha(HERE/'GO_REMAINING.json')
assert run['start_utc']<=manifest['start_utc']<manifest['end_utc']<=run['end_utc']
assert manifest['runtime']['python']==sys.version
assert manifest['runtime']['packages']==env['packages']
assert all(p['num_threads']==1 for p in manifest['runtime']['threadpools'])
assert manifest['new_MBVAR_baseline_replays']==manifest['new_training_runs']==manifest['new_RT_calls']==0

# Require accepted DEV before independent remaining observer evaluation.
dev_receipt=HERE/'audit/C1B_DEV_RESULT_AUDIT_RESULT.json'
assert sha(dev_receipt)==go['prerequisite_sha256']=='3ed290cde38e0da2a0766f6104aecfdde51ab858f3ccda03bd66aabb8ba886bd'
dev_audit=js(dev_receipt);assert dev_audit['decision']=='ACCEPT'
assert dev_audit['bindings_sha256']==bindings
# Import original observation source directly, never production C1b loader.
legacy=CACHE/'legacy'
sys.path[:0]=[str(legacy/'research/FFD_P0P3_20261016'),
 str(legacy/'research/EKF4_RANGE_S_STAGED_20261014'),
 str(legacy/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
spec=importlib.util.spec_from_file_location('independent_locked_source',
    legacy/'research/FFD_P0P3_20261016/source_model.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
banks=[]
for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
    banks.append(original.P.Bank(read(Path(lock['banks'][n]['path']))))
observer=original.SourceFFD(banks=banks)
case=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
table=iter(csv.DictReader((OUT/'POSE_EFFECTS.csv').open(newline='',encoding='utf8')))
saved_summary=js(OUT/'CELL_SUMMARY.json');summary_index=0;independent_summaries=[]
minimum_eigenvalue=float('inf');maximum_symmetry_error=0.
for route in ['R2','R4','R5']:
 for bias in ['B0','L2']:
  for seed in range(11,30):
     cell=f'{route}_{bias}_{seed}';d=read(OUT/'cells'/(cell+'.npz'))
     tr=read(INPUTS/(cell+'_TRACE.npz'))
     full=read(INPUTS/f'{route}_aB_m0_{bias}_Full.npz')
     los=read(INPUTS/f'{route}_aB_m0_{bias}_Native_LoS.npz')
     ctl=read(CACHE/'controls'/f'{route}_aB_m0_{bias}_{seed}.npz')
     c1path=PARENT/'RESULTS_001/cells'/(cell+'.npz')
     assert sha(c1path)==partifacts['cells/'+cell+'.npz'];old=read(c1path)
     truth=read(INPUTS/f'{route}_{bias}_TRUTH.npz')
     n=plan['route_rows'][route];assert len(d['t'])==n
     for data in [d,tr,full,los,old,truth]:
         exact(cell+' poses',data['pose_id'],full['pose_id'])
         exact(cell+' times',data['t'],full['t'])
     assert len(np.unique(d['pose_id']))==n
     exact('arm order',d['arms'],np.array(ARMS))
     for key,v in d.items():
         if key!='arms':assert np.isfinite(v).all(),(cell,key)
     for key,expected in [('prior',tr['prior']),('Pprior',tr['Pprior']),('h',tr['h']),
       ('H',tr['H']),('mu',tr['mu']),('R',tr['Rvar']),('BASE_mean',full['muBASE']),
       ('BASE_R',full['R']),('z_full',full['z']),('z_los',los['z'])]:
         exact(cell+' frozen '+key,d[key],expected)
     z=np.stack([full['z'],np.column_stack([los['z'][:,0],full['z'][:,1]]),
          np.column_stack([full['z'][:,0],los['z'][:,1]]),los['z']],axis=1)
     # Original observer is evaluated at stored BASE and archived MB_VAR priors,
     # independently of the production observation values.
     observed={}
     for label,states in [('BASE',d['BASE_prior']),('MB',tr['prior'])]:
         hs=[];js_=[]
         for start in range(0,n,32):
             hh,jj=observer.batch(states[start:start+32],case)
             hs.append(hh);js_.append(jj);COUNTS['source_observer_states']+=len(hh)
         observed[label]=(np.concatenate(hs),np.concatenate(js_))
     hb,Hb=observed['BASE']
     check('original_source_BASE_h',d['BASE_h'],hb)
     check('original_source_BASE_H',d['BASE_H'],Hb)
     check('original_source_MB_h',tr['h'],observed['MB'][0])
     check('original_source_MB_H',tr['H'],observed['MB'][1])
     gate=np.empty((n,4),dtype=bool)
     for k in range(n):
         if k==0:xp=np.r_[ctl['x0'],0.];pp=full['P0'].copy()
         else:xp,pp=predict(d['BASE_x'][k-1],d['BASE_P'][k-1],
                          ctl['ds'][k],ctl['gy'][k],ctl['dt'][k])
         check('BASE_transition_x',d['BASE_prior'][k],xp)
         check('BASE_transition_P',d['BASE_Pprior'][k],pp)
         COUNTS['BASE_transition_edges']+=1
         # Gate/update use independently verified saved prior and original
         # stored h/H, avoiding tolerance accumulation across local edge checks.
         bp=d['BASE_Pprior'][k];bx=d['BASE_prior'][k];H=d['BASE_H'][k];h=d['BASE_h'][k]
         S=H@bp@H.T+full['R'][k];check('BASE_S',d['BASE_S'][k],S)
         innovation=z[k]-h-full['muBASE'][k]
         inverse=inv2(S);nis=np.einsum('ai,ij,aj->a',innovation,inverse,innovation)
         check('BASE_NIS',d['BASE_nis'][k],nis)
         gate[k]=nis<=GATE;exact('BASE four joint gates',d['mask'][k],gate[k])
         assert gate[k,0]==tr['mask'][k]
         if gate[k,0]:
             gain=bp@H.T@inverse
             y=bx+gain@innovation[0];y[2]=wrap(y[2])
             a=np.eye(4)-gain@H
             post=sym(a@bp@a.T+gain@full['R'][k]@gain.T)
         else:y=bx;post=bp
         check('BASE_FF_update_x',d['BASE_x'][k],y)
         check('BASE_FF_update_P',d['BASE_P'][k],post)
         COUNTS['BASE_update_edges']+=1
     H=tr['H'];pp=tr['Pprior'];R=tr['Rvar']
     S=sym(H@pp@H.swapaxes(-1,-2)+R)
     K=pp@H.swapaxes(-1,-2)@inv2(S)
     check('unmasked_K_star',d['K_star'],K);check('MB_S',d['S'],S)
     innovation=z-tr['h'][:,None]-tr['mu'][:,None]
     potential=tr['prior'][:,None]+np.einsum('nij,naj->nai',K,innovation)
     u=np.where(gate[:,:,None],potential,tr['prior'][:,None])
     x=u.copy();x[:,:,2]=np.where(gate,wrap(x[:,:,2]),tr['prior'][:,None,2])
     a=np.eye(4)-K@H;post=sym(a@pp@a.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2))
     P=np.where(gate[:,:,None,None],post[:,None],pp[:,None])
     maskedK=np.where(gate[:,:,None,None],K[:,None],0.)
     for key,v in [('x',x),('u',u),('P',P),('K',maskedK)]:check('independent_'+key,d[key],v)
     exact('FF mask',gate[:,0],tr['mask'])
     for key in ['x','P','K']:check('FF_baseline_'+key,d[key][:,0],tr[key])
     check('C1a_FF_x',d['x'][:,0],old['x'][:,0])
     check('C1a_FF_P',d['P'][:,0],old['P'])
     for name,array in [('BASE_Pprior',d['BASE_Pprior']),('BASE_P',d['BASE_P']),
                         ('MB_prior',pp),('MB_posterior',d['P'])]:
         mat=array.reshape(-1,4,4)
         symmetry=np.max(abs(mat-mat.swapaxes(-1,-2)),axis=(1,2))
         eig=np.linalg.eigvalsh(sym(mat));scale=np.maximum(1,np.max(abs(eig),axis=1))
         assert np.all(symmetry<=1e-12*scale) and np.all(eig[:,0]>=-1e-12*scale)
         minimum_eigenvalue=min(minimum_eigenvalue,float(eig.min()))
         maximum_symmetry_error=max(maximum_symmetry_error,float(symmetry.max()))
     xy,heading=errors(x,truth['truth']);oldxy,oldhead=errors(old['x'],truth['truth'])
     primary=d['t']>=30.
     FLIPS[cell]={}
     for j,arm in enumerate(ARMS):
         for k in range(n):
             row=next(table)
             assert (row['route'],row['bias'],int(row['seed']),int(row['pose_id']),float(row['t_s']),row['arm'])==(route,bias,seed,int(d['pose_id'][k]),float(d['t'][k]),arm)
             assert row['accepted']==str(bool(gate[k,j])) and row['FF_accepted']==str(bool(gate[k,0]))
             expected=[xy[k,j],heading[k,j],xy[k,j]-xy[k,0],heading[k,j]-heading[k,0],
                       xy[k,j]-oldxy[k,j],heading[k,j]-oldhead[k,j]]
             fields=['xy_m','heading_deg','delta_xy_vs_FF','delta_heading_vs_FF','delta_xy_vs_C1a','delta_heading_vs_C1a']
             check('all_CSV_scores',np.array([float(row[f]) for f in fields]),np.array(expected))
             COUNTS['posterior_rows']+=1
         expected=dict(route=route,bias=bias,seed=seed,arm=arm,n=int(primary.sum()),
           mean_xy_m=float(xy[primary,j].mean()),median_xy_m=float(np.median(xy[primary,j])),
           mean_heading_deg=float(heading[primary,j].mean()),median_heading_deg=float(np.median(heading[primary,j])),
           mean_delta_xy_vs_FF=float((xy[primary,j]-xy[primary,0]).mean()),
           mean_delta_heading_vs_FF=float((heading[primary,j]-heading[primary,0]).mean()),
           mean_delta_xy_vs_C1a=float((xy[primary,j]-oldxy[primary,j]).mean()),
           mean_delta_heading_vs_C1a=float((heading[primary,j]-oldhead[primary,j]).mean()),
           accepted_all=int(gate[:,j].sum()),accepted_primary=int(gate[primary,j].sum()),
           newly_accepted_all=int((gate[:,j]&~gate[:,0]).sum()),
           newly_rejected_all=int((~gate[:,j]&gate[:,0]).sum()),
           newly_accepted_primary=int((gate[primary,j]&~gate[primary,0]).sum()),
           newly_rejected_primary=int((~gate[primary,j]&gate[primary,0]).sum()))
         independent_summaries.append(expected)
         saved=saved_summary[summary_index];assert set(saved)==set(expected)
         for key,value in expected.items():
             if isinstance(value,float):check('all_summary_fields',np.array(saved[key]),np.array(value))
             else:assert saved[key]==value,(cell,arm,key)
         FLIPS[cell][arm]={k:expected[k] for k in ['newly_accepted_all','newly_rejected_all']}
         summary_index+=1;COUNTS['summary_rows']+=1
     COUNTS['cells']+=1;COUNTS['priors']+=n;COUNTS['gate_rows']+=4*n
     print('C1B_REMAINING_INDEPENDENT_CELL',cell,flush=True)
assert next(table,None) is None
assert COUNTS['cells']==114 and COUNTS['priors']==119168 and COUNTS['posterior_rows']==476672
assert COUNTS['summary_rows']==456 and len(saved_summary)==456
assert manifest['completed_cells']==114 and manifest['priors']==119168 and manifest['posterior_rows']==476672
assert manifest['BASE_shadow_reconstructions']==114 and manifest['FFD_states_completed']==119168

# DEV evidence is reused, not scientifically rerun.
dev=HERE/'DEV_001';devindex=dev/'ARTIFACT_HASHES.json'
assert sha(devindex)==dev_audit['artifact_hashes_sha256']
devhashes=js(devindex)
assert {p.relative_to(dev).as_posix() for p in dev.rglob('*') if p.is_file()}==set(devhashes)|{'ARTIFACT_HASHES.json'}
for n,h in devhashes.items():assert sha(dev/n)==h,n
devsummary=js(dev/'CELL_SUMMARY.json')
combined=devsummary+independent_summaries
keys=[(r['route'],r['bias'],r['seed'],r['arm']) for r in combined]
wanted={(r,b,k,a) for r in ['R2','R4','R5'] for b in ['B0','L2'] for k in range(10,30) for a in ARMS}
assert len(keys)==len(set(keys))==480 and set(keys)==wanted
assert len({(r,b,k) for r,b,k,a in keys})==120
assert {r['seed'] for r in devsummary}=={10}
assert {r['seed'] for r in independent_summaries}==set(range(11,30))
aggregate=list(csv.DictReader((HERE/'AGGREGATE_SUMMARY.csv').open(newline='',encoding='utf8')))
assert len(aggregate)==24
report=(HERE/'RESULTS_KO.md').read_text(encoding='utf8')
reportrows=[line for line in report.splitlines() if line.startswith(('|R2|','|R4|','|R5|'))]
assert len(reportrows)==24
summary_fields=['mean_xy_m','mean_heading_deg','mean_delta_xy_vs_FF',
                'mean_delta_heading_vs_FF','mean_delta_xy_vs_C1a','mean_delta_heading_vs_C1a']
flipfields=['newly_accepted_all','newly_rejected_all','newly_accepted_primary','newly_rejected_primary']
aggregate_index=0
for route in ['R2','R4','R5']:
 for bias in ['B0','L2']:
  for arm in ARMS:
    group=[r for r in combined if (r['route'],r['bias'],r['arm'])==(route,bias,arm)]
    assert len(group)==20 and {r['seed'] for r in group}==set(range(10,30))
    assert len({r['n'] for r in group})==1
    expected={k:math.fsum(r[k] for r in group)/20 for k in summary_fields}
    expected.update({k:sum(r[k] for r in group) for k in flipfields})
    row=aggregate[aggregate_index]
    assert (row['route'],row['bias'],row['arm'],int(row['seeds']))==(route,bias,arm,20)
    for k in summary_fields:check('full120_aggregate_fields',np.array(float(row[k])),np.array(expected[k]))
    for k in flipfields:assert int(row[k])==expected[k]
    expected_line=(f"|{route}|{bias}|{arm}|{expected['mean_xy_m']:.9f}|{expected['mean_heading_deg']:.9f}|"
       f"{expected['mean_delta_xy_vs_FF']:+.9f}|{expected['mean_delta_heading_vs_FF']:+.9f}|"
       f"{expected['mean_delta_heading_vs_C1a']:+.9f}|{expected['newly_accepted_all']}/{expected['newly_rejected_all']}|")
    assert reportrows[aggregate_index]==expected_line,('report table',route,bias,arm,expected_line)
    aggregate_index+=1
assert sha(HERE/'RESULTS_KO.md')=='4d0c86229bb0b29348f3cccbd079bcd64833f8316bf7157b20818d88b70efe82'
assert sha(HERE/'AGGREGATE_SUMMARY.csv')=='2b685f078582decc91a81fec9f919a012e775db5b94b34e2789e4477c067fd30'
assert 'RMSE·미래 오차 적분·재귀효과가 아니다' in report
assert '동일 RF와 반복 seed를 독립 사건으로 해석하지 않는다' in report
assert '공분산 교정·일관성 개선이라고 부르지 않는다' in report
assert '기존 NO-GO/HOLD는 유지한다' in report
assert '상세 계약·코드·실행 GO는 별도' in report
# report.py has been reviewed as source only; it is never executed here.
assert (HERE/'report.py').is_file()
result=dict(schema='C1B_FULL_RESULT_AUDIT_V1',decision='ACCEPT',
 question_id='C1B-BASE-GATE-001',scope='All120 same-prior C1b cells and report only',
 bindings_sha256=bindings,remaining_go_sha256=sha(HERE/'GO_REMAINING.json'),
 dev_acceptance_sha256=sha(dev_receipt),
 dev_manifest_sha256=sha(dev/'MANIFEST.json'),dev_artifact_hashes_sha256=sha(devindex),
 remaining_manifest_sha256=sha(OUT/'MANIFEST.json'),remaining_artifact_hashes_sha256=sha(OUT/'ARTIFACT_HASHES.json'),
 remaining_pose_effects_sha256=sha(OUT/'POSE_EFFECTS.csv'),
 remaining_cell_summary_sha256=sha(OUT/'CELL_SUMMARY.json'),
 remaining_checks_sha256=sha(OUT/'CHECKS.json'),
 remaining_run_result_sha256=sha(HERE/'RUN_RESULT_REMAINING.json'),
 remaining_execution_log_sha256=sha(HERE/'EXECUTION_REMAINING.log'),
 report_sha256=sha(HERE/'RESULTS_KO.md'),aggregate_summary_sha256=sha(HERE/'AGGREGATE_SUMMARY.csv'),
 report_source_sha256=sha(HERE/'report.py'),
 counts=dict(cells=120,priors=125440,posterior_rows=501760,summary_rows=480,
             aggregate_rows=24,report_table_numeric_values=168,aggregate_numeric_values=264),
 remaining_independent_checks=COUNTS,accepted_DEV_cells_reused_without_reexecution=6,
 verified_remaining_output_artifacts=len(index),verified_DEV_output_artifacts=len(devhashes),
 verified_C1a_inputs=145,verified_controls_sources=134,verified_banks=2,
 max_absolute_differences=MAX,
 minimum_covariance_eigenvalue=min(minimum_eigenvalue,dev_audit['minimum_covariance_eigenvalue']),
 maximum_covariance_symmetry_error=max(maximum_symmetry_error,dev_audit['maximum_covariance_symmetry_error']),
 BASE_audit_method='Independent analytic motion and Joseph/gate closure at every stored remaining recursion edge; locked original FFD evaluated at all remaining BASE and archived MB_VAR priors. Accepted DEV evidence reused by hash, without a second policy replay.',
 production_conditional_calls=0,production_score_calls=0,production_legacy_loader_calls=0,
 report_source_executions=0,observer_initializations=1,observer_scope='Only completed remaining114 cells',
 new_policy_runs=0,new_MBVAR_baseline_replays=0,new_RT_calls=0,
 seed10_reruns=0,auditor_files_modified=0,children=0,C2_GO=False,
 claim_boundary='Published-RF conditional current-packet BASE-gate effects only; no recursive hybrid policy, independent-seed event counts, covariance calibration improvement, generalization or adoption. Original NO-GO/HOLD remains.',
 required_corrections=[])
print('C1B_RESULT_AUDIT_RESULT '+json.dumps(result,ensure_ascii=False,allow_nan=False),flush=True)
