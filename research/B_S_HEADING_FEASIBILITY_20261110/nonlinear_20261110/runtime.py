"""Import adapter only; the archived SourceFFD/Bank/observation code is unmodified.
Bypass unrelated LUT and audit-output initialization; pass SHA-verified banks.
"""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import pathlib,sys,types,json,hashlib
import numpy as np
ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT/'vendor'))
import pattern_apply as P,observation as O,corridor
def load_banks():
 records=json.loads((ROOT/'BANK_RECEIPT.json').read_text());banks=[]
 for rec in records:
  q=ROOT/rec['name']
  with q.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==rec['sha256']
  with np.load(q) as a:banks.append(P.Bank(dict(a)))
 return banks
p0=types.ModuleType('p0_initial')
for k,v in dict(load_banks=load_banks,ROOT=ROOT,OUT=ROOT,P=P,O=O,ANCHOR_ROTATION=corridor.ANCHOR_ROTATION).items():setattr(p0,k,v)
sys.modules['p0_initial']=p0
p3=types.ModuleType('p3_rf_adapter4');p3.B_OLD=-0.5315983906250129;sys.modules['p3_rf_adapter4']=p3
from source_model import SourceFFD
SPEC={'anchor':(10.,0.,2.65),'robot_z_m':.45,'mount_deg':0.}
def model():return SourceFFD(banks=load_banks())
def stop_check():
 q=os.environ.get('MANAGED_PROCESS_STOP_FILE')
 if q and pathlib.Path(q).exists():raise RuntimeError('STOP_REQUESTED')
