"""Independent stage 1: no fitted RF model, posterior search or RF update."""
import argparse,json,sys,time,traceback,subprocess,os
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import h3_offline as h
import run_full as r

NAMES=('theta','phi_TX','phi_RX')

def batch_geometry(lut,x,truth,case):
    angles=h.angles(x,case);_,gradient=lut(angles[:,0],angles[:,1],angles[:,2],with_grad=True)
    u=x[:,0]-case['anchor'][0];v=x[:,1]-case['anchor'][1]
    height=case['anchor'][2]-case['robot_z_m'];rho2=np.maximum(u*u+v*v,1e-12);rho=np.sqrt(rho2)
    da=np.stack([np.column_stack([height*u/rho/(rho2+height*height),height*v/rho/(rho2+height*height)]),np.column_stack([v/rho2,-u/rho2]),np.column_stack([-v/rho2,u/rho2])],axis=1)*h.RAD
    terms=gradient[:,:,None]*da
    _,jac=h.model(lut,x,case,True);jac=np.asarray(jac)
    chain_error=np.max(np.abs(terms.sum(1)-jac[:,:2]),axis=1)
    cells=np.column_stack([angles[:,0]/lut.dt,(angles[:,1]+180)/lut.dp,(angles[:,2]+180)/lut.dp])
    boundary=np.min(np.abs(cells-np.rint(cells)),axis=1)<1e-4
    clipping=(angles[:,0]<=lut.theta[0])|(angles[:,0]>=lut.theta[-1])
    numerical=np.empty_like(jac)
    for j in range(3):
        shift=np.eye(3)[j]*h.C['finite_difference_step']
        numerical[:,j]=(h.model(lut,x+shift,case)-h.model(lut,x-shift,case))/(2*h.C['finite_difference_step'])
    jac_error=np.max(np.abs(numerical-jac),axis=1)
    weak=np.abs(jac[:,2])<h.C['weak_heading_derivative_per_rad']
    delta=x[:,:2]-truth[:,:2];contrib=np.einsum('nij,nj->ni',terms,delta)
    comparable=truth.copy();comparable[:,2]=x[:,2]
    nonlinear=h.model(lut,x,case)-h.model(lut,comparable,case)
    implied=np.full_like(contrib,np.nan);implied[~weak]=-contrib[~weak]/jac[~weak,2,None]*h.RAD
    cross=np.column_stack([2*contrib[:,0]*contrib[:,1],2*contrib[:,0]*contrib[:,2],2*contrib[:,1]*contrib[:,2]])
    identity=contrib.sum(1)**2-(np.sum(contrib**2,axis=1)+cross.sum(1))
    eligible=~(boundary|clipping)
    failures=(chain_error>1e-10)|(eligible&(jac_error>h.C['jacobian_absolute_tolerance']))|(np.abs(identity)>1e-10)
    if failures.any():
        i=int(np.flatnonzero(failures)[0])
        raise RuntimeError(json.dumps(dict(local_sample=i,chain_error=float(chain_error[i]),numeric_jac_error=float(jac_error[i]),identity_error=float(identity[i]),boundary=bool(boundary[i]),clipping=bool(clipping[i]))))
    if not np.isfinite(contrib).all():raise RuntimeError('Nonfinite geometry decomposition')
    return dict(terms=terms,jac=jac,chain_error=chain_error,jac_error=jac_error,boundary=boundary,clipping=clipping,weak=weak,delta=delta,contrib=contrib,nonlinear=nonlinear,implied=implied,cross=cross,identity=identity)

def main(args):
    out=h.ROOT/args.out;out.mkdir(exist_ok=False);start=time.time();context={};aggregates=[];stream=None
    stage_contract=dict(scope='STAGE_1_ONLY_STOP_AFTER_RESULTS_REVIEW',parent_contract_sha256=h.c.file_sha(h.ROOT/'CONTRACT.json'),training='NOT_USED',RF_updates='NOT_USED',covariance_and_initial_state='FROZEN_D0',position_error='DR_POSITION_MINUS_GROUND_TRUTH_POSITION',evaluation_heading='DR_HEADING_FIXED_WHILE_COMPARING_POSITIONS',linear_compensation='minus_sum_grad_s_delta_position_divided_by_Hpsi',boundary_and_clipping='FLAG_SEPARATELY_EXCLUDE_FROM_SMOOTH_NUMERICAL_GATE',weak_Hpsi_threshold_per_rad=h.C['weak_heading_derivative_per_rad'],jacobian_absolute_tolerance=h.C['jacobian_absolute_tolerance'],chain_sum_tolerance=1e-10,squared_identity_tolerance=1e-10,parity_absolute_tolerance=h.C['parity_absolute_tolerance'],heading_sensitivity_division='OMITTED_WHEN_WEAK',RF_channel_and_range='NOT_INPUTS_TO_STAGE1_NO_DUPLICATE_GEOMETRY_ROWS',stages_2_5='NOT_RUN',scientific_PASS=False)
    h.c.atomic_json(out/'STAGE_CONTRACT.json',stage_contract)
    receipt=dict(stage=1,status='RUNNING',scientific_PASS=False,stages_2_5='NOT_RUN')
    try:
        p0=h.c.check_inputs();lut=h.c.original_lut(p0);caches,cache_manifest=r.load_caches(p0)
        inputs=dict(started_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,contract=stage_contract,parent_contract=h.C,repository_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=h.REPO,text=True).strip(),cache_sha256=cache_manifest['sha256'],frozen_blobs=h.c.check_frozen_baseline_files(),source_sha256={p.name:h.c.file_sha(p) for p in (h.ROOT/'h3_offline.py',h.ROOT/'run_full.py',Path(__file__))},reference_metrics_sha256={label:h.c.file_sha(r.REFERENCE/(label+'_RF_COMPONENT_METRICS.csv')) for label in ('NOISE','L0','L1','L2')})
        h.c.atomic_json(out/'INPUT_MANIFEST.json',inputs)
        priors,parity=r.prepare_priors(p0,caches,out)
        stream=r.Stream(out/'H3_GEOMETRY_JACOBIAN_DECOMPOSITION.csv')
        for case in p0['cases']:
            for condition,level in h.C['conditions']:
                for seed in h.C['seeds']:
                    context=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed)
                    t,truth,pose,cov=priors[(case['id'],condition,level,seed)]
                    ids=np.flatnonzero(t>=h.C['evaluation_start_s']);x=pose[ids];tr=truth[ids]
                    g=batch_geometry(lut,x,tr,case)
                    # Scalar/vectorized implementations must agree on bounded samples.
                    scalar_max=0.
                    for local in np.linspace(0,len(ids)-1,3,dtype=int):
                        terms,jac,_,_,_=h.chain(lut,x[local],case)
                        diff=max(float(np.max(np.abs(terms-g['terms'][local]))),float(np.max(np.abs(jac-g['jac'][local]))))
                        scalar_max=max(scalar_max,diff)
                    if scalar_max>h.C['parity_absolute_tolerance']:raise RuntimeError('Vectorized geometry parity failure')
                    for i,k in enumerate(ids):
                        row=dict(context,sample=int(k),t_s=float(t[k]),numeric_jac_error=float(g['jac_error'][i]),chain_error=float(g['chain_error'][i]),boundary=bool(g['boundary'][i]),clipping=bool(g['clipping'][i]),weak_heading_sensitivity=bool(g['weak'][i]),H_psi=float(g['jac'][i,2]),delta_x=float(g['delta'][i,0]),delta_y=float(g['delta'][i,1]),prior_heading_error_deg=float(h.wrap(x[i,2]-tr[i,2])*h.RAD),prior_heading_std_deg=float(np.sqrt(cov[k,2,2])*h.RAD),s_change_linear=float(g['contrib'][i].sum()),s_change_nonlinear=float(g['nonlinear'][i]),linear_remainder=float(g['nonlinear'][i]-g['contrib'][i].sum()))
                        for j,name in enumerate(NAMES):
                            row[name+'_Hx']=float(g['terms'][i,j,0]);row[name+'_Hy']=float(g['terms'][i,j,1]);row[name+'_delta_s']=float(g['contrib'][i,j]);row[name+'_implied_heading_deg']=None if g['weak'][i] else float(g['implied'][i,j])
                        for j,key in enumerate(('cross_0_1','cross_0_2','cross_1_2')):row[key]=float(g['cross'][i,j])
                        row['linear_squared_error_identity']=float(g['identity'][i]);stream.append(row)
                    eligible=~(g['boundary']|g['clipping']);valid=~g['weak'];contrib=g['contrib'];linear=contrib.sum(1)
                    agg=dict(context,n=len(ids),smooth_jacobian_samples=int(eligible.sum()),boundary_n=int(g['boundary'].sum()),clipping_n=int(g['clipping'].sum()),weak_heading_n=int(g['weak'].sum()),max_chain_error=float(g['chain_error'].max()),max_numeric_jac_error_smooth=float(g['jac_error'][eligible].max()) if eligible.any() else None,scalar_vectorized_max_abs=scalar_max,linear_delta_s_RMS=float(np.sqrt(np.mean(linear**2))),nonlinear_delta_s_RMS=float(np.sqrt(np.mean(g['nonlinear']**2))),linear_remainder_RMS=float(np.sqrt(np.mean((g['nonlinear']-linear)**2))),linear_nonlinear_correlation=float(np.corrcoef(linear,g['nonlinear'])[0,1]),heading_compensation_RMS_deg=float(np.sqrt(np.mean(g['implied'][valid].sum(1)**2))) if valid.any() else None)
                    for j,name in enumerate(NAMES):
                        agg[name+'_delta_s_mean']=float(contrib[:,j].mean());agg[name+'_delta_s_RMS']=float(np.sqrt(np.mean(contrib[:,j]**2)));agg[name+'_positive_fraction']=float(np.mean(contrib[:,j]>0));agg[name+'_heading_RMS_deg']=float(np.sqrt(np.mean(g['implied'][valid,j]**2))) if valid.any() else None
                    for j,key in enumerate(('cross_0_1','cross_0_2','cross_1_2')):agg[key+'_mean']=float(g['cross'][:,j].mean())
                    aggregates.append(agg);stream.flush();r.save_csv(out/'H3_GEOMETRY_CASE_SEED_METRICS.csv',aggregates)
                    print(json.dumps(dict(context,completed_cells=len(aggregates),rows=stream.n,elapsed_s=time.time()-start)),flush=True)
                    stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                    if stop and Path(stop).exists():raise RuntimeError('Managed stop requested')
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=h.REPO,text=True).strip()
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=h.REPO,text=True).strip()
        if revision!=h.C['base_commit'] or dirty:raise RuntimeError('Original checkout state changed')
        _,after=r.load_caches(p0)
        if after['sha256']!=cache_manifest['sha256']:raise RuntimeError('Input cache manifest changed')
        if inputs['frozen_blobs']!=h.c.check_frozen_baseline_files():raise RuntimeError('Frozen baseline blobs changed')
        receipt.update(status='PASS',exit_code=0,completed_cells=len(aggregates),rows=stream.n,prior_reference_cells=len(parity)*len(h.C['RF_pairs']),prior_max_absolute_difference=max(row['parity_max_abs'] for row in parity),max_numeric_jac_error_smooth=max(row['max_numeric_jac_error_smooth'] or 0 for row in aggregates),max_chain_error=max(row['max_chain_error'] for row in aggregates),repository_clean=True,repository_revision=revision,elapsed_s=time.time()-start)
    except Exception as exc:
        receipt.update(status='FAIL_CLOSED',exit_code=1,failure_reason=str(exc),failure_context=context,completed_cells=len(aggregates),rows=0 if stream is None else stream.n,elapsed_s=time.time()-start);traceback.print_exc()
    finally:
        if stream:stream.close()
        h.c.atomic_json(out/'VALIDATION_RECEIPT.json',receipt)
    return receipt['exit_code']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='STAGE1_01');sys.exit(main(parser.parse_args()))
