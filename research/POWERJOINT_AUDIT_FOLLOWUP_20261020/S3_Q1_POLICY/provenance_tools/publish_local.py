"""Publish S3-only text evidence in bounded Git API commits; no S0/S1 mutation."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[4];PREFIX='research/POWERJOINT_AUDIT_FOLLOWUP_20261020';HERE=ROOT/PREFIX/'S3_Q1_POLICY'
sys.path.insert(0,str(HERE.parent/'S0_CORRECTIONS'))
from github_io import session,api
def main():
 s=session();branch='research/powerjoint-audit-followup-20261020';head=api(s,'git/ref/heads/'+branch)['object']['sha'];tree_sha=api(s,'git/commits/'+head)['tree']['sha']
 def subtree(path):
  cur=tree_sha
  for part in path.split('/'):
   entry=next((x for x in api(s,'git/trees/'+cur)['tree'] if x['path']==part),None)
   if entry is None:return {}
   cur=entry['sha']
  d=api(s,'git/trees/'+cur,params={'recursive':1});assert not d.get('truncated')
  return {path+'/'+x['path']:x['sha'] for x in d['tree'] if x['type']=='blob'}
 remote=subtree(PREFIX+'/S3_Q1_POLICY');remote.update(subtree('.github/workflows'))
 summary=PREFIX+'/00_SUMMARY_KO.md';r=api(s,'contents/'+summary,params={'ref':head});remote[summary]=r['sha']
 paths=[p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]+[ROOT/summary]+list((ROOT/'.github/workflows').glob('powerjoint-audit-followup-s3-*.yml'))
 pending=[]
 for p in sorted(paths):
  if p.suffix.lower() in ['.npz','.npy','.zip','.pkl','.pickle','.tar','.gz']:continue
  b=p.read_bytes();rel=p.relative_to(ROOT).as_posix();assert len(b)<=20_000_000,(rel,len(b));b.decode('utf-8')
  want=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
  if remote.get(rel)!=want:pending.append((rel,b,want))
 print(json.dumps(dict(parent=head,files=len(pending),bytes=sum(len(b) for _,b,_ in pending))),flush=True);commits=[]
 while pending:
  batch=[];size=0
  while pending and (not batch or size+len(pending[0][1])<=6_000_000):
   item=pending.pop(0);batch.append(item);size+=len(item[1])
  t=api(s,'git/trees',method='POST',json=dict(base_tree=tree_sha,tree=[dict(path=rel,mode='100644',type='blob',content=b.decode('utf-8')) for rel,b,_ in batch]))
  assert api(s,'git/ref/heads/'+branch)['object']['sha']==head,'CONCURRENT_BRANCH_CHANGE'
  c=api(s,'git/commits',method='POST',json=dict(message='S3 preserve full evaluation and verification evidence part '+str(len(commits)+1),tree=t['sha'],parents=[head]))
  api(s,'git/refs/heads/'+branch,method='PATCH',json=dict(sha=c['sha'],force=False));head=c['sha'];tree_sha=t['sha'];commits.append(dict(commit=head,files=len(batch),bytes=size));print(json.dumps(commits[-1]),flush=True)
 receipt=dict(final_commit=head,commits=commits,scope='S3 subtree, S3 workflows, additive root summary only')
 (HERE/'PUBLICATION_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()

