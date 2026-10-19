from pathlib import Path
import os,json,urllib.request,urllib.error,hashlib,time
out=Path('external_inventory');out.mkdir(exist_ok=True)
class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def fetch(url,auth=False,octet=False):
    headers={'Accept':'application/octet-stream' if octet else 'application/vnd.github+json','Cache-Control':'no-cache'}
    if auth:headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
    req=urllib.request.Request(url,headers=headers)
    try:r=urllib.request.build_opener(NR()).open(req,timeout=60)
    except urllib.error.HTTPError as e:
        if e.code not in (301,302,303,307,308):raise
        r=urllib.request.urlopen(e.headers['Location'],timeout=90)
    with r:return r.read()
records=[]
for route in ['c01','c02','c03','o01','o02']:
    tag=f'route-rf-{route}-20261019-r01';url='https://api.github.com/repos/myoungsunk/sionna-resimulation/releases/tags/'+tag
    release=json.loads(fetch(url,True));assets=release['assets'];receipts=[a for a in assets if a['name'].endswith('RECEIPT.json')]
    rec={'route':route,'tag':tag,'published':release['published_at'],'assets':[{'name':a['name'],'bytes':a['size'],'sha256':a.get('digest'),'url':a['browser_download_url']} for a in assets]}
    for asset in receipts:
        try:b=fetch(asset['browser_download_url'])
        except Exception:b=fetch(asset['url']+'?nonce='+str(time.time_ns()),True,True)
        (out/asset['name']).write_bytes(b);d=json.loads(b);rec['receipt_top_keys']=list(d);rec['receipt_sha256']=hashlib.sha256(b).hexdigest()
        print('RECEIPT',route,json.dumps(d)[:9000],flush=True)
    records.append(rec)
(out/'DELIVERY_INVENTORY.json').write_text(json.dumps(records,indent=2));print('DELIVERY_INVENTORY',json.dumps(records),flush=True)
