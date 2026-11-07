from pathlib import Path
import urllib.request,hashlib,json,concurrent.futures,shutil
ROOT=Path(__file__).resolve().parent;DEST=ROOT/'R45_sources';REF='fca24720524068badeab79b78098a244cebc62b5'
manifest=json.loads(next((ROOT/'inputs').glob('*S1_MANIFEST.json')).read_text())
paths=[p.relative_to(DEST).as_posix() for p in DEST.rglob('*.py')]+['src/qclean_uwb/drivesim/observation.py','LP_plus45_bank.npz','LP_minus45_bank.npz']
def fetch(p):
    out=DEST/p;out.parent.mkdir(parents=True,exist_ok=True)
    expected=manifest.get('baseline_sources',{}).get(p) or manifest.get('code_files',{}).get(p) or manifest['model_files'].get(p)
    if out.exists() and hashlib.sha256(out.read_bytes()).hexdigest()==expected:return p,'CACHED'
    base='https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/'+REF+'/'
    with urllib.request.urlopen(base+p,timeout=60) as f:b=f.read()
    if b.startswith(b'version https://git-lfs.github.com/spec/v1'):
        print('LFS',p,b.decode().strip(),flush=True)
        with urllib.request.urlopen('https://media.githubusercontent.com/media/myoungsunk/sionna-resimulation/'+REF+'/'+p,timeout=180) as f: b=f.read()
    h=hashlib.sha256(b).hexdigest();assert expected==h,(p,expected,h)
    out.write_bytes(b);print('READY',p,len(b),flush=True);return p,h
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results=list(pool.map(fetch,paths))
(DEST/'SOURCE_LOCK.json').write_text(json.dumps(dict(results),indent=2))
print('PREPARED',len(results),flush=True)
