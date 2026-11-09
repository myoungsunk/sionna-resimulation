"""Post-audit Git tree append; original source/data untouched."""
import base64,json,os,time,urllib.request
from pathlib import Path
REPO='myoungsunk/sionna-resimulation'
def call(path,method='GET',obj=None):
    b=None if obj is None else json.dumps(obj).encode();h={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'PALO-V2-audit'}
    if b is not None:h['Content-Type']='application/json'
    last=None
    for i in range(4):
        try:
            req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,data=b,headers=h,method=method)
            with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
        except Exception as ex:last=ex;time.sleep(2**i)
    raise RuntimeError('Publish failed '+path+' '+str(last))
def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--phase',required=True);p.add_argument('--result',required=True);a=p.parse_args();root=Path(a.result)
    assert json.loads((root/'INDEPENDENT_ARITHMETIC_AUDIT.json').read_text())['status']=='PASS'
    ref='/git/ref/heads/'+os.environ['TARGET_BRANCH'].replace('/','%2F');parent=call(ref)['object']['sha'];assert parent==os.environ['GITHUB_SHA'],'Concurrent branch change'
    tree=call('/git/commits/'+parent)['tree']['sha'];items=[];prefix='research/PALO_IMM_V2_20261109/runs/'+os.environ['GITHUB_RUN_ID']
    for directory,target in [(root,'results'),(Path('source'),'executed_source'),(Path('prep'),'prep')]:
        if not directory.exists():continue
        for f in sorted(directory.rglob('*')):
            if not f.is_file() or '__pycache__' in str(f):continue
            blob=call('/git/blobs','POST',{'content':base64.b64encode(f.read_bytes()).decode(),'encoding':'base64'})['sha']
            items.append({'path':prefix+'/'+target+'/'+str(f.relative_to(directory)).replace('\\','/'),'mode':'100644','type':'blob','sha':blob})
    for st in range(0,len(items),8):tree=call('/git/trees','POST',{'base_tree':tree,'tree':items[st:st+8]})['sha']
    commit=call('/git/commits','POST',{'tree':tree,'parents':[parent],'message':'PALO IMM '+a.phase+': raw trajectories, executed code and arithmetic audit; no calibration claim'})['sha']
    assert call(ref)['object']['sha']==parent
    call('/git/refs/heads/'+os.environ['TARGET_BRANCH'].replace('/','%2F'),'PATCH',{'sha':commit,'force':False})
    print('PUBLISHED',commit,'FILES',len(items),flush=True)
if __name__=='__main__':main()
