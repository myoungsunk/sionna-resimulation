from pathlib import Path
import subprocess,json,hashlib,concurrent.futures,datetime,tarfile
J=Path('/home/KMS/DRIVE_SIM_HEADING_SENSOR_V2_20261010_01a124ff')
names=subprocess.check_output(['docker','ps','-a','--filter','name=drive-heading-v2','--format','{{.Names}}'],universal_newlines=True).splitlines();names=[n for n in names if n.endswith('01a124ff')];records=[];(J/'LOGS').mkdir(exist_ok=True)
for name in names:
 a=json.loads(subprocess.check_output(['docker','inspect',name],universal_newlines=True))[0];records.append({'name':name,'image_id':a['Image'],'started_at':a['State']['StartedAt'],'finished_at':a['State']['FinishedAt'],'exit_code':a['State']['ExitCode'],'status':a['State']['Status'],'command':a['Config']['Cmd'],'mounts':[{k:m[k] for k in ['Source','Destination','RW']} for m in a['Mounts']],'cpu_nanocpus':a['HostConfig']['NanoCpus'],'memory_bytes':a['HostConfig']['Memory']});r=subprocess.run(['docker','logs',name],stdout=subprocess.PIPE,stderr=subprocess.STDOUT);(J/'LOGS'/f'{name}.log').write_bytes(r.stdout)
(J/'EXECUTION_CONTAINERS.json').write_text(json.dumps(records,indent=2));print('containers',len(records),flush=True)
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return {'path':str(p.relative_to(J)),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
files=sorted(p for p in J.rglob('*') if p.is_file() and p.suffix!='.tar' and p.name not in ['OUTPUT_MANIFEST.json','DELIVERY_SUMMARY.tar.gz'])
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:rows=list(ex.map(hashfile,files))
(J/'OUTPUT_MANIFEST.json').write_text(json.dumps({'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':rows,'total_bytes':sum(r['bytes'] for r in rows),'source_preserved':True},indent=2))
with tarfile.open(J/'DELIVERY_SUMMARY.tar.gz','w:gz') as tar:
 for p in sorted(J.rglob('*')):
  if not p.is_file() or p.name in ['DELIVERY_SUMMARY.tar.gz','RAW_ARCHIVE.tar','sensor_source.tar','PREPARED.tar.gz']:continue
  rel=p.relative_to(J)
  if rel.parts[0] in ['TRACES','LABELS','FEATURES_V2'] or p.suffix=='.npz':continue
  tar.add(p,arcname=str(rel))
print('summary bytes',(J/'DELIVERY_SUMMARY.tar.gz').stat().st_size,'total evidence bytes',sum(r['bytes'] for r in rows),flush=True)

