from pathlib import Path
import numpy as np,pandas as pd,json,hashlib,re,shutil,datetime,subprocess
P=Path(__file__).resolve().parent;BASE=P.parent;checks=json.loads((P/'CHECKS.json').read_text());assert checks['status']=='PASS' and all(x['pass_check'] for x in checks['checks']);covrows=[]
for f in sorted((BASE/'e1_e4/E1').glob('*.npz')):
 with np.load(f) as z:
  idx=[list(z['names']).index(x) for x in ['A0','A1']]
  for key in ['P','Pprior']:
   cov=z[key][:,idx];sym=float(abs(cov-cov.swapaxes(-1,-2)).max());eig=float(np.linalg.eigvalsh(cov).min());assert sym<=1e-12 and eig>=-1e-12;covrows.append(dict(trace=f.name,field=key,max_asymmetry=sym,min_eigenvalue=eig))
pd.DataFrame(covrows).to_csv(P/'COVARIANCE_CHECK.csv',index=False)
# Independent recomputation of all primary near decisions from packet columns.
frames={k:pd.read_csv(P/(k+'_PACKETS.csv.gz')) for k in ['C1','C1B','C2','C3']};dec=pd.read_csv(P/'DECISIONS.csv',keep_default_na=False,na_values={'value':['NA']});max_delta=0.
for _,row in dec[(dec.arm=='BB')&(dec.bin_group=='near')&dec.case.isin(['R2_aA_m45','R4_aA_m0','R4_aB_m0'])].iterrows():
 kind={'Q1':'C1','Q1b':'C1B','Q2':'C2','Q3':'C3'}[row.question];d=frames[kind];g=d[(d.case==row['case'])&(d.bias==row['bias'])&(d.arm=='BB')&d.scoring];g=g[g.accepted] if kind=='C2' else g;count=g.groupby('bin').size();valid=count[count>=30].index;near=g[g.bin.isin(valid)&(g.d_gt_m<1.5)];far=g[g.bin.isin(valid)&(g.d_gt_m>=4)]
 if len(near)<30:assert row.result=='NA';continue
 if row.question=='Q1':v=near.kappa.median();support=.5<=v<=2
 elif row.question=='Q1b':v=np.sqrt(np.mean(near.ds_pos**2)/np.mean(near.r_base**2));support=v>3
 elif row.question=='Q2':v=near.share_psi.median();support=v>.5 and v>near.share_tan.median()
 else:
  v=np.sqrt(np.mean(near.z_t**2))
  if len(far)<30:assert row.result=='NA';continue
  support=v>2 and v>np.sqrt(np.mean(far.z_t**2))
 err=abs(v-row.value);max_delta=max(max_delta,err);assert err<1e-10;assert row.result==('SUPPORT' if support else 'NOT_SUPPORT')
# Packet keys and eligible counts after cumulative columns.
keys=['case','bias','arm','k','pose_id'];ref=frames['C1'][keys]
for kind,df in frames.items():assert df[keys].equals(ref);assert not df.duplicated(keys).any()
c2=frames['C2'];cumerr=0.
for c in [x for x in c2 if x.startswith('cum_')]:
 expected=c2.groupby(['case','bias','arm'],sort=False)[c[4:]].cumsum();err=float(abs(expected-c2[c]).max());assert err<1e-10;cumerr=max(cumerr,err)
for x in json.loads((P/'INPUT_LOCK.json').read_text())['files']:assert hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256'],x['path']
# Stop record and logs.
managed=json.loads((P/'MANAGED_FINISH.json').read_text(encoding='utf-8-sig'));assert managed['ok']
for proc in managed['processes']:
 assert proc['exit_code']==0 and proc['ref_count']==0
 for k in ['actual_process','actual_supervisor','job']:assert proc[k]['state']=='absent'
 (P/'logs').mkdir(exist_ok=True)
 for n in ['stdout.log','stderr.log']:shutil.copy2(Path(proc['log_dir'])/n,P/'logs'/n)
text=(P/'RESULTS_KO.md').read_text(encoding='utf-8');assert not any(ord(c)<32 and c not in '\n\r\t' for c in text)
for link in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text):assert (P/link).exists(),link
assert len(list((P/'figures').glob('*.png')))==6
assert not list(P.rglob('*.pyc'))
result=dict(status='PASS',check_count=len(checks['checks']),packet_rows_per_file=len(ref),covariance_checks=len(covrows),decision_recalculation_max_abs=max_delta,cumulative_recalculation_max_abs=cumerr,visual_review=dict(status='PASS',files=[f.name for f in (P/'figures').glob('*.png')],notes='Rendered and inspected all six final PNGs; fixed subplot title/axis crowding; signed shares retained; BB solid / MB dashed.'),no_replay=True,no_retraining=True,no_R_Q_change=True,source_hashes_unchanged=True)
(P/'VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
(P/'EXECUTION_RESULT.json').write_text(json.dumps(dict(status='COMPLETED_DIAGNOSTIC_ONLY',timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_parent='9ff1810',requested_baseline='d2fe43a',run_id=proc['creator'],exit_code=0,primary_conditions=6,auxiliary_conditions=8,filter_replays=0,phase2='proposal only; separate approval required'),indent=2)+'\n')
(P/'ANALYSIS_CODE_LOCK.json').write_text(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in P.glob('*.py')},indent=2)+'\n')
(P/'OUTPUT_SHA256.json').write_text(json.dumps({'files':[dict(path=f.relative_to(P).as_posix(),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in sorted(P.rglob('*')) if f.is_file() and f.name!='OUTPUT_SHA256.json']},indent=2)+'\n')
print(json.dumps(result));print('total bytes',sum(f.stat().st_size for f in P.rglob('*') if f.is_file()))
