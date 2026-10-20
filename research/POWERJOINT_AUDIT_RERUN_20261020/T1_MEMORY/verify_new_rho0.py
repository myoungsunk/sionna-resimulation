"""Verify stored POWER1/rho0 physical trajectories; does not replay any model."""
from pathlib import Path
import argparse,csv,hashlib,json,os,sys
import numpy as np

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--traces',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected-count',type=int,default=36);p.add_argument('--route',choices=['C01','C02','C03','O01','O02','O03']);a=p.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
 cases=[f'{route}_{anchor}_M45_FULL' for route in ([a.route] if a.route else ['C01','C02','C03','O01','O02','O03']) for anchor in (['A','B'] if route.startswith('C') else ['O0'])]
 expected={f'{case}_{bias}.npz' for case in cases for bias in ['B0','L0','L1','L2']}
 files=sorted(a.traces.glob('*.npz'));rows=[];errors=[]
 if len(files)!=a.expected_count or {f.name for f in files}!=expected:
  errors.append(dict(error='TRACE_SET_MISMATCH',expected_count=a.expected_count,expected_names=sorted(expected),actual_names=[f.name for f in files]))
 for path in files:
  row=dict(trace=path.name,sha256=sha(path),state_max_abs='',cov_max_abs='',gate_mismatches='',technical='ERROR')
  try:
   with np.load(path,allow_pickle=False) as z:
    names=[v.decode() if isinstance(v,bytes) else str(v) for v in z['names']]
    if len(names)!=len(set(names)):raise ValueError('DUPLICATE_ARM_NAMES')
    ip,ir=names.index('POWER1'),names.index('MEMORY_RHO0');state=z['state'];cov=z['cov'];gate=z['accepted']
    if state.ndim!=3 or state.shape[1]!=len(names) or state.shape[2]<4 or cov.shape[:2]!=state.shape[:2] or cov.ndim!=4 or cov.shape[2]<4 or cov.shape[3]<4 or gate.shape!=state.shape[:2]:raise ValueError('TRACE_SHAPE')
    x=state[:,[ip,ir],:4];P=cov[:,[ip,ir],:4,:4]
    if not np.isfinite(x).all() or not np.isfinite(P).all():raise ValueError('NONFINITE_PHYSICAL_TRACE')
    dx=float(np.max(np.abs(x[:,0]-x[:,1])));dp=float(np.max(np.abs(P[:,0]-P[:,1])));dg=int(np.count_nonzero(gate[:,ip]!=gate[:,ir]))
    row.update(state_max_abs=dx,cov_max_abs=dp,gate_mismatches=dg,n_frames=len(state),physical_dimensions=4)
    if dx>1e-10 or dp>1e-10 or dg:raise ValueError('RHO0_PARITY_FAILED')
    row['technical']='TECHNICAL_PASS'
  except Exception as exc:errors.append(dict(trace=path.name,error=str(exc)));row['error']=str(exc)
  rows.append(row)
 fields=list(dict.fromkeys(k for r in rows for k in r)) or ['trace','technical']
 with a.out.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
 a.out.with_suffix('.ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n')
 manifest=dict(technical='TECHNICAL_PASS' if not errors else 'ERROR',scientific='NOT_ESTABLISHED',check='Stored traces only; all frames; first four physical state and covariance dimensions; unchanged accept gates',tolerance=1e-10,expected_count=a.expected_count,actual_count=len(files),source_run_id=39359952488,validation_run_id=os.getenv('GITHUB_RUN_ID'),source_commit=os.getenv('GITHUB_SHA'),script_sha256=sha(Path(__file__)),csv_sha256=sha(a.out),traces=[dict(file=r['trace'],sha256=r['sha256']) for r in rows])
 receipt=a.traces.parent.parent/'ARTIFACT_RECEIPT.json'
 if receipt.exists():manifest['source_artifact_receipt']=json.loads(receipt.read_text())
 a.out.with_suffix('.MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(dict(technical=manifest['technical'],n=len(rows),error_count=len(errors))))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
