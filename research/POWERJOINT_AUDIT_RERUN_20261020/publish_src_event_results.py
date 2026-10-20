"""Publish the separate, locked source-tap F1 replay without changing B_OLD."""
from pathlib import Path
import json,subprocess,sys,hashlib,shutil
import pandas as pd
B=Path(__file__).resolve().parent;T=B/'T4_F1_EVENT'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ds=[T/'src_execution_r01'/mode/'t4_src' for mode in ['old','new']];out=T/'SRC_TAP';out.mkdir(exist_ok=True)
 subprocess.run([sys.executable,str(T/'run_events.py'),'--range-model','SRC_TAP','--aggregate',*[str(d/'INTERVENTIONS.csv') for d in ds],'--out',str(out)],check=True)
 for n in ['BASELINE_CHECKS','FIRST_HARMFUL_UPDATE','DIVERGENCE','GROWTH','EVENT_RECEIPT']:
  pd.concat([pd.read_csv(d/(n+'.csv')) for d in ds],ignore_index=True).to_csv(out/(n+'.csv'),index=False)
 errors=[e for d in ds for e in json.loads((d/'ERRORS.json').read_text())]
 (out/'ERRORS.json').write_text(json.dumps(errors,indent=2))
 if any(e.get('arm')!='D4' or 'NONSPD' not in e['error'] for e in errors):raise ValueError('UNRESOLVED_NON_D4_ERROR')
 for d in ds:
  for p in d.glob('PACKET_LOG_*.csv'):shutil.copy2(p,out/p.name)
 m=json.loads((out/'MANIFEST.json').read_text());m.update(technical='COMPLETE_WITH_PRESERVED_D4_NONSPD' if errors else 'TECHNICAL_PASS',actions_run_id=39361448922,artifacts=[json.loads((d.parent/'ACTIONS_ARTIFACT.json').read_text()) for d in ds],errors=len(errors),all_non_D4_required_arms_complete=True)
 (out/'MANIFEST.json').write_text(json.dumps(m,indent=2))
 dec=json.loads((out/'DECISION.json').read_text())
 with (out/'RESULTS_KO.md').open('a',encoding='utf8') as f:
  f.write('\nT6 Source tap 재학습 버전. 10개 이벤트에서 모든 비D4 arm을 완료했고 D4 NONSPD '+str(len(errors))+'건을 보존했다. B_OLD 판정과 섞지 않는다.\n\n| 이벤트 | 역할 | 정본 skip 개선량 ° | 부호 변경 | 기준 충족 개입 |\n|---|---|---|---|---|\n')
  for r in dec['events']:f.write('| '+r['event']+' | '+r['role']+' | '+str(r['skip_gain_deg'])+' | '+str(r['sign_changed'])+' | '+','.join(r['qualifying_safe_diagnostics'])+' |\n')
 with (T/'RESULTS_KO.md').open('a',encoding='utf8') as f:f.write('\nSRC_TAP 후속판: '+dec['scientific']+' (run39361448922). 전체 별도 표는 SRC_TAP/에 있다.\n')
 print(json.dumps(dec,ensure_ascii=False))
if __name__=='__main__':main()
