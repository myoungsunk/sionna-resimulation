import pathlib,subprocess,sys,json,datetime,hashlib
J=pathlib.Path('/job');O=J/'OUTPUT'
D='/routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669'
common=['--s1','/routes/source/results/DRIVE_SIM_20261007/S1','--h-dir',D+'/S2','--lut','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy','--lut-meta','/legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json','--bank-freqs','/job/freqs_hz.npy','--cases','R2A','--mounts','0','--drifts','0','1','2','--seeds','50','--seed0','0','--nproc','4','--trace-seeds','0','1','--out',str(O)]
steps=[('q2',['run']+common+['--arms','R1_bias','R2_ar0','R3_ar1','R4_iid','R5_realdem','R6_distbin','R7_tapbin','R8_real','--label','q2']),('joint',['run']+common+['--arms','J1_ar_indep','J2_ar_corr','J3_joint_block','--label','joint']),('report',['report','--csv']+[str(O/x) for x in ['A0_ARMS.csv','ARMS_controls.csv','ARMS_q1.csv','ARMS_q2.csv','ARMS_joint.csv']]+['--unit-stats']+[str(O/x) for x in ['A0_UNIT_STATS.csv','ARM_UNIT_STATS_controls.csv','ARM_UNIT_STATS_q1.csv','ARM_UNIT_STATS_q2.csv','ARM_UNIT_STATS_joint.csv']]+['--a0-check',str(O/'A0_CHECK.json'),'--out',str(O/'ARMS_REPORT_ALL.json')])]
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
