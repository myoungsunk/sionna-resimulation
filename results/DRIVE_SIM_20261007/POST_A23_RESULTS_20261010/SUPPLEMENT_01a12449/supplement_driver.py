from pathlib import Path
import sys,subprocess,json,datetime,hashlib,time,traceback
J=Path('/job'); records=[]; start=time.monotonic()
try:
 for name in ['replay_supplement','block_b_supplement','los_supplement']:
  cmd=[sys.executable,str(J/(name+'.py'))]; t=datetime.datetime.now(datetime.timezone.utc).isoformat()
  (J/'STATUS.json').write_text(json.dumps({'state':'running','phase':name,'completed':records}))
  with (J/(name+'.log')).open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
  records.append({'phase':name,'command':cmd,'started':t,'finished':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':r.returncode})
  (J/'EXECUTION.json').write_text(json.dumps(records,indent=2))
  if r.returncode: raise RuntimeError(name+' failed '+str(r.returncode))
 (J/'STATUS.json').write_text(json.dumps({'state':'completed','seconds':time.monotonic()-start,'completed':records},indent=2))
except BaseException:
 (J/'STATUS.json').write_text(json.dumps({'state':'failed','completed':records,'traceback':traceback.format_exc()},indent=2)); raise
finally:
 manifest={str(p.relative_to(J)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in J.rglob('*') if p.is_file() and p.name!='OUTPUT_MANIFEST.json'}
 (J/'OUTPUT_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
