from pathlib import Path
import os,re,zipfile,json,subprocess
from concurrent.futures import ThreadPoolExecutor
a=Path(__file__).resolve().parent
roots=[Path('D:/SLAM_bot'),Path('D:/codex'),Path('D:/codex_runs'),Path('D:/tmp'),Path.home()/'Downloads']
rx=re.compile(r'murec|mu_recursive|exds|39574195919|pj_ds_gated|powerjoint|native[_-]?los|mbvar|mu[_-]?r[_-]?pred',re.I)
model=re.compile(r'\.(pkl|pickle|joblib|skops|onnx|cbm|ubj|model)$',re.I)
arch=re.compile(r'\.zip$',re.I)
def walk(root):
 result=[]; errors=[]; bundles=0; files=0
 for folder,dirs,names in os.walk(root,onerror=lambda e:errors.append(str(e))):
  dirs[:]=[v for v in dirs if v not in {'.git','node_modules','.venv','__pycache__','site-packages'}]
  for name in names:
   path=Path(folder)/name;st=str(path)
   if model.search(name) and rx.search(st):result.append(dict(path=st,type='possible_model'))
   if arch.search(name) and rx.search(st):
    bundles+=1
    try:
     with zipfile.ZipFile(path) as z:
      members=[v for v in z.namelist() if model.search(v) or re.search(r'(?i)(exds|mr_series|murec|mu_r_pred)',v)]
      if members:result.append(dict(path=st,type='zip',members=members[:250],total_matches=len(members)))
    except Exception as e:errors.append(st+' '+type(e).__name__)
   if rx.search(name) and re.search(r'(?i)\.csv(\.gz)?$|\.(npz|parquet)$',name) and re.search('(?i)los|predict',st):result.append(dict(path=st,type='named_prediction_candidate'))
 return dict(root=str(root),archive_count=bundles,matches=result,errors=errors)
with ThreadPoolExecutor(5) as pool:r=list(pool.map(walk,roots))
(a/'LOCAL_INVENTORY.json').write_text(json.dumps(r,indent=2));print([(x['root'],x['archive_count'],len(x['matches'])) for x in r])
