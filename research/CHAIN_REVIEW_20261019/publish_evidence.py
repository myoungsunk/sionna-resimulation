from pathlib import Path
import os,sys,json,zipfile,urllib.request,urllib.error,shutil,time,hashlib,subprocess
ROOT=Path.cwd();DEST=ROOT/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence';DEST.mkdir(parents=True,exist_ok=True);MAIN=ROOT/'main_saved';MAIN.mkdir(exist_ok=True)
class NR(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None
def download(aid,target,expected):
 for attempt in range(6):
  try:
   req=urllib.request.Request(f'https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/artifacts/{aid}/zip?nonce={time.time_ns()}',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Cache-Control':'no-cache'})
   try:r=urllib.request.build_opener(NR()).open(req,timeout=90)
   except urllib.error.HTTPError as e:
    if e.code not in (301,302,303,307,308):raise
    r=urllib.request.urlopen(e.headers['Location'],timeout=180)
   with r,target.open('wb') as o:shutil.copyfileobj(r,o)
   with target.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
   if sha!=expected:raise RuntimeError('ARTIFACT_CONTENT_NOT_EXPECTED')
   return
  except urllib.error.HTTPError as e:
   if e.code not in [429,500,502,503,504] or attempt==5:raise
   print('TRANSIENT_DOWNLOAD_RETRY',aid,attempt+1,e.code,flush=True);time.sleep(10*(attempt+1))
items=[(12188067493,'review.zip',DEST,'91a90a8820857e536ac390118166c5cb583626df35d7bd8061ae1d4cf06ac5b7'),(12188081569,'main.zip',MAIN,'15a05bc327536b40a9da8e2329e026e930fc8ca486aab58600300355d6840bb2')]
for aid,name,dest,sha in items:
 target=ROOT/name;download(aid,target,sha)
 with zipfile.ZipFile(target) as z:
  if z.testzip():raise RuntimeError('ZIP_CRC')
  for info in z.infolist():
   if info.is_dir():continue
   p=Path(info.filename)
   if p.is_absolute() or '..' in p.parts:raise RuntimeError('UNSAFE_PATH')
   if dest==DEST and p.suffix not in ['.json','.csv']:continue
   if dest==MAIN and not (p.name=='OOF_PARAMETERS.csv.gz' or 'traces' in p.parts):continue
   q=dest/p;q.parent.mkdir(parents=True,exist_ok=True)
   with z.open(info) as i,q.open('wb') as o:shutil.copyfileobj(i,o)
subprocess.run([sys.executable,'-u','research/CHAIN_REVIEW_20261019/deep_metrics.py',str(MAIN),str(DEST)],check=True)
receipt={'main_run_id':39252522326,'main_artifact_id':12188081569,'review_run_id':39255330193,'review_artifact_id':12188067493,'publication':'exact CSV/JSON from verified artifact; no editing of observations, coefficients or scientific inference','original_review_manifest':'MANIFEST.json refers to original artifact members, not this selected publication subtree','files':[]}
for p in sorted(DEST.rglob('*')):
 if p.is_file():receipt['files'].append({'path':str(p.relative_to(DEST)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(DEST/'PUBLICATION_RECEIPT.json').write_text(json.dumps(receipt,indent=2));print('PUBLICATION_READY',len(receipt['files']),flush=True)
