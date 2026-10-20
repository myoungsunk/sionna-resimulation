"""T7B strict nested utility labels, fixed learners and causal recursive policy.

Only run after protocol commit AND complete T4 final evidence. GT appears only
in controls generation, offline utility labels and scoring. Never in callback.
"""
from pathlib import Path
import argparse,importlib.util,json,os,pickle,sys,traceback
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingRegressor
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'T1_MEMORY'))
from replay import score
from unit_tests import load_engine
sys.path.insert(0,str(HERE.parent/'T4_F1_EVENT'))
from run_events import sha,load_npz,normalize,wrap
LOCK=json.loads((HERE/'PROTOCOL_LOCK.json').read_text(encoding='utf-8'))
ACTIONS=['POWER','R0','INFLATE4','SKIP']
MEASURED=['range_m','log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns',
          'eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
FEATURES=MEASURED+['power_nis','sigma_psi_rad','P_psi_bg','H_spsi']
OLD_CASES={'R2_aA_m0','R2_aA_m45','R2_aB_m0','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0'}
NEW_CASES={f'C0{i}_{a}_M45_FULL' for i in (1,2,3) for a in ('A','B')}|{f'O0{i}_O0_M45_FULL' for i in (1,2,3)}
BIASES={'B0','L0','L1','L2'}


def dependency_gate(t4,t7a):
    decision=json.loads((t4/'DECISION.json').read_text(encoding='utf-8'))
    receipt=json.loads((t4/'MANIFEST.json').read_text(encoding='utf-8'))
    if decision.get('scientific') not in ('SUPPORTED_BUT_LIMITED','FALSIFIED_FOR_TESTED','NOT_ESTABLISHED','CONFIRMED_IN_REPLAY'):
        raise ValueError('BLOCKED_DEPENDENCY:T4_FINAL_VERDICT_REQUIRED')
    protocol=json.loads((HERE.parent/'T4_F1_EVENT/PROTOCOL_LOCK.json').read_text(encoding='utf-8'))
    table_path=t4/'INTERVENTIONS.csv';table=pd.read_csv(table_path)
    metric_columns=['heading_rmse_deg','signed_heading_deg','heading_sigma_rms_deg','heading95','heading_nees',
                    'pose_nees','conditional_xy_nees','xy_rmse_m','bias_rmse_dps','bias_mean_dps','bias_final_dps']
    if not set(metric_columns).issubset(table.columns):raise ValueError('BLOCKED_DEPENDENCY:T4_METRICS_MISSING')
    required={'POWER1','SKIP','D1','D2','D3','D5','D6'}
    errors_path=t4/'ERRORS.json'
    errors=json.loads(errors_path.read_text(encoding='utf-8')) if errors_path.is_file() else []
    if not isinstance(errors,list):raise ValueError('BLOCKED_DEPENDENCY:T4_ERRORS_SCHEMA_REQUIRES_FLAT_LIST')
    for error in errors:
        if error.get('arm')!='D4' or 'NONSPD' not in str(error.get('error','')).upper():
            raise ValueError('BLOCKED_DEPENDENCY:T4_NON_D4_OR_NONSPD_ERROR:'+str(error))
    for event in protocol['events']:
        subset=table[(table.event==event['event'])&(table.scope=='GLOBAL_T30')]
        for arm in required:
            row=subset[subset.arm==arm]
            if len(row)!=1 or row.iloc[0].get('status')!='TECHNICAL_PASS':
                raise ValueError('BLOCKED_DEPENDENCY:T4_INCOMPLETE:'+event['event']+':'+arm)
            if not np.isfinite(row[metric_columns].to_numpy(float)).all():raise ValueError('BLOCKED_DEPENDENCY:T4_NONFINITE_METRIC')
            if not np.isfinite(float(row.iloc[0]['scorer_max_abs_difference'])) or float(row.iloc[0]['scorer_max_abs_difference'])>1e-9:
                raise ValueError('BLOCKED_DEPENDENCY:T4_SCORER_FAILURE')
        d4=subset[subset.arm=='D4']
        if len(d4)>1:raise ValueError('BLOCKED_DEPENDENCY:T4_DUPLICATE_D4')
        if len(d4)==1 and d4.iloc[0].get('status')=='TECHNICAL_PASS':
            if not np.isfinite(float(d4.iloc[0]['scorer_max_abs_difference'])) or float(d4.iloc[0]['scorer_max_abs_difference'])>1e-9:
                raise ValueError('BLOCKED_DEPENDENCY:T4_D4_SCORER_FAILURE')
        elif not any(e.get('event')==event['event'] and e.get('arm')=='D4' for e in errors):
            raise ValueError('BLOCKED_DEPENDENCY:T4_D4_MISSING_WITHOUT_PRESERVED_NONSPD:'+event['event'])
    checks_path=t4/'BASELINE_CHECKS.csv'
    if not checks_path.is_file():raise ValueError('BLOCKED_DEPENDENCY:T4_BASELINE_CHECKS_REQUIRED')
    checks=pd.read_csv(checks_path)
    if not {e['case'] for e in protocol['events']}.issubset(set(checks.case)):
        raise ValueError('BLOCKED_DEPENDENCY:T4_BASELINE_CHECKS_INCOMPLETE')
    for col in ('stored_heading_difference_deg','key_b0_heading_difference_deg'):
        if col in checks and (checks[col].dropna()>1e-6).any():raise ValueError('BLOCKED_DEPENDENCY:T4_BASELINE_RMSE')
    if 'stored_heading_difference_deg' not in checks or not np.isfinite(checks.stored_heading_difference_deg).all():
        raise ValueError('BLOCKED_DEPENDENCY:T4_BASELINE_RMSE_MISSING')
    if 'gate_mismatches' not in checks or (checks.gate_mismatches!=0).any():raise ValueError('BLOCKED_DEPENDENCY:T4_BASELINE_GATES')
    recovered=json.loads(t7a.read_text(encoding='utf-8'))
    if not recovered.get('artifact_sha256'):raise ValueError('BLOCKED_DEPENDENCY:T7A_RECEIPT')
    paths=[t4/'DECISION.json',t4/'MANIFEST.json',table_path,checks_path,t7a]
    if errors_path.is_file():paths.append(errors_path)
    return {str(p):sha(p) for p in paths}


def runtime(source,execution,out):
    load_engine(source)
    for rel in ('research/CHAIN_HYPOTHESIS_20261019','research/R5_N4B_20261015','research/PHYSICS_RS_STAGED_20261015/code','research/FFD_P0P3_20261016'):
        sys.path.insert(0,str(source/rel))
    sys.path.insert(0,str(HERE.parent))
    sp=importlib.util.spec_from_file_location('utility_exact_chain_run',source/'research/CHAIN_HYPOTHESIS_20261019/run.py')
    original=importlib.util.module_from_spec(sp);sp.loader.exec_module(original)
    if original.ROOT.resolve()!=source.resolve() or original.DATA.resolve()!=execution.resolve():raise ValueError('EXPECTED_EXECUTION_ROOT_SOURCE_LAYOUT')
    if list(original.FEATURES)!=MEASURED:raise ValueError('PINNED_FEATURE_SCHEMA_CHANGED')
    import p0_initial
    p0_initial.DATA=execution;p0_initial.OUT=out/'bank_audit';p0_initial.OUT.mkdir(exist_ok=True)
    from source_model import SourceFFD
    from scalar_power import ScalarPower
    import canonical_engine as engine
    cases=json.loads((source/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases']
    return original,engine,SourceFFD(),ScalarPower,cases


def inputs_receipt(source,execution):
    paths=[source/'research/CHAIN_HYPOTHESIS_20261019/run.py',source/'research/FFD_P0P3_20261016/source_model.py',
           source/'research/R5_N4B_20261015/n4b_rf_errors.py',source/'research/PHYSICS_RS_STAGED_20261015/code/features.py',
           source/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src/r2_bias_replay.py',
           execution/'rf_frozen.zip',execution/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz',
           execution/'reference_ae/OOF_PARAMETERS.csv.gz',HERE.parent/'canonical_engine.py',HERE.parent/'scalar_power.py',
           HERE.parent/'T1_MEMORY/replay.py',HERE.parent/'T1_MEMORY/vendor/core.py']
    return {str(p):sha(p) for p in paths if p.is_file()}


def internal_features(measured,prior,P,h,H,mu,C,z):
    nu=z-h-mu;S=H@P@H.T+C
    extra=np.array([nu@np.linalg.solve(S,nu),np.sqrt(P[2,2]),P[2,3],H[1,2]])
    values=np.r_[measured,extra]
    if values.shape!=(len(FEATURES),) or not np.isfinite(values).all():raise ValueError('INVALID_CAUSAL_FEATURES')
    return values


def controls(data):return dict(dt_s=data['controls_dt'],ds_odom=data['controls_ds'],dtheta_gyro=data['controls_dyaw'])


def regular_run(engine,model,data,case,spec,callback=None):
    return engine.run(data['t'],controls(data),data['initial_pose'],data['z'],data['mu'],data['C'],data['risk'],case,model,[spec],
                      radio_mask=data['radio_mask'],decision_provider=callback)


def old_data(original,raw,case,label,frame,mu=None,C=None,channel='full'):
    packet=raw[case['id'],channel];ids=packet['pose_id'];ordered=frame.set_index('pose_id').loc[ids]
    t=packet['t_s'];truth=packet['truth_for_offline_scoring_only'][:,:3]
    if np.max(abs(np.c_[packet['z_r_m'],packet['z_s']]-ordered[['range_m','s_fp']].to_numpy()))>1e-10:
        raise ValueError('OLD_FEATURE_OBSERVATION_PARITY')
    ctrl,initial=original.build_positive_bias_controls(t,truth,label,0)
    if mu is None:
        mu=ordered[['mu_r','mu_s']].to_numpy();C=np.zeros((len(t),2,2))
        C[:,0,0]=ordered.C00;C[:,1,1]=ordered.C11;C[:,0,1]=C[:,1,0]=ordered.C01
    data=dict(t=t,truth=truth,initial_pose=initial,z=np.c_[packet['z_r_m'],packet['z_s']],mu=mu,C=C,risk=np.zeros(len(t)),
              controls_dt=ctrl['dt_s'],controls_ds=ctrl['ds_odom'],controls_dyaw=ctrl['dtheta_gyro'],radio_mask=np.ones(len(t),bool))
    return data,ordered[MEASURED].to_numpy(),ids


def choose_training_indices(t,radio):
    selected=[];next_time=30.
    for i in np.flatnonzero(radio):
        if t[i]>=next_time and t[i]+10<=t[-1]:selected.append(int(i));next_time=float(t[i]+5.)
    return selected


def label_command(args,inputs):
    original,engine,model,ScalarPower,cases=runtime(args.source_root,args.execution_root,args.out)
    inputs.update(inputs_receipt(args.source_root,args.execution_root))
    raw=original.frozen_inputs();df=pd.read_csv(args.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz')
    full=df[df.channel=='full'].copy().reset_index(drop=True)
    outer=None if args.outer=='ALL_OLD' else args.outer
    rows=[];fits=[];errors=[]
    for inner in ('R2','R4','R5'):
        if inner==outer:continue
        target=full[full.route==inner]
        allowed=full[(full.route!=inner)&(full.route!=outer)].copy()
        distance=cKDTree(target[['x_eval','y_eval']].to_numpy()).query(allowed[['x_eval','y_eval']].to_numpy())[0]
        train=allowed.loc[distance>1e-4].copy()
        if len(train)<100 or (outer is not None and outer in set(train.route)):raise ValueError('INVALID_NESTED_TRAIN_FOLD')
        fitted=ScalarPower(train,train.log_fp_power.to_numpy(),original.site_weights(np,pd,train),original.GROUPS)
        fits.append(dict(outer=args.outer,inner=inner,training_routes=sorted(set(train.route)),n_train=len(train),
                         training_keys=train[['case','pose_id']].values.tolist(),cutpoints=fitted.cuts.tolist(),
                         ridge_coef=fitted.ridge.coef_.tolist(),ridge_intercept=fitted.ridge.intercept_.tolist()))
        for case in [c for c in cases if c['id'].split('_')[0]==inner]:
            cid=case['id'];frame=target[target.case==cid].copy()
            ordered=frame.set_index('pose_id').loc[raw[cid,'full']['pose_id']]
            mu,C=fitted.predict(ordered.log_fp_power.to_numpy())
            data,measured,ids=old_data(original,raw,case,'B0',frame,mu,C)
            baseline=regular_run(engine,model,data,case,dict(name='POWER',base='power'))
            # Nested baseline is newly fitted, not claimed equal to historical OOF.
            for i in choose_training_indices(data['t'],data['radio_mask']):
                try:
                    end=int(np.searchsorted(data['t'],data['t'][i]+10,side='right'))
                    prior=baseline['prior'][i,0,:4];P=baseline['prior_cov'][i,0,:4,:4]
                    feature=internal_features(measured[i],prior,P,baseline['h'][i,0],baseline['H'][i,0,:,:4],mu[i],C[i],data['z'][i])
                    specs=[dict(name=a,base='power',first_action=a) for a in ACTIONS]
                    ctrl={k:v[i:end] for k,v in controls(data).items()}
                    branch=engine.run(data['t'][i:end],ctrl,data['initial_pose'],data['z'][i:end],mu[i:end],C[i:end],
                         np.zeros(end-i),case,model,specs,initial_state4=prior,initial_cov=P,
                         decision_provider=lambda k,x,p,h,H,m,c,s:s['first_action'] if k==0 else 'POWER')
                    mask=branch['t']>data['t'][i]
                    errors_deg=np.degrees(wrap(branch['state'][mask,:,2]-data['truth'][i:end][mask,2,None]))
                    mse=np.mean(errors_deg**2,axis=0)
                    # Same-prior POWER branch must reproduce the source nested baseline.
                    state_delta=float(abs(branch['state'][:,0,:4]-baseline['state'][i:end,0,:4]).max())
                    cov_delta=float(abs(branch['cov'][:,0,:4,:4]-baseline['cov'][i:end,0,:4,:4]).max())
                    gate_delta=int(np.count_nonzero(branch['accepted'][:,0]!=baseline['accepted'][i:end,0]))
                    if max(state_delta,cov_delta)>1e-10 or gate_delta:raise RuntimeError('COUNTERFACTUAL_POWER_RESTART_PARITY')
                    row=dict(outer=args.outer,inner_route=inner,case=cid,pose_id=int(ids[i]),frame=i,t_s=float(data['t'][i]),
                             label_class='ORACLE_OFFLINE_TRAINING_LABEL',horizon_samples=int(mask.sum()),
                             power_restart_state_max=state_delta,power_restart_cov_max=cov_delta,power_restart_gate_mismatch=gate_delta,
                             **dict(zip(FEATURES,map(float,feature))))
                    for j,action in enumerate(ACTIONS):
                        row['mse_'+action]=float(mse[j]);row['utility_'+action]=float(mse[0]-mse[j]);row['sign_'+action]=int(np.sign(mse[0]-mse[j]))
                    rows.append(row)
                except Exception as exc:
                    errors.append(dict(case=cid,outer=args.outer,frame=i,error=str(exc),traceback=traceback.format_exc(),retry=False))
            print('UTILITY_LABEL_CASE',args.outer,cid,len(rows),flush=True)
            pd.DataFrame(rows).to_csv(args.out/'UTILITY_LABELS.csv',index=False)
    (args.out/'TRAIN_FOLDS.json').write_text(json.dumps(fits,indent=2),encoding='utf-8')
    return rows,errors


def train_command(args,inputs):
    frames=[]
    for path in args.labels:
        receipt_path=path.parent/'MANIFEST.json';inputs[str(receipt_path)]=sha(receipt_path)
        receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
        if receipt.get('technical')!='TECHNICAL_PASS' or receipt.get('stage')!='labels' or receipt.get('protocol_sha256')!=sha(HERE/'PROTOCOL_LOCK.json'):
            raise ValueError('TRAIN_LABEL_RECEIPT_NOT_PASS:'+str(path))
        if receipt.get('outputs',{}).get(path.name)!=sha(path):raise ValueError('TRAIN_LABEL_HASH_MISMATCH:'+str(path))
        inputs[str(path)]=sha(path);frames.append(pd.read_csv(path))
    labels=pd.concat(frames,ignore_index=True)
    if labels.duplicated(['outer','case','frame']).any():raise ValueError('DUPLICATE_UTILITY_LABEL')
    manifest=dict(feature_names=FEATURES,actions=ACTIONS,models={},input_sha256=inputs,
                  sklearn_version=__import__('sklearn').__version__,protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'))
    hyper={k:v for k,v in LOCK['learner'].items() if k not in ('model','selection')}
    for outer in ('R2','R4','R5','ALL_OLD'):
        subset=labels[labels.outer==outer].copy()
        if len(subset)<40:raise ValueError('TOO_FEW_UTILITY_LABELS:'+outer)
        if outer!='ALL_OLD' and outer in set(subset.inner_route):raise ValueError('OUTER_ROUTE_LABEL_LEAK')
        estimators=[]
        for action in ACTIONS:
            fitted=HistGradientBoostingRegressor(**hyper).fit(subset[FEATURES].to_numpy(),subset['utility_'+action].to_numpy())
            estimators.append(fitted)
        path=args.out/(outer+'.pkl')
        with path.open('wb') as stream:pickle.dump(estimators,stream,protocol=5)
        manifest['models'][outer]=dict(file=path.name,sha256=sha(path),n_train=len(subset),training_routes=sorted(set(subset.inner_route)))
    (args.out/'MODELS.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return labels.to_dict('records'),[]


def load_models(path,inputs):
    inputs[str(path)]=sha(path);manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest['feature_names']!=FEATURES or manifest['actions']!=ACTIONS:raise ValueError('MODEL_SCHEMA_MISMATCH')
    if manifest['protocol_sha256']!=sha(HERE/'PROTOCOL_LOCK.json'):raise ValueError('MODEL_PROTOCOL_MISMATCH')
    if manifest['sklearn_version']!=__import__('sklearn').__version__:raise ValueError('MODEL_SKLEARN_VERSION_MISMATCH')
    models={}
    for name,rec in manifest['models'].items():
        file=(path.parent/rec['file']).resolve()
        if file.parent!=path.parent.resolve() or sha(file)!=rec['sha256']:raise ValueError('MODEL_HASH_OR_PATH_MISMATCH')
        inputs[str(file)]=rec['sha256']
        with file.open('rb') as stream:models[name]=pickle.load(stream)
    return models


def score_checked(result,data,bias,mask):
    a=score(result['state'][:,0],result['cov'][:,0],data['truth'],bias,mask)
    b=score(result['state'][:,0],result['cov'][:,0],data['truth'],bias,mask,scalar=True)
    delta=max(abs(a[k]-b[k]) for k in a)
    if delta>1e-9 or not np.isfinite(list(a.values())).all():raise RuntimeError('INDEPENDENT_SCORE:'+str(delta))
    return dict(scorer_max_abs_difference=delta,**a)


def evaluate_command(args,inputs):
    original,engine,model,_,cases=runtime(args.source_root,args.execution_root,args.out)
    inputs.update(inputs_receipt(args.source_root,args.execution_root));models=load_models(args.models,inputs)
    raw=original.frozen_inputs();labels=pd.read_csv(args.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz')
    cached=pd.read_csv(args.execution_root/'reference_ae/OOF_PARAMETERS.csv.gz');key=pd.read_csv(args.key_b0)
    inputs[str(args.key_b0)]=sha(args.key_b0)
    rows=[];checks=[];actions=[];errors=[]
    items=[]
    if args.old_bundle:
        inputs[str(args.old_bundle)]=sha(args.old_bundle)
        bundle=json.loads(args.old_bundle.read_text(encoding='utf-8'))
        for item in bundle['cases']:
            case=item['case'];cid=case['id'];label=item['bias'];path=args.old_bundle.parent/item['npz']
            inputs[str(path)]=sha(path);data=normalize(load_npz(path))
            ids=raw[cid,'full']['pose_id'];measured=labels[(labels.case==cid)&(labels.channel=='full')].set_index('pose_id').loc[ids,MEASURED].to_numpy()
            items.append((case,label,item['bias_dps'],'full','old',data,measured,args.old_bundle.parent/item['historical_power1_trace']))
        for case in [c for c in cases if c['id'] in ('R2_aA_m0','R2_aA_m45')]:
            cid=case['id']
            frame=labels[(labels.case==cid)&(labels.channel=='los')].merge(cached[(cached.case==cid)&(cached.channel=='los')][['pose_id','mu_r','mu_s','C00','C01','C11']],on='pose_id',validate='one_to_one')
            for label,bias in original.BIAS_LEVELS.items():
                data,measured,_=old_data(original,raw,case,label,frame,channel='los')
                items.append((case,label,bias,'los','old',data,measured,None))
    if args.new_config:
        inputs[str(args.new_config)]=sha(args.new_config)
        config=json.loads(args.new_config.read_text(encoding='utf-8'))
        if config.get('range_model','B_OLD')!='B_OLD':raise ValueError('NEW_RANGE_MODEL_REQUIRES_NEW_LOCK')
        for item in config['cases']:
            case=item['case'];path=args.new_config.parent/item['npz'];feature_path=args.new_config.parent/item['features']
            if case['id'] not in NEW_CASES or item['bias'] not in BIASES:raise ValueError('UNREGISTERED_NEW_CASE_OR_BIAS')
            inputs[str(path)]=sha(path);inputs[str(feature_path)]=sha(feature_path);data=normalize(load_npz(path))
            frame=pd.read_csv(feature_path)
            if 'case' in frame:frame=frame[frame.case==case['id']]
            frame=frame.set_index('pose_id',verify_integrity=True).loc[data['radio_pose_ids']]
            if np.max(abs(frame[['range_m','s_fp']].to_numpy()-data['z'][data['radio_mask']]))>1e-10:raise ValueError('NEW_FEATURE_OBSERVATION_PARITY')
            measured=np.zeros((len(data['t']),len(MEASURED)));measured[data['radio_mask']]=frame[MEASURED].to_numpy()
            items.append((case,item['bias'],item['bias_dps'],'full','new',data,measured,path))
    seen=set()
    for case,label,bias,channel,dataset,data,measured,reference in items:
        cid=case['id'];identity=(cid,label,channel)
        if identity in seen:raise ValueError('DUPLICATE_EVALUATION_CELL:'+str(identity))
        seen.add(identity);route=cid.split('_')[0];policy_models=models['ALL_OLD' if dataset=='new' else route]
        for arm in ('POWER1','R0','POLICY'):
            try:
                def callback(i,prior,P,h,H,mu,C,spec):
                    feature=internal_features(measured[i],prior,P,h,H,mu,C,data['z'][i])
                    predicted=np.array([est.predict(feature[None])[0] for est in policy_models]);action=ACTIONS[int(np.argmax(predicted))]
                    rec=dict(case=cid,channel=channel,bias=label,dataset=dataset,frame=i,t_s=float(data['t'][i]),action=action,
                             **dict(zip(FEATURES,map(float,feature))))
                    rec.update({'predicted_utility_'+a:float(v) for a,v in zip(ACTIONS,predicted)});actions.append(rec)
                    return action
                result=regular_run(engine,model,data,case,dict(name=arm,base='r0' if arm=='R0' else 'power'),callback if arm=='POLICY' else None)
                if arm=='POWER1' and reference is not None:
                    inputs[str(reference)]=sha(reference);old=load_npz(reference);j=list(old['names'].astype(str)).index('POWER1');mask=data['t']>=30
                    old_rmse=float(np.sqrt(np.mean(np.degrees(wrap(old['state'][mask,j,2]-data['truth'][mask,2]))**2)))
                    metrics=score_checked(result,data,bias,mask)
                    check=dict(case=cid,channel=channel,bias=label,heading_difference_deg=abs(metrics['heading_rmse_deg']-old_rmse),gate_mismatches=int(np.count_nonzero(result['accepted'][:,0]!=old['accepted'][:,j])))
                    if check['heading_difference_deg']>1e-6 or check['gate_mismatches']:raise RuntimeError('BASELINE_REFERENCE_PARITY')
                    if dataset=='old' and label=='B0':
                        row=key[(key.case==cid)&(key.method=='POWER1')]
                        if len(row)!=1 or abs(float(row.iloc[0].heading_rmse_deg)-metrics['heading_rmse_deg'])>1e-6:raise RuntimeError('KEY_B0_PARITY')
                    checks.append(check)
                for scope,mask in [('motion',data['t']>=30),('radio',(data['t']>=30)&data['radio_mask'])]:
                    rows.append(dict(case=cid,channel=channel,bias=label,dataset=dataset,arm=arm,scope=scope,**score_checked(result,data,bias,mask)))
                (args.out/'traces').mkdir(exist_ok=True)
                np.savez_compressed(args.out/'traces'/f'{cid}_{channel}_{label}_{arm}.npz',**result)
            except Exception as exc:
                errors.append(dict(case=cid,channel=channel,bias=label,arm=arm,error=str(exc),traceback=traceback.format_exc(),retry=False))
                if arm=='POWER1':break
        pd.DataFrame(rows).to_csv(args.out/'POLICY_RESULTS.csv',index=False)
    pd.DataFrame(checks).to_csv(args.out/'BASELINE_CHECKS.csv',index=False)
    if actions:
        for (cid,channel,label),frame in pd.DataFrame(actions).groupby(['case','channel','bias']):frame.to_csv(args.out/f'ACTIONS_{cid}_{channel}_{label}.csv',index=False)
    return rows,errors


def decision(rows):
    lookup={(r['case'],r['bias'],r['channel'],r['arm']):r for r in rows if r['scope']=='motion'}
    comparison=[]
    for cid,label,channel in sorted({(r['case'],r['bias'],r['channel']) for r in rows}):
        policy=lookup.get((cid,label,channel,'POLICY'));base=lookup.get((cid,label,channel,'POWER1' if channel=='full' else 'R0'))
        if policy is None or base is None:continue
        comparison.append(dict(case=cid,bias=label,channel=channel,ratio=policy['heading_rmse_deg']/base['heading_rmse_deg'],
                               pass_10pct=policy['heading_rmse_deg']<=1.1*base['heading_rmse_deg']))
    expected={(cid,bias,'full') for cid in OLD_CASES|NEW_CASES for bias in BIASES}|{(cid,bias,'los') for cid in ('R2_aA_m0','R2_aA_m45') for bias in BIASES}
    present={(r['case'],r['bias'],r['channel']) for r in comparison}
    complete=present==expected
    passed=complete and all(r['pass_10pct'] for r in comparison)
    return dict(complete=complete,go_no_go='GO_LIMITED' if passed else 'NO_GO',
                scientific='SUPPORTED_BUT_LIMITED' if passed else 'NOT_ESTABLISHED',cells=comparison)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['labels','train','evaluate','aggregate'])
    p.add_argument('--source-root',type=Path);p.add_argument('--execution-root',type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--t4-final',type=Path,required=True)
    p.add_argument('--t7a-receipt',type=Path,default=HERE/'RECOVERY_MANIFEST.json')
    p.add_argument('--outer',choices=['R2','R4','R5','ALL_OLD']);p.add_argument('--labels',type=Path,nargs='+')
    p.add_argument('--models',type=Path);p.add_argument('--old-bundle',type=Path);p.add_argument('--new-config',type=Path)
    p.add_argument('--aggregate',type=Path,nargs='+');p.add_argument('--key-b0',type=Path,default=HERE.parents[2]/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    inputs={str(HERE/'PROTOCOL_LOCK.json'):sha(HERE/'PROTOCOL_LOCK.json'),str(Path(__file__)):sha(Path(__file__))};rows=[];errors=[]
    try:
        inputs.update(dependency_gate(args.t4_final,args.t7a_receipt))
        if args.command in ('labels','evaluate') and (args.source_root is None or args.execution_root is None):p.error('source/execution roots required')
        if args.command=='labels':
            if args.outer is None:p.error('--outer required')
            rows,errors=label_command(args,inputs)
        elif args.command=='train':
            if not args.labels:p.error('--labels required')
            rows,errors=train_command(args,inputs)
        elif args.command=='evaluate':
            if args.models is None or not(args.old_bundle or args.new_config):p.error('--models plus old-bundle or new-config required')
            rows,errors=evaluate_command(args,inputs)
        else:
            if not args.aggregate:p.error('--aggregate required')
            for file in args.aggregate:inputs[str(file)]=sha(file);rows.extend(pd.read_csv(file).to_dict('records'))
            if pd.DataFrame(rows).duplicated(['case','bias','channel','arm','scope']).any():raise ValueError('DUPLICATE_POLICY_RESULT')
            pd.DataFrame(rows).to_csv(args.out/'POLICY_RESULTS.csv',index=False)
    except Exception as exc:errors.append(dict(error=str(exc),traceback=traceback.format_exc(),retry=False))
    for file in args.out.glob('*.csv'):
        if file.stat().st_size>20_000_000:errors.append(dict(error='CSV_EXCEEDS_20MB:'+file.name,retry=False))
    (args.out/'ERRORS.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    result=decision(rows) if args.command in ('evaluate','aggregate') else dict(scientific='NOT_ESTABLISHED',stage=args.command)
    if errors:result['scientific']='NOT_ESTABLISHED'
    (args.out/'DECISION.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    manifest=dict(task='T7B_UTILITY_POLICY',stage=args.command,technical='TECHNICAL_PASS' if not errors else 'ERROR_OR_BLOCKED_DEPENDENCY',
                  scientific=result['scientific'],protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),inputs=inputs,actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,
                  outputs={p.name:sha(p) for p in args.out.iterdir() if p.is_file() and p.name!='MANIFEST.json'})
    (args.out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    report='# T7B 효용 target 정책\n\nTECHNICAL: '+manifest['technical']+'; 과학 판정: '+result['scientific']+'.\n\n'
    report+='Nested route-heldout P1 prior 생성과 정책 label 학습을 분리한다. 학습 GT는 offline label에만, 온라인 결정은 실제 RF 특징과 해당 정책의 prior 내부량만 사용한다. 10 s label은 같은 prior에서 현재 행동만 바꾸고 이후 POWER로 계산한다. 단계별 완료는 전체 정책 승인과 다르다.\n\n'
    report+='## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. NO-GO와 오류도 보존한다.\n'
    (args.out/'RESULTS_KO.md').write_text(report,encoding='utf-8')
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
