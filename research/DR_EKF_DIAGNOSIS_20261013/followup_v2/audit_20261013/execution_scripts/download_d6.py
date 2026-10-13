import pathlib, subprocess, json, hashlib, sys, time, urllib.request, concurrent.futures
root = pathlib.Path(__file__).parent
out = root / 'audit_evidence/remote_03e06b55'
cache = out / 'cache'
commit = '03e06b5541e99ee3bbc680fe421701a126d8418b'
prefix = 'research/DR_EKF_DIAGNOSIS_20261013/'
entries = json.loads((cache/'CACHE_D6_MANIFEST.json').read_text())['files']
tree = {line.split('\t')[1]: line.split()[2] for line in (out/'git_tree.txt').read_text().splitlines()}
items = []
for rel, v in entries.items():
    for p in (v['parts'] if v['stored_as']=='parts' else [dict(path=rel, bytes=v['bytes'], sha256=v['sha256'])]):
        full = prefix + 'cache/' + p['path']
        assert full in tree, full
        assert not pathlib.PurePosixPath(p['path']).is_absolute() and '..' not in pathlib.PurePosixPath(p['path']).parts
        items.append((p, tree[full]))
expected = {f'{a}_s8100-8399/{r}_d{lv}.npz' for a in json.loads((out/'D6_SPEC.json').read_text())['arms'] for r in ['R2','R4','R5'] for lv in range(3)}
summary = dict(commit=commit, manifest_count=len(entries), stored_objects=len(items), missing=sorted(expected-set(entries)), extra=sorted(set(entries)-expected), total_bytes=sum(v['bytes'] for v in entries.values()))
(out/'inventory.json').write_text(json.dumps(summary, indent=2))
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()
def fetch(item):
    p, oid = item
    dest=cache/p['path']; dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        assert dest.stat().st_size==p['bytes'] and digest(dest)==p['sha256']
        return p['path']
    temp=dest.with_name(dest.name+'.download')
    url=f'https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/{commit}/{prefix}cache/{p["path"]}'
    for attempt in range(3):
        try:
            subprocess.run(['curl.exe','--fail','--silent','--show-error',
                            '--connect-timeout','15','--max-time','180','--continue-at','-',
                            '--output',str(temp),url],check=True)
            h=hashlib.sha256(); git=hashlib.sha1(f'blob {p["bytes"]}'.encode()+bytes([0])); n=0
            with temp.open('rb') as f:
                for b in iter(lambda:f.read(1024*1024),b''):
                    h.update(b); git.update(b); n+=len(b)
            assert n==p['bytes'] and h.hexdigest()==p['sha256'] and git.hexdigest()==oid, p['path']
            temp.rename(dest)
            return p['path']
        except Exception:
            if attempt==2: raise
started=time.time(); completed=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    futures=[pool.submit(fetch,x) for x in items]
    for future in concurrent.futures.as_completed(futures):
        completed.append(future.result())
        print('VERIFIED',len(completed),'/',len(items),completed[-1],flush=True)
        (out/'download_progress.json').write_text(json.dumps(dict(completed=len(completed),total=len(items),elapsed_s=time.time()-started)))
# All original part digests must pass before invoking the upstream restore.
cmd=[sys.executable,str(out/'package_d6_cache.py'),'restore']
with (out/'restore.log').open('x') as log:
    res=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
assert res.returncode==0, 'restore failed'
for rel,v in entries.items():
    assert (cache/rel).stat().st_size==v['bytes'] and digest(cache/rel)==v['sha256']
(out/'download_receipt.json').write_text(json.dumps(dict(**summary,all_sha256_verified=True,all_git_blob_ids_verified=True,restore_exit_code=res.returncode,elapsed_s=time.time()-started),indent=2))
sys.path.insert(0,str(root/'research/DR_EKF_DIAGNOSIS_20261013/followup_v2'))
import common as C
import v0_cache_audit as V0
report=V0.scan(cache_root=cache,min_age_s=0,hash_ready=True,full_psd=True)
C.write_json_new(out/'V0_UPLOADED_CACHE_AUDIT.json',report)
print(report['status'],report['counts'],flush=True)
