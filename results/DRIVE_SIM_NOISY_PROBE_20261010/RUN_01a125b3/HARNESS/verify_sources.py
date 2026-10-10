from pathlib import Path
import hashlib,json,sys,platform,importlib.metadata
J=Path('/job');O=Path('/old')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((O/'SOURCE_MANIFEST.json').read_text());rows=[]
for name,expected in m['sha256'].items():
 p=O/name.replace('\\','/');actual=sha(p) if p.is_file() else None;rows.append({'path':name,'expected':expected,'actual':actual,'equal':actual==expected})
report={'sensor_revision':m['sensor_revision'],'sources':rows,'all_equal':all(x['equal'] for x in rows),'own_source_hashes':{p.name:sha(p) for p in J.glob('*.py')},'lut_sha256':sha(O/'LUT/hs_lut_2deg.npy'),'metadata_sha256':sha(O/'LUT/hs_lut_meta.json'),'freq_sha256':sha(Path('/input/BLOCK_C/freqs_hz.npy')),'python':sys.version,'platform':platform.platform(),'versions':{n:importlib.metadata.version(n) for n in ['numpy','scipy','pandas']},'ordering_note':'Original source manifest existed before this execution. This content comparison is a post-pilot integrity verification, not a new preregistration.'}
(J/'SOURCE_INTEGRITY.json').write_text(json.dumps(report,indent=2));assert report['all_equal'];print(json.dumps({k:v for k,v in report.items() if k not in ['sources','own_source_hashes']}),flush=True)
