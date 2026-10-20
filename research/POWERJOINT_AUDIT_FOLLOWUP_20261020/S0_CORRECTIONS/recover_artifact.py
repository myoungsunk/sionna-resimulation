"""Full Actions ZIP verification and additive result recovery; no inferred hashes."""
from pathlib import Path
import argparse, hashlib, json, zipfile
from github_io import api, download, session
def main():
    p=argparse.ArgumentParser();p.add_argument('--id',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);s=session();meta=api(s,f'actions/artifacts/{a.id}')
    archive=a.out.parent/f'artifact-{a.id}.zip';digest,size=download(s,meta['archive_download_url'],archive)
    assert meta['digest']=='sha256:'+digest and meta['size_in_bytes']==size
    members=[]
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for i in z.infolist():
            if i.is_dir():continue
            dest=a.out/i.filename;assert a.out.resolve() in dest.resolve().parents
            raw=z.read(i);dest.parent.mkdir(parents=True,exist_ok=True)
            if dest.exists():assert dest.read_bytes()==raw
            else:dest.write_bytes(raw)
            members.append(dict(name=i.filename,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),zip_crc_verified=True))
    (a.out/'ACTIONS_ARTIFACT.json').write_text(json.dumps(dict(artifact_id=a.id,actions_run_id=meta['workflow_run']['id'],source_commit=meta['workflow_run']['head_sha'],archive_sha256=digest,archive_bytes=size,full_download_verified=True,members=members),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(id=a.id,bytes=size,members=len(members))))
if __name__=='__main__':main()
