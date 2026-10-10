from pathlib import Path
import json
import numpy as np,pandas as pd
J=Path('/job');OLD=Path('/old');rows=[];viol=[]
for folder in (J/'BODY_CONTROLS').glob('*/*'):
 if not (folder/'STATE_TRACE_A.npz').exists():continue
 case=folder.parent.name;tokens=folder.name.split('_');d=int(tokens[1][1:]);seed=int(tokens[2][1:]);base=case.rsplit('_m',1)[0]+'_m0';orig=np.load(OLD/'TRACES/main'/f'{base}_d{d}_s{seed}_A_stochastic_unknown.npz');z=np.load(folder/'STATE_TRACE_A.npz');oracle=np.load(folder/'ORACLE_EVAL_ONLY.npz');k=int(z['source_Tnone_index']);ep=oracle['true_xypsi'][0]-orig['truth'][k];ep[2]=(ep[2]+np.pi)%(2*np.pi)-np.pi
 errs={'pose':float(max(abs(ep))),'initial_state':float(max(abs(z['initial_state']-orig['pre_rf_state'][k]))),'initial_prior':float(np.max(abs(z['initial_prior']-orig['pre_rf_cov'][k]))),'static_sensor_parameters':float(max(abs(oracle['evaluation_true_parameters']-orig['evaluation_true_parameters'])))}
 eligible=bool(orig['keep'][k] and orig['completed'][k]);row={'case':case,'folder':folder.name,'source_Tnone_index':k,'source_time_s':float(orig['t'][k]),'source_eval_eligible':eligible,**errs};rows.append(row)
 if not eligible or max(errs.values())>1e-6:viol.append(row)
 masks={}
 for fp in folder.glob('STATE_TRACE_*.npz'):
  a=fp.stem.removeprefix('STATE_TRACE_');s=np.load(fp);last=int(s['last_valid_sample']);n=len(s['t_s']);valid=np.arange(n)<=last;endpoint=np.zeros(n,bool);endpoint[-1]=last==n-1 and str(s['error'])=='';third=np.zeros(n,bool);third[s['packet_indices'][-1]]=valid[s['packet_indices'][-1]];masks.update({a+'_valid_sample_mask':valid,a+'_endpoint_eval_mask':endpoint,a+'_third_RF_eval_mask':third})
 p=folder/'EVALUATION_MASKS.npz'
 if not p.exists():np.savez_compressed(p,**masks,source_prior_eligible=np.array(eligible),source_prior_time_s=orig['t'][k],scope=np.array('endpoint/third-RF diagnostic; no full-route evaluation'))
pd.DataFrame(rows).to_csv(J/'PRIOR_POSE_AND_CALIBRATION_CHECK.csv',index=False);r={'passed':not viol,'tasks':len(rows),'violations':viol,'max_difference':{key:max((x[key] for x in rows),default=None) for key in ['pose','initial_state','initial_prior','static_sensor_parameters']},'mask':'explicit last-valid, after-return endpoint, third-RF; original >=30s prior; failure not converted to success'};(J/'PRIOR_AND_MASK_CHECK.json').write_text(json.dumps(r,indent=2));print(json.dumps(r));assert r['passed']
