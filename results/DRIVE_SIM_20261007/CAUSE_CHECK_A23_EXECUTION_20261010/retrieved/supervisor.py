import pathlib,subprocess,sys,json,datetime,hashlib
J=pathlib.Path('/job');O=J/'OUTPUT'
D='/routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669'
common=['--s1','/routes/source/results/DRIVE_SIM_20261007/S1','--h-dir',D+'/S2','--lut','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy','--lut-meta','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json','--bank-freqs','/job/freqs_hz.npy','--cases','R2A','--mounts','0','--drifts','0','1','2','--seeds','50','--seed0','0','--nproc','4','--trace-seeds','0','1','--out',str(O)]
steps=[('preflight',['preflight']),('residuals',['residuals']+common),('check-a0',['check-a0']+common+['--s6-csv',D+'/S6_routes/results_R2_aA_m0.csv']),('controls',['run']+common+['--arms','tier0','--label','controls']),('q1',['run']+common+['--arms','S1_bias','S2_ar0','S3_ar1','S4_iid','S5_iid0','S6_realdem','S7_block','S8_real','--label','q1']),('report',['report','--csv',str(O/'A0_ARMS.csv'),str(O/'ARMS_controls.csv'),str(O/'ARMS_q1.csv'),'--unit-stats',str(O/'A0_UNIT_STATS.csv'),str(O/'ARM_UNIT_STATS_controls.csv'),str(O/'ARM_UNIT_STATS_q1.csv'),'--a0-check',str(O/'A0_CHECK.json'),'--out',str(O/'ARMS_REPORT.json')])]
records=[]
for phase,args in steps:
 cmd=[sys.executable,'/job/launch.py']+args
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (J/'STATUS.json').write_text(json.dumps(dict(state='running',phase=phase,completed=records),indent=2))
 with (J/(phase+'.log')).open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd='/job/source')
 records.append(dict(phase=phase,command=cmd,started=start,finished=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=r.returncode))
 (J/'EXECUTION.json').write_text(json.dumps(records,indent=2))
 print(phase,r.returncode,flush=True)
 if r.returncode:
  (J/'STATUS.json').write_text(json.dumps(dict(state='stopped',phase=phase,exit_code=r.returncode,completed=records),indent=2))
  sys.exit(r.returncode)
(J/'STATUS.json').write_text(json.dumps(dict(state='completed',completed=records),indent=2))
