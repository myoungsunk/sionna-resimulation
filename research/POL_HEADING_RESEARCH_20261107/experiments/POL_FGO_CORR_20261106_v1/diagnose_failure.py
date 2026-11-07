"""Post-hoc self-audit: read saved results and bounded local solver probes.
Does not modify frozen estimator, parameters, baseline, or original outputs.
"""
import experiment as e
import matched_gate as mg
import numpy as np,json
from scipy.optimize import least_squares
from pathlib import Path
OUT=e.BASE/'diagnosis_20261106';OUT.mkdir(exist_ok=True)
def save(name,x):(OUT/name).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf-8')
par=json.loads((e.BASE/'PARAMETERS.json').read_text());d=e.data('full');t=d['t_s'];truth=d['truth_for_offline_scoring_only']
h=np.array([e.LUT.model(x,e.CASE)[0][1] for x in truth]);res=d['z_s']-h
stats={}
for name,mask in [('train',t<30),('evaluation',t>=30)]:
 a=res[mask];v=a-a.mean();stats[name]={'n':len(a),'mean':float(a.mean()),'variance':float(v@v/len(v)),'rms':float(np.sqrt(np.mean(a*a))),'lag1':float(np.corrcoef(a[:-1],a[1:])[0,1]),'autocov':{str(l):float(v[l:]@v[:-l]/(len(v)-l)) for l in [1,2,5,10,20]}}
stats['model_autocov']={str(l):par['sigma_c2']*np.exp(-.2*l/par['tau_s']) for l in [1,2,5,10,20]}
stats['configured_total_variance']=par['total_variance'];save('RESIDUAL_STATS.json',stats)
rows=[]
for lv in ['B0','L0','L1','L2']:
 for method,folder in [('S4_original','outputs'),('FGO_basic_matched','matched_gate'),('FGO_corr_matched','matched_gate')]:
  z=np.load(e.BASE/f'{folder}/full_{lv}_{method}.npz');x=z['estimate'];P=z['covariance'];m=t>=30
  hp=np.array([e.LUT.model(a[:4],e.CASE)[0][1] for a in x]);ep=e.wrap(x[:,2]-truth[:,2]);row={'level':lv,'method':method,'heading_mean_deg':float(np.rad2deg(ep[m]).mean()),'bias_mean_dps':float(np.rad2deg(x[m,3]).mean())}
  if x.shape[1]==5:
   c=x[:,4];delta=hp-h;sol=json.loads((e.BASE/f'{folder}/full_{lv}_{method}_solver.json').read_text())
   row.update(c_rmse_vs_true_observation_error=float(np.sqrt(np.mean((c[m]-res[m])**2))),pose_prediction_error_rms=float(np.sqrt(np.mean(delta[m]**2))),postfit_residual_rms=float(np.sqrt(np.mean((res[m]-delta[m]-c[m])**2))),corr_c_pose_prediction_error=float(np.corrcoef(c[m],delta[m])[0,1]),solver_limit_count=sum(a['status']==0 for a in sol),solver_gtol_count=sum(a['status']==1 for a in sol),solver_max_optimality=max(a['optimality'] for a in sol),median_abs_heading_c_correlation=float(np.median(abs(P[m,2,4]/np.sqrt(P[m,2,2]*P[m,4,4])))))
  rows.append(row)
save('ATTRIBUTION.json',rows)
# Bounded local diagnostic: reconstruct B0 windows using unchanged code, compare
# selected SAME priors/objectives with a larger iteration allowance. Not a retuned trajectory.
saved=np.load(e.OLD/'results/replay/R2_aB_m0_full_B0_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
ctrl,x0=e.build_positive_bias_controls(t,truth,'B0');mu,P=e.initial(x0,5,par['sigma_c2']);start=0
orig=np.load(e.BASE/'matched_gate/full_B0_FGO_corr_matched.npz');oldsol=json.loads((e.BASE/'matched_gate/full_B0_FGO_corr_matched_solver.json').read_text())
selected=set([10,149,150,300,600,978,int(np.argmax(abs(e.wrap(orig['estimate'][:,2]-truth[:,2])))),int(np.argmax([a['optimality'] for a in oldsol]))]+[i for i,a in enumerate(oldsol) if a['status']==0])
probes=[];replay_max=0.;marg=[]
for k in range(len(t)):
 w=mg.MatchedWindow(mu,P,list(range(start,k+1)),ctrl,d['z_s'],par['R_epsilon'],par['sigma_c2'],par['tau_s'],mask=mask)
 xs,cov,info,v=w.solve();replay_max=max(replay_max,float(np.max(abs(xs[-1]-orig['estimate'][k]))))
 if k in selected:
  r,J,_,_=w.evaluate(v)
  alt=least_squares(lambda a:w.evaluate(a)[0],v,jac=lambda a:w.evaluate(a)[1],method='lm',max_nfev=600,ftol=1e-12,xtol=1e-12,gtol=1e-10)
  rr,jj,xx,DD=w.evaluate(alt.x)
  # A competing start uses prior-mean zero coordinates, same objective.
  alt0=least_squares(lambda a:w.evaluate(a)[0],np.zeros(w.n),jac=lambda a:w.evaluate(a)[1],method='lm',max_nfev=600,ftol=1e-12,xtol=1e-12,gtol=1e-10)
  probes.append({'k':k,'time_s':float(t[k]),'old_status':info['status'],'old_optimality':info['optimality'],'old_cost':info['cost'],'extra_cost':float(alt.cost),'extra_status':int(alt.status),'extra_optimality':float(alt.optimality),'heading_change_deg':float(np.rad2deg(e.wrap(xx[-1,2]-xs[-1,2]))),'xy_change_m':float(np.linalg.norm(xx[-1,:2]-xs[-1,:2])),'restart_cost':float(alt0.cost)})
  if k>start:
   # Compare correct linearization of the transition at optimized driving noise
   # with the implementation's zero-driving-noise expansion. Both are local approximations.
   nidx=start+1;dt=ctrl['dt_s'][nidx];ds=ctrl['ds_odom'][nidx];da=ctrl['dtheta_gyro'][nidx];std=e.noise_std(ds,dt);eta=v[w.d:w.d+2]
   pred,F,G=e.motion(xs[0],ds+std[0]*eta[0],da+std[1]*eta[1],dt);pred0,F0,G0=e.motion(xs[0],ds,da,dt)
   offset=pred-G@(std*eta)-pred0
   marg.append({'k':k,'noise_eta_norm':float(np.linalg.norm(eta)),'transition_intercept_max_abs':float(np.max(abs(offset))),'F_max_abs_difference':float(np.max(abs(F-F0))),'G_max_abs_difference':float(np.max(abs(G-G0)))})
 if k-start==e.LAG:mu,P=w.marginalize_oldest(xs[0]);start+=1
save('SOLVER_PROBES.json',{'scope':'B0 unchanged causal replay for extracting same-prior windows; alternative solves never propagated','selected_indices':sorted(selected),'saved_state_replay_max_abs':replay_max,'probes':probes,'marginalization_expansion_comparison':marg})
save('PROVENANCE.json',{'question_id':'POL-FGO-CORR-001-CAUSE','role':'AUDITOR self-review of own implementation, not independent audit','source_sha256':{f:e.sha(e.BASE/f) for f in ['experiment.py','matched_gate.py','PARAMETERS.json','CONTRACT.json']},'analysis_sha256':e.sha(__file__),'original_input_hashes_unchanged':all(e.sha(p)==h for p,h in json.loads((e.BASE/'INPUT_HASHES.json').read_text()).items()),'no_original_output_mutation':True})
print(json.dumps({'stats':stats,'probes':probes,'marginalization':marg,'replay_max':replay_max}),flush=True)
