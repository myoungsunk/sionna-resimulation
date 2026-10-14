"""Same stage2 posterior: local Gaussian versus circular multimodal HPD."""
import argparse,csv,json,sys,time,traceback,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import h3_offline as h
import run_full as r

STAGE2=h.ROOT/'STAGE2_01'

def initialize(p0,out):
    global LUT,OUT
    LUT=h.c.original_lut(p0);OUT=Path(out)

def cell(task):
    case,condition,level,seed,channel,t,truth,pose,cov,zs=task
    name=f"{case['id']}_{condition}_L{level}_S{seed}_{channel}"
    with (STAGE2/'cells'/(name+'.csv')).open(encoding='utf-8',newline='') as f:
        previous={int(row['sample']):row for row in csv.DictReader(f)}
    stream=r.Stream(OUT/'cells'/(name+'.csv'));n=0;maxdelta=0.;maxmass=0.
    summary=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed,channel=channel,n=0,status='RUNNING')
    try:
        for k in np.flatnonzero(t>=h.C['evaluation_start_s']):
            if n%25==0:
                stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                if (OUT/'STOP').exists() or (stop and Path(stop).exists()):raise RuntimeError('Stage3 stopped')
            x,P=pose[k],cov[k];ref=previous[int(k)]
            if float(ref['s_observed'])!=float(zs[k]) or float(ref['prior_heading_rad'])!=float(x[2]) or float(ref['prior_heading_variance'])!=float(P[2,2]):raise RuntimeError('Stage2 pair drift')
            post=h.posterior(h.fixed_logfun(LUT,x,P,float(zs[k]),case))
            difference=abs(float(h.wrap(post['MAP']-float(ref['MAP_rad']))));maxdelta=max(maxdelta,difference)
            if difference>h.C['parity_absolute_tolerance']:raise RuntimeError('Stage2 MAP parity failed '+str(difference))
            mass_error=abs(sum(mode['mass'] for mode in post['modes'])-1.);maxmass=max(maxmass,mass_error)
            if mass_error>h.C['parity_absolute_tolerance'] or abs(post['prob'].sum()-1)>1e-12:raise RuntimeError('Posterior mode partition mass gate failed')
            significant=[mode for mode in post['modes'] if mode['mass']>=h.C['mode_min_mass']]
            separations=[float(abs(h.wrap(a['angle_rad']-b['angle_rad']))*h.RAD) for i,a in enumerate(significant) for b in significant[i+1:]]
            score=h.scored(post,truth[k,2]);sigma=post['local_sigma']
            gaussian_width=None if sigma is None else min(360.,2*1.95996398454*sigma*h.RAD)
            row=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed,channel=channel,range_models_unchanged='B_OLD' if channel=='los' else 'B_OLD|E1_FULL_LORO',range_used=False,sample=int(k),t_s=float(t[k]),same_MAP_difference_rad=difference,mode_mass_sum_error=mass_error,hpd95_mass=float(post['prob'][post['hpd']].sum()),hpd_region_count=len(post['hpd_intervals']),significant_mode_pair_min_separation_deg=min(separations) if separations else None,significant_mode_pair_max_separation_deg=max(separations) if separations else None,local95_width_deg=gaussian_width,**score)
            stream.append(row);n+=1
        summary.update(status='PASS',n=n,max_MAP_parity_rad=maxdelta,max_mode_mass_error=maxmass)
    except Exception as exc:summary.update(status='FAIL_CLOSED',n=n,failure_sample=int(k),failure_reason=str(exc))
    finally:stream.close()
    return summary

def main(args):
    out=h.ROOT/args.out;out.mkdir(exist_ok=False);(out/'cells').mkdir();start=time.time();pool=None;completed=[]
    receipt=dict(stage=3,scientific_PASS=False,range_geometry='NOT_RUN_THIS_STAGE',recursive_fusion='NOT_RUN')
    contract=dict(scope='STAGE3_REPRESENTATION_ONLY_SAME_STAGE2_POSTERIOR',parent_contract_sha256=h.c.file_sha(h.ROOT/'CONTRACT.json'),Rs=h.c.RS,RF_mean=0.,prior='SAME_D0_WRAPPED_HEADING_PRIOR',position='FIXED_DR_XY',MAP='EXACT_STAGE2_PARITY_1e-8_REQUIRED',HPD='DISCONNECTED_CIRCULAR_HIGHEST_DENSITY_BINS_95_PERCENT',modes='LOCAL_PEAKS_WITH_ADJACENT_VALLEY_BASIN_MASS',meaningful_mode_min_mass=h.C['mode_min_mass'],local_Gaussian='MAP_CURVATURE_WITH_FROZEN_HESSIAN_AGREEMENT_TEST',local_Gaussian_invalid='REPORT_INVALID_NO_COVERAGE_IMPUTATION',comparison='REPORT_FULL_HPD_ALL_FRAMES_AND_MATCHED_LOCAL_VALID_SUBSET',online_modes_tracking='NOT_IMPLEMENTED_NOT_CLAIMED',recursive_entry='AFTER_STAGE4_GATE_AS_USER_SPECIFIED',scientific_PASS=False)
    h.c.atomic_json(out/'STAGE_CONTRACT.json',contract)
    try:
        prior_receipt=json.loads((STAGE2/'VALIDATION_RECEIPT.json').read_text())
        if prior_receipt['status']!='PASS' or h.c.file_sha(STAGE2/'H3_INVERSE_VS_MAP.csv')!=prior_receipt['output_sha256']:raise RuntimeError('Stage2 evidence gate failed')
        p0=h.c.check_inputs();caches,im=r.load_caches(p0)
        inputs=dict(command=sys.argv,started_utc=datetime.now(timezone.utc).isoformat(),contract=contract,stage2_sha256=prior_receipt['output_sha256'],stage2_cell_sha256={p.name:h.c.file_sha(p) for p in (STAGE2/'cells').glob('*.csv')},source_sha256={p.name:h.c.file_sha(p) for p in (Path(__file__),h.ROOT/'h3_offline.py',h.ROOT/'run_full.py')},cache_sha256=im['sha256'],frozen_blobs=h.c.check_frozen_baseline_files())
        h.c.atomic_json(out/'INPUT_MANIFEST.json',inputs)
        priors,parity=r.prepare_priors(p0,caches,out);tasks=[]
        for case in p0['cases']:
            for condition,level in h.C['conditions']:
                for seed in h.C['seeds']:
                    t,tr,x,P=priors[(case['id'],condition,level,seed)]
                    for channel in ('los','full'):tasks.append((case,condition,level,seed,channel,t,tr,x,P,caches[(case['id'],channel)]['s']))
        pool=ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(p0,str(out)))
        for future in as_completed([pool.submit(cell,task) for task in tasks]):
            result=future.result();completed.append(result);r.save_csv(out/'CELL_STATUS.csv',completed)
            print(json.dumps(dict(result,completed_cells=len(completed),elapsed_s=time.time()-start)),flush=True)
            if result['status']!='PASS':raise RuntimeError(json.dumps(result))
        pool.shutdown();pool=None;output=out/'H3_MULTIMODAL_POSTERIOR.csv'
        with output.open('w',encoding='utf-8',newline='') as target:
            writer=None
            for path in sorted((out/'cells').glob('*.csv')):
                with path.open(encoding='utf-8',newline='') as f:
                    reader=csv.DictReader(f)
                    if writer is None:writer=csv.DictWriter(target,fieldnames=reader.fieldnames);writer.writeheader()
                    writer.writerows(reader)
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=h.REPO,text=True).strip();revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=h.REPO,text=True).strip()
        if dirty or revision!=h.C['base_commit']:raise RuntimeError('Original checkout changed')
        r.load_caches(p0)
        receipt.update(status='PASS',exit_code=0,completed_cells=len(completed),rows=sum(row['n'] for row in completed),max_MAP_parity_rad=max(row['max_MAP_parity_rad'] for row in completed),max_mode_mass_error=max(row['max_mode_mass_error'] for row in completed),output_sha256=h.c.file_sha(output),repository_clean=True,elapsed_s=time.time()-start)
    except Exception as exc:
        (out/'STOP').write_text('FAIL_CLOSED',encoding='utf-8')
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        receipt.update(status='FAIL_CLOSED',exit_code=1,failure_reason=str(exc),completed_cells=len(completed),elapsed_s=time.time()-start);traceback.print_exc()
    h.c.atomic_json(out/'VALIDATION_RECEIPT.json',receipt);return receipt['exit_code']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='STAGE3_01');parser.add_argument('--workers',type=int,default=4);sys.exit(main(parser.parse_args()))
