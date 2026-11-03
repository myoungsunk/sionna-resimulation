import datetime,importlib.metadata as md,json,platform,socket,sys
import mitsuba as mi
mi.set_variant('llvm_ad_mono_polarized')
import drjit as dr
import sionna.rt as rt
from pathlib import Path
d=Path('research/DLP_R1B_CH4_20261103')
sys.path.insert(0,str(d/'runtime'))
import r1b_native as native
c,rows=native.load_contract(d/'local_p1_v1/00_LOCAL_EXECUTION_CONTRACT_FROZEN.json')
mods=native.source_modules()
sys.path.insert(0,'scripts')
import corridor_sionna_run as cr
dr.set_thread_count(1)
solver=rt.PathSolver()
assert float(dr.norm(mi.Vector3f(3,4,0))[0])==5
setup=cr.CorridorSetup(anchor_x_m=10.,anchor_y_m=0.)
assert all(v['passed'] for v in setup.validate())
scene,bindings=cr.build_scene(setup,Path('/tmp/scene'))
ref=native.readj(native.resolve(c['inputs']['material_reference']['path']))[0]['material_bindings']
key=lambda b:{x['object']:(x['ply_sha256'],x['itu_type'],x['thickness_m']) for x in b}
assert len(bindings)==6 and key(bindings)==key(ref)
versions={n:md.version(n) for n in c['runtime']['required_packages']}
assert versions==c['runtime']['required_packages'] and platform.python_version()=='3.11.17'
print(json.dumps(dict(status='PASS',scope='P0 import, contract inputs, LLVM, PathSolver construction and frozen six meshes/materials; zero native calls',actual_smoke_test=True,execution_host=socket.gethostname(),python=platform.python_version(),versions=versions,variant=mi.variant(),threads=dr.thread_count(),pose_count=len(rows),mesh_count=len(bindings),native_solver_calls=0,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2))
