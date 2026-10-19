from pathlib import Path
import os,json,hashlib,zipfile,urllib.request,urllib.error,urllib.parse,shutil,time
ROOT=Path.cwd(); SOURCE=ROOT/'source'; OUT=ROOT/'out'; OUT.mkdir(exist_ok=True)
(ROOT/'ffd_p0p3/out').mkdir(parents=True,exist_ok=True)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl): return None
records=[]
for aid,name in [(11948391783,'physics_rs_inputs.zip'),(11782748118,'rf_frozen.zip'),(12034154094,'ffd_original.zip')]:
    url=f'https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/artifacts/{aid}/zip?nonce={time.time_ns()}'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Cache-Control':'no-cache'})
    try:
        response=urllib.request.build_opener(NoRedirect()).open(req,timeout=90)
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308): raise
        # The Azure-signed artifact URL must NOT receive a GitHub bearer token.
        target=e.headers['Location']; response=urllib.request.urlopen(target,timeout=180)
    p=ROOT/name
    with response,p.open('wb') as f: shutil.copyfileobj(response,f)
    with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    records.append({'artifact':aid,'file':name,'sha256':digest,'bytes':p.stat().st_size})
    print('RESTORED',name,p.stat().st_size,digest,flush=True)
    with zipfile.ZipFile(p) as z:
        if z.testzip(): raise RuntimeError('Archive is not readable: '+name)
        if name=='physics_rs_inputs.zip':
            for info in z.infolist():
                if info.is_dir(): continue
                pp=Path(info.filename)
                if '..' in pp.parts or pp.is_absolute(): raise RuntimeError('UNSAFE_ZIP_PATH')
                dest=SOURCE/pp; dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists():
                    with z.open(info) as i,dest.open('wb') as o: shutil.copyfileobj(i,o)
        elif name=='ffd_original.zip':
            for bank in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
                names=[v for v in z.namelist() if v.endswith(bank)]
                if len(names)!=1: raise RuntimeError('BANK_NOT_UNIQUE')
                with z.open(names[0]) as i,(ROOT/bank).open('wb') as o: shutil.copyfileobj(i,o)
expected={'LP_plus45_bank.npz':'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','LP_minus45_bank.npz':'39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}
actual={}
for name,digest in expected.items():
    with (ROOT/name).open('rb') as f: actual[name]=hashlib.file_digest(f,'sha256').hexdigest()
    records.append({'bank':name,'sha256':actual[name],'matches_original':actual[name]==digest})
    if actual[name]!=digest:
        # Continue only after numerical arrays can be compared to an independent original.
        raise RuntimeError('Recovered archive bank differs; physical input identity not yet established')
(ROOT/'BANK_MANIFEST.json').write_text(json.dumps({'npz_sha256':actual}))
(OUT/'INPUT_RECEIPT.json').write_text(json.dumps(records,indent=2))
manifest=json.loads((SOURCE/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
print('CASE_FIELDS',json.dumps(manifest['cases'][0]),flush=True)
with zipfile.ZipFile(ROOT/'rf_frozen.zip') as z:
    print('RF_ARCHIVE_NAMES',json.dumps(z.namelist()[:8]),flush=True)
    import numpy as np,io
    first=next(n for n in z.namelist() if n.endswith('_ONE_STEP.npz'))
    with np.load(io.BytesIO(z.read(first)),allow_pickle=False) as d: print('RF_FIELDS',json.dumps({k:list(d[k].shape) for k in d.files}),flush=True)
