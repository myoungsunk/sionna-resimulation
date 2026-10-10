from pathlib import Path
import json
import numpy as np
J=Path('/job');rows=[];fail=[]
for root in [J/'RECEIVER_COV_existing7',J/'RECEIVER_COV']:
 if not root.exists():continue
 for p in root.glob('*.npz'):
  z=np.load(p);cov=z['cov_sr'];finite=np.isfinite(cov).all();row={'file':str(p.relative_to(J)),'finite':bool(finite)}
  if finite:
   ev=np.linalg.eigvalsh(cov);tol=512*np.finfo(float).eps*max(abs(ev));row.update(min_eigenvalue=float(ev.min()),tolerance=float(tol),symmetry_error=float(np.max(abs(cov-cov.T))))
   if ev.min()<-tol or row['symmetry_error']>max(tol,1e-300):fail.append(row)
   sample=z['centered_samples'] if 'centered_samples' in z else z['calibration_vectors'];expect=np.cov(sample,rowvar=False);err=float(np.max(abs(expect-cov)));row['recomputed_covariance_max_error']=err
   if err>1e-12:fail.append(row)
  if 'finite_repeats' in z:row.update(finite_repeats=int(z['finite_repeats']),total_repeats=int(z['total_repeats']),mean_s0=float(z['mean_sr'][0]),mean_range0=float(z['mean_sr'][3]))
  else:row['independent_sites']=int(z['independent_site_count'])
  rows.append(row)
r={'passed':not fail,'files':rows,'failure_count':len(fail),'failures':fail,'finite_covariances':sum(x['finite'] for x in rows),'not_estimated_covariances':sum(not x['finite'] for x in rows),'scope':'centering/units/PSD and finite sample accounting only; no held-out predictive coverage test; estimation eligible flag is not model validation'}
(J/'RECEIVER_COV_INDEPENDENT_CHECK.json').write_text(json.dumps(r,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['files','failures']}));assert r['passed']
