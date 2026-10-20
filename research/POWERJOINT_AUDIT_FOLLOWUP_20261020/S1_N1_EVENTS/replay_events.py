"""S1 adapter around unchanged T4 run_events helpers and canonical engine @034e57a.

The old T4 CLI is intentionally not invoked: its POST30 mode only reaggregates
old results and its metrics assumes B0. This adapter uses its actual run,
normalization, membership, baseline QA and packet routines, with an independent
11-metric POST30 scorer and the separately locked D7 input substitution.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,sys,traceback
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2]
AUDIT=SOURCE/'research/POWERJOINT_AUDIT_RERUN_20261020'
sys.path.insert(0,str(AUDIT/'T4_F1_EVENT'));import run_events as original
sys.path.insert(0,str(AUDIT/'T1_MEMORY'));from replay import score as reference_score
from independent_score import score_window
PINNED_ENGINE='e725f92bd74e6a845b07418d6f3b7a2974a518b2cd03b16969518bf879ee11b8'
PINNED_RUNNER='356854dad08f230c97e9fa4cb18c59e06d27f1f87835661054574b6578bc6ccb'

def sha(path):return original.sha(path)
def dump(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def metric(result,data,mask,bias_dps):
    x=result['state'][mask,0];P=result['cov'][mask,0];truth=data['truth'][mask]
    # Restrict arrays to the complete window first: bias_final is its last frame.
    main=reference_score(x,P,truth,bias_dps,np.ones(len(x),bool))
    independent=score_window(x,P,truth,bias_dps)
    difference=max(abs(main[k]-independent[k]) for k in main)
    if not np.isfinite(list(main.values())).all() or difference>1e-9:
        raise RuntimeError('INDEPENDENT_11_METRICS:'+str(difference))
    return dict(status='TECHNICAL_PASS',n=int(mask.sum()),scorer_max_abs_difference=difference,**main)

def d7_data(data,a,b):
    ri=np.flatnonzero(data['radio_mask']);membership=(ri>=a)&(ri<b)
    if 'actual_los_exists_at_radio' not in data:return None,'NOT_EVALUABLE_LOS_STATUS_UNCERTIFIED',{}
    flags=data['actual_los_exists_at_radio'].astype(bool)
    if not flags[membership].all():return None,'NOT_EVALUABLE_LOS_BLOCKED',{'blocked_event_RF_rows':int((~flags[membership]).sum())}
    lo=data['actual_los_z_at_radio'][membership,1]
    if not np.isfinite(lo).all():return None,'NOT_EVALUABLE_LOS_OBSERVER_INVALID',{}
    changed=dict(data);changed['z']=data['z'].copy();changed['mu']=data['mu'].copy()
    indices=ri[membership];changed['z'][indices,1]=lo;changed['mu'][indices,1]=0.
    keep=np.ones(len(data['t']),bool);keep[indices]=False
    assert np.array_equal(changed['z'][keep],data['z'][keep])
    assert np.array_equal(changed['mu'][keep],data['mu'][keep])
    assert np.array_equal(changed['z'][:,0],data['z'][:,0])
    assert np.array_equal(changed['mu'][:,0],data['mu'][:,0])
    assert changed['C'] is data['C'] and changed['risk'] is data['risk']
    return changed,'EVALUABLE',dict(replaced_RF_rows=len(indices),range_unchanged=True,mu_r_unchanged=True,
                                  raw_Full_C_unchanged=True,original_joint_gate=9.210340371976184)

def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--route',required=True)
    p.add_argument('--execution-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True);(args.out/'traces').mkdir(exist_ok=True)
    lock_path=HERE/'PROTOCOL_LOCK.json';lock=json.loads(lock_path.read_text());list_path=HERE/'EVENT_LIST.csv'
    assert sha(list_path)==lock['event_list_sha256'],'EVENT_LIST_LOCK_HASH'
    assert os.getenv('GITHUB_SHA'),'COMMITTED_ACTIONS_EXECUTION_REQUIRED'
    events=pd.read_csv(list_path).to_dict('records')
    assert len(events)==lock['event_count']
    engine_path=AUDIT/'canonical_engine.py'
    assert sha(engine_path)==PINNED_ENGINE and sha(Path(original.__file__))==PINNED_RUNNER,'PINNED_BYTE_IDENTITY'
    for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                'research/EKF4_RANGE_S_STAGED_20261014','research/FFD_P0P3_20261016'):
        sys.path.insert(0,str(SOURCE/rel))
    sys.path.insert(0,str(AUDIT/'T1_MEMORY/vendor'))
    import p0_initial
    p0_initial.DATA=args.execution_root;p0_initial.OUT=args.out/'bank_audit';p0_initial.OUT.mkdir(exist_ok=True)
    from source_model import SourceFFD
    model=SourceFFD()
    module=importlib.util.spec_from_file_location('s1_pinned_engine',engine_path)
    engine=importlib.util.module_from_spec(module);module.loader.exec_module(engine)
    key_path=SOURCE/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv';key=pd.read_csv(key_path)
    rows=[];checks=[];errors=[];unavailable=[];receipts=[];first=[];divergence=[];growth=[]
    inputs={str(lock_path):sha(lock_path),str(list_path):sha(list_path),str(engine_path):sha(engine_path),
            str(Path(original.__file__)):sha(Path(original.__file__)),str(args.bundle):sha(args.bundle),str(key_path):sha(key_path)}
    config=json.loads(args.bundle.read_text())
    for item in config['cases']:
        cid=item['case']['id'];bias=item.get('bias','B0')
        if cid.split('_')[0]!=args.route or bias not in ('B0','L2'):continue
        selected=[e for e in events if e['case']==cid]
        if not selected:continue
        path=args.bundle.parent/item['npz'];historical=(args.bundle.parent/item['historical_power1_trace']).resolve()
        try:
            inputs[str(path)]=sha(path);inputs[str(historical)]=sha(historical)
            data=original.normalize(original.load_npz(path));case=item['case'];bias_dps=float(item['bias_dps'])
            baseline=original.run(engine,model,data,case,dict(name='POWER1',base='power'))
            check=original.check_reference(baseline,data,historical,cid,key,check_key=(bias=='B0'))
            check.update(bias=bias,**metric(baseline,data,data['t']>=30,bias_dps))
            # Identical joint structure with a no-change adapter, before any D7.
            identity_data=dict(data,z=data['z'].copy(),mu=data['mu'].copy())
            identity=original.run(engine,model,identity_data,case,dict(name='D7_NO_CHANGE_CONTROL',base='power'))
            check['adapter_identity_state_max']=float(np.max(abs(identity['state']-baseline['state'])))
            check['adapter_identity_cov_max']=float(np.max(abs(identity['cov']-baseline['cov'])))
            check['adapter_identity_gate_mismatches']=int(np.count_nonzero(identity['accepted']!=baseline['accepted']))
            if max(check['adapter_identity_state_max'],check['adapter_identity_cov_max'])>1e-10 or check['adapter_identity_gate_mismatches']:
                raise RuntimeError('BASIC_JOINT_ADAPTER_PARITY')
            checks.append(check);np.savez_compressed(args.out/'traces'/f'{cid}_{bias}_POWER1.npz',**baseline)
        except Exception as exc:
            errors.append(dict(case=cid,bias=bias,arm='POWER1',error=str(exc),traceback=traceback.format_exc(),retry=False));continue
        for event in selected:
            eid=event['event'];packets=[]
            try:
                a,b,lo,hi=original.event_indices(data,event);t=data['t'];end=t[b-1]
                if lo!=event['rf_i0'] or hi!=event['rf_i1_exclusive'] or hi-lo!=event['n']:
                    raise RuntimeError('EVENT_LOCK_ROW_MEMBERSHIP')
                if a!=event['motion_i0'] or b!=event['motion_i1_exclusive'] or t[a]!=event['t_start_s'] or end!=event['t_end_s']:
                    raise RuntimeError('EVENT_LOCK_CLOCK_MEMBERSHIP')
                if end+30>t[-1]+1e-9:raise ValueError('EXCLUDED_SHORT_HORIZON_MUST_NOT_BE_IN_LOCK')
                receipts.append(dict(event=eid,case=cid,bias=bias,rf_i0=lo,rf_i1_exclusive=hi,n_RF=hi-lo,
                                     t_start_s=float(t[a]),t_end_s=float(end),POST30_end_s=float(end+30)))
                f=original.first_harmful(baseline,data,event,a,b);f['bias']=bias;first.append(f)
                mask=(t>=end)&(t<=end+30)
                for arm in lock['arms']:
                    common=dict(event=eid,case=cid,bias=bias,arm=arm,scope='POST30',label='ORACLE_DIAGNOSTIC')
                    try:
                        if arm=='POWER1':result=baseline
                        elif arm=='D7':
                            altered,status,detail=d7_data(data,a,b)
                            if altered is None:
                                rows.append(dict(**common,status=status,**detail));unavailable.append(dict(**common,status=status,**detail));continue
                            result=original.run(engine,model,altered,case,dict(name='D7',base='power'))
                            if not np.array_equal(result['Rwhite'][:,0],data['C']):raise RuntimeError('D7_RAW_FULL_C_CHANGED')
                            if not np.array_equal(result['mean'][:,0],altered['mu']):raise RuntimeError('D7_MU_INPUT_CHANGED')
                            receipts.append(dict(event=eid,bias=bias,arm='D7',status=status,**detail))
                        else:
                            details={'SKIP':dict(skip_event=True),'D1':dict(channel=1),'D2':dict(channel=0)}[arm]
                            result=original.run(engine,model,data,case,dict(name=arm,base='power',diagnostic_event=[a,b],**details))
                        rows.append(dict(**common,**metric(result,data,mask,bias_dps)))
                        pr=original.packet_rows(result,data,event,arm,a,b)
                        used=altered if arm=='D7' else data
                        for r in pr:
                            r['bias']=bias;r['prior_error_bg_dps']-=bias_dps
                            i=r['frame'];r.update(observed_r_m=float(used['z'][i,0]),observed_s=float(used['z'][i,1]),
                                used_mu_r=float(used['mu'][i,0]),used_mu_s=float(used['mu'][i,1]),
                                raw_Full_C00=float(data['C'][i,0,0]),raw_Full_C01=float(data['C'][i,0,1]),
                                raw_Full_C11=float(data['C'][i,1,1]))
                        packets.extend(pr)
                        if arm!='POWER1':np.savez_compressed(args.out/'traces'/f'{eid}_{bias}_{arm}.npz',**result)
                        if arm=='SKIP':
                            dr,gr=original.divergence(baseline,result,data,event,a,b)
                            for r in dr:r['bias']=bias
                            gr['bias']=bias;divergence.extend(dr);growth.append(gr)
                    except Exception as exc:
                        rows.append(dict(**common,status='ERROR',error=str(exc)))
                        errors.append(dict(**common,error=str(exc),traceback=traceback.format_exc(),retry=False))
                pd.DataFrame(packets).to_csv(args.out/f'PACKET_LOG_{eid}_{bias}.csv',index=False)
            except Exception as exc:
                errors.append(dict(event=eid,case=cid,bias=bias,error=str(exc),traceback=traceback.format_exc(),retry=False))
    for name,records in [('INTERVENTIONS',rows),('BASELINE_CHECKS',checks),('EVENT_RECEIPT',receipts),
                         ('FIRST_HARMFUL_UPDATE',first),('DIVERGENCE',divergence),('GROWTH',growth)]:
        pd.DataFrame(records).to_csv(args.out/(name+'.csv'),index=False)
    dump(args.out/'ERRORS.json',{'execution_errors':errors,'D7_not_evaluable':unavailable})
    dump(args.out/'MANIFEST.json',dict(task='S1_N1_EVENTS',route=args.route,technical='TECHNICAL_PASS_CORE' if not errors else 'ERROR',
        scientific='AGGREGATE_REQUIRED',source_commit=os.getenv('GITHUB_SHA'),actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,
        protocol_sha256=sha(lock_path),inputs=inputs,D7_not_evaluable_count=len(unavailable),
        output_sha256={str(p.relative_to(args.out)):sha(p) for p in args.out.rglob('*') if p.is_file() and p.name!='MANIFEST.json'}))
    print('S1_ROUTE_FINISHED',args.route,'errors',len(errors),'D7_unavailable',len(unavailable),flush=True)
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
