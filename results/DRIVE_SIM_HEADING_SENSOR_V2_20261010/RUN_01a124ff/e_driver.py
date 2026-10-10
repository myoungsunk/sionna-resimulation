from pathlib import Path
import json,subprocess,sys,time
import simulate_e as E
J=Path('/job');rows=[]
for c in E.BYCASE:
 r=E.single((c,0,0,'E','stochastic','unknown','E_smoke'));rows.append(r)
(J/'OUTPUT/E_SMOKE_STATUS.json').write_text(json.dumps(rows,indent=2))
if any(r['error'] for r in rows):raise SystemExit(2)
with (J/'E.log').open('w') as f:
 r=subprocess.run([sys.executable,'/job/simulate_e.py','E'],stdout=f,stderr=subprocess.STDOUT)
raise SystemExit(r.returncode)
