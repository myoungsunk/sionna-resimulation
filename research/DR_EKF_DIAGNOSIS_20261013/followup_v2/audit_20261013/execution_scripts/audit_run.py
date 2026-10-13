import pathlib, subprocess, sys, time, json, hashlib, datetime
root=pathlib.Path(__file__).parent
out=root/'audit_evidence';out.mkdir(exist_ok=True)
f=root/'research/DR_EKF_DIAGNOSIS_20261013/followup_v2'
stages=[('compile',[sys.executable,'-m','compileall','-q',str(f),str(root/'tests/test_dr_ekf_followup_v2.py')]),('tests',[sys.executable,'-m','pytest','-q','tests/test_dr_ekf_followup_v2.py']),('v0',[sys.executable,str(f/'v0_cache_audit.py'),'--out',str(out/'v0_local'),'--full-psd','--hash-ready']),('v1',[sys.executable,str(f/'v1_verdict_audit.py'),'--out',str(out/'v1_local')]),('v2',[sys.executable,str(f/'v2_pf_reference_audit.py'),'--out',str(out/'v2_github')]),('v3_smoke',[sys.executable,str(f/'v3_second_order.py'),'--out',str(out/'v3_smoke'),'--world','gauss_level','--routes','R2','--levels','0','2','--seeds','8000:8002','--steps','80']),('v4_pilot',[sys.executable,str(f/'v4_calibration.py'),'--out',str(out/'v4_pilot'),'--world','gauss_level','--routes','R2','--levels','2','--seeds','8000:8004'])]
protected=list((root/'research/DR_EKF_DIAGNOSIS_20261013').glob('*.py'))+list((root/'research/DR_EKF_DIAGNOSIS_20261013').glob('D6*'))+list((root/'research/DR_EKF_DIAGNOSIS_20261013/out').glob('*'))
def hashes(): return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
before=hashes(); records=[]
for name,cmd in stages:
 print('START',name,flush=True);start=time.time()
 with (out/(name+'.log')).open('x',encoding='utf-8') as log:
  run=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
 records.append(dict(stage=name,command=cmd,exit_code=run.returncode,elapsed_s=time.time()-start,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 (out/'execution_receipt.json').write_text(json.dumps(dict(records=records,protected_hashes_before=before,protected_hashes_after=hashes(),protected_unchanged=before==hashes()),indent=2),encoding='utf-8')
 print('END',name,run.returncode,records[-1]['elapsed_s'],flush=True)
 if run.returncode:sys.exit(run.returncode)
