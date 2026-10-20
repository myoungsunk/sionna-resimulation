"""Recover newly executed S1 output archives with full SHA/CRC verification."""
from pathlib import Path
import hashlib,json,sys,time,zipfile,os
sys.path.insert(0,r'D:/tmp/sionna-powerjoint-followup-20261020/research/POWERJOINT_AUDIT_FOLLOWUP_20261020/S0_CORRECTIONS')
from github_io import api,session,download
ROOT=Path(r'D:/tmp/pj_s1_output_recovery');ROOT.mkdir(exist_ok=True)
RUNS=[39370673576,39370942876];s=session();seen=set();records=[]
while True:
 complete=True
 for rid in RUNS:
  run=api(s,f'actions/runs/{rid}');complete &= run['status']=='completed'
  (ROOT/f'RUN_{rid}.json').write_text(json.dumps({k:run.get(k) for k in ['id','status','conclusion','head_sha','html_url','created_at','updated_at']},indent=2))
  for meta in api(s,f'actions/runs/{rid}/artifacts',params={'per_page':100})['artifacts']:
   aid=meta['id']
   if aid in seen:continue
   archive=ROOT/f'artifact-{aid}.zip'
   if not archive.exists():dg,size=download(s,meta['archive_download_url'],archive)
   else:
    size=archive.stat().st_size
    with archive.open('rb') as f:dg=hashlib.file_digest(f,'sha256').hexdigest()
   assert meta['digest']=='sha256:'+dg and meta['size_in_bytes']==size,'OUTPUT_ARCHIVE_SHA'
   dest=ROOT/f'run-{rid}'/meta['name'];members=[]
   with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None,'OUTPUT_ARCHIVE_CRC'
    for item in z.infolist():
     if item.is_dir():continue
     rel=Path(item.filename);assert not rel.is_absolute() and '..' not in rel.parts
     members.append({'name':item.filename,'bytes':item.file_size,'CRC32':item.CRC})
     if rel.suffix.lower() not in ['.csv','.json','.md','.py']:continue
     b=z.read(item);target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
     if target.exists():assert target.read_bytes()==b
     else:target.write_bytes(b)
     members[-1]['sha256']=hashlib.sha256(b).hexdigest();members[-1]['summary_extracted']=True
   record={'artifact_id':aid,'name':meta['name'],'actions_run_id':rid,'source_commit':run['head_sha'],'archive_sha256':dg,'archive_bytes':size,'expires_at':meta['expires_at'],'expired':meta['expired'],'full_archive_download_verified':True,'all_member_CRC_verified':True,'members':members}
   dest.mkdir(parents=True,exist_ok=True);(dest/'OUTPUT_ARCHIVE_RECEIPT.json').write_text(json.dumps(record,indent=2))
   records.append(record);seen.add(aid)
   (ROOT/'RECOVERY_RECEIPT.json').write_text(json.dumps({'complete':False,'records':records},indent=2))
   print('OUTPUT_RECOVERED',rid,aid,size,flush=True)
 if complete:
  assert len(records)==10,('EXPECTED10ARTIFACTS',len(records))
  (ROOT/'RECOVERY_RECEIPT.json').write_text(json.dumps({'complete':True,'records':records},indent=2))
  print('ALL_S1_OUTPUTS_RECOVERED',len(records),flush=True);break
 stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
 if stop and Path(stop).exists():raise SystemExit('STOP_REQUESTED')
 time.sleep(30)
