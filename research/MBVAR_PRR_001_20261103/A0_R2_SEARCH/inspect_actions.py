import csv, gzip, hashlib, io, json, pathlib, subprocess, zipfile, requests
a=pathlib.Path(__file__).resolve().parent
base='https://api.github.com/repos/myoungsunk/sionna-resimulation/actions/'
s=requests.Session()
cred=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=False)
for line in cred.stdout.splitlines():
 if line.startswith('password='):s.headers['Authorization']='Bearer '+line.split('=',1)[1]
def get(url):
 r=s.get(url,timeout=35);r.raise_for_status();return r
workflows=get(base+'workflows?per_page=100').json()
import re
names=subprocess.check_output(['git','ls-tree','-r','--name-only','7e28553','.github/workflows'],text=True).splitlines()
selected=[p.split('/')[-1] for p in names if re.search('powerjoint-(?:ds-gated-(?:murec|strict|hgate|hpath|d0var)|method-a-ds-mean)',p)]
report=[]
for wf in selected:
 runs=get(base+'workflows/'+wf+'/runs?per_page=100').json()['workflow_runs']
 for run in runs:
  if run['conclusion']!='success':continue
  arts=get(base+'runs/'+str(run['id'])+'/artifacts?per_page=100').json()['artifacts']
  for art in arts:
   if not any(k in art['name'].lower() for k in ('r4_ab_m0','r5_ab_m0')):continue
   rec=dict(workflow=wf,run=run['id'],id=art['id'],name=art['name'],expired=art['expired']);report.append(rec)
   if not art['expired']:
    r=s.get(art['archive_download_url'],timeout=50);rec['http']=r.status_code
    if r.ok:
     rec['sha256']=hashlib.sha256(r.content).hexdigest();z=zipfile.ZipFile(io.BytesIO(r.content)); members={}
     for p in z.namelist():
      m={};members[p]=m
      if p.endswith(('.csv','.csv.gz')):
       raw=z.read(p);raw=gzip.decompress(raw) if p.endswith('.gz') else raw
       rows=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')));fields=rows.fieldnames or [];m['has_pose_id']='pose_id' in fields;m['related_columns']=[v for v in fields if re.search(r'EXDS|mu_r|predict',v,re.I)][:12];m['channels']=sorted({row.get('channel','unspecified') for row in rows})
     rec['members']=members
   (a/'ACTIONS_ARCHIVES.json').write_text(json.dumps(report,indent=2))
print('archives',len(report),[(r['name'],r.get('http')) for r in report])
