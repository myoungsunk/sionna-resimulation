from pathlib import Path
import os,json,sys,time,hashlib,zipfile,urllib.request,urllib.error,shutil
import numpy as np,pandas as pd
RUN=39256517334;REPO='myoungsunk/sionna-resimulation';ROOT=Path.cwd();TMP=ROOT/'external_saved';TMP.mkdir(exist_ok=True);OUT=ROOT/'research/CHAIN_VALIDATED_RESULTS_20261019/external_evidence';OUT.mkdir(parents=True,exist_ok=True)
class NR(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
def response(url):
 req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Cache-Control':'no-cache'})
 try:return urllib.request.build_opener(NR()).open(req,timeout=90)
 except urllib.error.HTTPError as e:
  if e.code not in (301,302,303,307,308):raise
  return urllib.request.urlopen(e.headers['Location'],timeout=180)
def js(path):
 with response('https://api.github.com/repos/'+REPO+'/'+path) as r:return json.load(r)
started=time.time()
while time.time()-started<2400:
 info=js(f'actions/runs/{RUN}')
 if info['status']=='completed':
  aa=js(f'actions/runs/{RUN}/artifacts')['artifacts']
  if not aa:raise RuntimeError('External run completed without outputs; inspect run '+str(RUN))
  artifact=next(a for a in aa if a['name'].startswith('powerjoint-locked-external-evaluation-'));break
 time.sleep(20)
else:raise TimeoutError('External inference still running, not scientifically complete')
for attempt in range(6):
 try:
  p=ROOT/'external.zip'
  with response(f"https://api.github.com/repos/{REPO}/actions/artifacts/{artifact['id']}/zip?nonce={time.time_ns()}") as r,p.open('wb') as f:shutil.copyfileobj(r,f)
  break
 except urllib.error.HTTPError as e:
  if e.code not in [429,500,502,503,504] or attempt==5:raise
  time.sleep((attempt+1)*10)
with p.open('rb') as f:zipsha=hashlib.file_digest(f,'sha256').hexdigest()
if artifact.get('digest') and zipsha!=artifact['digest'].split(':')[1]:raise RuntimeError('ARTIFACT_BYTES_DIFFER')
with zipfile.ZipFile(p) as z:
 if z.testzip():raise RuntimeError('ZIP_CRC')
 for item in z.infolist():
  if item.is_dir():continue
  rel=Path(item.filename)
  if rel.is_absolute() or '..' in rel.parts:raise RuntimeError('UNSAFE_PATH')
  dest=TMP/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  with z.open(item) as i,dest.open('wb') as o:shutil.copyfileobj(i,o)
summary=json.loads((TMP/'EXTERNAL_SUMMARY.json').read_text());score=pd.read_csv(TMP/'EXTERNAL_EVALUATION.csv');qa=[];new=[]
levels={'B0':0.,'L0':.01,'L1':.05,'L2':.2}
for path in sorted((TMP/'traces').glob('*.npz')):
 cid,label=path.stem.rsplit('_',1);bias=levels[label]
 with np.load(path,allow_pickle=False) as z:a={k:z[k] for k in z.files}
 t=a['t'];mask=t>=30;truth=a['truth_for_offline_scoring_only'];names=list(a['names'])
 for j,name in enumerate(names):
  ee=a['state'][:,j,2]-truth[:,2];ee=np.arctan2(np.sin(ee),np.cos(ee));var=a['cov'][:,j,2,2];ne=ee*ee/var
  vals={'heading_rmse_deg':float(np.sqrt(np.mean(ee[mask]**2))*180/np.pi),'heading95':float(np.mean(ne[mask]<=3.841458820694124)),'heading_nees':float(ne[mask].mean()),'signed_heading_deg':float(ee[mask].mean()*180/np.pi),'sigma_rms_deg':float(np.sqrt(var[mask].mean())*180/np.pi)}
  rr=score[(score['case']==cid)&np.isclose(score.bias_dps,bias)&(score.method==name)].iloc[0]
  diff=max(abs(vals[k]-float(rr[k])) for k in vals)
  qa.append({'case':cid,'bias':bias,'method':str(name),'max_metric_error':diff,'min_cov_eig':float(np.linalg.eigvalsh(a['cov'][:,j]).min())})
  new.append({'case':cid,'bias_dps':bias,'method':str(name),**vals})
 check=names.index('POWER1');control=names.index('POWER_INDEPENDENT')
 delta=float(np.max(abs(a['state'][:,check,:4]-a['state'][:,control,:4])))
 if delta>1e-7:raise RuntimeError('EXTERNAL_INDEPENDENT_PARITY')
 if np.any(a['accepted'][np.setdiff1d(np.arange(len(t)),a['rf_indices'])]):raise RuntimeError('RF_UPDATE_WITHOUT_PACKET')
if max(x['max_metric_error'] for x in qa)>1e-8 or min(x['min_cov_eig'] for x in qa)<=0:raise RuntimeError('SCORER_QA')
v=pd.DataFrame(new);pd.DataFrame(qa).to_csv(OUT/'EXTERNAL_INDEPENDENT_SCORE_QA.csv',index=False);v.to_csv(OUT/'EXTERNAL_RECOMPUTED.csv',index=False)
for name in ['EXTERNAL_TEST_LOCK.json','EXTERNAL_INPUT_QA.csv','EXTERNAL_ERRORS.json','EXTERNAL_SUMMARY.json','EXTERNAL_EVALUATION.csv','INPUT_RECEIPTS.json']:
 if (TMP/name).exists():shutil.copy2(TMP/name,OUT/name)
for key in ['EXTERNAL_TEST_LOCK.json']:
 shutil.copy2(TMP/key,OUT/key)
comparison=[]
for group,sub in [('all',v),('corridor',v[v['case'].str.startswith('C')]),('office',v[v['case'].str.startswith('O')])]:
 b=sub[sub.method=='POWER1'].set_index(['case','bias_dps']);m=sub[sub.method=='POWER_MEMORY'].set_index(['case','bias_dps']);ratio=m.heading_rmse_deg/b.heading_rmse_deg-1
 comparison.append({'group':group,'conditions':len(b),'memory_rmse_improved_gt01pct':int((ratio<-.001).sum()),'memory_rmse_worse_gt10pct':int((ratio>.1).sum()),'mean_relative_rmse':float(ratio.mean()),'median_heading95_base':float(b.heading95.median()),'median_heading95_memory':float(m.heading95.median())})
pd.DataFrame(comparison).to_csv(OUT/'EXTERNAL_COMPARISON.csv',index=False)
receipt={'run_id':RUN,'artifact_id':artifact['id'],'artifact_sha256':zipsha,'scored_condition_traces':len(list((TMP/'traces').glob('*.npz'))),'scored_method_rows':len(qa),'max_metric_error':max(x['max_metric_error'] for x in qa),'minimum_cov_eigenvalue':min(x['min_cov_eig'] for x in qa),'comparison':comparison}
(OUT/'EXTERNAL_REVIEW_RECEIPT.json').write_text(json.dumps(receipt,indent=2));print('EXTERNAL_REVIEW',json.dumps(receipt),flush=True)
select=v[(v.bias_dps==0)&v.method.isin(['JOINT4','POWER1','POWER_MEMORY','POWER_MEMORY_NO_CROSS','POWER_SR4'])];print('NEW_ROUTE_B0',select.to_json(orient='records'),flush=True)
base=OUT.parent
lines=['# 새 주로 Mount45 고정 후보 검증 — F 단계','',f"실제 Run {RUN}, artifact {artifact['id']}. 후보를 기존 검증 성능을 보고 교체하지 않고 처음 등록한6개 방법을 그대로 시험했다.",'','훈련은 기존 R4/R5 Mount0, 원 R2-heldout 학습분할/평균·공분산 적합/시간상관 파라미터를 사용했다. 새 RF의 정답은 센서 생성·평가·입력 LoS 점검용이며 추론에 들어가지 않았다. 새 데이터로 파라미터를 조정하지 않았다.','',f"실제 완료 {receipt['scored_condition_traces']} 조건 / {len(qa)} 방법별 점수, 최대 재채점 차이 {receipt['max_metric_error']:.3g}. 직접 LoS 정합과 누락 RF 시각에서 업데이트하지 않는 것을 검사했다.",'','## B0 전체 주행 평가 (t>=30s)','', '| Case | Method | signed° | RMSE° | sigma RMS° | heading95 | NEES |','|---|---|---:|---:|---:|---:|---:|']
for _,r in select.iterrows():lines.append(f"| {r['case']} | {r.method} | {r.signed_heading_deg:.4f} | {r.heading_rmse_deg:.4f} | {r.sigma_rms_deg:.4f} | {100*r.heading95:.2f}% | {r.heading_nees:.4f} |")
lines += ['','## 전체 Bias 집계','',json.dumps(comparison,ensure_ascii=False,indent=2),'','이 통계는 동일 RF 조건에 B0/L0/L1/L2 센서 모델을 적용한 기술통계다. corridor C01/C02/C03은 같은 기존 장면, office O01/O02는 같은 오피스 하나이므로 다섯 개 독립 장면이 아니다. dt=.25s synthetic controls 전체를 예측에 사용하고 지정 RF 시점만 갱신했다. 일부 열화 또는 모델 NO-GO는 삭제하지 않았다. 새 경로의 직선·회전 구간도 EXTERNAL_SCORES.csv에 보존한다.','',f"[Full artifact](https://github.com/{REPO}/actions/runs/{RUN}/artifacts/{artifact['id']})",'','## 납품·판정 범위','',json.dumps(summary,ensure_ascii=False,indent=2)]
(base/'RESULTS_F_NEW_ROUTES_KO.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
