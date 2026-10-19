from pathlib import Path
import os,sys,json,urllib.request,urllib.error,zipfile,hashlib,shutil,time,subprocess
ROOT=Path.cwd();OUT=ROOT/'result';PHY=ROOT/'physics';OUT.mkdir(exist_ok=True);PHY.mkdir(exist_ok=True)
REPO='myoungsunk/sionna-resimulation';RUN=39252522326
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
def restore(aid,target,dest):
 with response(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip?nonce={time.time_ns()}') as r,target.open('wb') as o:shutil.copyfileobj(r,o)
 with target.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
 with zipfile.ZipFile(target) as z:
  if z.testzip():raise RuntimeError('ZIP_DAMAGED')
  for info in z.infolist():
   if info.is_dir():continue
   p=Path(info.filename)
   if p.is_absolute() or '..' in p.parts:raise RuntimeError('UNSAFE_PATH')
   q=dest/p;q.parent.mkdir(parents=True,exist_ok=True)
   with z.open(info) as i,q.open('wb') as o:shutil.copyfileobj(i,o)
 return dict(artifact_id=aid,sha256=sha,bytes=target.stat().st_size)
physics=restore(11948391783,ROOT/'physics.zip',PHY)
start=time.time();state=None
while time.time()-start<2400:
 info=js(f'actions/runs/{RUN}')
 if info['status']!=state:
  state=info['status'];print('AWAIT_SCIENTIFIC_JOB',state,flush=True)
 if state=='completed':
  artifacts=js(f'actions/runs/{RUN}/artifacts')['artifacts']
  if not artifacts:raise RuntimeError('Main run completed with no saved output: '+str(info.get('conclusion')))
  artifact=next(a for a in artifacts if a['name'].startswith('powerjoint-chain-hypotheses-'))
  break
 time.sleep(20)
else:raise TimeoutError('MAIN_STILL_RUNNING: no claim of scientific completion')
receipt=restore(artifact['id'],ROOT/'main.zip',OUT)
(OUT/'REVIEW_INPUT.json').write_text(json.dumps({'main':receipt,'physics':physics,'run':RUN,'main_workflow_conclusion':info.get('conclusion')},indent=2))
if not (OUT/'SUMMARY.json').exists():raise RuntimeError('PARTIAL_MAIN_ARTIFACT: inspect saved conditions rather than silently declaring completion')
for script,args in [('verify.py',[str(OUT)]),('co_compare.py',[str(OUT),str(PHY)])]:
 cmd=[sys.executable,str(ROOT/'research/CHAIN_REVIEW_20261019'/script),*args]
 print('REVIEW_START',script,flush=True);subprocess.run(cmd,check=True)
review=OUT/'review'
for name in ['SUMMARY.json','MODEL_COMPARISON.csv','MEMORY_TRAIN_PARAMS.json','PHYSICAL_PARITY.csv','NO_MEMORY_PARITY.csv','ERRORS.json','WARNINGS.json','EVALUATION_METRICS.csv','EVENTS.json','PROTOCOL_LOCK.json','LINEAR_MEMORY_UNIT_TEST.csv','REVIEW_INPUT.json']:
 p=OUT/name
 if p.exists():shutil.copy2(p,review/name)
manifest=[]
for p in sorted(review.rglob('*')):
 if p.is_file():
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  manifest.append({'path':str(p.relative_to(review)),'bytes':p.stat().st_size,'sha256':h})
(review/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
print('REVIEW_ARTIFACT_READY',len(manifest),flush=True)
