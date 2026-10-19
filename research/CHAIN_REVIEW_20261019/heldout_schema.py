from pathlib import Path
import urllib.request,urllib.error,tarfile,hashlib,io,json,csv,os
import numpy as np
OUT=Path('heldout_contract');OUT.mkdir(exist_ok=True)
records=[]
for route in ['C01','C02','C03','O01','O02']:
 tag='route-rf-'+route.lower()+'-20261019-r01';url='https://github.com/myoungsunk/sionna-resimulation/releases/download/'+tag+'/'+route+'.tar.gz'
 req=urllib.request.Request('https://api.github.com/repos/myoungsunk/sionna-resimulation/releases/tags/'+tag,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN']})
 with urllib.request.urlopen(req) as r:release=json.load(r)
 asset=next(a for a in release['assets'] if a['name']==route+'.tar.gz');expected=asset['digest'].split(':')[1]
 archive=OUT/(route+'.tar.gz');dest=OUT/route;dest.mkdir(exist_ok=True)
 with urllib.request.urlopen(url,timeout=180) as r,archive.open('wb') as o:
  while True:
   b=r.read(1048576)
   if not b:break
   o.write(b)
 with archive.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 if actual!=expected:raise RuntimeError('DELIVERY_BYTES_NOT_EXPECTED:'+route)
 entries=[];selected=[]
 with tarfile.open(archive,'r:gz') as tar:
  for info in tar:
   if not info.isfile():continue
   p=Path(info.name)
   if p.is_absolute() or '..' in p.parts:raise RuntimeError('UNSAFE_TAR')
   if '/raw_paths/' in '/'+info.name or '/raw/' in '/'+info.name:continue
   if p.suffix in ('.npy','.csv','.json','.txt','.py') and info.size<35000000:
    entries.append({'path':info.name,'bytes':info.size})
    # Retain all non-raw arrays plus observed pose and configuration metadata.
    if p.suffix in ('.npy','.csv') or any(v in p.name.upper() for v in ['MANIFEST','METADATA','CONFIG','PLAN','CASE_QA','RECEIPT']):
     src=tar.extractfile(info);q=dest/p;q.parent.mkdir(parents=True,exist_ok=True)
     with src,q.open('wb') as o:o.write(src.read())
     selected.append(q)
 schemas=[]
 for p in selected:
  if p.suffix=='.npy':
   a=np.load(p,allow_pickle=False,mmap_mode='r');schemas.append({'path':str(p.relative_to(dest)),'shape':list(a.shape),'dtype':str(a.dtype)})
  elif p.suffix=='.csv' and ('POSE' in p.name.upper() or 'SENSOR' in p.name.upper()):
   with p.open() as f:r=csv.reader(f);header=next(r);first=next(r,None)
   schemas.append({'path':str(p.relative_to(dest)),'header':header,'first_row':first})
 record={'route':route,'original_sha256':actual,'schema':schemas,'selected_files':len(selected),'entries':entries}
 records.append(record);(OUT/(route+'_SCHEMA.json')).write_text(json.dumps(record,indent=2))
 print('HELDOUT_SCHEMA',route,json.dumps(schemas)[:14000],flush=True)
 archive.unlink()
(OUT/'ALL_SCHEMAS.json').write_text(json.dumps(records,indent=2))
print('HELDOUT_SCHEMA_FINISHED',len(records),'NO_ESTIMATOR_EVALUATION',flush=True)
