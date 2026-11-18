"""Load converted geometry through the unchanged native producer on Snowball/KMS."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile

IMAGE = 'sha256:77244efd2cb92abfc3be258d97da2c76b4c91eeb29e1aeb50d7dc57ed72ad791'
REMOTE = r'''
import base64,hashlib,io,json,sys,zipfile,importlib.metadata
from pathlib import Path
import numpy as np
root=Path('/tmp/native_geometry');root.mkdir()
with zipfile.ZipFile(io.BytesIO(base64.b64decode(PAYLOAD))) as z:
 for name in z.namelist():
  dest=root/name
  assert dest.resolve().is_relative_to(root)
  dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(name))
sys.path.insert(0,str(root))
import sionna_native_runtime as native
mi,dr,rt=native.mi,native.dr,native.rt
dr.set_thread_count(2)
from sionna.rt.radio_materials import itu
contract=json.loads((root/'SOURCE_MATERIAL_CONTRACT.json').read_text())
assert hashlib.sha256(Path(itu.__file__).read_bytes()).hexdigest()==contract['itu_source']['sha256']
c=json.loads((root/'CONFIG.json').read_text())
manifest={s['scene_id']:s for s in json.loads((root/'SCENE_MESH_MANIFEST.json').read_text())['scenes']}
class Port:
 def evaluate(self,theta,phi):
  return mi.Complex2f(dr.ones(mi.Float,dr.width(theta)),0),mi.Complex2f(0,0)
ports=[Port(),Port()]
def scalar(x):return float(np.asarray(x).ravel()[0])
def ply(path):
 with path.open() as f:
  assert f.readline().strip()=='ply';assert f.readline().strip()=='format ascii 1.0'
  for line in f:
   if line.startswith('element vertex'):nv=int(line.split()[-1])
   if line.startswith('element face'):nf=int(line.split()[-1])
   if line.strip()=='end_header':break
  v=np.array([[float(x) for x in f.readline().split()] for _ in range(nv)])
  faces=np.array([[int(x) for x in f.readline().split()[1:]] for _ in range(nf)],dtype=np.uint32)
 return v,faces
rows=[]
for sid in manifest:
 row=next((dict(r) for r in c['rows'] if r['scene_id']==sid),None)
 if row is None:row=dict(scene_id=sid,tx=[0,0,1],rx=[1,0,1],tx_rotation=np.eye(3).tolist(),rx_rotation=np.eye(3).tolist())
 row.pop('dynamic_panel',None);row['check_scope']='BASE_SCENE';rows.append(row)
for original in c['rows']:
 if original.get('dynamic_panel'):
  row=dict(original);row['check_scope']='DYNAMIC_OVERLAY';rows.append(row)
geometry=[];materials=[];failures=[]
frequencies=6250400000.+1950000.*np.arange(257)
for index,row in enumerate(rows):
 scene,bindings=native.make_scene(root,row,manifest,ports,ports)
 expected=list(manifest[row['scene_id']]['materials'])
 if row.get('dynamic_panel'):
  expected.append(dict(mesh=row['dynamic_panel'],object_name='dynamic_panel',material_id='metal',thickness_m=.001))
 assert set(scene.objects)=={m['object_name'] for m in expected}
 for m in expected:
  path=root/m['mesh']
  if 'sha256' in m:assert hashlib.sha256(path.read_bytes()).hexdigest()==m['sha256']
  obj=scene.objects[m['object_name']];v,f=ply(path)
  rv=np.asarray(obj.mi_mesh.vertex_positions_buffer()).reshape(-1,3);rf=np.asarray(obj.mi_mesh.faces_buffer()).reshape(-1,3)
  ok=np.array_equal(rv,v.astype(np.float32)) and np.array_equal(rf,f)
  geometry.append(dict(scene_id=row['scene_id'],scope=row['check_scope'],object=m['object_name'],vertices=len(v),triangles=len(f),passed=bool(ok)))
  if not ok:failures.append(['GEOMETRY',row['scene_id'],m['object_name']])
 summaries={m['object_name']:dict(scene_id=row['scene_id'],scope=row['check_scope'],object=m['object_name'],material=m['material_id'],bins=0,failed=0,max_error=0.) for m in expected}
 for freq in frequencies:
  scene.frequency=float(freq)
  for m in expected:
   obj=scene.objects[m['object_name']];mat=obj.radio_material
   eps,sig,th=scalar(mat.relative_permittivity),scalar(mat.conductivity),scalar(mat.thickness)
   if m['material_id']=='EPS4_LOSSLESS':ee,es=4.,0.
   else:
    a,b,cc,d=contract['materials'][m['material_id']]['coefficients_abcd'];ee=a*(freq/1e9)**b;es=cc*(freq/1e9)**d
   error=max(abs(eps-ee)/max(1,abs(ee)),abs(sig-es)/max(1e-6,abs(es)))
   ok=error<5e-6 and abs(th-m['thickness_m'])<1e-7 and type(mat) in (rt.RadioMaterial,rt.ITURadioMaterial)
   summary=summaries[m['object_name']];summary['bins']+=1;summary['failed']+=int(not ok);summary['max_error']=max(summary['max_error'],error)
 materials.extend(summaries.values())
 if any(x['failed'] for x in summaries.values()):failures.append(['MATERIAL',row['scene_id']])
 if (index+1)%10==0:print(json.dumps(dict(loaded=index+1,total=len(rows))),flush=True)
result=dict(status='PASS_NATIVE_SCENE_READBACK' if not failures else 'FAIL',scene_count=len(manifest),
 dynamic_overlays=len(rows)-len(manifest),geometry=geometry,materials=materials,failures=failures,
 versions={n:importlib.metadata.version(n) for n in ['sionna-rt','mitsuba','drjit']},
 material_frequency_checks=sum(r['bins'] for r in materials),pathsolver_calls=0,
 source_runtime_sha256=hashlib.sha256((root/'sionna_native_runtime.py').read_bytes()).hexdigest(),
 scope='unchanged native producer scene factory; geometry/material readback only, no RF propagation')
print('RESULT_JSON='+json.dumps(result),flush=True)
if failures:raise SystemExit(1)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--attempt', default='01')
    a = ap.parse_args()
    out = a.out.resolve()
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'PasswordAuthentication=no', 'Snowball']
    def query(args):
        return subprocess.check_output(ssh+[shlex.join(args)], text=True).strip()
    assert query(['whoami']) == 'KMS'
    uid, gid = query(['id','-u']), query(['id','-g'])
    assert uid != '0'
    source = Path(json.loads((out/'RUN_CONFIG.json').read_text())['source_root'])
    payload = io.BytesIO((out/'INPUTS.zip').read_bytes())
    with zipfile.ZipFile(payload, 'a', zipfile.ZIP_DEFLATED) as z:
        z.write(source/'MATERIAL_CONTRACT.json', 'SOURCE_MATERIAL_CONTRACT.json')
    script = 'PAYLOAD='+repr(base64.b64encode(payload.getvalue()).decode())+'\n'+REMOTE
    cmd = ['docker','run','--rm','-i','--network','none','--read-only','--user',uid+':'+gid,
           '--tmpfs','/home/kms/.drjit:rw,mode=1777,size=256m',
           '--tmpfs','/tmp:rw,nosuid,size=1g','-e','XDG_CACHE_HOME=/tmp','-e','PYTHONDONTWRITEBYTECODE=1',
           '--entrypoint','/opt/rt-env/bin/python',IMAGE,'-']
    invocation = dict(user='KMS', command=cmd, local_command=sys.argv,
        payload_sha256=hashlib.sha256(payload.getvalue()).hexdigest(),
        script_sha256=hashlib.sha256(script.encode()).hexdigest(),
        validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        material_contract_path=str(source/'MATERIAL_CONTRACT.json'),
        material_contract_sha256=hashlib.sha256((source/'MATERIAL_CONTRACT.json').read_bytes()).hexdigest())
    prefix = 'RUNTIME_A'+a.attempt
    (out/(prefix+'_INVOCATION.json')).write_text(json.dumps(invocation,indent=2))
    with (out/(prefix+'_RAW.log')).open('x',encoding='utf8') as log, (out/(prefix+'_STDERR.log')).open('x',encoding='utf8') as err:
        process = subprocess.run(ssh+[shlex.join(cmd)], input=script, text=True, encoding='utf8', stdout=log, stderr=err)
    lines=(out/(prefix+'_RAW.log')).read_text().splitlines()
    results=[line[len('RESULT_JSON='):] for line in lines if line.startswith('RESULT_JSON=')]
    if results:
        result=json.loads(results[-1])
        (out/'RUNTIME_READBACK.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k not in ['geometry','materials']}))
    if process.returncode or not results:
        raise RuntimeError('NATIVE_RUNTIME_FAILED; inspect RUNTIME_STDERR.log')


if __name__ == '__main__':
    main()
