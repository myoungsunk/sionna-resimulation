"""Run the authorized 41-row refresh against an immutable native geometry revision."""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from rt_cp_uwb_py.g2_native_channel import file_sha
GEOMETRY=ROOT/'results/SIONNA_NATIVE_GEOMETRY_20260925_01a0d83b'
IMAGE='sha256:77244efd2cb92abfc3be258d97da2c76b4c91eeb29e1aeb50d7dc57ed72ad791'
BANK='/home/KMS/SIONNA_NATIVE41_20260925_01a0d812/input/bank'
SSH=['ssh','-o','BatchMode=yes','-o','PasswordAuthentication=no','Snowball']


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,data):Path(path).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf8')
def remote(code):
    r=subprocess.run(SSH+['python3 -'],input=code,text=True,capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr)
    return r.stdout


def prepare(out):
    geometry_status=read(GEOMETRY/'STATUS.json')
    assert geometry_status['status']=='NATIVE_SLAB_GEOMETRY_PASS'
    final=read(GEOMETRY/'FINAL_MANIFEST.json')
    for name,h in final['outputs'].items():assert file_sha(GEOMETRY/name)==h
    out.mkdir(parents=True,exist_ok=False)
    c=read(GEOMETRY/'CONFIG.json')
    c.update(channel_status='SCHEDULED_FOR_RECOMPUTATION',geometry_revision=str(GEOMETRY),
             geometry_manifest_sha256=file_sha(GEOMETRY/'SCENE_MESH_MANIFEST.json'),
             geometry_contract_sha256=file_sha(GEOMETRY/'MODEL_CONTRACT.json'),
             execution_revision=str(out),previous_channels_reused=False)
    write(out/'CONFIG.json',c)
    inputs={str(GEOMETRY/name):file_sha(GEOMETRY/name) for name in
            ['CONFIG.json','SCENE_MESH_MANIFEST.json','MODEL_CONTRACT.json','STATUS.json',
             'FINAL_MANIFEST.json','INDEPENDENT_VERIFICATION.json','RUNTIME_READBACK.json','INPUTS.zip']}
    for s in read(GEOMETRY/'SCENE_MESH_MANIFEST.json')['scenes']:
        for m in s['materials']:
            assert file_sha(GEOMETRY/m['mesh'])==m['sha256']
            inputs[str(GEOMETRY/m['mesh'])]=m['sha256']
    for name,h in c['bank_sha256'].items():
        p=Path(c['bank_root'])/name;assert file_sha(p)==h;inputs[str(p)]=h
    runtime=ROOT/'scripts/g2_completion/sionna_native_runtime.py'
    with zipfile.ZipFile(GEOMETRY/'INPUTS.zip') as old, zipfile.ZipFile(out/'INPUTS.zip','w',zipfile.ZIP_DEFLATED) as new:
        for name in old.namelist():
            if name not in ['CONFIG.json','sionna_native_runtime.py']:new.writestr(name,old.read(name))
        new.write(out/'CONFIG.json','CONFIG.json')
        new.write(runtime,runtime.name)
    inputs[str(runtime)]=file_sha(runtime)
    inputs[str(Path(__file__).resolve())]=file_sha(__file__)
    write(out/'INPUT_MANIFEST.json',dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
        command=sys.argv,config_sha256=file_sha(out/'CONFIG.json'),inputs=inputs,
        payload_sha256=file_sha(out/'INPUTS.zip')))
    return c


def stage(out,hostroot):
    assert subprocess.check_output(SSH+['whoami'],text=True).strip()=='KMS'
    remote("from pathlib import Path\np=Path("+repr(hostroot)+")\np.mkdir(exist_ok=True)\n")
    subprocess.run(['scp','-q','-o','BatchMode=yes',str(out/'INPUTS.zip'),'Snowball:'+hostroot+'/INPUTS.zip'],check=True)
    code="""import hashlib,json,zipfile
from pathlib import Path
root=Path(HOSTROOT);archive=root/'INPUTS.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==PAYLOADSHA
target=root/'input';target.mkdir(exist_ok=True)
with zipfile.ZipFile(archive) as z:
 for name in z.namelist():
  p=target/name;assert target.resolve() in p.resolve().parents
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
c=json.loads((target/'CONFIG.json').read_text())
for name,h in c['bank_sha256'].items():
 assert hashlib.sha256((Path(BANKROOT)/name).read_bytes()).hexdigest()==h
(target/'bank').mkdir(exist_ok=True)
print(json.dumps(dict(status='STAGED_SHA_VERIFIED',rows=len(c['rows']),bank_files=len(c['bank_sha256']))))
"""
    result=remote('HOSTROOT='+repr(hostroot)+'\nPAYLOADSHA='+repr(file_sha(out/'INPUTS.zip'))+'\nBANKROOT='+repr(BANK)+'\n'+code)
    write(out/'STAGING_RECEIPT.json',json.loads(result))


def docker(hostroot,name,start=0,stop=41,smoke=False):
    cmd=['docker','run','--rm','--user','1001:1001','--network','none','--tmpfs','/tmp:rw,size=2g',
         '-e','XDG_CACHE_HOME=/tmp','-e','OPENBLAS_NUM_THREADS=1','-v',hostroot+':/work',
         '-v',BANK+':/work/input/bank:ro','--entrypoint','/opt/rt-env/bin/python',IMAGE,
         '/work/input/sionna_native_runtime.py','--root','/work/input','--out','/work/'+name,
         '--start',str(start),'--stop',str(stop)]
    if smoke:cmd.append('--smoke')
    return cmd


def launch(out,hostroot):
    smoke=docker(hostroot,'smoke',smoke=True)
    with (out/'SMOKE.log').open('x',encoding='utf8') as f:
        r=subprocess.run(SSH+[shlex.join(smoke)],stdout=f,stderr=subprocess.STDOUT)
    assert r.returncode==0,'SMOKE_FAILED'
    smoke_receipt=json.loads(remote("import json\nfrom pathlib import Path\np=Path("+repr(hostroot+"/smoke")+")\nprint(json.dumps(dict(status=json.loads((p/'STATUS.json').read_text()),fixtures=json.loads((p/'LOS_FIXTURE.json').read_text()))))"))
    write(out/'SMOKE_RECEIPT.json',smoke_receipt)
    assert all(t['passed'] for t in smoke_receipt['fixtures'])
    jobs=[dict(name=f'lane_{i:02d}',start=i,stop=min(i+3,41)) for i in range(0,41,3)]
    for j in jobs:j['command']=docker(hostroot,j['name'],j['start'],j['stop'])
    write(out/'NATIVE_INVOCATION.json',dict(user='KMS',docker_image=IMAGE,remote_root=hostroot,
        runner_sha256=file_sha(ROOT/'scripts/g2_completion/sionna_native_runtime.py'),
        command=sys.argv,smoke_command=smoke,jobs=jobs,max_concurrent_containers=8,threads_per_container=4))
    print('SMOKE_PASS; launching 41 rows in 14 jobs, at most 8 containers',flush=True)
    def run(job):
        with (out/(job['name']+'.log')).open('x',encoding='utf8') as f:
            r=subprocess.run(SSH+[shlex.join(job['command'])],stdout=f,stderr=subprocess.STDOUT)
        print(job['name'],r.returncode,flush=True)
        return dict(name=job['name'],exit_code=r.returncode)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(run,jobs))
    write(out/'EXECUTION_RESULTS.json',results)
    assert all(r['exit_code']==0 for r in results),'LANE_FAILURE'


def collect(out,hostroot):
    code="""import hashlib,json,zipfile
from pathlib import Path
r=Path(HOSTROOT)
lanes=[r/f'lane_{i:02d}' for i in range(0,41,3)]
statuses=[json.loads((p/'STATUS.json').read_text()) for p in lanes]
assert all(s['status']=='NATIVE_BAND_COMPUTED' for s in statuses)
assert sum(s['rows'] for s in statuses)==41
files={};runtimes=[]
for lane in lanes:
 runtimes.append(json.loads((lane/'RUNTIME.json').read_text()))
 for p in lane.iterdir():
  if p.name in ['STATUS.json','RUNTIME.json']:continue
  assert p.name not in files;files[p.name]=p
assert len(files)==82 and all(x==runtimes[0] for x in runtimes)
merged=dict(status='NATIVE_BAND_COMPUTED',rows=41,pathsolver_calls=sum(s['pathsolver_calls'] for s in statuses),custom_propagation_calls=0)
assert merged['pathsolver_calls']==31611
digests={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
with zipfile.ZipFile(r/'NATIVE_OUTPUTS.zip','x',zipfile.ZIP_STORED) as z:
 for n,p in files.items():z.write(p,n)
 z.writestr('STATUS.json',json.dumps(merged,indent=2))
 z.writestr('RUNTIME.json',json.dumps(runtimes[0],indent=2))
 z.writestr('REMOTE_OUTPUT_SHA.json',json.dumps(digests,indent=2))
print(json.dumps(dict(status=merged,archive_sha256=hashlib.sha256((r/'NATIVE_OUTPUTS.zip').read_bytes()).hexdigest(),bytes=(r/'NATIVE_OUTPUTS.zip').stat().st_size)))
"""
    receipt=json.loads(remote('HOSTROOT='+repr(hostroot)+'\n'+code))
    write(out/'TRANSFER_RECEIPT.json',receipt)
    archive=out/'NATIVE_OUTPUTS.zip'
    subprocess.run(['scp','-q','-o','BatchMode=yes','Snowball:'+hostroot+'/NATIVE_OUTPUTS.zip',str(archive)],check=True)
    assert file_sha(archive)==receipt['archive_sha256']
    raw=out/'native_raw';raw.mkdir(exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            p=raw/name;assert p.resolve().parent==raw.resolve();p.write_bytes(z.read(name))
    for name,h in read(raw/'REMOTE_OUTPUT_SHA.json').items():assert file_sha(raw/name)==h
    print(json.dumps(receipt),flush=True)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--resume-prepared',action='store_true')
    a=ap.parse_args();out=a.out.resolve()
    assert out.is_relative_to(ROOT/'results')
    assert out.exists() if a.resume_prepared else not out.exists()
    hostroot='/home/KMS/'+out.name
    if a.dry_run:
        print(json.dumps(dict(rows=41,bins=257,arms=3,production_calls=31611,smoke_calls=18,
                              geometry=str(GEOMETRY),out=str(out),remote=hostroot,max_containers=8)))
        return
    if a.resume_prepared:
        manifest=read(out/'INPUT_MANIFEST.json')
        old=manifest['inputs'].pop(str(Path(__file__).resolve()))
        preserved=out/'PREPARATION_RUNNER_ORIGINAL.py'
        assert file_sha(preserved)==old
        assert all(file_sha(p)==h for p,h in manifest['inputs'].items())
        assert file_sha(out/'INPUTS.zip')==manifest['payload_sha256']
        write(out/'INPUT_MANIFEST_PREPARATION.json',read(out/'INPUT_MANIFEST.json'))
        manifest['inputs'][str(preserved)]=old
        manifest['inputs'][str(Path(__file__).resolve())]=file_sha(__file__)
        write(out/'INPUT_MANIFEST.json',manifest)
    else:prepare(out)
    stage(out,hostroot);launch(out,hostroot);collect(out,hostroot)


if __name__=='__main__':main()
