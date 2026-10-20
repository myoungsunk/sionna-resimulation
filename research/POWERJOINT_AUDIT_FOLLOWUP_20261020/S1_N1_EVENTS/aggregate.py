"""Aggregate every locked S1 event without dropping errors or missing arms."""
from pathlib import Path
import argparse,json,math
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text());roster=pd.read_csv(HERE/'EVENT_LIST.csv')
 tables=[];run_errors=[];baseline=[];manifests=[]
 for route in lock['routes']:
  dirs=[q.parent for q in a.runs.rglob('INTERVENTIONS.csv') if q.parent.name==route]
  if len(dirs)!=1:run_errors.append(dict(route=route,error='MISSING_OR_DUPLICATE_ROUTE_OUTPUT'));continue
  d=dirs[0];tables.append(pd.read_csv(d/'INTERVENTIONS.csv'));baseline.append(pd.read_csv(d/'BASELINE_CHECKS.csv'))
  er=json.loads((d/'ERRORS.json').read_text());run_errors.extend(er['execution_errors']);manifests.append(json.loads((d/'MANIFEST.json').read_text()))
 merged=pd.concat(tables,ignore_index=True) if tables else pd.DataFrame(columns=['event','bias','arm','status'])
 if merged.duplicated(['event','bias','arm']).any():raise ValueError('DUPLICATE_EVENT_BIAS_ARM')
 index={(r['event'],r['bias'],r['arm']):r for r in merged.to_dict('records')}
 event_tables={};missing=[]
 for bias in lock['biases']:
  output=[]
  for event in roster.to_dict('records'):
   row=dict(event,bias=bias,role='UNKNOWN_EXECUTION_FAILURE',g_deg=None,scene='office' if event['case'].startswith('O') else 'corridor')
   base=index.get((event['event'],bias,'POWER1'));skip=index.get((event['event'],bias,'SKIP'))
   ready=lambda r:r is not None and r.get('status')=='TECHNICAL_PASS'
   if ready(base) and ready(skip):
    g=float(base['heading_rmse_deg']-skip['heading_rmse_deg']);row['g_deg']=g
    row['role']='HARMFUL' if g>=.2 else 'BENEFICIAL' if g<=-.2 else 'NEUTRAL'
    row['POWER1_heading_rmse_deg']=base['heading_rmse_deg'];row['SKIP_heading_rmse_deg']=skip['heading_rmse_deg']
   for arm in lock['arms']:
    r=index.get((event['event'],bias,arm));row[arm+'_status']=r.get('status') if r else 'MISSING_EXECUTION'
    if r is None:missing.append(dict(event=event['event'],bias=bias,arm=arm))
    row['r_'+arm]=None;row['h_'+arm]=None
    if ready(r) and row['g_deg'] is not None:
     if row['role']=='HARMFUL':row['r_'+arm]=float((base['heading_rmse_deg']-r['heading_rmse_deg'])/row['g_deg'])
     elif row['role']=='BENEFICIAL':row['h_'+arm]=float((r['heading_rmse_deg']-base['heading_rmse_deg'])/(-row['g_deg']))
   d2=row['r_D2'];d7=row['r_D7'];row['D7_D2_exploratory_pattern']='NOT_APPLICABLE'
   if row['role']=='HARMFUL' and d2 is not None and d7 is not None:
    row['D7_D2_exploratory_pattern']=('관측 교체만으로 회복' if d2>=.5 and d7>=.5 else
                                   '필터 구조 변경이 필요 - 이 비교의 제한된 패턴' if d2>=.5 and d7<.2 else 'OTHER')
   output.append(row)
  event_tables[bias]=pd.DataFrame(output)
  event_tables[bias].to_csv(a.out/('EVENT_TABLE.csv' if bias=='B0' else 'EVENT_TABLE_L2.csv'),index=False)
 decisions={}
 for scene in ['overall','corridor','office']:
  t=event_tables['B0'];t=t if scene=='overall' else t[t.scene==scene]
  h=t[t.role=='HARMFUL'];b=t[t.role=='BENEFICIAL'];u=t[t.role=='UNKNOWN_EXECUTION_FAILURE']
  hn=int((h.r_D2>=.5).sum());bn=int((b.h_D2<=.5).sum());hd=len(h);bd=len(b)
  failures=int(((t.D2_status!='TECHNICAL_PASS')|(t.POWER1_status!='TECHNICAL_PASS')|(t.SKIP_status!='TECHNICAL_PASS')).sum())
  if len(u) or failures or run_errors:verdict='NOT_ESTABLISHED'
  elif hd==0 or bd==0:verdict='NOT_ESTABLISHED'
  elif 3*hn>=2*hd and 3*bn>=2*bd:verdict='SUPPORTED_BUT_LIMITED'
  elif 3*hn<=hd:verdict='FALSIFIED_FOR_TESTED'
  else:verdict='NOT_ESTABLISHED'
  decisions[scene]=dict(scientific=verdict,harmful_numerator=hn,harmful_denominator=hd,
      beneficial_numerator=bn,beneficial_denominator=bd,neutral_count=int((t.role=='NEUTRAL').sum()),
      unknown_role_count=len(u),core_event_failures=failures,total_locked_events=len(t),
      D7_evaluable_harmful=int((h.D7_status=='TECHNICAL_PASS').sum()),
      observation_replacement_recovered=int((h.D7_D2_exploratory_pattern=='관측 교체만으로 회복').sum()),
      D7_low_D2_high_pattern=int(h.D7_D2_exploratory_pattern.str.startswith('필터 구조').sum()))
 # The only preexisting feature population is SPEC12. Do not extend definitions.
 fpath=HERE.parents[1]/'POWERJOINT_AUDIT_RERUN_20261020/T7_POLICY/ONLINE_FEATURES.csv'
 features=pd.read_csv(fpath);mapping=[];correlation=[];t=event_tables['B0']
 for _,f in features.iterrows():
  cid=f"{f.route}_{f.anchor}_M45_FULL"
  candidates=t[(t['case']==cid)&(t.axis==str(f.coordinate)[0])&(t.low==f.low)&(t.high==f.high)&(t.visit==f.visit)]
  m=dict(case=cid,axis=str(f.coordinate)[0],low=float(f.low),high=float(f.high),visit=int(f.visit),feature_source_rows=int(f.n))
  if len(candidates)==1:
   r=candidates.iloc[0]
   equal=(r.n==f.n and r.t_start_s==f.t_start_s and r.t_end_s==f.t_end_s)
   m.update(event=r.event,mapping_status='EXACT_RF_MEMBERSHIP' if equal else 'RF_MEMBERSHIP_MISMATCH',role=r.role,r_D2=r.r_D2)
   if equal:
    for k in features.columns:
     if k.endswith(('_mean','_median')):m[k]=float(f[k])
  else:m.update(event=None,mapping_status='NOT_IN_REVISED_INCLUDED_ROSTER',role=None,r_D2=None)
  mapping.append(m)
 fm=pd.DataFrame(mapping);fm.to_csv(a.out/'ONLINE_FEATURE_MAPPING.csv',index=False)
 for k in features.columns:
  if not k.endswith(('_mean','_median')):continue
  if k not in fm:continue
  q=fm[(fm.mapping_status=='EXACT_RF_MEMBERSHIP')&(fm.role=='HARMFUL')][[k,'r_D2']].dropna()
  coefficient=None
  if len(q)>=3 and q[k].nunique()>1 and q.r_D2.nunique()>1:
   coefficient=float(q[k].rank(method='average').corr(q.r_D2.rank(method='average')))
  correlation.append(dict(feature=k,n_harmful_exact_mapped=len(q),spearman_rho=coefficient,p_value_reported=False,
                          scope='SPEC12 subset; B0 harmful only; no feature extension'))
 pd.DataFrame(correlation).to_csv(a.out/'ONLINE_FEATURE_SPEARMAN.csv',index=False)
 merged.to_csv(a.out/'INTERVENTIONS.csv',index=False)
 if baseline:pd.concat(baseline,ignore_index=True).to_csv(a.out/'BASELINE_CHECKS.csv',index=False)
 dump(a.out/'ERRORS.json',dict(execution_errors=run_errors,missing_event_arms=missing))
 dump(a.out/'DECISION.json',dict(task='S1_N1_EVENTS',technical='TECHNICAL_PASS_CORE' if not run_errors and not missing else 'INCOMPLETE_OR_ERROR',
      scientific=decisions['overall']['scientific'],primary_bias='B0',supplemental_bias='L2',groups=decisions,
      event_count=len(roster),feature_source_rows=len(features),feature_exact_matched=int((fm.mapping_status=='EXACT_RF_MEMBERSHIP').sum()),
      D7_unavailable_count=int((merged.arm.eq('D7')&merged.status.ne('TECHNICAL_PASS')).sum()),
      limitation='Shared corridor and one office scene; all interventions ORACLE_DIAGNOSTIC. D7 pattern is not causal necessity.',
      route_execution_manifests=manifests))
 print(json.dumps({'event_count':len(roster),'groups':decisions,'execution_errors':len(run_errors),'missing_event_arms':len(missing)},ensure_ascii=False))
if __name__=='__main__':main()
