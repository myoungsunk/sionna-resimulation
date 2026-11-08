#!/usr/bin/env python3
"""Download locked Release assets into a disposable cache, never into raw evidence."""
import argparse,hashlib,json,os,time,urllib.request
from pathlib import Path

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def verify(p,record):
    if not p.is_file():return False
    with p.open('rb') as f:
        if f.read(48).startswith(b'version https://git-lfs.github.com/spec/v1'):return False
    return p.stat().st_size==record['size'] and sha(p)==record['sha256']

def acquire(record,out,attempts=3):
    target=out/record['asset_name']
    if verify(target,record):return target
    # An existing invalid cache entry is evidence of a mismatch, not reusable data.
    if target.exists():raise ValueError('INVALID_EXISTING_CACHE: '+str(target))
    part=target.with_suffix(target.suffix+'.part')
    for attempt in range(attempts):
        try:
            req=urllib.request.Request(record['download_url'],headers={'User-Agent':'fp-input-acquisition'})
            with urllib.request.urlopen(req,timeout=60) as src,part.open('wb') as dst:
                started=time.monotonic()
                while chunk:=src.read(1024*1024):
                    dst.write(chunk)
                    if time.monotonic()-started>300:raise TimeoutError('ASSET_DOWNLOAD_DEADLINE')
            if not verify(part,record):raise ValueError('SHA_OR_SIZE_MISMATCH: '+record['asset_name'])
            os.replace(part,target)
            return target
        except (OSError,ValueError) as e:
            print('DOWNLOAD_ATTEMPT_FAILED',record['asset_name'],attempt+1,type(e).__name__,str(e),flush=True)
            if attempt+1==attempts:raise
    raise RuntimeError('UNREACHABLE')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    lock=Path(__file__).with_name('RELEASE_INPUT_LOCK.json');records=json.loads(lock.read_text())['files']
    assert len(records)==8 and len({r['asset_name'] for r in records})==8
    done=[]
    try:
        for record in records:
            file=acquire(record,a.out)
            done.append(dict(record,path=str(file.resolve())))
            print('INPUT_SHA_PASS',record['asset_name'],flush=True)
        (a.out/'ACQUISITION_RECEIPT.json').write_text(json.dumps({'status':'PASS','lock_sha256':sha(lock),'files':done},indent=2))
    except BaseException as e:
        (a.out/'ACQUISITION_FAILURE.json').write_text(json.dumps({'status':'INPUT_ACQUISITION_FAILED','verified':done,'error':repr(e)},indent=2))
        raise
if __name__=='__main__':main()
