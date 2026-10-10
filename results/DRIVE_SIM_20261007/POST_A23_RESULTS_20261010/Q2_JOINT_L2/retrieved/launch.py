import pathlib,sys,json,hashlib,importlib.util,difflib
import numpy as np
ROOT=pathlib.Path('/job');SRC=ROOT/'source';OUT=ROOT/'OUTPUT'
R=pathlib.Path('/routes/source/results/DRIVE_SIM_20261007');D=R/'SNOWBALL_ROUTES_01a11669';L=pathlib.Path('/legacy/source')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
if sys.argv[1]=='preflight':
 OUT.mkdir(exist_ok=False)
 checks={}
 hm=json.loads((D/'S6_routes/manifest_R2_aA_m0.json').read_text())
 H=D/'S2/H_R2_aA_m0.npy';lut=L/'results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy';s6=D/'S6_routes/results_R2_aA_m0.csv'
 expected={H:'1c40aea5ab7af87223f942c0727c0f6aabe7bd60e55a70c68c74d2c115750a51',lut:'711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079',s6:'16428ad0ce782193a90d6c0323fb4be05d6ea825bce835f08c62aea575765c13',ROOT/'freqs_hz.npy':'fe0bcfeb1426847ea090668845fe124482086d0510e38ebdb463609e2a1169f8'}
 for p,e in expected.items():checks[str(p)]={'sha256':sha(p),'expected':e,'match':sha(p)==e}
 h=np.load(H,mmap_mode='r');f=np.load(ROOT/'freqs_hz.npy');lv=np.load(lut)
 with np.load(L/'LP_plus45_bank.npz') as z:checks['freq_axis_matches_original_bank']=bool(np.array_equal(f,z['freqs_hz']))
 checks['array_contract']=dict(H_shape=list(h.shape),H_dtype=str(h.dtype),H_finite=bool(np.isfinite(h).all()),LUT_shape=list(lv.shape),LUT_finite=bool(np.isfinite(lv).all()),freq_count=len(f),freq_first=float(f[0]),freq_last=float(f[-1]),freq_step=float(f[1]-f[0]))
 rec=dict(inputs=checks,original_S6_manifest=hm,original_source_provenance=json.loads(pathlib.Path('/routes/PROVENANCE_START.json').read_text()),runtime=dict(python=sys.version,numpy=np.__version__),source_revision=json.loads((ROOT/'SOURCE_REVISION.json').read_text()))
 source_files=['filters.py','experiment.py','sensors.py','observation.py','hs_lut.py','trajectory.py','routes.py','pattern_apply.py']
 rec['original_vs_current_source']={}
 for name in source_files:
  old=pathlib.Path('/routes/source/src/qclean_uwb/drivesim')/name;new=SRC/'src/qclean_uwb/drivesim'/name
  if old.exists() and new.exists():
   rec['original_vs_current_source'][name]=dict(old_sha256=sha(old),new_sha256=sha(new))
   (OUT/('SOURCE_DIFF_'+name+'.txt')).write_text(''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile=str(old),tofile=str(new))))
 (OUT/'PREFLIGHT.json').write_text(json.dumps(rec,indent=2))
 (OUT/'S6_MANIFEST_ORIGINAL.json').write_text(json.dumps(hm,indent=2))
 (OUT/'S6_SOURCE_PROVENANCE.json').write_text(pathlib.Path('/routes/PROVENANCE_START.json').read_text())
 assert all(checks[str(p)]['match'] for p in expected)
 assert checks['freq_axis_matches_original_bank'] and checks['array_contract']['H_finite'] and checks['array_contract']['LUT_finite']
 assert h.shape==(1303,257,2,2) and lv.shape==(46,180,180)
 print(json.dumps(checks,indent=2));sys.exit(0)
spec=importlib.util.spec_from_file_location('a23',SRC/'scripts/drive_sim/structured_noise_control.py');m=importlib.util.module_from_spec(spec);sys.modules['a23']=m;spec.loader.exec_module(m)
meta=json.loads((ROOT/'SOURCE_REVISION.json').read_text())
# Metadata only: the unchanged container has no git. Frozen source hashes remain those of the committed archive.
m.git_info=lambda:dict(head=meta['head'],branch=meta['branch'],dirty_files=[],runtime_git_available=False,provenance_method=meta['provenance_method'],archive_sha256=meta['archive_sha256'],local_checkout_dirty_files=meta['dirty_files'])
sys.argv=[str(SRC/'scripts/drive_sim/structured_noise_control.py')]+sys.argv[1:]
m.main()
