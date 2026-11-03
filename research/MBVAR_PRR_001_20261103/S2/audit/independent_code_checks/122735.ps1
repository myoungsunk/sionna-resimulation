@'
from pathlib import Path
import hashlib,json,subprocess
repo=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');package=Path('research/MBVAR_PRR_001_20261103');code='4eeb7f539ea40fbbc4a4d5eb477d788f2d230945';orig=Path('/mnt/d/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849');cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/S1_INPUTS')
def git(*args,input=None):return subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args],input=input)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['S2/IMPLEMENTATION_RULES.json','S2/OWNER_APPROVAL.json','S2/OWNER_AUTHORIZATION.md','S1/MATERIALIZED_INPUTS.json','S1/EPSILON_INPUTS.json']:
 p=package/name;assert (repo/p).read_bytes()==git('show',code+':'+p.as_posix()),name
files=json.loads((repo/package/'A0_R1/VERIFIED_INPUT_SUBSET.json').read_bytes())['files']
for name in ['LP_plus45_bank.npz','LP_minus45_bank.npz']:assert sha(orig/name)==files[name]
sub='results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb';rev='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13'
paths=['research/FFD_P0P3_20261016/source_model.py','research/FFD_P0P3_20261016/p0_initial.py','research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py']+git('ls-tree','-r','--name-only',rev,sub).decode().splitlines();count=0
for rel in paths:
 if not rel.endswith('.py'):continue
 data=(orig/'p2'/rel).read_bytes();h=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert h==git('rev-parse',rev+':'+rel).decode().strip(),rel;count+=1
mat=json.loads((repo/package/'S1/MATERIALIZED_INPUTS.json').read_bytes());eps=json.loads((repo/package/'S1/EPSILON_INPUTS.json').read_bytes())
for name,h in mat.items():assert sha(cache/name)==h,name
for name,h in eps.items():assert sha(cache/'evaluator_epsilon_r1'/name)==h,name
print(json.dumps(dict(status='PASS',rules_owner_and_manifests_match_frozen_commit=True,source_dependency_blob_matches=count,source_banks=2,materialized_input_files=len(mat),epsilon_files=len(eps),native_runtime_production_validation_inherited_from_S1=True)))
'@ | wsl -d Ubuntu-24.04 env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/home/myoung-sun/.local/share/prr31117 LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib /home/myoung-sun/.local/share/prr31117/bin/python3 -