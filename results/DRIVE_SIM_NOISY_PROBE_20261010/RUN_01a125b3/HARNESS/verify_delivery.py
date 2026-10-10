from pathlib import Path
import hashlib,json,datetime,csv
root=Path(r'D:\SLAM_bot\artifacts\DRIVE_SIM_NOISY_PROBE_20261010_01a125b3\checkout\results\DRIVE_SIM_NOISY_PROBE_20261010\RUN_01a125b3')
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
checks=[]
for d in ['PRE_CORRECTION_ARCHIVE','C_CORRECTION_ARCHIVE']:
 p=root/d;m=json.loads((p/'PACKAGE_MANIFEST.json').read_text());h=hashlib.sha256();n=0
 for x in m['parts']:
  q=p/x['file'];assert q.stat().st_size==x['bytes'];assert hashfile(q)==x['sha256']
  with q.open('rb') as f:
   while b:=f.read(8*1024*1024):h.update(b);n+=len(b)
 assert n==m['archive_bytes'] and h.hexdigest()==m['archive_sha256']
 checks.append(dict(directory=d,archive_sha256=h.hexdigest(),bytes=n,parts=len(m['parts']),passed=True))
(root/'DOWNLOAD_INTEGRITY.json').write_text(json.dumps({'checks':checks,'all_passed':True,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2),encoding='utf8')
(root/'.gitattributes').write_text('* -filter -diff -merge -text\n',encoding='utf8')
job=Path(r'D:\SLAM_bot\artifacts\DRIVE_SIM_NOISY_PROBE_20261010_01a125b3\job')
import shutil
(root/'HARNESS').mkdir(exist_ok=True)
for p in job.iterdir():
 if p.is_file() and p.suffix in ['.py','.json','.md']:shutil.copyfile(p,root/'HARNESS'/p.name)
print(json.dumps(checks))
