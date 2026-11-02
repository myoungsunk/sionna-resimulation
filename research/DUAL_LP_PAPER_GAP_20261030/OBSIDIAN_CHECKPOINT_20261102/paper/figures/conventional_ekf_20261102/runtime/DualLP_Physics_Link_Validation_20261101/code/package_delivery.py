"""Build a verified results ZIP; immutable FFD bank inputs remain companions."""
from __future__ import annotations
import argparse,datetime,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def included(p):
    rel=p.relative_to(ROOT)
    return (p.is_file() and '__pycache__' not in rel.parts and p.suffix!='.pyc'
            and not p.name.endswith('_PID.txt') and 'banks' not in rel.parts
            and p.name not in ('FILE_INVENTORY.json','SHA256SUMS.txt'))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--no-zip',action='store_true');ap.add_argument('--out',type=Path);a=ap.parse_args()
    manfile=ROOT/'MANIFEST.json'
    if not manfile.exists():raise FileNotFoundError('MANIFEST.json must be created first')
    man=json.loads(manfile.read_text());man['implementation_sha256']={p.name:sha(p) for p in sorted((ROOT/'code').glob('*.py'))}
    man['final_assembly_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();manfile.write_text(json.dumps(man,ensure_ascii=False,indent=2))
    files=[p for p in sorted(ROOT.rglob('*')) if included(p)]
    rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
    source=json.loads((ROOT/'recovered/RECOVERY_MANIFEST.json').read_text())
    external=[dict(path='recovered/'+r['path'],bytes=r['bytes'],sha256=r['sha256'],url=r['url']) for r in source['files'] if r['path'].startswith('inputs/banks/')]
    inv=dict(files=rows,external_inputs=external,n_files=len(rows),excludes_self=True,checksum_inventory_excludes=['FILE_INVENTORY.json','SHA256SUMS.txt'])
    (ROOT/'FILE_INVENTORY.json').write_text(json.dumps(inv,indent=2))
    (ROOT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['path']+'\n' for r in rows))
    if a.no_zip:print('INVENTORY_COMPLETE',len(rows));return
    out=(a.out or ROOT.parent/(ROOT.name+'.zip')).resolve()
    if out.exists():raise FileExistsError('Archive already exists; choose a new output filename: '+str(out))
    archive_files=files+[ROOT/'FILE_INVENTORY.json',ROOT/'SHA256SUMS.txt']
    with zipfile.ZipFile(out,'x',allowZip64=True) as z:
        for p in archive_files:
            compression=zipfile.ZIP_STORED if p.suffix.lower() in ('.npz','.gz','.png','.zip') else zipfile.ZIP_DEFLATED
            z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix(),compress_type=compression,compresslevel=6)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(archive_files)
        # Rehash every archive member, not only its ZIP CRC.
        expected={r['path']:r['sha256'] for r in rows}
        for member in z.infolist():
            rel=member.filename.removeprefix(ROOT.name+'/')
            if rel in expected:
                with z.open(member) as f:got=hashlib.file_digest(f,'sha256').hexdigest()
                assert got==expected[rel],rel
    receipt=dict(path=str(out),bytes=out.stat().st_size,sha256=sha(out),zip_crc_pass=True,all_member_sha256_pass=True,
                 archive_file_count=len(archive_files),hashed_file_count=len(rows),external_bank_count=len(external),
                 actual_recursions=132,logical_comparisons=144,old_archive_byte_equality='NOT_VERIFIABLE',independent_audit='NOT_PERFORMED_SELF_REVIEW_ONLY')
    target=out.with_name(out.stem+'_DELIVERY.json');target.write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2),flush=True)
if __name__=='__main__':main()
