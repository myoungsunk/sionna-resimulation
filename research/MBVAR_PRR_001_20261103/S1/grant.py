"""Resolve a phase grant from the published experiment branch before loading S1."""
import hashlib,importlib.metadata,json,os,platform,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[3]
package=Path('research/MBVAR_PRR_001_20261103')
stage=package/'S1'
base=package/'A0_R3_REFIT'
branch='refs/heads/research/mbvar-prr-001-20261103'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
def digest(raw):return hashlib.sha256(raw).hexdigest()
def require(condition,why):
 if not condition:raise RuntimeError(why)
def blob(commit,path):return git('show',commit+':'+path.as_posix())
def pinned(commit,path):
 raw=(repo/path).read_bytes();require(digest(raw)==digest(blob(commit,path)),str(path));return raw
def authorize(phase):
 require(sys.flags.optimize==0,'Python optimizations disable numerical assertions')
 token={'dev':'GO_S1_DEV','eval':'GO_S1_LOCKED_EVAL'}[phase]
 head=git('ls-remote','origin',branch).decode().split()[0]
 grant_path=stage/'audit'/(token+'.json')
 grant=json.loads(blob(head,grant_path));require(grant['token']==token and grant['auditor']=='/root/a0','phase grant')
 code=grant['code_commit']
 require(subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',code,head]).returncode==0,'unpublished code')
 for path in (repo/stage).glob('*.py'):pinned(code,path.relative_to(repo))
 pinned(code,base/'check_base.py')
 mat=pinned(code,stage/'MATERIALIZED_INPUTS.json');require(digest(mat)==grant['materialized_sha256'],'materialized inputs')
 require(digest(pinned(code,stage/'EPSILON_INPUTS.json'))==grant['epsilon_manifest_sha256'],'evaluator epsilon')
 contract_rev='4c99971a60dfee3404c5539d0e3c2f8e50b8f907'
 approved=json.loads(blob('6fecf36b3b206b87a9672243be8ed1be5a69e3c8',base/'independent/SPEC_AUDIT.json'))
 require(approved['decision']=='SPEC_APPROVED' and approved['audited_commit']==contract_rev,'A0')
 receipt=json.loads(pinned(contract_rev,base/'LOCK_RECEIPT.json'))
 for name,h in receipt.items():require(digest(pinned(contract_rev,base/name))==h,name)
 require(grant['contract_sha256']==receipt['CONTRACT_LOCK.json'],'grant contract')
 inputs=json.loads((repo/base/'INPUT_LOCK.json').read_bytes())
 for path,h in inputs['component_hashes'].items():require(digest(pinned(contract_rev,package/path))==h,path)
 contract=json.loads((repo/base/'CONTRACT_LOCK.json').read_bytes())
 for path,h in contract['decision_rules']['document_hashes'].items():require(digest(pinned(contract_rev,package/path))==h,path)
 env=json.loads((repo/base/'ENV_LOCK.json').read_bytes())
 require(sys.version==env['python'] and platform.platform()==env['os'],'runtime platform')
 for name,v in env['packages'].items():require(importlib.metadata.version(name)==v,name)
 for name,v in env['threads'].items():require(os.environ.get(name)==str(v),name)
 if phase=='eval':
  dev=json.loads(blob(head,stage/'audit'/'DEV_RESULTS.json'))
  require(dev['complete'] and dev['code_commit']==code and grant['dev_manifest_sha256']==dev['run_manifest_sha256'],'dev prerequisite')
 return dict(token=token,code_commit=code,source_commit=head,audit_sha256=digest(blob(head,grant_path)),contract_sha256=receipt['CONTRACT_LOCK.json'],input_sha256=digest(mat))
def verify_external():
 local=Path('D:/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849')
 files=json.loads((repo/package/'A0_R1/VERIFIED_INPUT_SUBSET.json').read_bytes())['files']
 for bank in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
  require(digest((local/bank).read_bytes())==files[bank],bank)
 sub='results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/qclean_uwb'
 paths=['research/FFD_P0P3_20261016/source_model.py','research/FFD_P0P3_20261016/p0_initial.py','research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py']
 paths+=git('ls-tree','-r','--name-only','9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13',sub).decode().splitlines()
 for rel in paths:
  if not rel.endswith('.py'):continue
  raw=(local/'p2'/rel).read_bytes()
  oid=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  require(oid==git('rev-parse','9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13:'+rel).decode().strip(),rel)
