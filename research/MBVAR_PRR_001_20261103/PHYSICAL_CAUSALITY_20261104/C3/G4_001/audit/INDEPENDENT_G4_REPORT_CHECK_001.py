import pathlib,json,hashlib,csv,re,datetime
P=pathlib.Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C3/G4_001')
def read(p):return json.loads(p.read_bytes())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def table(p):return list(csv.DictReader(p.open(newline='',encoding='utf8')))
v=read(P/'audit/INDEPENDENT_G4_RESULT_001.json');assert v['decision']=='ACCEPT'
assert sha(P/'audit/INDEPENDENT_G4_VERIFIER_001.py')==v['source_sha256']=='e29ad74337e4f8bc843ef17803145bd3d0f031cc761b0dc258a9998b5cc6ccf4'
for relative,key in [('RUN_001/ARTIFACT_HASHES.json','artifact_hashes_sha256'),('RUN_001/MANIFEST.json','manifest_sha256'),('logs/analysis_001.json','host_receipt_sha256'),('logs/analysis_001_managed_finish.json','managed_receipt_sha256'),('GO_G4_001.json','go_sha256'),('INPUT_LOCK.json','input_lock_sha256')]:assert sha(P/relative)==v[key]
for n,h in v['bindings_sha256'].items():assert sha(P/n)==h
for n,h in read(P/'RUN_001/ARTIFACT_HASHES.json').items():assert sha(P/'RUN_001'/n)==h
host=read(P/'logs/independent_verify_001.json');assert host['exit_code']==0
managed=read(P/'logs/independent_verify_001_managed_finish.json')['processes'];assert len(managed)==1
proc=managed[0];assert proc['id']==host['managed_resource'] and proc['creator']==host['managed_run'] and proc['exit_code']==0 and proc['termination']=='natural' and proc['ref_count']==0
assert all(proc[k]['state']=='absent' for k in ['actual_process','actual_supervisor','job'])
assert all(o['ownership']=='released' for o in proc['owners'])
stderr=(P/'logs/independent_verify_001.stderr.txt').read_text(encoding='utf8');assert stderr==''
stdout=(P/'logs/independent_verify_001.stdout.txt').read_text(encoding='utf8')
assert stdout.count('INDEPENDENT_G4_CONDITION ')==24
line=next(x for x in stdout.splitlines() if x.startswith('C3_G4_INDEPENDENT_RESULT '));assert json.loads(line.split(' ',1)[1])==v
report=(P/'G4_PHYSICAL_FINDINGS_KO.md').read_text(encoding='utf8');lines=[x for x in report.splitlines() if x.startswith('|')]
rows=[[c.strip() for c in x.strip('|').split('|')] for x in lines]
conditions=table(P/'RUN_001/CONDITIONS.csv');pairs=read(P/'RUN_001/YAW_PAIRS.json');records=read(P/'RUN_001/CONDITIONS.json')
def near(display,expected,digits=6):
 z=float(display.replace('−','-'));assert abs(z-float(expected))<=.500001*10**(-digits),(display,expected)
condition_rows=[r for r in rows if len(r)==10 and r[0] in {x['coordinate'] for x in conditions}]
assert len(condition_rows)==24
if condition_rows:
 for rr,c in zip(condition_rows,conditions):
  assert rr[0]==c['coordinate'];near(rr[1],c['yaw_deg'])
  for j,k in [(2,'sFull'),(3,'sLoS'),(4,'eMP'),(5,'fixed'),(6,'selector'),(8,'Hpsi_s_per_rad')]:near(rr[j],c[k])
  assert rr[7]==c['tapFull']+'/'+c['tapLoS']
  assert rr[9]==('smooth' if c['derivative_status']=='VERIFIED_SMOOTH' else 'branch undefined')
spans=[r for r in rows if len(r)==5 and r[0] in {x['coordinate'] for x in conditions}];assert len(spans)==6
for rr in spans:
 selected=[p for p in pairs if p['coordinate']==rr[0]];assert len(selected)==6
 for text,k in zip(rr[1:],['delta_sFull','delta_sLoS','delta_fixed','delta_selector']):
  lo,hi=text.split(' … ');near(lo,min(p[k] for p in selected));near(hi,max(p[k] for p in selected))
tops=[r for r in rows if len(r)==5 and r[0].startswith('SM2_')];assert len(tops)==8
for rr in tops:
 candidates=[r for r in table(P/'RUN_001'/rr[0]/'SURFACE_REMOVAL.csv') if r['tap_ref']=='fpLoS']
 top=max(candidates,key=lambda x:abs(float(x['delta_s_fixed'])))
 assert rr[1]==top['surface'] and int(rr[2])==int(top['removed_group_count'])
 near(rr[3],top['delta_s_fixed']);near(rr[4],top['delta_s_redetected'])
maxcir=max(x for r in records for t in r['physical']['cir_closure'].values() for x in t.values())
maxpower=max(abs(x) for r in records for c in r['physical']['power_closure'] for x in c['residual'])
maxpair=max(p['decomposition_residual'] for p in pairs)
smoothsteps=[s for r in records for s in r['model']['fd_checks'] if s['same_branch']]
maxfd=max(s['absolute_error'] for s in smoothsteps)
for key,val in [('Erel/Emax=',maxcir),('전력 폐합 최대 절대 잔차=',maxpower),('36쌍 분해 최대 절대 잔차=',maxpair),('최대 절대 오차=',maxfd)]:
 display=re.search(re.escape(key)+r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)',report).group(1);assert abs(float(display)-val)<=5.1e-6*abs(val)
assert len(smoothsteps)==40 and 'smooth FD step 수=40' in report
lookup={r['condition_id']:r for r in conditions}
for suffix in ['P10Yp','P10Yn']:
 for i in range(4):
  r=lookup['SM2_'+suffix+'_Y'+str(i)];assert r['tapFull']==r['tapLoS']=='11' and float(r['selector'])==0
a,b=lookup['SM2_R5_982_Y0'],lookup['SM2_R5_982_Y2']
d_los=float(b['sLoS'])-float(a['sLoS']);d_mp=float(b['eMP'])-float(a['eMP']);d_full=float(b['sFull'])-float(a['sFull'])
assert d_los*d_mp<0 and abs(d_full)<abs(d_los)
result=dict(decision='PASS',report_sha256=sha(P/'G4_PHYSICAL_FINDINGS_KO.md'),report_condition_rows=24,report_span_rows=6,report_top_surface_rows=8,report_aggregate_metrics=dict(max_CIR_normalized=maxcir,max_power_closure_abs=maxpower,max_pair_identity_abs=maxpair,smooth_FD_steps=len(smoothsteps),max_smooth_FD_abs=maxfd),verifier_result_sha256=sha(P/'audit/INDEPENDENT_G4_RESULT_001.json'),verifier_host_sha256=sha(P/'logs/independent_verify_001.json'),verifier_manager_sha256=sha(P/'logs/independent_verify_001_managed_finish.json'),verifier_host=host,verifier_termination='natural',all_103_output_artifacts_unchanged=True,no_production_or_source_reexecution=True)
print(json.dumps(result,indent=2))
