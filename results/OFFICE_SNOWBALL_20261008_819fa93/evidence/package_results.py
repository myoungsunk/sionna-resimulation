import hashlib,json,subprocess,tarfile,time
from pathlib import Path
r=Path('/home/KMS/OFFICE_SNOWBALL_20261008_819fa93')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
status=json.loads((r/'full35_stride1/RUN_STATUS.json').read_text())
verify=json.loads((r/'full35_stride1/VERIFY.json').read_text())
assert status['exit_code']==0 and status['status']=='COMPLETE'
assert verify['ok'] and verify['n_requested']==verify['n_valid']==35
assert (r/'full35_stride1/logs/SWEEP_COMPLETE').is_file()
raw=[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted((r/'full35_stride1').rglob('*.npz'))]
assert len(raw)==35
(r/'evidence/RAW_NPZ_MANIFEST.json').write_text(json.dumps({'preserved_on':'Snowball','root':str(r),'files':raw},indent=2))
ci=json.loads(subprocess.check_output(['docker','inspect','office-full35-819fa93']))[0]
meta={'source_commit':'819fa93b152ca3cdf66297af09ff073880bd9d9b','remote_root':str(r),'container':ci['Name'],'image_id':ci['Image'],'started_at':ci['State']['StartedAt'],'finished_at':ci['State']['FinishedAt'],'exit_code':ci['State']['ExitCode'],'final_cpu_quota':ci['HostConfig']['NanoCpus']/1e9,'parallelism_note':'started4; user raised CPU/xargs limit64; completed4 preserved, remaining31 ran simultaneously','repeat_validation':{'command':'scripts/sweep_verify.py run --scenario office --run-dir /work/full35_stride1 --positions results/OFFICE_RUN_PLAN_20261008/positions_all.txt --bin-stride 1 --expect-n 35','exit_code':0,'valid':35},'captured_unix':time.time()}
assert meta['exit_code']==0
(r/'evidence/EXECUTION_MANIFEST.json').write_text(json.dumps(meta,indent=2))
files=[p for root in ['full35_stride1','pilot_stride128_lf'] for p in (r/root).rglob('*') if p.is_file() and p.suffix!='.npz']
files += [r/'slab_check/SLAB_CHECK.json',r/'geom_check/GEOM_LOS_CHECK.json']
files += [p for p in (r/'evidence').rglob('*') if p.is_file()]
for rel in ['results/OFFICE_RUN_PLAN_20261008/positions_all.txt','results/OFFICE_RUN_PLAN_20261008/positions_pilot.txt','results/OFFICE_RUN_PLAN_20261008/RUN_PLAN.json','results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json','results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json']:
 files.append(r/'source'/rel)
manifest={str(p.relative_to(r)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(set(files))}
(r/'evidence/TRANSFER_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
files.append(r/'evidence/TRANSFER_MANIFEST.json')
out=r/'OFFICE_VERIFIED_RESULTS.tgz'
with tarfile.open(out,'w:gz') as t:
 for p in sorted(set(files)):t.add(p,arcname=str(p.relative_to(r)),recursive=False)
print(json.dumps({'bundle':str(out),'bytes':out.stat().st_size,'sha256':sha(out),'npz_retained':len(raw),'uploaded_files':len(set(files)),'execution':meta}))
