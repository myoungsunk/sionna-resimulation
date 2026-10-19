from pathlib import Path
import os,json,urllib.request,urllib.error,zipfile,hashlib,shutil,time,subprocess,sys
ROOT=Path.cwd();REPO='myoungsunk/sionna-resimulation';RUN=39252522326
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
def restore(aid,name,dest,selected=None):
 dest.mkdir(exist_ok=True);target=ROOT/name
 with response(f'https://api.github.com/repos/{REPO}/actions/artifacts/{aid}/zip?nonce={time.time_ns()}') as r,target.open('wb') as o:shutil.copyfileobj(r,o)
 with target.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 with zipfile.ZipFile(target) as z:
  if z.testzip():raise RuntimeError('ZIP_DAMAGED')
  for info in z.infolist():
   if info.is_dir():continue
   p=Path(info.filename)
   if p.is_absolute() or '..' in p.parts:raise RuntimeError('UNSAFE_PATH')
   if selected is not None and p.name not in selected:continue
   q=dest/p;q.parent.mkdir(parents=True,exist_ok=True)
   with z.open(info) as i,q.open('wb') as o:shutil.copyfileobj(i,o)
 return dict(artifact_id=aid,sha256=sha,bytes=target.stat().st_size)
records=[restore(12187837531,'new_contract.zip',ROOT/'heldout'),restore(12161061156,'new_poses.zip',ROOT/'poses')]
start=time.time()
while time.time()-start<2400:
 info=js(f'actions/runs/{RUN}')
 if info['status']=='completed':
  arts=js(f'actions/runs/{RUN}/artifacts')['artifacts']
  if not arts:raise RuntimeError('No previous training artifact available')
  aid=next(a['id'] for a in arts if a['name'].startswith('powerjoint-chain-hypotheses-'));break
 time.sleep(20)
else:raise TimeoutError('Source experiment has not completed')
records.append(restore(aid,'main_source.zip',ROOT/'main_result',selected={'PACKETS_SOURCE_LABELS.csv.gz','MEMORY_TRAIN_PARAMS.json','SUMMARY.json'}))
(ROOT/'external_out').mkdir(exist_ok=True);(ROOT/'external_out/INPUT_RECEIPTS.json').write_text(json.dumps(records,indent=2))
subprocess.run([sys.executable,'-u','source/research/CHAIN_REVIEW_20261019/heldout_run.py'],check=True)
