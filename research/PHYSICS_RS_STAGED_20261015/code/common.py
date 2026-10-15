from __future__ import annotations
import hashlib,json,os,platform,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'input'
OUT=ROOT/'results'
AUDIT=ROOT/'audit'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,obj):
 Path(p).parent.mkdir(parents=True,exist_ok=True)
 Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def code_hashes():return {p.name:sha(p) for p in sorted((ROOT/'code').glob('*.py'))}
def write_gate(stage,checks):
 gate={'stage':stage,'decision':'GO','checks':checks,'source_hashes':code_hashes(),'environment':{'python':sys.version,'platform':platform.platform(),'numpy':np.__version__}}
 write_json(AUDIT/(stage+'_GO.json'),gate)
def require_gate(stage):
 g=json.loads((AUDIT/(stage+'_GO.json')).read_text());assert g['decision']=='GO'
 for p,s in g['source_hashes'].items():
  assert sha(ROOT/'code'/p)==s,('SOURCE_CHANGED_REAUDIT_REQUIRED',p)
 return g

def setup_original():
 p=INPUT/'research/EKF4_RANGE_S_STAGED_20261014'
 sys.path.insert(0,str(p))
 sys.path.insert(0,str(INPUT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
 return p
