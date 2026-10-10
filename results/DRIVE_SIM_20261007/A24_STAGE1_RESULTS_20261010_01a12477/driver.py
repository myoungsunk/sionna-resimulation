from pathlib import Path
import subprocess,json,sys,datetime,shutil,hashlib
J=Path('/job');R=Path('/routes/source/results/DRIVE_SIM_20261007');D=R/'SNOWBALL_ROUTES_01a11669';L=Path('/legacy/source/results/DRIVE_SIM_20261007/S4');PY='/opt/rt-env/bin/python'
common=['--s1',str(R/'S1'),'--h-dir',str(D/'S2'),'--lut',str(L/'hs_lut_2deg.npy'),'--lut-meta',str(L/'hs_lut_meta.json'),'--bank-freqs',str(J/'freqs_hz.npy'),'--cases','R2A','--mounts','0','--drifts','0','1','2','--seeds','50','--seed0','0','--nproc','4','--trace-seeds','0','1','2','3','4']
records=[]
def execute(label,args):
 cmd=[PY,str(J/'launch.py')]+args;start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (J/(label+'.log')).open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=J/'source')
 rec={'label':label,'command':cmd,'started':start,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':r.returncode};records.append(rec);(J/'EXECUTION.json').write_text(json.dumps(records,indent=2));print(json.dumps(rec),flush=True);return r.returncode
if sys.argv[1]=='gate':
 gate=J/'OUTPUT_GATE';code=execute('check-a0',['check-a0']+common+['--filter-variant','F0aug','--s6-csv',str(D/'S6_routes/results_R2_aA_m0.csv'),'--out',str(gate)])
 check=json.loads((gate/'A0_CHECK.json').read_text()) if (gate/'A0_CHECK.json').exists() else {}
 (J/'STATUS.json').write_text(json.dumps({'stage':'gate','exit_code':code,'inference_valid':check.get('inference_valid',False),'main_started':False},indent=2));sys.exit(code if code else 0 if check.get('inference_valid') else 2)
assert sys.argv[1]=='main';assert json.loads((J/'OUTPUT_GATE/A0_CHECK.json').read_text())['inference_valid']
records=json.loads((J/'EXECUTION.json').read_text())
for label,variant,fitvariant in [('F2','F2','primary'),('F1','F1','primary'),('F3','F3','primary'),('F2acf','F2','acf_variant'),('F1acf','F1','acf_variant')]:
 out=J/('OUTPUT_'+label);out.mkdir(exist_ok=False)
 for name in ['A0_CHECK.json','RUN_MANIFEST_check-a0.json']:shutil.copyfile(J/'OUTPUT_GATE'/name,out/name)
 code=execute(label,['run']+common+['--filter-variant',variant,'--fit-params',str(J/'source/results/DRIVE_SIM_20261007/A24/A24_FIT_PARAMS.json'),'--fit-variant',fitvariant,'--arms','all','--label',label,'--out',str(out)])
 (J/'STATUS.json').write_text(json.dumps({'stage':label,'exit_code':code,'inference_valid':True,'completed_labels':[r['label'] for r in records if r['exit_code']==0]},indent=2))
 if code:sys.exit(code)
(J/'STATUS.json').write_text(json.dumps({'stage':'completed','exit_code':0,'inference_valid':True,'completed_labels':['F2','F1','F3','F2acf','F1acf']},indent=2))
