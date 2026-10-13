"""Retrieve original LoS assets; no simulation or model fitting."""
from pathlib import Path
import json, hashlib, urllib.request, datetime
HERE=Path(__file__).resolve().parent
OUT=HERE/'out/rf_location_addendum'
CACHE=HERE.parents[1]/'artifacts/i0_los_release_originals'
def main():
    audit=json.loads((OUT/'AUDIT.json').read_text(encoding='utf-8'))
    p0=json.loads((OUT/'references/out_p0_p5/R1/P0/P0_INPUT_MANIFEST.json').read_text())
    CACHE.mkdir(parents=True,exist_ok=True)
    rows=[]
    for asset in audit['release']['assets']:
        if not asset['name'].endswith('.npy'):continue
        dest=CACHE/asset['name']
        if dest.exists():raise FileExistsError(dest)
        h=hashlib.sha256()
        with urllib.request.urlopen(asset['url'],timeout=60) as remote, dest.open('xb') as local:
            for block in iter(lambda:remote.read(1<<20),b''):
                h.update(block);local.write(block)
        key='los:'+asset['name'].removeprefix('H_LoS_').removesuffix('.npy')
        row=dict(file=asset['name'],local_path=str(dest),bytes=dest.stat().st_size,sha256=h.hexdigest(),p0_sha256=p0['h_sha256'][key],matches=h.hexdigest()==p0['h_sha256'][key])
        rows.append(row);print(asset['name'],row['matches'],flush=True)
    result=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=rows,status='PASS' if len(rows)==5 and all(x['matches'] for x in rows) else 'FAIL',I1='NOT_RUN')
    (OUT/'LOS_RELEASE_VERIFICATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if result['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':main()
