from pathlib import Path
import json,csv,hashlib,shutil,datetime,re
p=Path(r'D:\SLAM_bot\DS_COMPONENT_AZIMUTH_20261027')
def read(n): return json.loads((p/n).read_text(encoding='utf-8-sig'))
def sha(f): return hashlib.sha256(f.read_bytes()).hexdigest()
def write(n,d): (p/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rows(n):
 with (p/n).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
locked=read('INPUT_LOCK.json')['files']
for x in locked: assert sha(Path(x['path']))==x['sha256'],x['path']
for f,h in read('B_CODE_LOCK.json').items(): assert sha(Path(f))==h,f
checks={}
for n in ['B_CHECKS.json','TRANSFER_CHECKS.json','B_MOVEMENT_CHECKS.json']:
 d=read(n); assert all(x['pass_check'] for x in d),n; checks[n]=len(d)
for n in ['B_COMPONENT_GATE.json','B_GATE.json','B_ANALYSIS_GATE.json','TRANSFER_PROVIDER_GATE.json','TRANSFER_GATE.json']: assert read(n)['status']=='PASS',n
counts={'B_SCORES.csv':154,'B_ALL_ARMS_DECOMPOSITION.csv':210,'B_POSITION_MOVEMENT.csv':210,'TRANSFER_SCORES.csv':24,'TRANSFER_SIX_CELLS.csv':36,'TRANSFER_RATIOS.csv':6,'PRIMARY_CLOSURE.csv':6}
for n,count in counts.items(): assert len(rows(n))==count,n
cells=rows('TRANSFER_SIX_CELLS.csv')
for x in rows('TRANSFER_RATIOS.csv'):
 def val(a,s): return float(next(y for y in cells if y['case']==x['case'] and y['bias']==x['bias'] and int(y['range_alpha'])==a and y['azimuth_source']==s)['heading_bias_deg'])
 forward=val(0,'MB')-val(0,'BB');backward=val(1,'MB')-val(1,'BB')
 for label,g in [('E1',float(x['E1_MB'])-float(x['E1_BB'])),('control',val(1,'MB')-val(0,'BB'))]:
  assert abs(g-float(x['G_'+label]))<1e-10
  for direction,numerator in [('forward',forward),('backward',backward)]:
   ratio=numerator/g; assert abs(ratio-float(x[direction+'_ratio_'+label]))<1e-10; assert ratio>=.7
 assert x['denominator_disagreement']=='False'
for n in ['B_MANAGED_FINISH.json','TRANSFER_MANAGED_FINISH.json']:
 d=read(n); assert d['ok']
 for proc in d['processes']:
  assert proc['exit_code']==0 and proc['ref_count']==0
  for key in ['actual_process','actual_supervisor','job']: assert proc[key]['state']=='absent'
  dest=p/'logs'/proc['id'];dest.mkdir(parents=True,exist_ok=True)
  for log in ['stdout.log','stderr.log']: shutil.copy2(Path(proc['log_dir'])/log,dest/log)
assert len(list(p.glob('B_*/*.npz')))==42
assert len(list((p/'TRANSFER').glob('*.npz')))==6
assert not list(p.rglob('*.pyc'))
report=(p/'RESULTS_KO.md').read_text(encoding='utf-8-sig')
assert not any(ord(c)<32 and c not in '\n\r\t' for c in report)
for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',report):
 if not ':' in link and not link.startswith('#'): assert (p/link.split('#')[0]).exists(),link
write('REPORT_VALIDATION.json',{'status':'PASS','locked_files_verified':len(locked),'checks':checks,'row_counts':counts,'independent_transplant_ratio_recalculation':'PASS','plots_visually_reviewed':3,'primary_conditions':6,'paired_bias_sets_not_independent':True})
write('EXECUTION_RESULT.json',{'status':'PRIMARY_SIX_VERIFICATION_COMPLETED','timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'B':'PASS','azimuth_transfer':'PASS','primary_sufficiency_both_directions':6,'scientific_scope':'Frozen prior azimuth intervention; route-specific component results; no generalization to secondary cases.','managed_jobs':'exit0, released, processes absent','source_commit':read('INPUT_LOCK.json')['source_commit']})
write('OUTPUT_SHA256.json',{'files':[{'path':str(f.relative_to(p)).replace('\\','/'),'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(p.rglob('*')) if f.is_file() and f.name!='OUTPUT_SHA256.json']})
print('PASS',checks,counts)
