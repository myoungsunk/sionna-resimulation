import subprocess,sys,json,datetime,time,pathlib
j=pathlib.Path('/job');cmd=[sys.executable,str(j/'l2_probe.py')];start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
try:
 with (j/'L2.log').open('w') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=600,cwd='/job/source')
 code=r.returncode;error=None
except subprocess.TimeoutExpired:
 code=124;error='outer 600s RF budget exhausted; partial output retained'
(j/'L2_EXECUTION.json').write_text(json.dumps(dict(command=cmd,started=start,finished=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_seconds=time.monotonic()-t,exit_code=code,error=error),indent=2));sys.exit(code)
