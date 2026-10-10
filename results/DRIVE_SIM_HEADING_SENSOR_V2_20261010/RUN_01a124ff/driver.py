from pathlib import Path
import subprocess,json,datetime,sys,hashlib
J=Path('/job');records=[]
assert json.loads((J/'OUTPUT/PILOT_STATUS.json').read_text())['failed']==0
for phase in ['main','controls']:
 cmd=[sys.executable,'/job/simulate.py',phase];start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (J/(phase+'.log')).open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 records.append({'phase':phase,'command':cmd,'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':r.returncode,'harness_sha256':hashlib.sha256((J/'simulate.py').read_bytes()).hexdigest()})
 (J/'EXECUTION.json').write_text(json.dumps(records,indent=2))
 if r.returncode:sys.exit(r.returncode)
print('completed main and controls',flush=True)
