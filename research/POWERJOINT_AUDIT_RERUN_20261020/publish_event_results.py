"""Publish already-scored event summaries; never rerun RF or change a protocol."""
from pathlib import Path
import json,subprocess,sys,shutil,hashlib
import pandas as pd
B=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def merge(paths,target):
 frames=[pd.read_csv(p) for p in paths if p.exists()]
 if frames:pd.concat(frames,ignore_index=True).to_csv(target,index=False)
def main():
 t4=B/'T4_F1_EVENT';dirs=[t4/'old_execution_r01']+[t4/'new_execution_r01'/r/'t4_new' for r in ['C01','C02','O02','O03']]
 out=t4/'final_B_OLD';out.mkdir(exist_ok=True)
 subprocess.run([sys.executable,str(t4/'run_events.py'),'--aggregate',*[str(d/'INTERVENTIONS.csv') for d in dirs],'--out',str(out)],check=True)
 for name in ['BASELINE_CHECKS','FIRST_HARMFUL_UPDATE','DIVERGENCE','GROWTH','EVENT_RECEIPT']:merge([d/(name+'.csv') for d in dirs],out/(name+'.csv'))
 errors=[e for d in dirs for e in json.loads((d/'ERRORS.json').read_text())]
 (out/'ERRORS.json').write_text(json.dumps(errors,indent=2))
 if any(e.get('arm')!='D4' or 'NONSPD' not in e.get('error','') for e in errors):raise ValueError('UNRESOLVED_NON_D4_ERROR')
 table=pd.read_csv(out/'INTERVENTIONS.csv');lock=json.loads((t4/'PROTOCOL_LOCK.json').read_text());required=['POWER1','SKIP','D1','D2','D3','D5','D6']
 for event in lock['events']:
  for arm in required:
   row=table[(table.event==event['event'])&(table.arm==arm)&(table.scope=='GLOBAL_T30')]
   if len(row)!=1 or row.iloc[0]['status']!='TECHNICAL_PASS':raise ValueError('INCOMPLETE_EVENT:'+event['event']+':'+arm)
 receipts=[]
 for d in dirs:
  p=d/'ACTIONS_ARTIFACT.json' if (d/'ACTIONS_ARTIFACT.json').exists() else d.parent/'ACTIONS_ARTIFACT.json'
  meta=json.loads(p.read_text());receipts.append(dict(id=meta['id'],sha256=meta['digest'],run_id=meta['workflow_run']['id'],receipt_sha256=sha(p)))
  for p in d.glob('PACKET_LOG_*.csv'):shutil.copy2(p,out/p.name)
 mf=json.loads((out/'MANIFEST.json').read_text());mf.update(technical='COMPLETE_WITH_PRESERVED_D4_NONSPD' if errors else 'TECHNICAL_PASS',artifacts=receipts,errors=len(errors),all_non_D4_required_arms_complete=True,publication_script_sha256=sha(Path(__file__)))
 (out/'MANIFEST.json').write_text(json.dumps(mf,indent=2))
 decision=json.loads((out/'DECISION.json').read_text())
 with (out/'RESULTS_KO.md').open('a',encoding='utf8') as f:
  f.write('\n全10イベントの baseline/skip/D1/D2/D3/D5/D6 は完了。D4 NONSPD failures='+str(len(errors))+'; no covariance repair. Technical status: '+mf['technical']+'.\n'.replace('全10イベントの baseline/skip/D1/D2/D3/D5/D6 は完了。','10개 이벤트의 baseline/skip/D1/D2/D3/D5/D6를 완료했다.'))
  f.write('\n| 이벤트 | 역할 | 정본 skip 개선량 ° | 부호 변경 | 기준 충족 개입 |\n|---|---|---|---|---|\n')
  for r in decision['events']:f.write('| '+r['event']+' | '+r['role']+' | '+str(r['skip_gain_deg'])+' | '+str(r['sign_changed'])+' | '+','.join(r['qualifying_safe_diagnostics'])+' |\n')
 for p in out.iterdir():
  if p.is_file():shutil.copy2(p,t4/p.name)
 (t4/'FINAL_READY.json').write_text(json.dumps(dict(complete_all_ten_events=True,scientific=decision['scientific'],manifest_sha256=sha(out/'MANIFEST.json'),allowed_failures='Only explicitly recorded D4 NONSPD',source_runs=[39359599833,39361156858]),indent=2))
 t5=B/'T5_INITIALIZATION';ds=[t5/'new_execution_r01'/r/'t5_new' for r in ['C03','O01']]
 subprocess.run([sys.executable,str(t5/'run_initialization.py'),'--aggregate',*[str(d/'RESULTS.csv') for d in ds],'--out',str(t5)],check=True)
 for name in ['BASELINE_CHECKS','EVENT_RECEIPT']:merge([d/(name+'.csv') for d in ds],t5/(name+'.csv'))
 m=json.loads((t5/'MANIFEST.json').read_text());m.update(actions_run_id=39361156858,artifacts=[json.loads((d.parent/'ACTIONS_ARTIFACT.json').read_text()) for d in ds]);(t5/'MANIFEST.json').write_text(json.dumps(m,indent=2))
 print(json.dumps({'T4':decision,'T5':json.loads((t5/'DECISION.json').read_text())},ensure_ascii=False))
if __name__=='__main__':main()
