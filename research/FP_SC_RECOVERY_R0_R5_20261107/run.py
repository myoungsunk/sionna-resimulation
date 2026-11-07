import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import csv,json,gzip,io,sys,hashlib,datetime,urllib.request,math,collections,traceback,html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'RUN_002';CACHE=ROOT/'inputs'
OLD=ROOT.parent/'vab_pm_check/inputs'
REF='fca24720524068badeab79b78098a244cebc62b5';STEP=299792458/(1028*1950000)
HASH={};START=datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(b):return hashlib.sha256(b).hexdigest()
def get(path,expected=None):
 p=CACHE/(hashlib.sha256(path.encode()).hexdigest()[:20]+'_'+Path(path).name)
 if p.exists():b=p.read_bytes()
 elif (OLD/path).exists():b=(OLD/path).read_bytes()
 else:
  url='https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/'+REF+'/'+path
  b=urllib.request.urlopen(url,timeout=90).read()
  if b.startswith(b'version https://git-lfs.github.com/spec/v1'):
   pointer=b.decode();oid=next(x[11:] for x in pointer.splitlines() if x.startswith('oid sha256:'))
   b=urllib.request.urlopen('https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/'+REF+'/'+path,timeout=120).read()
   assert sha(b)==oid,'LFS_PAYLOAD_HASH'
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 if expected:assert sha(b)==expected,'HASH:'+path
 HASH[path]=dict(sha256=sha(b),bytes=len(b));print('INPUT',path,len(b),flush=True);return b
def js(path):return json.loads(get(path))
def write(name,obj):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def table(name,rows):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['NO_ROWS']);w.writeheader()
  for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
def rfscore(c,pool):
 return max([min(1.,(s['prominence'] if s['support_kind']=='BILATERAL' else s['left_rise'])/pool['raw']['peak'])*min(1.,s['tap_amplitude']/s['peak_amplitude']) for s in c['support_records']],default=0.)
def draw(row,cir,pool,cr,tag):
 case=row['case'];k=row['k'];name=f'{case}_k{k:04d}_{tag}';a=np.abs(cir);a/=a.max()
 fig,axes=plt.subplots(2,1,figsize=(13,8),gridspec_kw={'height_ratios':[1,2]},layout='constrained')
 lo=max(0,min(row['B'],row['reference'],*row['P_grid'])-8);hi=max(row['B'],row['reference'],*row['P_grid'])+12
 for ax in axes:
  ax.plot(a[:,0],label='RX0 amplitude',color='#1565c0');ax.plot(a[:,1],label='RX1 amplitude',color='#ef6c00')
  for rx,color in [(0,'#1565c0'),(1,'#ef6c00')]:
   ax.axhline(.3*a[:,rx].max(),color=color,ls=':',lw=.8,label=f'RX{rx} peak x 0.3')
   ax.axvline(row[f'edge{rx}'],color=color,ls='--',lw=1,label=f'RX{rx} edge={row[f"edge{rx}"]}')
  ax.axvspan((row['P_center_m']-.075)/STEP,(row['P_center_m']+.075)/STEP,color='green',alpha=.13,label='Fixed P interval')
  ax.axvline(row['B'],color='black',lw=2,label=f'B={row["B"]}')
  ax.axvline(row['reference'],color='#c2185b',lw=2,ls='--',label=f'Reference={row["reference"]} (evaluation only)')
  for valid,color,marker in [(True,'#388e3c','|'),(False,'red','x')]:
   taps=[c['tap'] for c in cr if c['eligible']==valid]
   ax.scatter(taps,[-.035 if valid else -.075]*len(taps),marker=marker,color=color,s=60,label='Eligible RF taps' if valid else 'Excluded generated taps')
  ax.set_ylim(-.1,1.07);ax.set_xlabel('CIR tap');ax.set_ylabel('Amplitude / common peak');ax.grid(alpha=.2)
 axes[0].set_xlim(0,1027);axes[0].set_title('Full CIR: every generated candidate marked')
 axes[1].set_xlim(lo,hi);axes[1].set_xticks(range(lo,hi+1));axes[1].tick_params(axis='x',labelsize=8)
 axes[1].legend(fontsize=8,ncol=3,loc='upper right')
 exclusions=collections.Counter(c['reason'] for c in cr if not c['eligible'])
 fig.suptitle(f'{case} | k={k}, t={row["t"]:.1f}s | {row["cohort"]} | {tag}\nB-ref={row["B"]-row["reference"]:+d}; RF&P={row["intersection"]}; excluded={dict(exclusions) or "none"}',fontsize=12)
 fig.savefig(OUT/'figures'/f'{name}.png',dpi=150);plt.close(fig)
 np.savez_compressed(OUT/'figures'/f'{name}_CIR.npz',cir=cir)
 write('figures/'+name+'_POOL.json',pool)
 return dict(name=name,case=case,k=k,t=row['t'],category=tag,png='figures/'+name+'.png',pool='figures/'+name+'_POOL.json',cir='figures/'+name+'_CIR.npz')
def main():
 OUT.mkdir(exist_ok=False);(OUT/'figures').mkdir();
 contract=dict(question_id='B-PONLY-RECOVERY-R0R1-20261107',role='IMPLEMENTER_SELF_CHECK',source_commit=REF,started_utc=START,scope='R0 baseline reproduction and R1 candidate availability + evidence only; no choice/replacement/EKF',policy=dict(B='valid earliest per-port own-peak30 crossing',P_radius_m=.075,M=False),figures='All FP11; first missing TP per reason if present; first two-P-tap TP; first early and late TP. No cherry-picked threshold fitting.',governance={n:sha((Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n).read_bytes()) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md']})
 write('CONTRACT.json',contract)
 # Namespace package imports avoid executing unrelated runtime initializers.
 sys.path.insert(0,str(ROOT/'sources/src'))
 from qclean_uwb.drivesim import observation as obs
 from qclean_uwb.fp_sc.candidates import CandidateConfig
 from qclean_uwb.fp_sc.candidate_revision import generate_revision
 srcpaths=['src/qclean_uwb/drivesim/observation.py','src/qclean_uwb/fp_sc/candidates.py','src/qclean_uwb/fp_sc/candidate_revision.py']
 for p in srcpaths:HASH[p]={'sha256':sha((ROOT/'sources'/p).read_bytes())}
 saved=list(csv.DictReader(io.StringIO(get('research/FP_SC_B_PONLY_075_20261106/RUN_001/ROWS.csv').decode('utf-8-sig'))));idx={(r['case'],int(r['k'])):r for r in saved};assert len(idx)==3136
 allrows=[];candrows=[];figs=[];false_details=[];pools=[];selected=set();checks=collections.Counter()
 for route,n in [('R2',979),('R4',742),('R5',1415)]:
  cid=route+'_B0_Full_10';manifest=js(f'research/FP_SC_S1_PREPARATION_20261106/FINAL_002/{cid}_S1_MANIFEST.json')
  for p in srcpaths:assert HASH[p]['sha256']==manifest['code_files'][p],'SOURCE_LOCK:'+p
  spec=manifest['case'];on=get(spec['online_npz'],manifest['input_files'][spec['online_npz']]);ev=get(spec['evaluator_npz'],manifest['input_files'][spec['evaluator_npz']])
  with np.load(io.BytesIO(on),allow_pickle=False) as f:H=f['Hrf'];t=f['t'];pose=f['pose_id']
  with np.load(io.BytesIO(ev),allow_pickle=False) as f:clean=f['clean_H'];assert np.array_equal(t,f['t']) and np.array_equal(pose,f['pose_id'])
  assert len(t)==n and H.shape==clean.shape==(n,257,2)
  cir=obs.cir_batch(H);clean_cir=obs.cir_batch(clean);refs=obs.first_path_batch(clean_cir,1950000);raws=obs.first_path_batch(cir,1950000)
  prefix=f'research/FP_SC_S1_RUN_20261106/RESULTS/{cid}/';receipt=js(prefix+'RUN_RECEIPT.json');sb=get(prefix+'ROWS.json.gz',receipt['result_sha256']);old={r['k']:r for r in json.loads(gzip.decompress(sb)) if r['mode']=='C'}
  assert len(old)==n;noise=spec['metadata']['noise_variance'];assert noise==0
  cfg=CandidateConfig(noise_var_per_bin=noise)
  for k in range(n):
   s=idx[cid,k];pool=generate_revision(cir[k],'VAB',cfg)['TWO_PORT_UNION'];a=np.abs(cir[k]);floor=max(pool['noise_amplitude_floor'],pool['numeric_amplitude_floor'])
   edges=[]
   for rx in [0,1]:
    peak=a[:,rx].max();edge=int(np.flatnonzero(a[:,rx]>=.3*peak)[0]);assert peak>=floor and a[edge,rx]>=floor;edges.append(edge)
   assert pool['usable'];B=min(edges);ref=int(refs['index'][k]);p=old[k]['p_interval'];center=(p['low']+p['high'])/2;alarm=abs(B*STEP-center)>.075+1e-12
   assert B==int(s['B']) and ref==int(s['reference']) and alarm==(s['alarm']=='True') and abs(center-float(s['P_center_m']))<1e-12 and abs(t[k]-float(s['t']))<1e-12
   assert int(raws['index'][k])==old[k]['raw_tap']==pool['raw']['tap']
   powers=a[B]**2;S=float((powers[0]-powers[1])/powers.sum());assert abs(S-float(s['B_S']))<1e-12 and abs(float(refs['s'][k])-float(s['LOS_S']))<1e-12
   checks['baseline_waveform_rows']+=1
   cohort='TP' if alarm and B!=ref else 'FP' if alarm else 'FN' if B!=ref else 'TN'
   grid=[i for i in range(1028) if abs(i*STEP-center)<=.075+1e-12]
   generated={c['tap'] for c in pool['candidates']};valid={c['tap'] for c in pool['candidates'] if pool['usable'] and c['supported'] and c['polarization_valid']};inter=sorted(valid&set(grid));byold={c['tap']:c for c in old[k]['decision']['scores']}
   assert generated==set(byold),'CANDIDATE_PARITY'
   cr=[]
   for c in pool['candidates']:
    tap=c['tap'];score=rfscore(c,pool);eligible=tap in valid
    assert eligible==byold[tap]['selection_eligible'] and abs(score-byold[tap]['support'])<1e-12
    checks['candidate_score_parity']+=1
    reason='ELIGIBLE' if eligible else 'POLARIZATION_INVALID' if not c['polarization_valid'] else 'NO_CIR_SUPPORT' if not c['supported'] else pool['status']
    kinds=sorted(set('EDGE_MINUS1' if tap==spt['edge_tap']-1 else 'ACTUAL_EDGE' if tap==spt['edge_tap'] else 'POST_EDGE' for spt in c['support_records']))
    cr.append(dict(case=cid,k=k,t=float(t[k]),cohort=cohort,tap=tap,eligible=eligible,reason=reason,in_P=tap in grid,is_B=tap==B,is_reference=tap==ref,RF_support=score,RF_cost=-math.log(max(score,1e-12)),S=c['signed_s'],ports=c['support_ports'],origin=kinds,support_records=c['support_records']))
   refc=next((c for c in cr if c['tap']==ref),None);bc=next(c for c in cr if c['tap']==B)
   ranked=sorted([c for c in cr if c['eligible']],key=lambda c:(c['RF_cost'],c['tap']));rankref=next((i+1 for i,c in enumerate(ranked) if c['tap']==ref),None)
   bestp=sorted([c for c in cr if c['eligible'] and c['in_P']],key=lambda c:(c['RF_cost'],c['tap']))
   status='NOT_GENERATED' if ref not in generated else 'GENERATED_EXCLUDED' if ref not in valid else 'OUTSIDE_P' if ref not in grid else 'AVAILABLE_RF_AND_P'
   row=dict(case=cid,k=k,t=float(t[k]),pose_id=int(pose[k]),cohort=cohort,B=B,reference=ref,error=B-ref,edge0=edges[0],edge1=edges[1],P_center_m=center,P_grid=grid,P_grid_count=len(grid),generated_count=len(generated),valid_count=len(valid),intersection=inter,intersection_count=len(inter),ref_generated=ref in generated,ref_valid=ref in valid,ref_in_P=ref in grid,ref_available=ref in inter,status=status,ref_RF_rank=rankref,ref_RF_support=None if refc is None else refc['RF_support'],B_RF_support=bc['RF_support'],best_P_tap=bestp[0]['tap'] if bestp else None,best_P_support=bestp[0]['RF_support'] if bestp else None,ref_origin=[] if refc is None else refc['origin'],B_origin=bc['origin'],B_S=S,LOS_S=float(refs['s'][k]))
   allrows.append(row)
   if alarm:
    candrows.extend(cr);pools.append(dict(case=cid,k=k,pool=pool))
    tags=[]
    if cohort=='FP':tags.append('FALSE_ALARM');false_details.append(dict(**row,alternatives=[c for c in cr if c['in_P']],B_candidate=bc,rejected_lobes=[l for l in pool['lobes'] if not l['eligible']]))
    if cohort=='TP':
     choices=[]
     if not row['ref_available']:choices.append('MISSING_'+status)
     if len(grid)==2:choices.append('TWO_P_TAPS')
     choices.append('B_TOO_EARLY' if B<ref else 'B_TOO_LATE')
     for tag in choices:
      if tag not in selected:tags.append(tag);selected.add(tag)
    if tags:figs.append(draw(row,cir[k],pool,cr,'__'.join(tags)))
   if k%250==0:print('PROGRESS',cid,k,flush=True)
  print('CASE_DONE',cid,flush=True)
  del H,clean,cir,clean_cir,on,ev
 counts=dict(collections.Counter(r['cohort'] for r in allrows));assert counts==dict(TP=678,FP=11,FN=321,TN=2126)
 assert len({(r['case'],r['k']) for r in allrows})==3136
 tp=[r for r in allrows if r['cohort']=='TP'];fp=[r for r in allrows if r['cohort']=='FP']
 assert collections.Counter(r['P_grid_count'] for r in tp)=={1:655,2:23}
 table('A_ALL_3136.csv',allrows)
 for label in ['TP','FP','FN','TN']:table('A_'+label+'.csv',[r for r in allrows if r['cohort']==label])
 table('A_ALARMS_689.csv',[r for r in allrows if r['cohort'] in ['TP','FP']]);table('B_CANDIDATES.csv',candrows);write('B_FALSE_ALARMS_11.json',false_details)
 with gzip.open(OUT/'B_ALARM_POOLS.json.gz','wt',encoding='utf-8') as f:json.dump(pools,f,ensure_ascii=False)
 summary=dict(contract=contract,cohorts=counts,checks=dict(checks),TP_funnel=dict(total=len(tp),generated=sum(r['ref_generated'] for r in tp),valid=sum(r['ref_valid'] for r in tp),RF_and_P=sum(r['ref_available'] for r in tp)),TP_status=dict(collections.Counter(r['status'] for r in tp)),TP_grid={str(c):dict(n=len(q),available=sum(r['ref_available'] for r in q),intersection_counts=dict(collections.Counter(r['intersection_count'] for r in q))) for c in [1,2] for q in [[r for r in tp if r['P_grid_count']==c]]},TP_RF_rank=dict(reference_top=sum(r['ref_RF_rank']==1 for r in tp),reference_beats_B=sum(r['ref_RF_support'] is not None and r['ref_RF_support']>r['B_RF_support']+1e-12 for r in tp),reference_ties_B=sum(r['ref_RF_support'] is not None and abs(r['ref_RF_support']-r['B_RF_support'])<=1e-12 for r in tp)),FP=dict(n=len(fp),P_intersection_counts=dict(collections.Counter(r['intersection_count'] for r in fp)),B_beats_best_P=sum(r['best_P_support'] is not None and r['B_RF_support']>r['best_P_support']+1e-12 for r in fp),B_ties_best_P=sum(r['best_P_support'] is not None and abs(r['B_RF_support']-r['best_P_support'])<=1e-12 for r in fp),details=fp),figures=figs,source_hashes=HASH,script_sha256=sha(Path(__file__).read_bytes()),ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),limitations=['Candidate upper bound only; no recovery selection executed.','All data exposed, no independent validation.','RF score is uncalibrated; ranking diagnostic only.'])
 write('SUMMARY.json',summary);write('FIGURE_INDEX.json',figs)
 print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k in ['cohorts','checks','TP_funnel','TP_status','TP_grid','TP_RF_rank','FP']},ensure_ascii=False),flush=True)
 # Standalone browsing report: all figures plus every generated candidate and exclusion.
 blocks=['<meta charset="utf-8"><title>R0 R1 CIR evidence</title><style>body{font-family:Arial;margin:30px}img{max-width:100%}table{border-collapse:collapse}td,th{padding:4px;border:1px solid #ccc}section{margin-bottom:70px}</style><h1>R0–R1 CIR evidence</h1><p>Evaluation reference is plotted only for diagnosis. No FP replacement. Every generated candidate is marked in the overview; tables include eligibility and origin.</p>']
 for f in figs:
  cs=[c for c in candrows if c['case']==f['case'] and c['k']==f['k']]
  blocks.append('<section><h2>'+html.escape(f['name'])+'</h2><img src="'+f['png']+'"><p><a href="'+f['pool']+'">Full pool, all lobes and rejection reasons</a> | <a href="'+f['cir']+'">Actual complex CIR</a></p><table><tr><th>tap</th><th>eligible / exclusion reason</th><th>in P</th><th>origin</th><th>RF support</th><th>S</th></tr>')
  for c in cs:blocks.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [c['tap'],c['reason'],c['in_P'],c['origin'],round(c['RF_support'],6),c['S']])+'</tr>')
  blocks.append('</table></section>')
 (OUT/'EVIDENCE.html').write_text('\n'.join(blocks),encoding='utf-8')
 write('ARTIFACT_HASHES.json',{str(p.relative_to(OUT)):sha(p.read_bytes()) for p in OUT.rglob('*') if p.is_file()})
if __name__=='__main__':
 try:main()
 except Exception as e:
  if OUT.exists():write('FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  raise
