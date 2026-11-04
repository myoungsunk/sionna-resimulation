"""Independent C0-B result observer. SciPy FFT, raw legacy components; no QA/diagnostics imports.
Read-only: stdout JSON evidence only. No new RT, no C1-C3.
"""
import csv,json,hashlib,math,sys,datetime
from pathlib import Path
import numpy as np
from scipy.fft import ifft
H=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0')
C=H/'C0B_ANALYSIS_001';O=C/'RESULTS_001'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
def rows(p):
 with p.open() as f:return list(csv.DictReader(f))
checks=0;max_signed=0.;max_power=0.;max_window=0.;max_closure=0.;chain_rows=0;surface_rows=0;window_scalars=0
# Scalar/power audit tolerances. Closure residual comparison follows the frozen
# production 1e-14 absolute closure limit, correcting the verifier's initial 1e-18.
def close(x,y,kind='scalar'):
 global checks,max_signed,max_power
 if y is None:assert x is None or x=='';checks+=1;return
 x=float(x);y=float(y);delta=abs(x-y);assert math.isfinite(x) and math.isfinite(y)
 if kind=='closure':
  assert delta<=1e-14,(kind,x,y,delta)
 elif kind=='power':
  assert delta<=1e-18+1e-8*abs(y),(kind,x,y,delta);max_power=max(max_power,delta)
 else:
  assert delta<=1e-10+1e-10*abs(y),(kind,x,y,delta);max_signed=max(max_signed,delta)
 checks+=1
window=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
def transform(h):return ifft(np.asarray(h,complex)*window[:,None],n=1028,axis=0)*257
def signed(v):
 p=np.real(v)**2+np.imag(v)**2;den=float(p[0]+p[1]);return (None if den==0 else float((p[0]-p[1])/den)),den,p

def detect(c,df,allow_zero=False):
 assert np.isfinite(c).all();peak_per_port=np.max(abs(c),axis=0);port=int(np.argmax(peak_per_port));peak=float(peak_per_port[port])
 if peak==0:
  assert allow_zero
  return dict(tap=None,s=None)
 tap=next(i for i in range(1028) if abs(c[i,port])>=.3*peak)
 s,den,power=signed(c[tap])
 return dict(tap=tap,rx=port,peak=peak,leading_edge=.3*peak,range_m=tap*299792458./(1028*df),s=s,denominator=den,power=power.tolist())
def observer(full,los,df):
 f,l=detect(full,df),detect(los,df);same,den,_=signed(full[l['tap']]);assert same is not None
 fixed=same-l['s'];choice=f['s']-same;emp=f['s']-l['s']
 return dict(full=f,los=l,delta_tap=f['tap']-l['tap'],delta_range_m=f['range_m']-l['range_m'],full_at_los_tap_s=same,full_at_los_tap_denominator=den,same_los_tap=fixed,detector_choice=choice,e_mp=emp,identity_error=abs(emp-fixed-choice))

def compare_observer(saved,ref):
 for field in ('full','los'):
  for k,v in ref[field].items():
   if isinstance(v,list):
    for x,y in zip(saved[field][k],v):close(x,y,'power')
   elif k in ('tap','rx'):assert saved[field][k]==v
   else:close(saved[field][k],v,'power' if k in ('denominator',) else 'scalar')
 for k,v in ref.items():
  if k not in ('full','los'):close(saved[k],v,'power' if k=='full_at_los_tap_denominator' else 'scalar')
manifest=load(O/'MANIFEST.json');assert manifest['status']=='ANALYSIS_COMPLETE_PENDING_INDEPENDENT_AUDIT'
accept_path=H/'BATCH_AMENDED_001/audit/SM0_DATA15_ACCEPTANCE_RESULT.json';accept=load(accept_path)
go_path=C/'audit/SM0_C0B_EXECUTION_GO_RESULT.json';go=load(go_path)
assert sha(accept_path)=='291b040d8036bb3f031d5db0075f8da13042ee753d742629e78db96c427dcc3e'
assert manifest['data_acceptance_sha256']==go['data_acceptance_sha256']==sha(accept_path)
assert manifest['go_sha256']==sha(go_path) and go['decision']=='GO'
assert manifest['captures']==accept['captures'] and len(manifest['completed'])==15
for n,d in manifest['code_sha256'].items():assert sha(H/n)==d and go['code_sha256'][n]==d
assert manifest['code_sha256']==go['code_sha256']
runtime=load(H/'RUNTIME_LOCK.json')
for k,v in manifest['validated_runtime'].items():assert runtime[k]==v
for n,d in manifest['governance_sha256'].items():assert sha(Path('/mnt/c/Users/Myoungsun Kim/.codex/research-governance')/n)==d
artifacts=load(O/'ARTIFACT_HASHES.json')
for n,d in artifacts.items():assert sha(O/n)==d,n
summary=rows(O/'SUMMARY.csv');assert len(summary)==15
pose_results=[];undefined=dict(undefined_surface_signed=0,undefined_surface_redetected=0,undefined_chain_signed=0,undefined_chain_redetected=0)
for entry,srow,completed in zip(accept['captures'],summary,manifest['completed']):
 case,pid=entry['case'],entry['pose_id'];assert (srow['case'],int(srow['pose_id']))==(case,pid)
 assert completed==dict(case=case,pose_id=pid,qa_status='AMENDED_NUMERICAL_PASS')
 capture=H/entry['capture'];assert sha(capture/'RAW.npz')==entry['raw_sha256'] and sha(capture/'MANIFEST.json')==entry['manifest_sha256']
 with np.load(capture/'RAW.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
 labels=a['group_labels'].tolist();direct=labels.index('DIRECT');ng=len(labels)
 G=np.zeros((ng,257,2),complex)
 for fi in range(257):
  lo,hi=map(int,a['offsets'][fi:fi+2]);np.add.at(G[:,fi,:],a['source_group'][lo:hi],a['original_field'][lo:hi])
 CG=np.array([transform(v) for v in G]);full=transform(G.sum(0));los=CG[direct]
 af=transform(a['archive_full']);al=transform(a['archive_los']);df=float(a['frequencies_hz'][1]-a['frequencies_hz'][0])
 native=observer(full,los,df);archive=observer(af,al,df)
 folder=O/(case+'_'+str(pid));saved=load(folder/'detector.json')
 compare_observer(saved['native'],native);compare_observer(saved['archive'],archive)
 assert native['full']['tap']==archive['full']['tap'] and native['los']['tap']==archive['los']['tap']
 crows=rows(folder/'attribution.csv');srows=rows(folder/'surface_removal.csv')
 cdict={(r['group_id'],r['tap_ref']):r for r in crows};sdict={(r['surface'],r['tap_ref']):r for r in srows}
 reflection=[j for j in range(ng) if j!=direct and labels[j]!='INVALID']
 assert len(crows)==len(cdict)==2*len(reflection)
 surfaces=sorted({surface for j in reflection for surface,kind in json.loads(labels[j])})
 assert len(srows)==len(sdict)==2*len(surfaces)
 fixed_undef=redetect_undef=sfixed_undef=sredetect_undef=0
 for tapname,tap in [('fpFull',native['full']['tap']),('fpLoS',native['los']['tap'])]:
  baseline=signed(full[tap])[0];V=CG[:,tap,:];allocated=np.zeros(2)
  for j in reflection:
   r=cdict[(labels[j],tapname)];assert int(r['tap'])==tap
   removed=CG[[k for k in range(ng) if k!=j]].sum(0)
   val,den,power=signed(removed[tap]);nd=detect(removed,df,True)
   close(r['removed_s_fixed'],val);close(r['delta_s_fixed'],None if val is None else baseline-val)
   close(r['removed_denominator'],den,'power');close(r['removed_plus_power'],power[0],'power');close(r['removed_minus_power'],power[1],'power')
   assert (r['removed_detected_tap']=='' if nd['tap'] is None else int(r['removed_detected_tap'])==nd['tap'])
   close(r['removed_s_redetected'],nd['s']);close(r['delta_s_redetected'],None if nd['s'] is None else native['full']['s']-nd['s'])
   # Independent quadratic-Shapley expansion, explicitly summing other players.
   phi=np.zeros(2)
   for rx in range(2):
    d=V[direct,rx];v=V[j,rx]
    phi[rx]=abs(d+v)**2-abs(d)**2+math.fsum(float((v*np.conj(V[k,rx])).real) for k in reflection if k!=j)
   close(r['shapley_plus'],phi[0],'power');close(r['shapley_minus'],phi[1],'power');allocated+=phi
   fixed_undef+=val is None;redetect_undef+=nd['s'] is None;chain_rows+=1
  expected_gap=allocated-(abs(full[tap])**2-abs(los[tap])**2)
  assert np.allclose(allocated,abs(full[tap])**2-abs(los[tap])**2,atol=1e-14,rtol=1e-8)
  max_closure=max(max_closure,float(abs(expected_gap).max()))
  for x,y in zip(saved[tapname+'_allocation_residual'],expected_gap):close(x,y,'closure')
  for surface in surfaces:
   indices=[j for j in reflection if surface in {v[0] for v in json.loads(labels[j])}]
   r=sdict[(surface,tapname)];assert int(r['tap'])==tap and int(r['removed_group_count'])==len(indices)
   removed=CG[[k for k in range(ng) if k not in indices]].sum(0)
   val,den,power=signed(removed[tap]);nd=detect(removed,df,True)
   close(r['s_removed_fixed'],val);close(r['delta_s_fixed'],None if val is None else baseline-val)
   close(r['removed_denominator'],den,'power');close(r['removed_plus_power'],power[0],'power');close(r['removed_minus_power'],power[1],'power')
   assert (r['removed_detected_tap']=='' if nd['tap'] is None else int(r['removed_detected_tap'])==nd['tap'])
   close(r['s_removed_redetected'],nd['s']);close(r['delta_s_redetected'],None if nd['s'] is None else native['full']['s']-nd['s'])
   sfixed_undef+=val is None;sredetect_undef+=nd['s'] is None;surface_rows+=1
 with np.load(folder/'tap_windows.npz',allow_pickle=False) as z:
  for tapname,tap in [('fpFull',native['full']['tap']),('fpLoS',native['los']['tap'])]:
   ids=(tap+np.arange(-4,5))%1028;assert np.array_equal(z[tapname+'_bins'],ids)
   for name,array in [('full',full),('direct',los),('archive_full',af),('archive_los',al)]:
    savedw=z[tapname+'_'+name];ref=array[ids];delta=float(abs(savedw-ref).max());assert delta<1e-12
    max_window=max(max_window,delta);window_scalars+=ref.size
 close(srow['fp_full'],native['full']['tap']);close(srow['fp_los'],native['los']['tap']);close(srow['tap_shift'],native['delta_tap'])
 for k,v in [('range_shift_m',native['delta_range_m']),('s_full',native['full']['s']),('s_los',native['los']['s']),('e_mp',native['e_mp']),('same_los_tap',native['same_los_tap']),('detector_choice',native['detector_choice']),('identity_error',native['identity_error']),('archive_e_mp',archive['e_mp']),('native_archive_e_mp_difference',native['e_mp']-archive['e_mp'])]:close(srow[k],v)
 candidates=[r for r in srows if r['tap_ref']=='fpLoS' and r['delta_s_fixed']!=''];top=max(candidates,key=lambda r:abs(float(r['delta_s_fixed']))) if candidates else None
 assert srow['strongest_fixed_los_surface']==('' if top is None else top['surface'])
 close(srow['strongest_fixed_los_surface_delta_s'],None if top is None else float(top['delta_s_fixed']))
 local_undefined=dict(undefined_surface_signed=sfixed_undef,undefined_surface_redetected=sredetect_undef,undefined_chain_signed=fixed_undef,undefined_chain_redetected=redetect_undef)
 for k,v in local_undefined.items():assert int(srow[k])==v;undefined[k]+=v
 pose_results.append(dict(case=case,pose_id=pid,full_tap=native['full']['tap'],los_tap=native['los']['tap'],emp=native['e_mp'],same_tap=native['same_los_tap'],tap_choice=native['detector_choice'],chain_rows=len(crows),surface_rows=len(srows)))
report=C/'RESULTS_KO.md';provenance=load(C/'REPORT_PROVENANCE.json')
assert provenance['report_sha256']==sha(report) and provenance['summary_sha256']==sha(O/'SUMMARY.csv') and provenance['analysis_manifest_sha256']==sha(O/'MANIFEST.json')
assert provenance['builder_sha256']==sha(C/'build_report.py')
report_text=report.read_text()
for r in summary:
 assert '| '+r['case'].split('_')[0]+' | '+r['pose_id']+' | '+r['fp_full']+'/'+r['fp_los']+' | '+format(float(r['e_mp']),'+.4f')+' | '+format(float(r['same_los_tap']),'+.4f')+' | '+format(float(r['detector_choice']),'+.4f')+' | '+r['strongest_fixed_los_surface']+' ('+format(float(r['strongest_fixed_los_surface_delta_s']),'+.4f')+') |' in report_text
max_archive=max(abs(float(r['native_archive_e_mp_difference'])) for r in summary);max_identity=max(float(r['identity_error']) for r in summary)
assert format(max_archive,'.8g') in report_text and format(max_identity,'.8g') in report_text
for k,v in undefined.items():assert k+': '+str(v) in report_text
result=dict(decision='ACCEPT',scope='C0B_SELECTED_15_SIMULATED_POSES',auditor='independent_precision_audit',observer='independent SciPy FFT with analytic Hann and explicit pair-cross Shapley; no qa/diagnostics imports',poses=len(pose_results),native_archive_tap_checks=60,chain_removal_rows=chain_rows,surface_removal_rows=surface_rows,tap_window_complex_values=window_scalars,scalar_checks=checks,output_artifacts_verified=len(artifacts),max_observer_scalar_absolute_difference=max_signed,max_observer_power_absolute_difference=max_power,max_window_complex_absolute_difference=max_window,max_independent_coherent_closure_absolute=max_closure,max_native_archive_emp_difference=max_archive,max_stored_decomposition_identity_error=max_identity,undefined_counts=undefined,analysis_manifest_sha256=sha(O/'MANIFEST.json'),report_sha256=sha(report),summary_sha256=sha(O/'SUMMARY.csv'),artifact_hashes_sha256=sha(O/'ARTIFACT_HASHES.json'),report_provenance_sha256=sha(C/'REPORT_PROVENANCE.json'),data_acceptance_sha256=sha(accept_path),execution_go_sha256=sha(go_path),new_pathsolver_calls=0,C1_C2_C3_run=False,causality_claim='stored-ray offline counterfactuals in selected poses only; Heading/overconfidence causality not tested',timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
print('SM0_C0B_RESULT_ACCEPTANCE_RESULT '+json.dumps(result))
print('SM0_C0B_INDEPENDENT_POSE_RESULTS '+json.dumps(pose_results))
