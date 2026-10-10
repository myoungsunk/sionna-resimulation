"""Restore one archived stage into a NEW folder; no automatic experiment."""
import sys,pathlib,json,gzip,shutil,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[3]
if __name__=='__main__':
    stage=sys.argv[1];dst=pathlib.Path(sys.argv[2]).resolve();assert not dst.exists(),'Destination must not exist'
    assert ROOT not in dst.parents and dst!=ROOT,'Restore outside the repository'
    rows=[r for r in json.loads((ROOT/'audits/DRIVE_SIM_20261010/ARTIFACT_INDEX.json').read_text(encoding='utf-8')) if r['stage']==stage]
    assert rows,'Unknown stage';dst.mkdir(parents=True)
    for r in rows:
        if r['published_path']:
            p=ROOT/r['published_path'];rel=p.relative_to(ROOT/'audits/DRIVE_SIM_20261010'/stage)
            if r['storage']=='gzip_lossless':rel=pathlib.Path(str(rel)[:-3])
            if rel.parts[0]=='source':rel=pathlib.Path(*rel.parts[1:])
            stream=gzip.open(p,'rb') if r['storage']=='gzip_lossless' else p.open('rb')
        elif '--include-local-raw' in sys.argv:
            p=pathlib.Path(r['original_path']);assert p.is_file(),str(p)
            rel=pathlib.Path(r['archive_relative_path'])
            if rel.parts[0]=='source':rel=pathlib.Path(*rel.parts[1:])
            stream=p.open('rb')
        else:continue
        target=dst/rel;assert dst in target.resolve().parents;assert not target.exists(),str(target);target.parent.mkdir(parents=True,exist_ok=True)
        h=hashlib.sha256()
        with stream,target.open('wb') as f:
            for b in iter(lambda:stream.read(1048576),b''):h.update(b);f.write(b)
        assert h.hexdigest()==r['original_sha256'],str(target)
    print('Restored',stage,'to',dst,'; no experiment executed')
