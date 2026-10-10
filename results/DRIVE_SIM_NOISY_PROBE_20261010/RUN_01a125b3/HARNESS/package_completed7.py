"""Immutable first delivery; pending full-RF stores explicitly excluded."""
from pathlib import Path
import hashlib,json,tarfile,shutil,datetime
import numpy as np
J=Path('/job');OLD=Path('/old');B=Path('/input/BLOCK_C');R=Path('/routes/source/results/DRIVE_SIM_20261007');D=J/'DELIVERY_EXISTING7';D.mkdir(exist_ok=False);IN=D/'INPUTS';IN.mkdir();S=D/'SOURCE';S.mkdir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
inputs=[]
def cp(p,name,role):
 dst=IN/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst);r={'source_path':str(p),'delivery_path':str(dst.relative_to(D)),'sha256':sha(p),'bytes':p.stat().st_size,'role':role}
 if p.suffix=='.npy':a=np.load(p,mmap_mode='r');r.update(shape=list(a.shape),dtype=str(a.dtype),finite=bool(np.isfinite(a).all()))
 inputs.append(r)
for case in [x['case'] for x in json.loads((B/'CASES.json').read_text())]:
 cp(B/'FULL_RF'/f'H_{case}.npy',f'RF/H_full_{case}.npy','frozen legacy full RF, not regenerated')
 cp(B/f'H_LoS_{case}.npy',f'RF/H_LoS_{case}.npy','original native LoS reference')
for p in (OLD/'LUT').glob('*'):
 if p.is_file():cp(p,'LUT/'+p.name,'original LUT/metadata, unchanged')
cp(B/'freqs_hz.npy','freqs_hz.npy','Hz, 257 bins, TX0 +45 LP, RX0 +45 LP/RX1 -45 LP')
for route in ['R2','R4','R5']:
 cp(R/'S1/routes'/f'rf_poses_{route}.json',f'routes/rf_poses_{route}.json','recorded RF pose set')
 cp(R/'S1/routes'/f'timeline_{route}_Tnone.csv',f'routes/timeline_{route}_Tnone.csv','original timeline mask/prior mapping')
source_manifest=json.loads((OLD/'SOURCE_MANIFEST.json').read_text())
for key,value in source_manifest['sha256'].items():
 p=OLD/key.replace('\\','/');assert sha(p)==value;dst=S/key.replace('\\','/');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst)
shutil.copyfile(OLD/'SOURCE_MANIFEST.json',S/'ORIGINAL_SOURCE_MANIFEST.json')
bankroot=Path('/legacy/source');bankmanifest=bankroot/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json';shutil.copyfile(bankmanifest,IN/'BANK_MANIFEST.json')
bankrows=[{'path':str(bankroot/name),'sha256':sha(bankroot/name),'bytes':(bankroot/name).stat().st_size,'delivery':'external preserved Snowball input, not duplicated in this package'} for name in ['LP_plus45_bank.npz','LP_minus45_bank.npz']]
for path in [Path('/input/source/scripts/corridor_sionna_run.py'),*Path('/input/source/scripts/g2_completion').glob('*.py')]:
 dst=S/'RF_RUNTIME'/path.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst)
(D/'INPUT_MANIFEST.json').write_text(json.dumps({'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inputs':inputs,'external_FFD_banks':bankrows,'port_units':'H[pose,freq,RX,TX]; TX0 only; no assumption that RX0 is always co-polar','original_RAW_archive':'96398a070d12e4613c29e2bcd40df5088a49ecb806556971ecf3790703116b75; full original remote archive, station subset only delivered here','sensor_revision':source_manifest['sensor_revision'],'spec_revision':'7fefdbbf6c4f36ebff72fb281bbbbc5900fffd25','new_native_full_RF':'PENDING, excluded from this immutable delivery; not a passed 12-case gate'},indent=2))
entries=[]
def entry(p,arc):entries.append({'source_path':str(p),'archive_path':arc,'bytes':p.stat().st_size,'sha256':sha(p)})
for root in ['RAW_BACKFILL','BODY_CONTROLS','RECEIVER_COV_existing7','NATIVE_LOS','BODY_PILOT']:
 for p in sorted((J/root).rglob('*')):
  if p.is_file():entry(p,str(p.relative_to(J)))
for p in sorted(J.iterdir()):
 if p.is_file() and p.suffix in ['.json','.csv','.py','.md','.log'] and p.name!='RF_PROGRESS.json':entry(p,'SUMMARY_AND_HARNESS/'+p.name)
for p in sorted(D.rglob('*')):
 if p.is_file():entry(p,str(p.relative_to(D)))
manifest={'entries':entries,'scope':'completed existing7 control + original station-P6 + five completed LoS stores, not pending native full RF','source_file_count':len(source_manifest['sha256']),'payload_bytes':sum(x['bytes'] for x in entries),'count':len(entries)};(D/'OUTPUT_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
archive=D/'COMPLETED_EXISTING7.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as t:
 for x in entries:t.add(x['source_path'],arcname=x['archive_path'],recursive=False)
 t.add(D/'OUTPUT_MANIFEST.json',arcname='OUTPUT_MANIFEST.json',recursive=False)
parts=[]
with archive.open('rb') as f:
 i=0
 while True:
  buf=f.read(32*1024*1024)
  if not buf:break
  p=D/f'COMPLETED_EXISTING7.tar.gz.part-{i:03d}';p.write_bytes(buf);parts.append({'file':p.name,'bytes':len(buf),'sha256':sha(p)});i+=1
result={'archive_sha256':sha(archive),'archive_bytes':archive.stat().st_size,'parts':parts,'payload_bytes':manifest['payload_bytes'],'file_count':len(entries),'pending_native_full_not_included':True};(D/'PACKAGE_MANIFEST.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='parts'}),flush=True)
