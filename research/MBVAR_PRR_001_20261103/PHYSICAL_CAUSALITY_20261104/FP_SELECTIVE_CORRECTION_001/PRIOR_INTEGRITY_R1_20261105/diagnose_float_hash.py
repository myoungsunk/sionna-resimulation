"""Posthoc single-waveform float diagnostic; not a whole-corpus tolerance gate."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import sys,json,gzip,hashlib,subprocess
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[5];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.candidate_revision import generate_revision
from qclean_uwb.fp_sc.revision_corpus import production_cir
P=Path(__file__).parent;B=P.parent
source=B/'E1_20261105/CANDIDATE_REVISION_R1_20261105/RUN_001/VAB/TRACE_PARTS/POOLS.ndjson.gz.part001'
with gzip.open(source,'rt') as f:old=json.loads(f.readline())
m=json.loads((B/'DYNAMIC_MAPPING_R1_20261105/FINAL_PREPARATION_MANIFEST.json').read_text());spec=m['cases']['R2_B0_Full_10']
with np.load(R/spec['online_npz']) as z:new=generate_revision(production_cir(z['Hrf'][0]),'VAB')['TWO_PORT_UNION']
prev=old['pools']['TWO_PORT_UNION'];diff=[]
def compare(a,b,path):
 if isinstance(a,dict) and isinstance(b,dict):
  for k in sorted(set(a)|set(b)):
   if k in ('pool_hash','lobes'):continue
   if k not in a or k not in b:diff.append(dict(path=path+'/'+k,kind='KEY'))
   else:compare(a[k],b[k],path+'/'+k)
 elif isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b):diff.append(dict(path=path,kind='LENGTH'))
  else:
   for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
 elif a!=b:diff.append(dict(path=path,kind='NUMERIC' if isinstance(a,(int,float)) and isinstance(b,(int,float)) else 'OTHER',old=a,new=b))
compare(prev,new,'')
result=dict(scope='POSTHOC_ONE_WAVEFORM_SAMPLE_ONLY',packet_uid=old['packet_uid'],arm='VAB',mode='TWO_PORT_UNION',
    old_pool_hash=prev['pool_hash'],new_pool_hash=new['pool_hash'],differences=diff,
    max_numeric_abs_difference=max((abs(d['old']-d['new']) for d in diff if d['kind']=='NUMERIC'),default=0),
    nonnumeric_differences=sum(d['kind']!='NUMERIC' for d in diff),
    whole_corpus_float_parity='NOT_TESTED',whole_corpus_bytewise_parity=False,
    code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
    source_part_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    online_input_sha256=hashlib.sha256((R/spec['online_npz']).read_bytes()).hexdigest(),E1_02_started=False,E2_started=False)
(P/'FLOAT_HASH_DIAGNOSTIC.json').write_text(json.dumps(result,indent=2)+'\n')
print(result['max_numeric_abs_difference'],result['nonnumeric_differences'])
