"""Read-only estimator audit; diagnostic computations only, no filter rerun or repair."""
import sys,json,csv,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'POL_ANGLE_CALIBRATED_20261107_v5'));import model as m
cal=json.loads((m.BASE/'CALIBRATION.json').read_text(encoding='utf-8'))['parameters']
def dump(name,x):(BASE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
files=[Path(m.__file__),Path(m.base.__file__),Path(m.base.old.__file__),m.BASE/'CALIBRATION.json']+list((m.e.OLD/'verified_inputs').glob('*.npz'))
hashes={str(p.resolve()):m.sha(p) for p in files};dump('INPUT_HASHES.json',hashes)
rows=[];references=[];examples=[];summaries=[]
grid=np.deg2rad(np.arange(-180,180,.25))
for ch in ['los','full']:
 d=m.e.data(ch);truth=d['truth_for_offline_scoring_only'];xx=np.c_[truth,np.zeros(len(truth))];h,H=m.base.old.model(xx)
 scalar=np.array([m.e.LUT.model(x,m.e.CASE)[0][1] for x in xx]);assert np.max(abs(h-scalar))<1e-10
 noiseless=[];periodic=[];derivatives=[]
 for k,x in enumerate(xx):
  roots=m.roots(x,d['z_s'][k]);zero=m.roots(x,h[k]);closure=min([abs(m.e.wrap(a-x[2])) for a,_,_ in zero],default=np.inf);assert closure<1e-7;noiseless.append(closure)
  xturn=x.copy();xturn[2]+=2*np.pi;rt=m.roots(xturn,d['z_s'][k]);assert len(rt)==len(roots)
  periodic.append(max([min(abs(m.e.wrap(a-b)) for b,_,_ in rt) for a,_,_ in roots],default=0))
  delta=[abs(m.e.wrap(a-x[2])) for a,_,_ in roots];axis=[abs((a-x[2]+np.pi/2)%np.pi-np.pi/2) for a,_,_ in roots]
  row=dict(channel=ch,k=k,t=float(d['t_s'][k]),root_count=len(roots),error_deg=float(np.rad2deg(min(delta))) if roots else None,axial_error_deg=float(np.rad2deg(min(axis))) if roots else None,s_residual=float(d['z_s'][k]-h[k]),true_slope=float(abs(H[k,2])),horizontal_anchor_distance=float(np.hypot(x[0]-m.e.CASE['anchor'][0],x[1]-m.e.CASE['anchor'][1])))
  rows.append(row)
  # Dense sign-change brackets + canonical scalar LUT Brent root solver, independent of inverse knot interpolation.
  if k>=200 and (k%10==0 or (roots and min(delta)>np.pi/2)):
   X=np.tile(x,(len(grid),1));X[:,2]=grid;curve=m.base.old.model(X)[0]-d['z_s'][k];tt=np.r_[grid,grid[0]+2*np.pi];vv=np.r_[curve,curve[0]];ref=[]
   for j in np.flatnonzero(vv[:-1]*vv[1:]<0):
    def fun(angle):
     q=x.copy();q[2]=angle;return m.e.LUT.model(q,m.e.CASE)[0][1]-d['z_s'][k]
    ref.append(m.e.wrap(brentq(fun,tt[j],tt[j+1],xtol=1e-13)))
   error=max([min(abs(m.e.wrap(a-b)) for b,_,_ in roots) for a in ref],default=0.) if roots or not ref else np.pi
   missing=max([min(abs(m.e.wrap(a-b)) for b in ref) for a,_,_ in roots],default=0.) if ref or not roots else np.pi
   references.append(dict(channel=ch,k=k,production_count=len(roots),brent_count=len(ref),max_root_error_rad=float(max(error,missing))))
  if ch=='los' and k in [262,266]:
   X=np.tile(x,(len(grid),1));X[:,2]=grid;curve=m.base.old.model(X)[0];local=abs(m.e.wrap(grid-x[2]))<=np.deg2rad(30)
   angles=np.array([a for a,_,_ in roots]);sd=np.array([float(m.sigma(g,cal)) for a,H0,g in roots]);eps=cal['outlier_probability']
   def angular_like(angle):return eps/(2*np.pi)+(1-eps)*np.mean([np.exp(m.base.wrapped_stats(m.e.wrap(a-angle),s*s)[0]) for a,s in zip(angles,sd)])
   ratio=float(max(angular_like(a) for a in angles)/angular_like(x[2]))
   examples.append(dict(**row,true_heading_deg=float(np.rad2deg(m.e.wrap(x[2]))),roots_deg=np.rad2deg(angles).tolist(),observed_s=float(d['z_s'][k]),predicted_s=float(h[k]),local_pm30_s_range=[float(curve[local].min()),float(curve[local].max())],nearest_local_s_mismatch=float(np.min(abs(curve[local]-d['z_s'][k]))),original_s_likelihood_true_over_exact_root=float(np.exp(-.5*(d['z_s'][k]-h[k])**2/m.e.RS)),v5_angle_likelihood_best_root_over_truth=ratio))
 for label,selection in [('calibration',lambda r:r['t']<30),('evaluation',lambda r:r['t']>=40)]:
  selected=[r for r in rows if r['channel']==ch and selection(r)];valid=[r for r in selected if r['error_deg'] is not None];err=np.array([r['error_deg'] for r in valid]);ax=np.array([r['axial_error_deg'] for r in valid]);far=err>90
  summaries.append(dict(channel=ch,split=label,total=len(selected),supported=len(valid),directed_rmse_deg=float(np.sqrt(np.mean(err**2))),axial_rmse_deg=float(np.sqrt(np.mean(ax**2))),over90_count=int(far.sum()),over90_squared_error_fraction=float(np.sum(err[far]**2)/np.sum(err**2)),under90_rmse_deg=float(np.sqrt(np.mean(err[~far]**2))),max_abs_s_residual=float(max(abs(r['s_residual']) for r in selected)),s_residual_rms=float(np.sqrt(np.mean([r['s_residual']**2 for r in selected])))))
 dump(ch+'_FORWARD_CLOSURE.json',dict(scalar_vector_max_error=float(np.max(abs(h-scalar))),noiseless_inverse_max_error_deg=float(np.rad2deg(max(noiseless))),periodicity_max_error_deg=float(np.rad2deg(max(periodic)))))
 print(ch,'done',flush=True)
# Exact circular moment of unequal-variance wrapped Gaussian mixture, independent closed form.
mu0=np.zeros(4);mu1=np.zeros(4);mu1[2]=np.pi;P0=np.diag([.1,.1,.01,.001]);P1=np.diag([.1,.1,4.,.001]);parts=[(.4,mu0,P0),(.6,mu1,P1)];_,reported,_=m.base.moment(parts);exact=np.angle(.4*np.exp(-.01/2)+.6*np.exp(1j*np.pi-4./2))
dump('CIRCULAR_MOMENT_COUNTEREXAMPLE.json',dict(reported_heading_deg=float(np.rad2deg(reported[2])),exact_heading_deg=float(np.rad2deg(exact)),error_deg=float(np.rad2deg(abs(m.e.wrap(reported[2]-exact)))),scope='broad unequal-variance mixture; actual-run impact not established; cannot cause pre-filter inverse-angle diagnostic'))
with (BASE/'FRAME_DIAGNOSTIC.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
dump('ROOT_REFERENCE.json',references);dump('EXAMPLES.json',examples);dump('SUMMARY.json',summaries)
assert all(m.sha(p)==h for p,h in hashes.items())
dump('RESULT.json',dict(status='AUDIT_COMPUTATION_COMPLETED',role='AUDITOR_SELF_REVIEW_NOT_INDEPENDENT',estimator_files_changed=False,filter_rerun=False,inputs_unchanged=True,reference_cases=len(references),reference_count_disagreements=sum(r['production_count']!=r['brent_count'] for r in references),max_root_error_rad=max(r['max_root_error_rad'] for r in references)))
