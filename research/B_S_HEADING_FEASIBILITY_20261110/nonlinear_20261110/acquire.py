import pathlib,zipfile,json,hashlib,urllib.request,concurrent.futures
p=pathlib.Path(__file__).parent
z=zipfile.ZipFile(p.parent/'R5.zip')
files=[f for f in json.loads(z.read('tmp/fp-release-assets/ACQUISITION_RECEIPT.json'))['files'] if f['asset_name'] in ['LP_plus45_bank.npz','LP_minus45_bank.npz']]
def get(f):
 q=p/f['asset_name']
 if not q.exists():
  tmp=q.with_suffix('.partial')
  with urllib.request.urlopen(f['download_url'],timeout=60) as src,tmp.open('wb') as dst:
   while b:=src.read(1024*1024):dst.write(b)
  assert hashlib.sha256(tmp.read_bytes()).hexdigest()==f['sha256']
  tmp.replace(q)
 assert q.stat().st_size==f['size'] and hashlib.sha256(q.read_bytes()).hexdigest()==f['sha256']
 print('SHA_PASS',f['asset_name'],flush=True)
 return dict(name=f['asset_name'],sha256=f['sha256'],size=f['size'])
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:r=list(ex.map(get,files))
(p/'BANK_RECEIPT.json').write_text(json.dumps(r,indent=2))
