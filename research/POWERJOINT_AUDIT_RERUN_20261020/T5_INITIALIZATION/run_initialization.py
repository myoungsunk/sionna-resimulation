"""T5 fixed initial-covariance sensitivity on canonical T2 seed0 inputs."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import sys
import traceback
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'T4_F1_EVENT'))
from run_events import sha, load_npz, normalize, event_indices, metrics, check_reference
LOCK = json.loads((HERE/'PROTOCOL_LOCK.json').read_text(encoding='utf-8'))


def interval(data, event):
    if 'axis' in event:
        return event_indices(data, event)[:2]
    indices = np.flatnonzero(data['radio_mask'] & (data['t'] >= event['time_start_s']) &
                             (data['t'] <= event['time_end_s']))
    if len(indices) < 3:
        raise ValueError('BLOCKED_INPUT:TOO_FEW_INITIAL_RF_ROWS')
    return int(indices[0]), int(indices[-1])+1


def covariance(default, setting):
    P = default.copy()
    if 'variance_scale' in setting:
        j = setting['diagonal']; P[j, j] *= setting['variance_scale']
    if 'bg_sigma_dps' in setting:
        P[3, 3] = np.radians(setting['bg_sigma_dps'])**2
    return P


def replay(engine, model, data, case, P, a, b, skip):
    spec = dict(name='SKIP_INITIAL_EVENT' if skip else 'FULL_POWER1', base='power')
    if skip: spec.update(diagnostic_event=[a,b], skip_event=True)
    controls = dict(dt_s=data['controls_dt'], ds_odom=data['controls_ds'], dtheta_gyro=data['controls_dyaw'])
    result = engine.run(data['t'], controls, data['initial_pose'], data['z'], data['mu'], data['C'],
                        data['risk'], case, model, [spec], radio_mask=data['radio_mask'], initial_cov=P)
    for field in ('prior_cov','cov'):
        eig = np.linalg.eigvalsh(result[field][:,0])
        bad = np.argwhere(eig <= 0)
        if len(bad):
            i,k = map(int,bad[0]); raise FloatingPointError(f'NONSPD_NO_REPAIR:{field}:{i}:{eig[i,k]}')
    return result


def effects(rows):
    lookup = {(r['case'],r['setting'],r['scope'],r['arm']):r for r in rows if r['status']=='TECHNICAL_PASS'}
    out=[]
    for event in LOCK['events']:
        cid=event['case']
        for setting in LOCK['settings']:
            for start in LOCK['evaluation_starts_s']:
                for mode in ('MOTION','RADIO'):
                    scope=f'{mode}_T{start}'; name=setting['name']
                    full=lookup.get((cid,name,scope,'FULL_POWER1')); skip=lookup.get((cid,name,scope,'SKIP_INITIAL_EVENT'))
                    base=lookup.get((cid,'BASELINE',scope,'FULL_POWER1')); base_skip=lookup.get((cid,'BASELINE',scope,'SKIP_INITIAL_EVENT'))
                    if full is None or skip is None: continue
                    gain=full['heading_rmse_deg']-skip['heading_rmse_deg']
                    rec=dict(case=cid,event=event['event'],setting=name,scope=scope,skip_gain_deg=gain,
                             full_heading_rmse_deg=full['heading_rmse_deg'],skip_heading_rmse_deg=skip['heading_rmse_deg'],
                             label='ORACLE_DIAGNOSTIC')
                    if base is not None and base_skip is not None:
                        base_gain=base['heading_rmse_deg']-base_skip['heading_rmse_deg']
                        rec['baseline_skip_gain_deg']=base_gain
                        if base_gain != 0:
                            rec['effect_removed_fraction']=1-abs(gain)/abs(base_gain)
                            rec['sign_changed']=bool(gain*base_gain<0)
                    out.append(rec)
    return out


def decide(records):
    primary=[r for r in records if r['case']==LOCK['decision']['primary_case'] and r['scope']=='MOTION_T30']
    qualifying=[r['setting'] for r in primary if r['setting']!='BASELINE' and
                r.get('baseline_skip_gain_deg',0)>0 and r.get('effect_removed_fraction',-1)>=.5]
    return dict(scientific='SUPPORTED_BUT_LIMITED' if qualifying else 'NOT_ESTABLISHED',
                primary_case=LOCK['decision']['primary_case'],main_scope='MOTION_T30',qualifying_settings=qualifying,
                interpretation='initialization sensitivity; no sole-cause or multipath-exclusion claim')


def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--new-traces',type=Path); group.add_argument('--aggregate',type=Path,nargs='+',help='RESULTS.csv files')
    parser.add_argument('--case-config',type=Path); parser.add_argument('--source-root',type=Path)
    parser.add_argument('--execution-root',type=Path); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    rows,checks,errors,receipts=[],[],[],[]
    inputs={str(HERE/'PROTOCOL_LOCK.json'):sha(HERE/'PROTOCOL_LOCK.json'),str(Path(__file__)):sha(Path(__file__)),
            str(HERE.parent/'T4_F1_EVENT/run_events.py'):sha(HERE.parent/'T4_F1_EVENT/run_events.py'),
            str(HERE.parent/'T1_MEMORY/replay.py'):sha(HERE.parent/'T1_MEMORY/replay.py')}
    if args.aggregate:
        for path in args.aggregate:
            inputs[str(path)]=sha(path); rows.extend(pd.read_csv(path).to_dict('records'))
        if pd.DataFrame(rows).duplicated(['case','setting','scope','arm']).any():
            raise ValueError('DUPLICATE_CASE_SETTING_SCOPE_ARM')
    else:
        if any(v is None for v in (args.case_config,args.source_root,args.execution_root)):
            parser.error('--case-config --source-root --execution-root required with --new-traces')
        try:
            for rel in ('results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src',
                        'research/EKF4_RANGE_S_STAGED_20261014','research/FFD_P0P3_20261016'):
                sys.path.insert(0,str(args.source_root/rel))
            sys.path.insert(0,str(HERE.parent/'T1_MEMORY/vendor'))
            import p0_initial
            p0_initial.DATA=args.execution_root; p0_initial.OUT=args.out/'bank_audit'; p0_initial.OUT.mkdir(exist_ok=True)
            from source_model import SourceFFD
            model=SourceFFD(); engine_path=HERE.parent/'canonical_engine.py'
            spec=importlib.util.spec_from_file_location('t5_canonical_engine',engine_path)
            engine=importlib.util.module_from_spec(spec); spec.loader.exec_module(engine)
            for path in (engine_path,Path(sys.modules['source_model'].__file__),args.case_config): inputs[str(path)]=sha(path)
            config=json.loads(args.case_config.read_text(encoding='utf-8'))
            if config.get('range_model','B_OLD')!='B_OLD': raise ValueError('RANGE_MODEL_REQUIRES_NEW_LOCK')
            seen=set()
            for item in config['cases']:
                if item.get('bias','B0')!='B0': continue
                case=item['case']; cid=case['id']
                matched=[e for e in LOCK['events'] if e['case']==cid]
                if not matched: continue
                if cid in seen: raise ValueError('DUPLICATE_CASE:'+cid)
                seen.add(cid); event=matched[0]
                try:
                    path=args.new_traces/item.get('trace',cid+'_B0.npz'); inputs[str(path)]=sha(path)
                    data=normalize(load_npz(path)); a,b=interval(data,event)
                    receipts.append(dict(case=cid,event=event['event'],i0=a,i1=b,start_s=float(data['t'][a]),
                                         end_s=float(data['t'][b-1]),input_trace_sha256=sha(path)))
                    baseline=replay(engine,model,data,case,engine.PINIT.copy(),a,b,False)
                    checks.append(check_reference(baseline,data,path,cid,pd.DataFrame(columns=['case','method'])))
                except Exception as exc:
                    errors.append(dict(case=cid,error=str(exc),traceback=traceback.format_exc(),retry=False)); continue
                for setting in LOCK['settings']:
                    P=covariance(engine.PINIT,setting)
                    for skip in (False,True):
                        arm='SKIP_INITIAL_EVENT' if skip else 'FULL_POWER1'
                        try:
                            result=baseline if setting['name']=='BASELINE' and not skip else replay(engine,model,data,case,P,a,b,skip)
                            for start in LOCK['evaluation_starts_s']:
                                for mode in ('MOTION','RADIO'):
                                    mask=data['t']>=start
                                    if mode=='RADIO': mask=mask & data['radio_mask']
                                    rows.append(dict(case=cid,event=event['event'],setting=setting['name'],arm=arm,
                                                     scope=f'{mode}_T{start}',label='ORACLE_DIAGNOSTIC',
                                                     P0_psi_rad2=float(P[2,2]),P0_bg_rad2_s2=float(P[3,3]),
                                                     **metrics(result,data,mask)))
                            (args.out/'traces').mkdir(exist_ok=True)
                            np.savez_compressed(args.out/'traces'/f'{cid}_{setting["name"]}_{arm}.npz',**result)
                        except Exception as exc:
                            errors.append(dict(case=cid,setting=setting['name'],arm=arm,error=str(exc),
                                               traceback=traceback.format_exc(),retry=False))
        except Exception as exc:
            errors.append(dict(error=str(exc),traceback=traceback.format_exc(),retry=False))
    effect_rows=effects(rows); decision=decide(effect_rows)
    for name,records in [('RESULTS',rows),('SKIP_EFFECTS',effect_rows),('BASELINE_CHECKS',checks),('EVENT_RECEIPT',receipts)]:
        # Aggregate preserves original baseline-check evidence in per-route artifacts.
        if records: pd.DataFrame(records).to_csv(args.out/(name+'.csv'),index=False)
    (args.out/'ERRORS.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    (args.out/'DECISION.json').write_text(json.dumps(decision,indent=2,allow_nan=False),encoding='utf-8')
    expected=3*10*2*6
    complete=len(rows)==expected and all(r['status']=='TECHNICAL_PASS' for r in rows)
    technical='ERROR_OR_BLOCKED_INPUT' if errors else 'TECHNICAL_PASS' if complete else 'PARTIAL_CASE_SET'
    manifest=dict(task='T5_INITIALIZATION',technical=technical,scientific=decision['scientific'],inputs=inputs,
                  actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,
                  outputs={p.name:sha(p) for p in args.out.iterdir() if p.is_file() and p.name!='MANIFEST.json'},
                  note='NPZ traces Actions-only; publisher adds archive SHA256/artifact id. Baseline evidence remains in per-case artifacts.')
    (args.out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    report='# T5 초기화 민감도\n\nTECHNICAL: '+technical+'; 과학 판정: '+decision['scientific']+'.\n\n'
    report+='주 판정은 C03 A 전체 motion t≥30 s이다. 5/10 s 및 RF 시점 결과는 민감도 비교다. 모든 설정의 FULL과 skip에 동일한 초기 P를 적용했다. O01은 고정 t∈[0,5] s 대조다. 개입 비교는 ORACLE_DIAGNOSTIC이다.\n\n'
    report+='≥50% 효과 소실 설정: '+(', '.join(decision['qualifying_settings']) or '없음/미확립')+'.\n\n'
    report+='초기화에 대한 민감성은 다중경로 부재나 유일 원인을 입증하지 않는다. baseline skip 효과가 양수가 아니면 주 가설을 지지하지 않는다.\n\n'
    report+='## 주장하지 않는 것\n\n독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증을 주장하지 않는다. 고정 seed0 센서 입력에서의 진단이다.\n'
    (args.out/'RESULTS_KO.md').write_text(report,encoding='utf-8')
    if errors: raise SystemExit(1)


if __name__=='__main__':
    main()
