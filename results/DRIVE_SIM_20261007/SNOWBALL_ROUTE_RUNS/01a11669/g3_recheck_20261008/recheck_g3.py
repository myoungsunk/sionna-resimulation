import json,subprocess,os,datetime,hashlib,csv
from pathlib import Path
q=Path('/job');s=q/'source';env=dict(os.environ,PYTHON='/opt/rt-env/bin/python',S2_DIR='/job/S2',PYTHONPATH='/runtime_packages:/job/source/src',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
args=['bash','scripts/drive_sim/run_rf_snowball.sh','routes-continuity']
with (q/'routes-continuity_recheck.log').open('x') as f:rc=subprocess.call(args,cwd=s,env=env,stdout=f,stderr=subprocess.STDOUT)
reports={};checks={}
for route in ['R2','R4','R5']:
 timeline=s/'results/DRIVE_SIM_20261007/S1/routes'/('timeline_'+route+'_Tnone.csv');rows=list(csv.DictReader(timeline.open()));expected=len({(round(float(t['x']),6),round(float(t['y']),6)) for t in rows if t['phase'] in ('drive_out','drive_back','drive')})
 for a in ['A','B']:
  k=route+'_a'+a;p=q/'S2'/('G3_continuity_'+k+'.json')
  if p.exists():
   v=json.loads(p.read_text());reports[k]=v;checks[k]=dict(expected_stations=expected,actual_stations=v['stations'],nonempty=v['stations']>0,count_matches=v['stations']==expected,missing=len(v['missing_traces']),bad=len(v['status_not_ok']))
rep=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=args,exit_code=rc,scope='G3 only; original traces/H/S6 read-only, no new RF or S6',previous_G3_valid=False,previous_reason='all six reports stations=0',G3_authorized_tolerance_s=2e-13,checks=checks,strict={k:v['passed_strict_prereg_tol'] for k,v in reports.items()},relaxed={k:v['passed_relaxed_2e13'] for k,v in reports.items()},previous_scientific_PASS_claim=False)
rep['coverage_valid']=rc==0 and len(checks)==6 and all(v['nonempty'] and v['count_matches'] and v['missing']==0 and v['bad']==0 for v in checks.values());rep['B_G3_eligible_after_recheck']=rep['coverage_valid'] and all(rep['relaxed'].values())
(q/'G3_RECHECK_RECEIPT.json').write_text(json.dumps(rep,indent=2));print(json.dumps(rep),flush=True)
assert rep['coverage_valid'],repr(rep)
