import pathlib, subprocess, json, hashlib, datetime, re
ROOT=pathlib.Path(__file__).resolve().parent
REPO=ROOT/'checkout'
B=REPO/'results/DRIVE_SIM_20261007'
def git(*args):
    return subprocess.check_output(['git',*args],cwd=REPO)
def sha(data): return hashlib.sha256(data).hexdigest()
out={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':git('rev-parse','HEAD').decode().strip(),'working_tree':git('status','--porcelain').decode(),'external_read_only':True}
out['A14_diff_files']=git('diff','--name-only','13caea1^','13caea1').decode().splitlines()
out['guide_diff_files']=git('diff','--name-only','155bf5a^','155bf5a').decode().splitlines()
out['prereg_unchanged_from_original']=git('show','02009ca:results/DRIVE_SIM_20261007/S0/PREREG.json')==git('show','HEAD:results/DRIVE_SIM_20261007/S0/PREREG.json')
out['prereg_sha256']=sha(git('show','HEAD:results/DRIVE_SIM_20261007/S0/PREREG.json'))
out['hash_policy']='Canonical Git blob bytes, because Windows working copy uses CRLF; remote bytes are read unchanged.'
amend='results/DRIVE_SIM_20261007/S0/PREREG_AMENDMENTS.md'
intro={}
for commit in git('log','--reverse','--format=%H','--',amend).decode().splitlines():
    text=git('show',commit+':'+amend).decode('utf-8')
    for label in re.findall(r'^#{2,3} (A\d+(?:[bc])?)(?: —| result)',text,re.M):
        if label not in intro:
            intro[label]={'commit':commit,'date_utc':git('show','-s','--format=%cI',commit).decode().strip()}
out['amendment_first_committed']=intro
final=B/'SNOWBALL_ROUTE_RUNS/01a11669/final_20261007T140446Z'
manifest=json.loads((final/'TRANSFER_MANIFEST.json').read_text())['files_sha256']
verified=[]; pointers=[]; mismatches=[]; missing=[]
for name,expected in manifest.items():
    p=final/name
    if not p.exists(): missing.append(name); continue
    data=git('show','HEAD:'+p.relative_to(REPO).as_posix())
    if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
        pointers.append({'path':name,'oid':re.search(rb'oid sha256:(\w+)',data).group(1).decode(),'matches_manifest_oid':expected.encode() in data})
    elif sha(data)==expected: verified.append(name)
    else: mismatches.append({'path':name,'expected':expected,'actual':sha(data)})
out['transfer_local']={'verified_files':len(verified),'mismatches':mismatches,'missing':missing,'lfs_pointers':pointers}
remote_code=r'''import pathlib,json,hashlib
roots={'r1':pathlib.Path('/home/KMS/COOL_DIJKSTRA_20261007_01a11582/source'),'routes':pathlib.Path('/home/KMS/DRIVE_SIM_ROUTES_20261007_01a11669/source')}
out={}
def h(p):
    d=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):d.update(b)
    return d.hexdigest()
for kind,root in roots.items():
    files=list((root/'src/qclean_uwb/drivesim').glob('*.py'))+list((root/'scripts/drive_sim').glob('*.py'))+[root/'scripts/corridor_sionna_run.py',root/'src/qclean_uwb/scenarios/corridor.py']
    d=root/'results/DRIVE_SIM_20261007'
    out[kind]={'code':{str(p.relative_to(root)):h(p) for p in files if p.is_file()},'H':{},'banks':{},'headers':{},'S6_hashes':{},'execution_logs':{}}
    for p in sorted(d.rglob('H_*.npy')):
        out[kind]['H'][str(p.relative_to(root))]={'sha256':h(p),'bytes':p.stat().st_size}
    for name in ['LP_plus45_bank.npz','LP_minus45_bank.npz']:
        p=root/name
        if p.is_file():out[kind]['banks'][name]={'sha256':h(p),'bytes':p.stat().st_size}
    for p in sorted(d.rglob('hs_lut_2deg.npy')):
        out[kind]['headers'][str(p.relative_to(root))]={'sha256':h(p),'bytes':p.stat().st_size}
    for p in sorted((d/'SNOWBALL_ROUTES_01a11669/S6_routes').rglob('*')):
        if p.is_file():out[kind]['S6_hashes'][str(p.relative_to(d/'SNOWBALL_ROUTES_01a11669'))]=h(p)
    for p in root.parent.glob('*EXECUTION*.jsonl'):
        out[kind]['execution_logs'][p.name]={'sha256':h(p),'content':p.read_text()}
print(json.dumps(out))
'''
p=subprocess.run(['ssh','-o','BatchMode=yes','-o','PasswordAuthentication=no','-o','ConnectTimeout=10','Snowball','python3 -'],input=remote_code.encode(),capture_output=True,timeout=180)
out['remote_exit']=p.returncode
out['remote_stderr']=p.stderr.decode()
if p.returncode==0:
    remote=json.loads(p.stdout); out['remote']=remote
    out['executed_code_correspondence']={}
    for kind,rev in [('r1','1b9cf190244f91d0097a82106a02ec1dd5f53220'),('routes','0d4588f79116e221d874307f233d69ff0b13d99c')]:
        changed=[]; exact=[]
        for name,digest in remote[kind]['code'].items():
            try: exp=sha(git('show',rev+':'+name))
            except subprocess.CalledProcessError: exp=None
            (exact if exp==digest else changed).append(name)
        out['executed_code_correspondence'][kind]={'revision':rev,'exact_count':len(exact),'mismatches':changed}
    historical=json.loads((B/'SNOWBALL_ROUTE_RUNS/01a11669/g3_recheck_20261008/UNCHANGED_H_S6_VERIFICATION.json').read_text())
    out['route_H_hashes_vs_recheck']={pathlib.PurePosixPath(k).name:v['sha256']==historical['H_hashes'].get(pathlib.PurePosixPath(k).name) for k,v in remote['routes']['H'].items()}
    out['route_S6_local_hashes_vs_recheck']={k:sha(git('show','HEAD:'+(final/k).relative_to(REPO).as_posix()))==v for k,v in historical['S6_hashes'].items() if (final/k).exists()}
    out['route_S6_remote_hashes_vs_recheck']={k:remote['routes']['S6_hashes'].get(k.removeprefix('results/'))==v for k,v in historical['S6_hashes'].items()}
(ROOT/'provenance_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k not in ['remote','transfer_local','route_S6_local_hashes_vs_recheck']},ensure_ascii=False,indent=2))
print('transfer summary',len(verified),'verified;',len(mismatches),'mismatches;',len(pointers),'LFS pointers;',len(missing),'missing')
print('S6 recheck hashes',sum(out.get('route_S6_local_hashes_vs_recheck',{}).values()),'/',len(out.get('route_S6_local_hashes_vs_recheck',{})))
