"""Stage2 only: fixed Rs, same DR prior, whole-circle inverse and MAP."""
import argparse,csv,json,sys,time,traceback,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import h3_offline as h
import run_full as r

def exact_roots(lut,x,z,case):
    a=h.angles(x,case);bearing=a[2]/h.RAD+x[2]
    knots=np.sort(h.wrap(bearing-lut.phi/h.RAD))
    points=np.tile(x,(len(knots),1));points[:,2]=knots
    values=h.model(lut,points,case)-z;roots=[]
    for i in np.flatnonzero((values==0)|(values*np.roll(values,-1)<0)):
        j=(i+1)%len(knots);width=float(h.wrap(knots[j]-knots[i]))
        fraction=values[i]/(values[i]-values[j]) if values[i]!=values[j] else 0.
        roots.append(float(h.wrap(knots[i]+fraction*width)))
    if not roots:return [],0.
    unique=[]
    for value in roots:
        if not any(abs(h.wrap(value-other))<1e-10 for other in unique):unique.append(value)
    check=np.tile(x,(len(unique),1));check[:,2]=unique
    error=float(np.max(np.abs(h.model(lut,check,case)-z)))
    if error>1e-10:raise RuntimeError('Exact interpolant inverse residual '+str(error))
    return unique,error

def initialize(p0,out):
    global LUT,OUT
    LUT=h.c.original_lut(p0);OUT=Path(out)

def cell(task):
    case,condition,level,seed,channel,t,truth,pose,cov,zs,pids=task
    name=f"{case['id']}_{condition}_L{level}_S{seed}_{channel}"
    path=OUT/'cells'/(name+'.csv');stream=r.Stream(path);n=0;previous=None
    summary=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed,channel=channel,n=0,status='RUNNING')
    try:
        for k in np.flatnonzero(t>=h.C['evaluation_start_s']):
            if n%25==0:
                stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                if (OUT/'STOP').exists() or (stop and Path(stop).exists()):raise RuntimeError('Stage2 stopped')
            x,P=pose[k],cov[k];z=float(zs[k]);target=float(truth[k,2])
            inverse=h.legacy(LUT,x,P,z,case)
            parity=h.baseline_parity(LUT,x,P,z,case)
            roots,residual=exact_roots(LUT,x,z,case)
            nearest=min(roots,key=lambda root:abs(h.wrap(root-x[2]))) if roots else None
            # Oracle is used only after online inference, solely for labelled scoring.
            posterior=h.posterior(h.fixed_logfun(LUT,x,P,z,case))
            oracle=min(roots,key=lambda root:abs(h.wrap(root-target))) if roots else None
            def error(value):return None if value is None else float(h.wrap(value-target)*h.RAD)
            def rotation(value):return None if value is None else float(h.wrap(value-x[2])*h.RAD)
            exact_error=error(nearest);map_error=error(posterior['MAP']);filtered_error=error(inverse['selected'])
            row=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed,channel=channel,range_models_unchanged='B_OLD' if channel=='los' else 'B_OLD|E1_FULL_LORO',range_used=False,sample=int(k),pose_id=int(pids[k]),t_s=float(t[k]),s_observed=z,prior_heading_rad=float(x[2]),prior_heading_variance=float(P[2,2]),prior_heading_error_deg=error(x[2]),exact_root_count=len(roots),exact_inverse_rad=nearest,exact_inverse_error_deg=exact_error,exact_inverse_rotation_deg=rotation(nearest),exact_inverse_opposite_branch=None if nearest is None else int(abs(exact_error)>90),exact_inverse_residual=residual,legacy_root_count=inverse['root_count'],legacy_nearest_root_rad=inverse['nearest'],legacy_nearest_root_error_deg=error(inverse['nearest']),legacy_corrected_rad=inverse['selected'],legacy_corrected_error_deg=filtered_error,legacy_rotation_deg=rotation(inverse['selected']),legacy_opposite_branch=int(abs(filtered_error)>90),legacy_status=inverse['status'],legacy_NIS=inverse.get('NIS'),legacy_parity_abs=parity,MAP_rad=posterior['MAP'],MAP_error_deg=map_error,MAP_rotation_deg=rotation(posterior['MAP']),MAP_opposite_branch=int(abs(map_error)>90),MAP_measurement_residual=float(z-h.model(LUT,np.r_[x[:2],posterior['MAP']],case)),MAP_vs_exact_inverse_deg=None if nearest is None else float(h.wrap(posterior['MAP']-nearest)*h.RAD),MAP_vs_exact_opposite_branch=None if nearest is None else int(abs(h.wrap(posterior['MAP']-nearest))>np.pi/2),oracle_exact_root_rad=oracle,oracle_exact_root_error_deg=error(oracle),oracle_label='ORACLE_DIAGNOSTIC_ONLY',exact_no_root=not roots,roots_disappeared=bool(previous is not None and previous>0 and not roots),angle_grid_n=posterior['angle_grid_n'],angle_TV=posterior['TV'],MAP_grid_change_deg=posterior['MAP_change_deg'],internal_HPD_width_change_deg=posterior['HPD_width_change_deg'])
            stream.append(row);n+=1;previous=len(roots)
        summary.update(n=n,status='PASS',output=path.name)
    except Exception as exc:
        summary.update(n=n,status='FAIL_CLOSED',failure_reason=str(exc),failure_sample=int(k),output=path.name)
    finally:stream.close()
    return summary

def main(args):
    out=h.ROOT/args.out;out.mkdir(exist_ok=False);(out/'cells').mkdir();start=time.time();pool=None;completed=[];receipt=dict(stage=2,stages_3_5='NOT_RUN',scientific_PASS=False)
    contract=dict(scope='STAGE2_ONLY_STOP_AFTER_RESULT_REVIEW',parent_contract_sha256=h.c.file_sha(h.ROOT/'CONTRACT.json'),prior='SAME_FROZEN_D0_FOR_ALL_METHODS',position='FIXED_DR_XY',measurement_model='FROZEN_LOS_LUT',Rs=h.c.RS,RF_mean=0.,training='NONE',methods=['EXACT_INTERPOLANT_NEAREST_PRIOR_ROOT','LEGACY_0.5_DEG_NEAREST_ROOT','LEGACY_INVERSE_CORRECTED_WITH_ORIGINAL_GATE','WHOLE_CIRCLE_LIKELIHOOD_MAP','ORACLE_EXACT_ROOT_DIAGNOSTIC_ONLY'],exact_inverse='enumerate every periodic phi_RX LUT segment at fixed XY; linear crossing within segment',exact_root_residual_tolerance=1e-10,opposite_branch_error_deg=90,MAP='whole circle grid convergence and local refinement with original wrapped normal prior',angle_grids=h.C['angle_grids'],angle_TV_tolerance=h.C['posterior_TV_tolerance'],MAP_angle_convergence_deg=h.C['MAP_angle_convergence_deg'],internal_HPD_width_convergence_deg=h.C['HPD_width_convergence_deg'],legacy_gate='ORIGINAL_FILTERCONFIG_UNCHANGED',Range='NOT_AN_INPUT_NO_DUPLICATE_FULL_ROWS_FOR_B_OLD_E1',no_root='MISSING_EXACT_ROOT; LEGACY_FALLBACK_PRIOR; MAP_STILL_DEFINED',root_disappearance='previous sampled frame had >=1 exact root and current has zero',workers=args.workers,stages_3_5='NOT_RUN',scientific_PASS=False)
    h.c.atomic_json(out/'STAGE_CONTRACT.json',contract)
    try:
        p0=h.c.check_inputs();caches,im=r.load_caches(p0)
        if json.loads((h.ROOT/'STAGE1_01/VALIDATION_RECEIPT.json').read_text())['status']!='PASS':raise RuntimeError('Stage1 gate not passed')
        inputs=dict(command=sys.argv,started_utc=datetime.now(timezone.utc).isoformat(),contract=contract,source_sha256={p.name:h.c.file_sha(p) for p in (Path(__file__),h.ROOT/'h3_offline.py',h.ROOT/'run_full.py')},cache_sha256=im['sha256'],frozen_blobs=h.c.check_frozen_baseline_files(),repository_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=h.REPO,text=True).strip())
        h.c.atomic_json(out/'INPUT_MANIFEST.json',inputs)
        priors,parity=r.prepare_priors(p0,caches,out)
        tasks=[]
        for case in p0['cases']:
            for condition,level in h.C['conditions']:
                for seed in h.C['seeds']:
                    t,tr,x,P=priors[(case['id'],condition,level,seed)]
                    for channel in ('los','full'):
                        data=caches[(case['id'],channel)];tasks.append((case,condition,level,seed,channel,t,tr,x,P,data['s'],data['pose_ids']))
        pool=ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(p0,str(out)))
        futures=[pool.submit(cell,task) for task in tasks]
        for future in as_completed(futures):
            result=future.result();completed.append(result);r.save_csv(out/'CELL_STATUS.csv',completed)
            print(json.dumps(dict(result,completed_cells=len(completed),elapsed_s=time.time()-start)),flush=True)
            if result['status']!='PASS':raise RuntimeError(json.dumps(result))
        pool.shutdown();pool=None
        output=out/'H3_INVERSE_VS_MAP.csv'
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
        receipt.update(status='PASS',exit_code=0,completed_cells=len(completed),rows=sum(row['n'] for row in completed),prior_reference_cells=len(parity)*len(h.C['RF_pairs']),max_prior_parity=max(row['parity_max_abs'] for row in parity),output_sha256=h.c.file_sha(output),repository_clean=True,elapsed_s=time.time()-start)
    except Exception as exc:
        (out/'STOP').write_text('FAIL_CLOSED',encoding='utf-8')
        if pool:pool.shutdown(wait=True,cancel_futures=True)
        receipt.update(status='FAIL_CLOSED',exit_code=1,failure_reason=str(exc),completed_cells=len(completed),elapsed_s=time.time()-start);traceback.print_exc()
    h.c.atomic_json(out/'VALIDATION_RECEIPT.json',receipt)
    return receipt['exit_code']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='STAGE2_01');parser.add_argument('--workers',type=int,default=4);sys.exit(main(parser.parse_args()))
