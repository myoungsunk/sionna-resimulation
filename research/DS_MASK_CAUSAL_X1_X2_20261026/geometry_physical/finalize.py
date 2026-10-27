from pathlib import Path
import json,hashlib,re,shutil,datetime
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent
def write(n,d):(R/n).write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for row in json.loads((R/'INPUT_LOCK.json').read_text())['files']:assert sha(row['path'])==row['sha256'],row['path']
for n in ['A_CODE_LOCK.json','C_CODE_LOCK.json','B_CODE_LOCK.json']:
 for p,h in json.loads((R/n).read_text()).items():assert sha(p)==h,p
for stage in ['A0','A','C_CONTROL','C']:
 assert json.loads((R/f'{stage}_GATE.json').read_text())['status']=='PASS'
 assert all(x['pass_check'] for x in json.loads((R/f'{stage}_CHECKS.json').read_text()))
a=pd.read_csv(R/'A_METRICS.csv');c=pd.read_csv(R/'C_SCORES.csv');assert len(a)==70 and len(c)==140
assert not a.duplicated(['case','bias','alpha']).any();assert not c.duplicated(['case','bias','arm']).any();assert a.wrap_count.sum()==0
maxres=0.;minsl=np.inf;valid_total=0
for f in (R/'A').glob('*.npz'):
 with np.load(f) as z:
  valid=np.isfinite(z['psi_eq']);maxres=max(maxres,float(abs(z['root_residual'][valid]).max()));minsl=min(minsl,float(abs(z['root_slope_per_rad'][valid]).min()));valid_total+=int(valid.sum())
assert maxres<=1e-9 and minsl>=1e-3
bm=pd.read_csv(R/'B_MASK_AUDIT.csv');bc=pd.read_csv(R/'B_COMPONENTS.csv');assert bm.delta_mu_max_difference_m.max()==0
assert (R/'B_FAILURE.json').exists() and not list(R.glob('B_*/*.npz'))
assert abs(bm.loc[bm.case=='R2_aA_m0','c_difference_m'].iloc[0])>1e-12
text=(R/'RESULTS_KO.md').read_text(encoding='utf-8');links=re.findall(r'\]\(([^)]+)\)',text)
assert all((R/path).exists() for path in links),links
assert not any(ord(ch)<32 and ch not in '\n\r\t' for ch in text)
resources=['b2fa4bad-fd31-447e-a5a6-ec35a72ec3d9','94dfa08c-e3a1-4bb0-a9a8-9d55c6df8a7e','084a30a0-79ae-477f-985a-bab5c002d02f','00567536-f66f-4128-a9e4-f805535169a3','8543970f-67a4-4f41-bae0-6de941411ccd']
receipts=[]
for name in ['A0_MANAGED_FINAL.json','A_MANAGED_FINISH.json','C_MANAGED_FINISH.json','B_MANAGED_FINISH.json']:
 rec=json.loads((R/name).read_text(encoding='utf-8-sig'));items=rec.get('processes',[rec.get('process',{})])
 for x in items:
  assert x['ref_count']==0 and x['actual_process']['state']=='absent' and x['actual_supervisor']['state']=='absent' and x['job']['state']=='absent'
  receipts.append(dict(id=x['id'],exit_code=x['exit_code'],termination=x['termination']))
assert {x['id'] for x in receipts}==set(resources)
for uid in resources:
 src=Path(r'C:\Users\Myoungsun Kim\.codex\managed-processes\runs')/uid;dest=R/'logs'/uid;dest.mkdir(parents=True,exist_ok=True)
 for filename in ['stdout.log','stderr.log']:
  if (src/filename).exists():shutil.copy2(src/filename,dest/filename)
write('EXECUTION_RESULT.json',dict(status='STOP_B_PAIRED_CONSTANT_GATE',completed=['A0_DOUBLE_PRIME','A','C'],B_replay_executed=False,B_stop_reason=json.loads((R/'B_FAILURE.json').read_text())['error'],inputs_preserved=True,processes=receipts))
write('REPORT_VALIDATION.json',dict(status='PASS',meaning='Report and completed-stage evidence checked; pipeline stopped at B guard.',A_rows=70,C_rows=140,root_valid_samples=valid_total,root_max_residual=maxres,root_min_abs_derivative=minsl,undefined_over_10pct_arm_conditions=int((a.undefined_fraction>.1).sum()),wrap_violations=int(a.wrap_count.sum()),figures_visually_reviewed=3,report_links=len(links),inputs_reverified=True,all_helpers_finished=True))
files=[dict(path=p.relative_to(R).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(R.rglob('*')) if p.is_file() and p.name!='OUTPUT_SHA256.json']
write('OUTPUT_SHA256.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=files))
print(json.dumps(dict(files=len(files),status='STOP_B_PAIRED_CONSTANT_GATE',A_rows=len(a),C_rows=len(c),root_max_residual=maxres,helpers_finished=len(receipts))))
