"""Re-run the 7 published cases under the *published* library versions (numpy 2.4.6 / scipy 1.17.1 / pandas 3.0.6) to attribute the sensor-v2 replay differences."""
import sys,json,types,shutil,subprocess
from pathlib import Path
import numpy as np
S=Path(__file__).resolve().parent;G=S/'g7';JP=G/'job_pub'
if not JP.exists():shutil.copytree(G/'job',JP)
for f in (JP/'OBS').glob('*.npz'):f.unlink()
for f in (JP/'OUTPUT').glob('09_V2*'):f.unlink()
src=(G/'pub/audit.py').read_text()
for a,b in (("Path('/job')",f"Path('{JP}')"),("Path('/input/BLOCK_C')",f"Path('{G}/input/BLOCK_C')"),("Path('/lut')",f"Path('{G}/lut')"),("Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes')",f"Path('{G}/none')")):src=src.replace(a,b)
m=types.ModuleType('a');m.__dict__['__name__']='a';exec(compile(src,'audit','exec'),m.__dict__)
pubcases=json.load(open(G/'pub/CASES_7.json')) if (G/'pub/CASES_7.json').exists() else None
cases=json.loads((G/'input/BLOCK_C/CASES.json').read_text());names7=['R2_aA_m0','R2_aB_m0','R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0']
for c in cases:
    if c['case'] in names7:m.work(c)
plan=json.loads((JP/'PLAN.json').read_text());plan['cases']=names7;(JP/'PLAN.json').write_text(json.dumps(plan,indent=1))
s=(G/'job/simulate_g7.py').read_text().replace(str(G/'job'),str(JP));(JP/'simulate_g7.py').write_text(s)
print('numpy',np.__version__,'OBS regenerated for',len(names7),'cases; running replay',flush=True)
subprocess.run([sys.executable,'-I',str(JP/'simulate_g7.py'),'main'],check=True)
