import pathlib,json,csv,gzip,hashlib,sys,datetime
import numpy as np
ROOT=pathlib.Path('/work');sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import observation
E=ROOT/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105'
RUN=E/'RUN_SNOWBALL_20261105_0643/RUN_001'
OUT=E/'DIAG_MISSING_8_20261105';OUT.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
lock=json.loads((E/'INPUT_LOCK.json').read_text()); verified={}
for f in lock['files']:
 if f['path'].endswith('.npy'):
  assert sha(ROOT/f['path'])==f['sha256'];verified[f['path']]=f['sha256']
hashes=json.loads((RUN/'ARTIFACT_HASHES.json').read_text())
for name in ['PACKET_CANDIDATE_COVERAGE.csv','LOBE_RECORDS.csv.gz','CANDIDATES.csv.gz']:
 assert sha(RUN/name)==hashes[name];verified[name]=hashes[name]
with (RUN/'PACKET_CANDIDATE_COVERAGE.csv').open() as f:
 cases=[r for r in csv.DictReader(f) if r['corpus']=='dynamic' and r['channel']=='Full' and r['mode']=='TWO_PORT_UNION' and r['large_error']=='True' and r['reference_usable']=='False']
assert len(cases)==8
uids={r['packet_uid'] for r in cases};lobes={u:[] for u in uids};cand={u:[] for u in uids}
for filename,target in [('LOBE_RECORDS.csv.gz',lobes),('CANDIDATES.csv.gz',cand)]:
 with gzip.open(RUN/filename,'rt') as f:
  for r in csv.DictReader(f):
   if r['packet_uid'] in uids and r.get('mode','TWO_PORT_UNION')=='TWO_PORT_UNION':target[r['packet_uid']].append(r)
 print('READ_LOG',filename,flush=True)
RF=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
results=[];windows=[]
for row in cases:
 route=row['route'];pose=int(row['pose_id']);ref=int(row['reference_tap']);uid=row['packet_uid']
 H=np.load(RF/'FULL_RF'/f'H_{route}_aB_m0.npy',mmap_mode='r')[pose,:,:,0]
 L=np.load(RF/f'H_LoS_{route}_aB_m0.npy',mmap_mode='r')[pose,:,:,0]
 cir=observation.cir_batch(H[None])[0];los=observation.cir_batch(L[None])[0];amp=np.abs(cir);gp=float(amp.max())
 assert int(observation.first_path_batch(cir[None],1950000.)['index'][0])==int(row['raw_tap'])
 assert int(observation.first_path_batch(los[None],1950000.)['index'][0])==ref
 assert np.isclose(gp,float(row['raw_peak']),rtol=1e-12,atol=1e-15)
 detail=[];maxerr=0
 for l in lobes[uid]:
  rx=int(l['rx']);peak=int(l['peak_tap']);lo=int(l['left_local_valley']);hi=int(l['right_local_valley']);a=amp[:,rx]
  assert np.isclose(a[peak],float(l['peak_amplitude']),rtol=1e-12,atol=1e-15)
  if not (ref-8<=peak<=ref+12 or lo<=ref<=hi):continue
  prom=float(l['prominence']);height=float(l['peak_amplitude']);hit=np.flatnonzero(a[lo:peak+1]>=.3*height)
  edge=lo+int(hit[0]) if len(hit) else None
  blocks=[]
  if l['reason']!='SUPPORTED_LOBE':blocks.append(l['reason'])
  if not lo<=ref<=peak:blocks.append('OUTSIDE_VALLEY_TO_PEAK')
  if edge is None or abs(ref-edge)>1:blocks.append('OUTSIDE_EDGE_PLUS_MINUS_1')
  if a[ref]<.15*height:blocks.append('BELOW_15_PERCENT_LOCAL_PEAK')
  detail.append({'rx':rx,'peak_tap':peak,'valley':lo,'right_valley':hi,'peak_over_global':height/gp,'prominence_over_global':prom/gp,
   'valley_over_peak':float(a[lo]/height),'computed_edge':edge,'logged_edge':l['edge_tap'],'reference_offset_from_edge':ref-edge if edge is not None else None,
   'reference_over_peak':float(a[ref]/height),'reference_over_global':float(a[ref]/gp),'reason':l['reason'],'candidate_taps':json.loads(l['candidate_taps_json']),
   'reference_blockers':blocks})
 taps=sorted(int(c['tap']) for c in cand[uid]);assert ref not in taps
 for t in range(max(0,ref-8),min(1028,ref+17)):
  windows.append({'uid':uid,'tap':t,'reference_tap':ref,'raw_tap':int(row['raw_tap']),'full_rx0':float(amp[t,0]),'full_rx1':float(amp[t,1]),'los_rx0':float(abs(los[t,0])),'los_rx1':float(abs(los[t,1])),'global_peak':gp,'candidate':t in taps,
  'full_rx0_real':float(cir[t,0].real),'full_rx0_imag':float(cir[t,0].imag),'full_rx1_real':float(cir[t,1].real),'full_rx1_imag':float(cir[t,1].imag)})
 result={'uid':uid,'route':route,'pose_id':pose,'time_s':float(row['t_s']),'reference':ref,'raw':int(row['raw_tap']),'candidate_taps':taps,'overflow':row['overflow'],'noise_floor':row['noise_amplitude_floor'],'lobes_near_reference':detail}
 results.append(result)
 print(json.dumps(result),flush=True)
(OUT/'DIAGNOSIS.json').write_text(json.dumps({'role':'AUDITOR_SELF_REVIEW','scope':'8 missing cases, fixed original CIR transformation and recorded lobe/candidate logs only','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_selector_runs':0,'E2_started':False,'verified_hashes':verified,'cases':results},indent=2)+'\n')
with (OUT/'CIR_WINDOWS.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(windows[0]));w.writeheader();w.writerows(windows)
(OUT/'SOURCE_LOBES.json').write_text(json.dumps(lobes,indent=2)+'\n')
(OUT/'SOURCE_CANDIDATES.json').write_text(json.dumps(cand,indent=2)+'\n')
print('DIAG_DONE',flush=True)
