"""Orchestrate full-route causal replay; scoring is deliberately outside inference."""
from pathlib import Path
import argparse,json,time,traceback,hashlib,os
import numpy as np
import pandas as pd
from runtime import load,write_json
from temporal_clock import recalibrate
from engine import replay
from policies import ARMS
from scoring import scores,equivalence,episode_rows
from colored_math import unit_tests


def independent_score(result,t,truth,arms):
    out=[];mask=t>=30
    for j,arm in enumerate(arms):
        raw=result['state'][mask,j,2]-truth[mask,2]
        err=np.arctan2(np.sin(raw),np.cos(raw));v=result['cov'][mask,j,2,2]
        sd=np.sqrt(v);normalized=err/sd
        out.append({'arm':arm,'rmse_deg':float(np.rad2deg(np.linalg.norm(err)/np.sqrt(len(err)))),'signed_mean_deg':float(np.rad2deg(err.mean())),'coverage95':float(np.mean(np.abs(normalized)<=1.959963984540054)),'nees':float(np.dot(normalized,normalized)/len(err))})
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',required=True);ap.add_argument('--case',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    work=Path(args.work);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    rt=load(work);case=json.loads((work/'CASES.json').read_text())[args.case]
    cfg,tp=recalibrate(work,rt,args.case[:2]);write_json(out/'TRAIN_TEMPORAL_ACTUAL_CLOCK.json',cfg)
    write_json(out/'LINEAR_UNIT_QA.json',unit_tests())
    print('TEMPORAL_ACTUAL_CLOCK',json.dumps(tp),flush=True)
    with np.load(work/(args.case+'_full.npz'),allow_pickle=False) as a:data={k:a[k].copy() for k in a.files}
    # Whitelist inference fields; truth and h/J at truth never enter replay.
    stream={k:data[k] for k in data if k.startswith('feature_') or k in ['mu','R','mu_rich','R_rich','risk','utility']}
    allrows=[];allqa=[];allepisodes=[];fail=[];times=[]
    for level,bias in [('B0',0.),('L0',.01),('L1',.05),('L2',.20)]:
        started=time.monotonic();controls={k:data[level+'_'+k] for k in ['dt_s','ds_odom','dtheta_gyro']}
        try:
            result,event,qa,iters=replay(data['t'],controls,data['z'],data[level+'_x0'],stream,case,cfg,rt['model'],rt['transition'])
            eq=equivalence(result,ARMS,event)
            ref=independent_score(result,data['t'],data['truth'],ARMS)
            rows=scores(result,data['t'],data['truth'],bias,ARMS,event)
            for r in rows:r.update(case=args.case,bias=level)
            scoreby={r['arm']:r for r in rows if r['scope']=='evaluation'}
            for r in ref:
                a=scoreby[r['arm']]
                if abs(r['rmse_deg']-a['heading_rmse_deg'])>1e-8 or abs(r['coverage95']-a['heading95'])>1e-10:raise ArithmeticError('Independent score mismatch')
            eq.update(case=args.case,bias=level,baseline_update_checks=len(qa),max_original_update_diff=max([max(r['state_diff'],r['cov_diff']) for r in qa],default=0),original_gate_differences=sum(r['gate_diff'] for r in qa))
            allqa.append(eq)
            np.savez_compressed(out/(args.case+'_'+level+'_TRACE.npz'),**result,t=data['t'],pose_id=data['pose_id'],truth_offline=data['truth'],arms=np.array(ARMS),z=data['z'],mu_static=data['mu'],R_static=data['R'],risk=data['risk'],utility=data['utility'])
            eps=episode_rows(result,data['truth'],data['t'],ARMS,data)
            for r in eps:r.update(case=args.case,bias=level)
            allepisodes.extend(eps);allrows.extend(rows)
            write_json(out/(level+'_EVENT.json'),event)
            pd.DataFrame(iters).to_csv(out/(level+'_ITERATION_QA.csv'),index=False)
            for r in rows:
                if r['scope']=='evaluation' and r['arm'] in ['JOINT4','POWER1','MEM_WHITE','MEM_RS','MEM_R','MEM_S','STATIC_RICH','POWER_IEKF','POWER_RECOVERY','P4_HARD_BOTH','P4_UTILITY','LOCAL_MEM_KEEP','LOCAL_MEM_DROP']:
                    print('RESULT_SCORE',json.dumps(r),flush=True)
            print('REPLAY_QA',json.dumps(eq),flush=True)
        except Exception as e:
            item={'case':args.case,'bias':level,'error':repr(e),'traceback':traceback.format_exc()};fail.append(item);print('CASE_FAILURE',json.dumps(item),flush=True)
        times.append({'case':args.case,'bias':level,'seconds':time.monotonic()-started})
        pd.DataFrame(allrows).to_csv(out/'SCORES.csv',index=False);pd.DataFrame(allepisodes).to_csv(out/'EPISODES.csv',index=False)
        write_json(out/'QA.json',allqa);write_json(out/'FAILURES.json',fail)
    receipt={'case':args.case,'n_arms':len(ARMS),'completed_bias_conditions':len(allqa),'requested_bias_conditions':4,'failed_bias_conditions':len(fail),'elapsed':times,'scientific_success':False,'completion':'ALL_REGISTERED_REPLAYS_COMPLETE' if not fail else 'PARTIAL_FAILURES_RETAINED','source_commit':os.getenv('GITHUB_SHA'),'inference_uses_gt':False,'new_RF_generated':False,'models_exploratory':True}
    write_json(out/'RECEIPT.json',receipt)
    pd.DataFrame([{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file()]).to_csv(out/'MANIFEST.csv',index=False)
    print('CASE_COMPLETE',json.dumps(receipt),flush=True)
    if fail:raise SystemExit(2)

if __name__=='__main__':main()
