from pathlib import Path
import subprocess,sys,json,datetime
J=Path('/job');cmd=[sys.executable,str(J/'extra_metadata.py')];start=datetime.datetime.now(datetime.timezone.utc).isoformat()
with (J/'extra_metadata.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
(J/'EXTRA_EXECUTION.json').write_text(json.dumps({'command':cmd,'started':start,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':r.returncode},indent=2));sys.exit(r.returncode)
