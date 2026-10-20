"""Compare every recovered upstream P1 field without fitting or changing labels."""
from pathlib import Path
import base64,hashlib,io,json
import numpy as np
from diagnose_p1_storage import Reader,canonical

def main():
 root=Path('D:/tmp/pj_s3_verified_recovery/run-39378144903');groups={};records=[];diff=[]
 def compare(a,b,path):
  if isinstance(a,dict) and isinstance(b,dict):
   for k in sorted(set(a)|set(b)):compare(a.get(k),b.get(k),path+'/'+k)
  elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
   for j,(aa,bb) in enumerate(zip(a,b)):compare(aa,bb,path+'/'+str(j))
  elif a!=b:
   try:
    aa=np.asarray(a,dtype=float);bb=np.asarray(b,dtype=float);maximum=float(np.max(abs(aa-bb))) if aa.shape==bb.shape else None
   except (ValueError,TypeError):maximum=None
   diff.append(dict(path=path,maximum_abs=maximum,a=a,b=b))
 for p in sorted(root.rglob('P1_MODEL.json')):
  m=json.loads(p.read_text());obj=Reader(io.BytesIO(base64.b64decode(m['model']['base64']))).load();params=canonical(obj);key=m['outer']+'_'+m['inner_route'];dg=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest();records.append(dict(path=str(p),fold=key,pickle_sha256=m['model']['sha256'],canonical_sha256=dg))
  if key in groups:compare(groups[key],params,str(p))
  else:groups[key]=params
 report=dict(n_models=len(records),records=records,differences=diff,nonnumeric_differences=sum(r['maximum_abs'] is None for r in diff),maximum_numeric_difference=max((r['maximum_abs'] for r in diff if r['maximum_abs'] is not None),default=0.));out=Path('D:/tmp/pj_s3_p1_diagnostic/DIAGNOSIS_ALL_P1.json');out.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['records','differences']}),flush=True)
if __name__=='__main__':main()
