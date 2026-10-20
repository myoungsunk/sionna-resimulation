"""Read two preserved P1 pickles as plain parameter bags, without refitting."""
from pathlib import Path
import base64,hashlib,io,json,pickle,sys,zipfile
import numpy as np
sys.path.insert(0,'D:/tmp')
from powerjoint_github import session,api

class Bag:pass
class Reader(pickle.Unpickler):
 def find_class(self,module,name):
  if (module,name) in [('scalar_power','ScalarPower'),('sklearn.preprocessing._data','StandardScaler'),('sklearn.linear_model._ridge','Ridge')]:return Bag
  return super().find_class(module,name)
def canonical(x):
 if isinstance(x,np.ndarray):return dict(dtype=x.dtype.str,shape=list(x.shape),values=x.tolist())
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,Bag):return {k:canonical(v) for k,v in sorted(vars(x).items())}
 if isinstance(x,dict):return {k:canonical(v) for k,v in sorted(x.items())}
 if isinstance(x,(list,tuple)):return [canonical(v) for v in x]
 return x
def main():
 out=Path('D:/tmp/pj_s3_p1_diagnostic');out.mkdir(exist_ok=True);s=session();models=[]
 for aid in [12244179573,12244314247,12244314301,12244224044,12244419862]:
  meta=api(s,f'actions/artifacts/{aid}');p=out/f'{aid}.zip'
  if not p.exists():
   r=s.get(meta['archive_download_url'],timeout=180);r.raise_for_status();p.write_bytes(r.content)
  b=p.read_bytes();dg=hashlib.sha256(b).hexdigest();assert meta['digest']=='sha256:'+dg
  with zipfile.ZipFile(p) as z:
   assert z.testzip() is None;name=next(n for n in z.namelist() if n.endswith('P1_MODEL.json'));m=json.loads(z.read(name));model=Reader(io.BytesIO(base64.b64decode(m['model']['base64']))).load();params=canonical(model);c=json.dumps(params,sort_keys=True,allow_nan=False,separators=(',',':'));(out/f'{aid}.json').write_text(json.dumps(params,indent=2));models.append(dict(artifact_id=aid,fold=[m['outer'],m['inner_route']],archive_sha256=dg,pickle_sha256=m['model']['sha256'],canonical_sha256=hashlib.sha256(c.encode()).hexdigest(),parameters=params))
 diff=[]
 def compare(a,b,path=''):
  if isinstance(a,dict) and isinstance(b,dict):
   for k in sorted(set(a)|set(b)):compare(a.get(k),b.get(k),path+'/'+k)
  elif a!=b:diff.append(dict(path=path,a=a,b=b))
 groups={}
 for model in models:
  key=tuple(model['fold'])
  if key in groups:compare(groups[key]['parameters'],model['parameters'],str(model['artifact_id']))
  else:groups[key]=model
 report=dict(models=[{k:v for k,v in m.items() if k!='parameters'} for m in models],differences=diff);(out/'DIAGNOSIS.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
if __name__=='__main__':main()
