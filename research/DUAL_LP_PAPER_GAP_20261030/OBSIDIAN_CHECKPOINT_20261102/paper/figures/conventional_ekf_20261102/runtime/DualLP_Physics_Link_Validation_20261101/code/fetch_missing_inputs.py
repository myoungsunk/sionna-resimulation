"""Fetch only missing inputs from pinned URLs; never overwrite a mismatched existing file."""
from __future__ import annotations
import argparse,hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--verify-only',action='store_true');args=ap.parse_args()
    manifest=json.loads((ROOT/'recovered/RECOVERY_MANIFEST.json').read_text());missing=[]
    for row in manifest['files']:
        p=ROOT/'recovered'/row['path']
        if p.exists():
            if sha(p)!=row['sha256']:raise RuntimeError('EXISTING_INPUT_HASH_MISMATCH: '+str(p))
            continue
        if args.verify_only:missing.append(row['path']);continue
        p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.download')
        if tmp.exists():raise RuntimeError('PARTIAL_DOWNLOAD_EXISTS: '+str(tmp))
        req=urllib.request.Request(row['url'],headers={'User-Agent':'DualLP-retrospective-reproduction'})
        with urllib.request.urlopen(req,timeout=180) as response,tmp.open('xb') as out:
            while buf:=response.read(1024*1024):out.write(buf)
        if sha(tmp)!=row['sha256']:raise RuntimeError('DOWNLOADED_INPUT_HASH_MISMATCH: '+str(tmp))
        tmp.replace(p);print('VERIFIED',row['path'],flush=True)
    if missing:raise RuntimeError('MISSING_INPUTS: '+', '.join(missing))
    print('All locked inputs verified.')
if __name__=='__main__':main()
