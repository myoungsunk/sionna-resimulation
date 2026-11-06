"""Stage 1 stored-array lineage inspection; no filter/model/provider execution."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import json,hashlib,subprocess,datetime,sys
from pathlib import Path
import numpy as np
import psutil
psutil.Process().cpu_affinity(psutil.Process().cpu_affinity()[:3])
P=Path(__file__).resolve().parent;R=P.parents[4];B=P.parent
M=B/'PRIOR_INTEGRITY_R1_20261105/PREPARATION_001/MANIFEST_PREP_ONLY.json'
manifest=json.loads(M.read_text());base=B/'E0_20261105/A2_20261105/RUN_E0_A2_001/baseline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def arrays(p):
 with np.load(p,allow_pickle=False) as a:return {k:a[k] for k in a.files}
index=json.loads((base/'ARTIFACT_HASHES.json').read_text());records=[];inputs={};channels={}
for cid,spec in manifest['cases'].items():
 paths={'online':R/spec['online_npz'],'controls':base/(cid+'_CONTROLS.npz'),'trace':base/(cid+'_REPLAY.npz'),'receipt':base/(cid+'.json')}
 for name,p in paths.items():
  actual=sha(p);expected=manifest['input_files'].get(p.relative_to(R).as_posix()) if name=='online' else index[p.name]
  assert actual==expected,(cid,name);inputs[p.relative_to(R).as_posix()]=actual
 a=arrays(paths['online']);c=arrays(paths['controls']);tr=arrays(paths['trace']);receipt=json.loads(paths['receipt'].read_text())
 n=spec['expected_rows'];assert len(a['t'])==n and len(set(a['pose_id']))==n and np.all(np.diff(a['t'])>0)
 assert np.array_equal(a['t'],tr['t']) and np.array_equal(a['pose_id'],tr['pose_id'])
 assert np.max(abs(a['dt'][1:]-np.diff(a['t'])))<1e-10
 for key in ('ds','gy','dt'):assert np.array_equal(a[key],c[key])
 assert np.array_equal(a['x0'][:3],c['x0']) and a['x0'][3]==0
 for key in ('prior','Pprior'):assert np.array_equal(a[key],tr[key])
 assert np.array_equal(a['prior'][0],a['x0'])
 innovation=a['z']-tr['h']-a['muMB'];nu_error=float(np.max(abs(innovation-tr['nu'])))
 nis=np.einsum('ni,ni->n',tr['nu'],np.linalg.solve(tr['S'],tr['nu'][...,None])[...,0])
 nis_error=float(np.max(abs(nis-tr['nis'])))
 # One-step arithmetic on archived previous POSTERIOR, no recursive execution.
 prev=tr['x'][:-1];angle=a['gy'][1:]-prev[:,3]*a['dt'][1:]
 phi=prev[:,2]+angle/2;distance=a['ds'][1:]*np.sinc(angle/(2*np.pi))
 expected=prev.copy();expected[:,0]+=distance*np.cos(phi);expected[:,1]+=distance*np.sin(phi)
 expected[:,2]=(prev[:,2]+angle+np.pi)%(2*np.pi)-np.pi
 err=float(np.max(abs(expected-tr['prior'][1:])))
 assert nu_error<=1e-10 and nis_error<=1e-10 and err<=1e-10
 assert all(np.isfinite(tr[k]).all() for k in ('nu','S','nis','x','P','h','H'))
 missing=[k for k in ('x','P','nu','S','nis') if k not in a and 'trace_'+k not in a]
 route=spec['metadata']['route'];channel=spec['metadata']['channel']
 channels[(route,channel)]={k:c[k] for k in ('ds','gy','dt','x0')}
 records.append(dict(case_id=cid,n=n,control_origin=receipt.get('controls'),source_status=receipt.get('status'),
  accepted=int(tr['mask'].sum()),rejected=int((~tr['mask']).sum()),nu_rows=n,nis_rows=n,
  missing_from_canonical=missing,innovation_formula_error=nu_error,nis_formula_error=nis_error,
  prior_from_previous_posterior_error=err,initial_prior_equals_shared_x0=True,dt_s=float(np.median(a['dt'][1:])),
  source_trace_fields=sorted(tr),canonical_fields=sorted(a)))
paired={route:{k:bool(np.array_equal(channels[(route,'Full')][k],channels[(route,'Native_LoS')][k])) for k in ('ds','gy','dt','x0')} for route in ('R2','R4','R5')}
assert all(all(v.values()) for v in paired.values())
sourcepaths=['scripts/prepare_fp_sc_e102.py','src/qclean_uwb/fp_sc/followup/data.py','src/qclean_uwb/fp_sc/e0_baseline.py','src/qclean_uwb/fp_sc/e0_rematerialized.py','research/MBVAR_PRR_001_20261103/S1/online.py','research/EKF4_RANGE_S_STAGED_20261014/core.py','src/qclean_uwb/drivesim/sensor_v2.py','research/DS_MASK_CAUSAL_X1_X2_20261026/pol_bias_model/exp_pb.py','research/MBVAR_PRR_001_20261103/S1/materialize.py']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
sources={p:hashlib.sha256(subprocess.check_output(['git','show',head+':'+p],cwd=R)).hexdigest() for p in sourcepaths}
for p,h in sources.items():
 if (R/p).exists():assert sha(R/p)==h
result=dict(question_id='FP-SC-PRIOR-PROVIDER-STAGE1',role='PROPOSER_LINEAGE_SELF_CHECK',base_commit=head,
 utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,analysis_script_sha256=sha(Path(__file__)),
 status='PASS_LINEAGE_CHECK_NOT_PRIOR_VALIDATION',total_rows=sum(r['n'] for r in records),cases=records,
 paired_controls_and_initial_state_identical=paired,input_hashes=inputs,source_hashes=sources,
 governance_hashes={n:sha(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n) for n in ('COMMON_CONTRACT.md','ROLE_PROPOSER.md')},
 cpu_affinity=psutil.Process().cpu_affinity(),new_RF_calls=0,model_calls=0,EKF_replay_calls=0,provider_runs=0,E1_02_started=False,E2_started=False,
 no_NEW_VALID_basis=True,independent_audit=False)
(P/'LINEAGE_CHECK.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(total_rows=result['total_rows'],paired=paired,cases=[{k:r[k] for k in ('case_id','accepted','rejected','innovation_formula_error','nis_formula_error','prior_from_previous_posterior_error','missing_from_canonical')} for r in records]),indent=2))
