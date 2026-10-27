"""Copy and validate an existing completed run; never execute experiment stages."""
import argparse,hashlib,json,shutil,tarfile,zipfile,datetime
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    for n in ['run-root','code-root','zip','out']:ap.add_argument('--'+n,required=True)
    a=ap.parse_args();run=Path(a.run_root);code=Path(a.code_root);out=Path(a.out)
    out.mkdir(exist_ok=True)
    assert not (out/'results').exists(),'DELIVERY_ALREADY_EXISTS'
    records=[];inputs={};count=0
    stages=sorted(p for p in run.iterdir() if p.is_dir() and p.name[:2].isdigit())
    assert len(stages)==6
    for d in stages:
        s=json.loads((d/'RUN_STATUS.json').read_text())
        assert s['status']=='CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION'
        checks=json.loads((d/'CHECKS.json').read_text())
        assert all(c['status']=='PASS' for c in checks)
        hashes=json.loads((d/'OUTPUT_SHA256.json').read_text())
        for n,h in hashes.items():assert sha(d/n)==h,(d,n)
        for n,h in s['inputs']['package_code_sha256'].items():assert sha(code/n)==h,n
        for n,h in s['inputs']['input_sha256'].items():
            assert n not in inputs or inputs[n]==h
            inputs[n]=h
        count+=len(hashes)
        records.append({'stage':d.name,'status':s['status'],'hashed_outputs':len(hashes),'checks':len(checks),'max_parity_error':max((c.get('max_abs',0) for c in checks),default=0),'cases':s['inputs']['config']['cases'],'biases':s['inputs']['config']['biases']})
    for n,h in inputs.items():assert sha(Path(n))==h,n
    for n,h in json.loads((run/'ROOT_SHA256.json').read_text()).items():assert sha(run/n)==h,n
    with zipfile.ZipFile(a.zip) as z:
        changed=[]
        for n in z.namelist():
            rel=Path(n).relative_to('DS_REASSESS_V1_20261027')
            if not rel.parts or n.endswith('/'):continue
            dest=out/'code'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            data=(code/rel).read_bytes()
            if data!=z.read(n):changed.append(str(rel))
            dest.write_bytes(data)
        assert changed==['dsreassess\\io.py'] or changed==['dsreassess/io.py'],changed
        old=z.read('DS_REASSESS_V1_20261027/dsreassess/io.py').decode()
        assert (code/'dsreassess/io.py').read_text()==old.replace('import pandas as pd\n','import pandas as pd\nfrom .numerics import wrap\n')
    shutil.copy2(a.zip,out/Path(a.zip).name)
    # Original upstream checksum file covers unpatched ZIP, preserve as provenance.
    original=(out/'code/SHA256SUMS.txt').read_bytes()
    (out/'ORIGINAL_ZIP_SHA256SUMS.txt').write_bytes(original)
    (out/'code/SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.relative_to(out/'code').as_posix()+'\n' for p in sorted((out/'code').rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'))
    for p in run.rglob('*'):
        if p.is_file() and p.suffix!='.npz':
            dest=out/'results'/p.relative_to(run);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    archive=out/'EXECUTION_COMPLETE.tar.gz'
    with tarfile.open(archive,'w:gz') as t:
        for p in sorted(run.rglob('*')):
            if p.is_file():t.add(p,arcname=p.relative_to(run).as_posix())
    with tarfile.open(archive) as t:
        for d in stages:
            for n,h in json.loads((d/'OUTPUT_SHA256.json').read_text()).items():
                assert hashlib.sha256(t.extractfile(d.name+'/'+n).read()).hexdigest()==h
    # Keep each Git blob below GitHub's 100 MiB limit without altering original data.
    chunks=[]
    if archive.stat().st_size>90*1024*1024:
        with archive.open('rb') as f:
            i=0
            while True:
                data=f.read(48*1024*1024)
                if not data:break
                p=out/(archive.name+'.part'+str(i).zfill(3));p.write_bytes(data);chunks.append(p.name);i+=1
        # The complete local archive is retained, excluded from Git by delivery .gitignore.
        (out/'.gitignore').write_text('/EXECUTION_COMPLETE.tar.gz\n')
    else:chunks=[archive.name]
    receipt={'status':'VERIFIED_FOR_UPLOAD','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_run':str(run),'original_code':str(code),'zip_sha256':sha(Path(a.zip)),'originals':'PRESERVED; no moves or deletions','code_change':'dsreassess/io.py: import wrap from .numerics; thresholds unchanged','stages':records,'output_hashes_verified':count,'unique_input_hashes_verified':len(inputs),'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'archive_parts':chunks,'archive_roundtrip_hashes':'ALL_OUTPUTS_PASS','scientific_status':'CODE_EXECUTION_PASS_NOT_SCIENTIFIC_VALIDATION','historical_record':'results/EXECUTION_SUMMARY.json commit_push=NOT_PERFORMED describes pre-upload state; Git commit/remote identifies this delivery','files':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p!=archive}}
    (out/'UPLOAD_VALIDATION.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','output_hashes_verified','unique_input_hashes_verified','archive_bytes','archive_parts']}))

if __name__=='__main__':main()
