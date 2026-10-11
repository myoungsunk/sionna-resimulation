#!/usr/bin/env python3
"""V01 remaining source-family gate: original twelve legacy H and five Native H.
Restores only checksum-verified archive bytes; never equates observer parity
with propagation parity. No new estimator, no P1 run, no ignored failures.
"""
from __future__ import annotations
import argparse,hashlib,io,json,tarfile,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim import observation as O
BASE=ROOT/'results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3'
LEGACY=ROOT/'results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2'
ROUTES=ROOT/'results/DRIVE_SIM_20261007/S1/routes'
FREQ=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/freqs_hz.npy'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

def unpack_needed(out,expected):
 found={};arch=[];metadata=[]
 target={v['H_sha256']:v['case'] for v in expected}
 for folder in sorted(BASE.glob('*_ARCHIVE')):
  mf=folder/'PACKAGE_MANIFEST.json'
  if not mf.exists():continue
  desc=json.loads(mf.read_text());joined=out/(folder.name+'.tar.gz')
  H=hashlib.sha256();size=0
  with joined.open('wb') as w:
   for part in desc['parts']:
    p=folder/part['file']
    if not p.exists() or p.stat().st_size!=part['bytes'] or sha(p)!=part['sha256']:raise AssertionError('archive part checksum: '+str(p))
    with p.open('rb') as f:
     for b in iter(lambda:f.read(4*1024*1024),b''):w.write(b);H.update(b);size+=len(b)
  assert H.hexdigest()==desc['archive_sha256'] and size==desc['archive_bytes']
  candidate_count=0
  with tarfile.open(joined,'r:gz') as tar:
   for m in tar:
    if not m.isfile():continue
    if m.name.endswith('.json') and any(x in m.name.upper() for x in ('NATIVE_FULL','NATIVE_LOS','MANIFEST','FREQUENCY_COMPLETION')) and m.size<400000:
     try:
      j=json.load(tar.extractfile(m));metadata.append(dict(archive=folder.name,path=m.name,content=j))
     except (ValueError,TypeError):pass
    if m.name.endswith('.npy') and ('NATIVE_FULL' in m.name or m.name.endswith('H_full.npy')):
     candidate_count+=1
     b=tar.extractfile(m).read();digest=hashlib.sha256(b).hexdigest()
     if digest in target:
      case=target[digest];dest=out/(case+'_native.npy');dest.write_bytes(b)
      found[case]=dict(path=str(dest),archive=folder.name,member=m.name,sha256=digest)
  arch.append(dict(archive=folder.name,archive_sha256=H.hexdigest(),bytes=size,full_H_candidates=candidate_count))
  joined.unlink()
  print('ARCHIVE_SCAN',arch[-1],list(found),flush=True)
 (out/'ARCHIVE_PROVENANCE.json').write_text(json.dumps(dict(archives=arch,native_H_found=found,metadata=metadata),indent=2))
 return found,metadata

def observe(H,f):
 q=O.observe(H,f,None,None,tx=0)
 return q

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path);a=ap.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
 (out/'STATUS.json').write_text(json.dumps(dict(execution='STARTED',gate='NOT_PASS',stage_B_allowed=False)))
 expected=json.loads((BASE/'SUMMARY_FINAL/NATIVE_FULL_EFFECTIVE_STATUS_FREQUENCY.json').read_text())['cases']
 matrix=json.loads((BASE/'SUMMARY_CURRENT/MOUNT_CASE_MATRIX.json').read_text())
 assert len(matrix)==12 and len(expected)==5
 legacy=[]
 for c in matrix:
  path=LEGACY/('H_'+c['case']+'.npy');p=ROUTES/('rf_poses_'+c['case'][:2]+'.json')
  ok=path.exists() and sha(path)==c['full_sha256'];pose_ok=p.exists() and sha(p)==c['rf_pose_sha256']
  legacy.append(dict(case=c['case'],n_pose=c['poses'],H_present=path.exists(),H_SHA_PASS=ok,pose_SHA_PASS=pose_ok))
 pd.DataFrame(legacy).to_csv(out/'ALL_12_LEGACY_INPUT_IDENTITY.csv',index=False)
 found,metadata=unpack_needed(out,expected)
 if len(found)<5 or not all(r['H_SHA_PASS'] and r['pose_SHA_PASS'] for r in legacy):
  (out/'STATUS.json').write_text(json.dumps(dict(execution='INPUT_AUDIT_COMPLETED',gate='BLOCKED_MISSING_OR_UNVERIFIED_INPUT',native_found=list(found),legacy_identity=legacy,stage_B_allowed=False),indent=2));return
 f=np.load(FREQ);assert len(f)==257
 perpose=[];summary=[]
 for c in expected:
  name=c['case'];old=np.load(LEGACY/('H_'+name+'.npy'),mmap_mode='r');new=np.load(found[name]['path'],mmap_mode='r')
  samples=json.loads((ROUTES/('rf_poses_'+name[:2]+'.json')).read_text())
  assert old.shape==new.shape==(len(samples),257,2,2)
  assert np.isfinite(new).all() and np.isfinite(old).all()
  qold=observe(old,f);qnew=observe(new,f)
  diff=new-old;den=np.maximum(np.linalg.norm(old,axis=(1,2,3)),1e-30)
  rel=np.linalg.norm(diff,axis=(1,2,3))/den
  mag=np.linalg.norm(abs(new)-abs(old),axis=(1,2,3))/den
  ds=qnew['s']-qold['s'];dtap=qnew['index']-qold['index']
  for i,p in enumerate(samples):
   perpose.append(dict(case=name,row=i,pose_id=int(p['pose_id']),x=p['x'],y=p['y'],yaw_body_deg=p['yaw_body_deg'],relative_H_error=float(rel[i]),relative_magnitude_error=float(mag[i]),s_old=float(qold['s'][i]),s_native=float(qnew['s'][i]),s_delta=float(ds[i]),tap_old=int(qold['index'][i]),tap_native=int(qnew['index'][i]),tap_delta=int(dtap[i])))
  physical_meta=[m for m in metadata if name in m['path'] and isinstance(m['content'],dict) and 'poses_sha256' in m['content']]
  poses_ok=any(m['content']['poses_sha256']==sha(ROUTES/('rf_poses_'+name[:2]+'.json')) for m in physical_meta)
  row=dict(case=name,n_poses=len(samples),native_SHA=found[name]['sha256'],native_pose_order_manifest_PASS=poses_ok,relative_H_global=float(np.linalg.norm(diff)/np.linalg.norm(old)),relative_H_max=float(rel.max()),relative_H_median=float(np.median(rel)),s_delta_RMS=float(np.sqrt(np.mean(ds**2))),s_delta_absmax=float(np.max(abs(ds))),same_tap_rate=float(np.mean(dtap==0)),full_equivalence_numeric_PASS=bool(np.all(rel<=1e-3) and np.all(abs(ds)<=.01) and np.all(dtap==0)))
  summary.append(row);print('FAMILY_ALL_POSES',row,flush=True)
 pd.DataFrame(perpose).to_csv(out/'NATIVE5_VS_LEGACY5_ALL_POSES.csv.gz',index=False)
 pd.DataFrame(summary).to_csv(out/'NATIVE5_VS_LEGACY5_SUMMARY.csv',index=False)
 verified=all(r['full_equivalence_numeric_PASS'] and r['native_pose_order_manifest_PASS'] for r in summary)
 result=dict(execution='COMPLETE',gate='PASS' if verified else 'FAIL_OR_PROVENANCE_BLOCKED',observer_gate='INDEPENDENT_P0_V01_PREVIOUS',n_legacy_cases=12,n_native_cases=5,n_native_pose_comparisons=len(perpose),full_source_family_equivalent=verified,all_native_numeric_PASS=all(r['full_equivalence_numeric_PASS'] for r in summary),summary=summary,stage_B_allowed=False,scientific_PASS=False)
 (out/'STATUS.json').write_text(json.dumps(result,indent=2));print('V01_FULL_ARCHIVE_RESULT',json.dumps(result),flush=True)
 # Compact exact source snapshot permits local independent computational review.
 snapshot=out/'source_snapshot'
 for p in list((ROOT/'src/qclean_uwb/drivesim').glob('*.py'))+list((ROOT/'research/P0_RESTORE_20261011').glob('*.py')):
  dest=snapshot/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
 (out/'executed_V01.py').write_bytes(Path(__file__).read_bytes())
 for p in out.glob('*_native.npy'):p.unlink() # Original source remains in immutable Git/archive; output has digests and per-pose evidence.
if __name__=='__main__':main()
