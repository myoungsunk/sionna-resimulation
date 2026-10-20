"""Locked q/delta-q/distance ablations with causal prior-state parameters."""
from pathlib import Path
import argparse, importlib.util, json, os, sys, traceback
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
HERE=Path(__file__).resolve().parent; REPO=HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'T1_MEMORY'))
from replay import score
from unit_tests import load_engine
sys.path.insert(0,str(HERE.parent/'T4_F1_EVENT'))
from run_events import sha,load_npz,wrap
LOCK=json.loads((HERE/'PROTOCOL_LOCK.json').read_text(encoding='utf-8'))
ARMS=LOCK['arms']; R0=np.diag([.0068578637,.0081])


def geometry(states,case):
    states=np.atleast_2d(states); anchor=np.asarray(case['anchor'])
    dx=anchor[0]-states[:,0]; dy=anchor[1]-states[:,1]
    distance=np.sqrt(dx*dx+dy*dy+(anchor[2]-case['robot_z_m'])**2)
    theta=wrap(np.arctan2(dy,dx)-states[:,2]-np.radians(case['mount_deg']))
    logd=np.log10(np.maximum(distance,1e-6))
    X=np.column_stack([logd,logd**2,np.cos(theta),np.sin(theta),np.cos(2*theta),np.sin(2*theta),
          np.full(len(states),case['mount_deg']/45),*[np.full(len(states),v/10) for v in anchor]])
    return distance,theta,X


def frame_geometry(frame,cases):
    d=np.empty(len(frame)); theta=np.empty(len(frame)); X=np.empty((len(frame),10))
    ids=frame.case.to_numpy()
    for cid in np.unique(ids):
        ix=np.flatnonzero(ids==cid)
        state=frame.iloc[ix][['x_eval','y_eval','yaw_rad']].to_numpy()
        d[ix],theta[ix],X[ix]=geometry(state,cases[cid])
    return d,theta,X


def serialize_scalar(model):
    return dict(scaler_mean=model.scaler.mean_.tolist(),scaler_scale=model.scaler.scale_.tolist(),
                ridge_coef=model.ridge.coef_.tolist(),ridge_intercept=model.ridge.intercept_.tolist(),
                cuts=model.cuts.tolist(),offsets=model.offsets.tolist(),covs=model.covs.tolist(),info=model.info)


def independent(result,truth,bias,mask):
    values=score(result['state'][:,0],result['cov'][:,0],truth,bias,mask)
    other=score(result['state'][:,0],result['cov'][:,0],truth,bias,mask,scalar=True)
    diff=max(abs(values[k]-other[k]) for k in values)
    if not np.isfinite(list(values.values())).all() or diff>1e-9: raise RuntimeError('SCORER:'+str(diff))
    return values,diff


def historical_check(result,truth,bias,cid,label,t,reference,key):
    old=load_npz(reference); j=list(old['names'].astype(str)).index('POWER1'); mask=t>=30
    if len(old['state'])!=len(t): raise ValueError('REFERENCE_LENGTH')
    expected=float(np.sqrt(np.mean(np.degrees(wrap(old['state'][mask,j,2]-truth[mask,2]))**2)))
    values,delta=independent(result,truth,bias,mask)
    check=dict(case=cid,bias=label,heading_difference_deg=abs(values['heading_rmse_deg']-expected),
               gate_mismatches=int(np.count_nonzero(old['accepted'][:,j]!=result['accepted'][:,0])),scorer_max_abs=delta)
    if check['heading_difference_deg']>1e-6 or check['gate_mismatches']: raise RuntimeError('Q_REFERENCE_PARITY:'+str(check))
    if label=='B0':
        row=key[(key.case==cid)&(key.method=='POWER1')]
        if len(row)!=1: raise ValueError('MISSING_KEY_B0')
        check['key_b0_difference_deg']=abs(values['heading_rmse_deg']-float(row.iloc[0].heading_rmse_deg))
        if check['key_b0_difference_deg']>1e-6: raise RuntimeError('KEY_B0_PARITY')
    return check


def verdict(rows):
    lookup={(r['case'],r['channel'],r['bias'],r['arm']):r['heading_rmse_deg'] for r in rows}
    comparisons=[]; positive=[]; delta_ok=[]; los_ok=[]; los_improvement=[]
    for cid,channel,label in sorted({(r['case'],r['channel'],r['bias']) for r in rows}):
        vals={arm:lookup.get((cid,channel,label,arm)) for arm in ARMS}
        if any(v is None for v in vals.values()): continue
        r0,q,dq,d=[vals[a] for a in ARMS]; gain=r0-q
        rec=dict(case=cid,channel=channel,bias=label,q_gain_deg=gain,distance_gain_deg=r0-d,
                 delta_q_minus_q_deg=dq-q,q_minus_r0_deg=q-r0,delta_q_minus_r0_deg=dq-r0)
        if channel=='full':
            delta_ok.append(dq<=q+1e-6)
            if gain>1e-6: rec['distance_gain_fraction']=(r0-d)/gain; positive.append(rec)
            else: rec['gain_status']='NONPOSITIVE_OR_TINY_POWER_GAIN_NO_RATIO'
        else:
            los_ok.append(max(0.,dq-r0)<=max(0.,q-r0)+1e-6)
            los_improvement.append(max(0.,q-r0)-max(0.,dq-r0)>1e-6)
        comparisons.append(rec)
    full_count=sum(1 for r in comparisons if r['channel']=='full'); los_count=len(comparisons)-full_count
    complete=(full_count==14 and los_count==4)
    distance=complete and bool(positive) and all(r['distance_gain_fraction']>=.8 for r in positive)
    adoption=complete and all(delta_ok) and all(los_ok) and any(los_improvement)
    decision=dict(complete=complete,distance_scientific='SUPPORTED_BUT_LIMITED' if distance else 'NOT_ESTABLISHED',
                  delta_q_scientific='SUPPORTED_BUT_LIMITED' if adoption else 'NOT_ESTABLISHED',
                  delta_q_adoption_candidate=adoption,positive_power_gain_cells=len(positive),
                  full_cells=full_count,native_los_cells=los_count,
                  sum_positive_gain_ratio=(sum(r['distance_gain_deg'] for r in positive)/sum(r['q_gain_deg'] for r in positive)) if positive else None)
    return comparisons,decision


def main():
    p=argparse.ArgumentParser(); p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--execution-root',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--key-b0',type=Path,default=REPO/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
    args=p.parse_args(); args.out.mkdir(parents=True,exist_ok=True); (args.out/'traces').mkdir(exist_ok=True)
    rows,checks,features,params,errors=[],[],[],[],[]
    inputs={str(HERE/'PROTOCOL_LOCK.json'):sha(HERE/'PROTOCOL_LOCK.json'),str(Path(__file__)):sha(Path(__file__))}
    try:
        load_engine(args.source_root)
        for rel in ('research/CHAIN_HYPOTHESIS_20261019','research/R5_N4B_20261015',
                    'research/PHYSICS_RS_STAGED_20261015/code','research/FFD_P0P3_20261016'):
            sys.path.insert(0,str(args.source_root/rel))
        sys.path.insert(0,str(HERE.parent))
        path=args.source_root/'research/CHAIN_HYPOTHESIS_20261019/run.py'
        sp=importlib.util.spec_from_file_location('t9_exact_chain_run',path)
        original=importlib.util.module_from_spec(sp);sp.loader.exec_module(original)
        if original.ROOT.resolve()!=args.source_root.resolve() or original.DATA.resolve()!=args.execution_root.resolve():
            raise ValueError('RESTORE_LAYOUT_MUST_BE_EXECUTION_ROOT_SOURCE')
        import p0_initial
        p0_initial.DATA=args.execution_root;p0_initial.OUT=args.out/'bank_audit';p0_initial.OUT.mkdir(exist_ok=True)
        from source_model import SourceFFD
        from scalar_power import ScalarPower
        import canonical_engine as engine
        model=SourceFFD(); raw=original.frozen_inputs()
        labels_path=args.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz'
        cached_path=args.execution_root/'reference_ae/OOF_PARAMETERS.csv.gz'
        cases_path=args.source_root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
        cases=json.loads(cases_path.read_text())['cases']; by_id={c['id']:c for c in cases}
        df=pd.read_csv(labels_path); cached=pd.read_csv(cached_path); key=pd.read_csv(args.key_b0)
        full=df[df.channel=='full'].copy().reset_index(drop=True)
        native=df[df.channel=='los'].set_index(['case','pose_id'],verify_integrity=True)
        for path in (labels_path,cached_path,cases_path,args.key_b0,args.execution_root/'rf_frozen.zip',
                     Path(original.__file__),Path(sys.modules['source_model'].__file__),
                     Path(sys.modules['scalar_power'].__file__),Path(engine.__file__),Path(sys.modules['n4b_rf_errors'].__file__),
                     Path(sys.modules['features'].__file__),Path(sys.modules['core'].__file__),
                     HERE.parent/'T1_MEMORY/replay.py',HERE.parent/'T4_F1_EVENT/run_events.py'):
            inputs[str(path)]=sha(path)
        for held,tr,te in original.feature_splits(np,full):
            train=full.loc[tr].copy(); weights=original.site_weights(np,pd,train)
            matching=pd.MultiIndex.from_frame(train[['case','pose_id']])
            los_train=native.loc[matching].reset_index()
            _,_,Xlos=frame_geometry(los_train,by_id)
            scaler=StandardScaler().fit(Xlos)
            expected=Ridge(alpha=30.,fit_intercept=True).fit(scaler.transform(Xlos),los_train.log_fp_power.to_numpy(),sample_weight=weights)
            dtrain,_,Xtrain=frame_geometry(train,by_id)
            qtrain=train.log_fp_power.to_numpy(); expected_train=expected.predict(scaler.transform(Xtrain))
            models={name:ScalarPower(train,feature,weights,original.GROUPS) for name,feature in
                    [('Q_POWER1',qtrain),('DELTA_Q_POWER1',qtrain-expected_train),('DISTANCE_ONLY_POWER1',dtrain)]}
            checks.append(dict(held_route=held,scalar_fitter_internal_parity='PASS_MAX_ABS_LE_1e-12',
                               scalar_fits=3,matching_los_train_rows=len(los_train),full_train_rows=len(train)))
            held_native=df[(df.channel=='los')&(df.route==held)].copy()
            _,_,Xtest=frame_geometry(held_native,by_id)
            prediction=expected.predict(scaler.transform(Xtest))
            info=dict(held_route=held,training_keys=[list(x) for x in matching.tolist()],
                      expected_q_scaler_mean=scaler.mean_.tolist(),expected_q_scaler_scale=scaler.scale_.tolist(),
                      expected_q_coef=expected.coef_.tolist(),expected_q_intercept=float(expected.intercept_),
                      los_q_train_rmse=float(np.sqrt(np.mean((expected.predict(scaler.transform(Xlos))-los_train.log_fp_power.to_numpy())**2))),
                      los_q_heldout_rmse=float(np.sqrt(np.mean((prediction-held_native.log_fp_power.to_numpy())**2))),
                      power_models={name:serialize_scalar(fit) for name,fit in models.items()})
            params.append(info)
            for case in [c for c in cases if c['id'].split('_')[0]==held]:
                cid=case['id']
                channels=['full']+(['los'] if cid in ('R2_aA_m0','R2_aA_m45') else [])
                for channel in channels:
                    packet=raw[cid,channel]; t=packet['t_s'];truth=packet['truth_for_offline_scoring_only'][:,:3]
                    ids=packet['pose_id']; z=np.c_[packet['z_r_m'],packet['z_s']]
                    frame=df[(df.case==cid)&(df.channel==channel)].set_index('pose_id').loc[ids]
                    cache=cached[(cached.case==cid)&(cached.channel==channel)].set_index('pose_id').loc[ids]
                    q=frame.log_fp_power.to_numpy(); mu,C=models['Q_POWER1'].predict(q)
                    target_mu=cache[['mu_r','mu_s']].to_numpy(); target_C=np.zeros_like(C)
                    target_C[:,0,0]=cache.C00;target_C[:,1,1]=cache.C11;target_C[:,0,1]=target_C[:,1,0]=cache.C01
                    parity=max(float(abs(mu-target_mu).max()),float(abs(C-target_C).max()))
                    checks.append(dict(case=cid,channel=channel,q_fit_cached_max_abs=parity))
                    if parity>1e-10:raise RuntimeError('Q_FIT_CACHE_PARITY:'+str(parity))
                    if np.max(abs(z-frame[['range_m','s_fp']].to_numpy()))>1e-10:raise RuntimeError('SOURCE_OBSERVATION_PARITY')
                    for label in ('B0','L2'):
                        bias=original.BIAS_LEVELS[label];controls,initial=original.build_positive_bias_controls(t,truth,label,0)
                        for arm in ['Q_POWER1']+[a for a in ARMS if a!='Q_POWER1']:
                            try:
                                def provider(i,prior,spec):
                                    distance,theta,X=geometry(prior,case); eq=float(expected.predict(scaler.transform(X))[0])
                                    value=q[i] if arm=='Q_POWER1' else q[i]-eq if arm=='DELTA_Q_POWER1' else distance[0]
                                    mean,cov=(np.zeros(2),R0.copy()) if arm=='JOINT4_R0' else tuple(a[0] for a in models[arm].predict([value]))
                                    features.append(dict(case=cid,channel=channel,bias=label,arm=arm,frame=i,t_s=float(t[i]),
                                           prior_x_m=float(prior[0]),prior_y_m=float(prior[1]),prior_yaw_rad=float(prior[2]),
                                           q=float(q[i]),expected_q_los=eq,delta_q=float(q[i]-eq),distance_m=float(distance[0]),theta_rad=float(theta[0]),
                                           conditioning_scalar=None if arm=='JOINT4_R0' else float(value),mu_r=float(mean[0]),mu_s=float(mean[1]),C00=float(cov[0,0]),C01=float(cov[0,1]),C11=float(cov[1,1])))
                                    return mean,cov
                                result=engine.run(t,controls,initial,z,mu,C,np.zeros(len(t)),case,model,
                                      [dict(name=arm,base='r0' if arm=='JOINT4_R0' else 'power')],parameter_provider=provider)
                                values,delta=independent(result,truth,bias,t>=30)
                                if arm=='Q_POWER1' and channel=='full':
                                    reference=args.execution_root/'reference_ae/traces'/f'{cid}_{label}.npz';inputs[str(reference)]=sha(reference)
                                    checks.append(historical_check(result,truth,bias,cid,label,t,reference,key))
                                rows.append(dict(case=cid,channel=channel,bias=label,arm=arm,n=int((t>=30).sum()),
                                                 scorer_max_abs_difference=delta,**values))
                                np.savez_compressed(args.out/'traces'/f'{cid}_{channel}_{label}_{arm}.npz',**result,
                                                    truth_for_offline_scoring_only=truth,pose_id=ids,observations=z)
                            except Exception as exc:
                                errors.append(dict(case=cid,channel=channel,bias=label,arm=arm,error=str(exc),traceback=traceback.format_exc(),retry=False))
                                # Reference mismatch invalidates the condition; do not proceed as verified.
                                if arm=='Q_POWER1':break
    except Exception as exc:
        errors.append(dict(error=str(exc),traceback=traceback.format_exc(),retry=False))
    comparison,decision=verdict(rows)
    for name,records in [('RESULTS',rows),('GAIN_COMPARISON',comparison),('CHECKS',checks)]:
        pd.DataFrame(records).to_csv(args.out/(name+'.csv'),index=False)
    if features:
        for (cid,channel,label),frame in pd.DataFrame(features).groupby(['case','channel','bias'],sort=True):
            frame.to_csv(args.out/f'ONLINE_FEATURES_{cid}_{channel}_{label}.csv',index=False)
    (args.out/'TRAIN_PARAMS.json').write_text(json.dumps(params,indent=2),encoding='utf-8')
    (args.out/'DECISION.json').write_text(json.dumps(decision,indent=2,allow_nan=False),encoding='utf-8')
    (args.out/'ERRORS.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    technical='TECHNICAL_PASS' if not errors and decision['complete'] else 'ERROR_OR_INCOMPLETE'
    for path in args.out.glob('*.csv'):
        if path.stat().st_size>20_000_000:
            errors.append(dict(error='CSV_EXCEEDS_20MB:'+path.name,retry=False));technical='ERROR_OR_INCOMPLETE'
    (args.out/'ERRORS.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    manifest=dict(task='T9_Q_DISTANCE',technical=technical,decision=decision,inputs=inputs,
                  actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,
                  outputs={p.name:sha(p) for p in args.out.iterdir() if p.is_file() and p.name!='MANIFEST.json'},
                  note='NPZ Actions-only; publisher adds archive SHA256/artifact id. ONLINE_FEATURES partitioned per case/channel/bias, CSV size checked <=20MB')
    (args.out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    report='# T9 q와 거리 교란 분리\n\nTECHNICAL: '+technical+'; 거리 가설: '+decision['distance_scientific']+'; Δq: '+decision['delta_q_scientific']+'.\n\n'
    report+='모든 양의 POWER 이득 조건에서 거리 arm 회수율 ≥80%를 요구했다. 비양수·미소 이득은 분모로 사용하지 않는다. Δq 기본 feature 채택은 후보 판정이며 자동 변경하지 않는다. 학습은 원래 route-heldout/site-disjoint이며 추론 특징은 prior와 실제 RF q뿐이다. 기대 LoS q의 근사 오차는 TRAIN_PARAMS.json에 보존한다.\n\n'
    report+='## 주장하지 않는 것\n\n거리만이 유일 원인이라는 주장, 독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다.\n'
    (args.out/'RESULTS_KO.md').write_text(report,encoding='utf-8')
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
