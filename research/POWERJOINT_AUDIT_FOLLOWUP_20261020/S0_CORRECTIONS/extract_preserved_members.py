"""Read selected members only after full archive preservation gate verification."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import requests

HERE=Path(__file__).resolve().parent
class Remote(io.RawIOBase):
    def __init__(self,url,size):self.url=url;self.size=size;self.pos=0;self.net=requests.Session()
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset;return self.pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        if n==0:return b''
        end=min(self.size-1,self.pos+n-1)
        r=self.net.get(self.url,headers={'Range':f'bytes={self.pos}-{end}'},timeout=60);r.raise_for_status()
        if r.status_code!=206:raise RuntimeError('RANGE_NOT_HONORED')
        b=r.content;self.pos+=len(b);return b
def main():
    p=argparse.ArgumentParser();p.add_argument('--artifact-id',type=int,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--suffix',action='append',required=True);args=p.parse_args()
    receipt=json.loads((HERE/'TRACE_RECEIPT.json').read_text());assert receipt['task_status']=='COMPLETE'
    item=next(r for r in receipt['artifacts'] if r['artifact_id']==args.artifact_id)
    assert item['original_digest_verified'] and item['downloaded_sha256']==item['release_download_sha256']
    args.out.mkdir(parents=True,exist_ok=True);selected=[]
    with zipfile.ZipFile(Remote(item['release_asset_url'],item['downloaded_bytes'])) as z:
        members=[dict(name=i.filename,bytes=i.file_size,compressed_bytes=i.compress_size,crc=i.CRC) for i in z.infolist()]
        for n in z.namelist():
            if not any(n.endswith(s) for s in args.suffix):continue
            rel=Path(n);assert not rel.is_absolute() and '..' not in rel.parts
            b=z.read(n);dest=args.out/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
            selected.append(dict(member=n,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),zip_crc_verified=True))
    (args.out/'EXTRACTION_RECEIPT.json').write_text(json.dumps(dict(artifact_id=args.artifact_id,archive_sha256=item['downloaded_sha256'],url=item['release_asset_url'],whole_archive_verified_in_S0_5=True,whole_archive_rehashed_this_extraction=False,selected=selected,members=members),indent=2),encoding='utf-8')
    print(json.dumps(dict(selected=selected,members=len(members))))

if __name__=='__main__':main()
