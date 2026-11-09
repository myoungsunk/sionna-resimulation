"""Fetch one SHA-locked historical trace archive; no silently rebuilt gold data."""
import argparse,hashlib,json,os,time,urllib.request,zipfile
from pathlib import Path

def run(out,archive=None):
    lock=json.loads(Path(__file__).with_name('ARCHIVE_LOCK.json').read_text())
    out.mkdir(parents=True,exist_ok=True)
    path=Path(archive) if archive else out/'calibration_archive.zip'
    if not path.exists():
        for attempt in range(3):
            req=urllib.request.Request(lock['api_url']+'?attempt='+str(attempt),headers={'User-Agent':'b-mcg-v1','Accept':'application/vnd.github+json'})
            if os.environ.get('GH_TOKEN'):req.add_unredirected_header('Authorization','Bearer '+os.environ['GH_TOKEN'])
            try:
                with urllib.request.urlopen(req,timeout=60) as src,path.with_suffix('.part').open('wb') as dest:
                    while block:=src.read(1024*1024):dest.write(block)
                path.with_suffix('.part').replace(path);break
            except OSError:
                if attempt==2:raise
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=lock['sha256'] or path.stat().st_size!=lock['size_bytes']:raise ValueError('ARCHIVE_SHA_OR_SIZE_MISMATCH')
    dest=out/'extracted';dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for item in z.infolist():
            target=(dest/item.filename).resolve()
            if not target.is_relative_to(dest.resolve()):raise ValueError('UNSAFE_ZIP_PATH')
        z.extractall(dest)
    root=dest/'tmp/fp-b-calibration'
    for rel,digest in lock['files_sha256'].items():
        if hashlib.sha256((root/rel).read_bytes()).hexdigest()!=digest:raise ValueError('ARCHIVE_MEMBER_SHA_MISMATCH '+rel)
    (out/'ARCHIVE_RECEIPT.json').write_text(json.dumps({'status':'PASS','sha256':actual,'archive_root':str(root.resolve()),'lock':lock},indent=2)+'\n')
    print(root.resolve(),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--archive',type=Path);a=p.parse_args();run(a.out,a.archive)
