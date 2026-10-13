import pathlib,subprocess,sys,time,json,datetime
root=pathlib.Path(__file__).parent;out=root/'audit_evidence'
cmd=[sys.executable,str(root/'research/DR_EKF_DIAGNOSIS_20261013/followup_v2/v3_second_order.py'),'--out',str(out/'v3_fullroute_pilot'),'--world','gauss_level','--routes','R2','--levels','2','--seeds','8000:8004','--steps','0']
t=time.time()
with (out/'v3_fullroute_pilot.log').open('x') as log:r=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
(out/'v3_fullroute_receipt.json').write_text(json.dumps(dict(command=cmd,exit_code=r.returncode,elapsed_s=time.time()-t,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2))
sys.exit(r.returncode)
