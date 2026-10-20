"""GitHub IO with credentials only in memory; shared by S0 evidence tools."""
import hashlib
import os
from pathlib import Path
import subprocess
import time
import requests
REPO='myoungsunk/sionna-resimulation'
def session():
    token=os.environ.get('GH_TOKEN')
    if not token:
        p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,check=True)
        token=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)['password']
    s=requests.Session();s.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    return s
def api(s,path,method='GET',**kw):
    r=s.request(method,'https://api.github.com/repos/'+REPO+'/'+path,timeout=90,**kw)
    if r.status_code>=400:raise RuntimeError(f'{path}: HTTP{r.status_code} {r.text[:200]}')
    return r.json() if r.content else None
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def download(s,url,path):
    join='&' if '?' in url else '?'
    r=s.get(url+join+'nonce='+str(time.time_ns()),allow_redirects=False,timeout=(20,60))
    if r.status_code in (301,302,303,307,308):
        r=requests.get(r.headers['Location'],stream=True,timeout=(20,120))
    r.raise_for_status();h=hashlib.sha256();n=0
    with Path(path).open('wb') as f:
        for b in r.iter_content(2**20):f.write(b);h.update(b);n+=len(b)
    return h.hexdigest(),n
