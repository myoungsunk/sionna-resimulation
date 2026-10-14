"""Stages 1--4 only; streaming evidence and fail-closed numerical gates."""
import argparse,csv,json,sys,time,traceback,subprocess,os
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import norm
import h3_offline as h
from h3_offline import c,C,ROOT,REPO
import run_gates as gates

CACHE=gates.CACHE
REFERENCE=REPO/'research/EKF3_INDEPENDENT_20261013/diagnostics/robust_fusion/results/LOSS_FAMILY_20261013'

def save_csv(path,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

class Stream:
    def __init__(self,path):self.file=path.open('w',encoding='utf-8',newline='');self.writer=None;self.n=0
    def append(self,row):
        if self.writer is None:
            self.writer=csv.DictWriter(self.file,fieldnames=list(row));self.writer.writeheader()
        self.writer.writerow(row);self.n+=1
    def flush(self):self.file.flush()
    def close(self):self.file.close()

def load_caches(p0):
    result={};manifest=json.loads((CACHE/'MANIFEST.json').read_text())
    for name,sha in manifest['sha256'].items():
        if c.file_sha(CACHE/name)!=sha:raise RuntimeError('Frozen RF drift: '+name)
    for case in p0['cases']:
        for channel in ('los','full'):
            with np.load(CACHE/(case['id']+'_'+channel+'.npz'),allow_pickle=False) as data:
                result[(case['id'],channel)]={k:data[k].copy() for k in data.files}
            data=result[(case['id'],channel)]
            if channel=='full' and not np.array_equal(data['E1_FULL_LORO'],data['E1_outer_'+case['route']]):
                raise RuntimeError('E1 evaluation fold mismatch '+case['id'])
    return result,manifest

def train_models(p0,lut,caches):
    models={};records=[];ledger=[]
    for heldout in sorted({case['route'] for case in p0['cases']}):
        xy=np.concatenate([caches[(case['id'],'los')]['truth'][:,:2] for case in p0['cases'] if case['route']==heldout])
        tree=cKDTree(xy)
        for channel,rm in C['RF_pairs']:
            values=[];keys=set();removed=0;used_cases=[]
            for case in p0['cases']:
                if case['route']==heldout:continue
                data=caches[(case['id'],channel)];tr=data['truth']
                valid=(data['t']>=C['evaluation_start_s'])&(tree.query(tr[:,:2])[0]>C['training_spatial_buffer_m'])
                removed+=int(np.count_nonzero((data['t']>=C['evaluation_start_s'])&~valid))
                ids=[]
                for k in np.flatnonzero(valid):
                    key=(case['id'],int(data['pose_ids'][k]))
                    if key not in keys:keys.add(key);ids.append(k)
                if not ids:continue
                ids=np.asarray(ids);truth=tr[ids]
                hs=h.model(lut,truth,case)
                hr=np.sqrt(np.sum((truth[:,:2]-case['anchor'][:2])**2,axis=1)+(case['robot_z_m']-case['anchor'][2])**2)
                range_key=rm if rm=='B_OLD' else 'E1_outer_'+heldout
                errors=np.column_stack([data['s'][ids]-hs,data[range_key][ids]-hr])
                if not np.isfinite(errors).all():raise RuntimeError('Nonfinite training residual')
                values.append(errors);used_cases.append(case['id'])
                ledger.append(dict(heldout_route=heldout,channel=channel,range_model=rm,training_case=case['id'],training_route=case['route'],n=len(ids),pose_ids_sha256=__import__('hashlib').sha256(data['pose_ids'][ids].tobytes()).hexdigest(),range_key=range_key,min_spatial_distance_m=float(tree.query(truth[:,:2])[0].min())))
            if not values:raise RuntimeError('No nonoverlapping training samples '+heldout)
            arr=np.concatenate(values);mu=arr.mean(0);R=np.cov(arr,rowvar=False,ddof=1)
            if np.linalg.eigvalsh(R).min()<=0:raise RuntimeError('Training covariance not positive definite')
            models[(heldout,channel,rm)]=(mu,R)
            records.append(dict(heldout_route=heldout,channel=channel,range_model=rm,n_train=len(arr),buffer_removed=removed,mu_s=float(mu[0]),mu_r=float(mu[1]),R_s=float(R[0,0]),R_r=float(R[1,1]),R_sr=float(R[0,1]),rho=float(R[0,1]/np.sqrt(R[0,0]*R[1,1])),minimum_eigenvalue=float(np.linalg.eigvalsh(R).min()),training_cases=json.dumps(used_cases),sensor_seed_duplicates=0))
    return models,records,ledger

def prepare_priors(p0,caches,out):
    refs={}
    for label in ('NOISE','L0','L1','L2'):
        path=REFERENCE/(label+'_RF_COMPONENT_METRICS.csv')
        with path.open(encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r['model']=='M0' and r['arm']=='D0':
                    refs[(r['case'],r['condition'],int(r['level']),int(r['seed']),r['channel'],r['range_model'])]=r
    priors={};rows=[]
    for case in p0['cases']:
        for condition,level in C['conditions']:
            for seed in C['seeds']:
                t,tr,pids,motion,_=c.case_motion(p0,case,seed,level,condition)
                cache=caches[(case['id'],'los')]
                if not (np.array_equal(t,cache['t']) and np.array_equal(tr,cache['truth']) and np.array_equal(pids,cache['pose_ids'])):
                    raise RuntimeError('Motion/cache alignment mismatch')
                f=c.DiagnosticFilter(c.initial_state(tr[0],seed));poses=[];covs=[]
                for k in range(len(t)):
                    if k:f.predict(float(motion['ds_odom'][k]),float(motion['dtheta_gyro'][k]),float(motion['dt_s'][k]))
                    poses.append(f.pose.copy());covs.append(f.Ppose.copy())
                poses=np.asarray(poses);covs=np.asarray(covs);mask=t>=C['evaluation_start_s']
                err=poses[mask]-tr[mask];err[:,2]=h.wrap(err[:,2]);pp=covs[mask]
                solved=np.linalg.solve(pp,err[...,None])[...,0]
                metrics=dict(n=int(mask.sum()),heading_rmse_deg=float(np.sqrt(np.mean(err[:,2]**2))*h.RAD),xy_rmse_m=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),mean_pose_NEES=float(np.mean(np.einsum('ni,ni->n',err,solved))),mean_heading_NEES=float(np.mean(err[:,2]**2/pp[:,2,2])))
                maxdiff=0.
                for channel,rm in C['RF_pairs']:
                    ref=refs[(case['id'],condition,level,seed,channel,rm)]
                    diff=max(abs(metrics[key]-float(ref[key])) for key in metrics)
                    if diff>C['parity_absolute_tolerance']:raise RuntimeError('D0 parity failure '+str((case['id'],condition,level,seed,channel,rm,diff)))
                    maxdiff=max(maxdiff,diff)
                # Position-conditioning uses the nearest normal lift only where its
                # omitted aliases have rigorously negligible heading prior mass.
                tail=float(2*norm.sf(np.pi/np.sqrt(covs[:,2,2].max())))
                if tail>C['parity_absolute_tolerance']:raise RuntimeError('Wrapped joint prior aliases cannot be neglected')
                key=(case['id'],condition,level,seed);priors[key]=(t,tr,poses,covs)
                rows.append(dict(case=case['id'],condition=condition,level=level,seed=seed,parity_max_abs=maxdiff,omitted_prior_alias_mass_bound=tail,**metrics))
    save_csv(out/'D0_PARITY.csv',rows)
    return priors,rows

def geometry_row(lut,x,P,tr,case,base):
    terms,J,err,boundary,clipping=h.chain(lut,x,case);delta=x[:2]-tr[:2]
    contrib=terms@delta;weak=abs(J[2])<C['weak_heading_derivative_per_rad']
    comparable=tr.copy();comparable[2]=x[2]
    nonlinear=float(h.model(lut,x,case)-h.model(lut,comparable,case))
    row=dict(base,numeric_jac_error=err,boundary=boundary,clipping=clipping,weak_heading_sensitivity=weak,H_psi=float(J[2]),delta_x=float(delta[0]),delta_y=float(delta[1]),s_change_linear=float(contrib.sum()),s_change_nonlinear=nonlinear,linear_remainder=float(nonlinear-contrib.sum()))
    for i,name in enumerate(('theta','phi_TX','phi_RX')):
        row[name+'_Hx']=float(terms[i,0]);row[name+'_Hy']=float(terms[i,1]);row[name+'_delta_s']=float(contrib[i]);row[name+'_implied_heading_deg']=None if weak else float(-contrib[i]/J[2]*h.RAD)
    for i,j in ((0,1),(0,2),(1,2)):row[f'cross_{i}_{j}']=float(2*contrib[i]*contrib[j])
    row['linear_squared_error_identity']=float(contrib.sum()**2-(np.sum(contrib**2)+2*(contrib[0]*contrib[1]+contrib[0]*contrib[2]+contrib[1]*contrib[2])))
    return row

def main(args):
    out=ROOT/args.out;out.mkdir(exist_ok=False);start=time.time();streams={};context={};completed=0
    receipt=dict(status='RUNNING',scientific_PASS=False,recursive_fusion='NOT_RUN',completed_pairs=0)
    try:
        p0=c.check_inputs();lut=c.original_lut(p0);caches,im=load_caches(p0)
        c.atomic_json(out/'INPUT_MANIFEST.json',dict(started_utc=datetime.now(timezone.utc).isoformat(),command=sys.argv,contract=C,repository_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),source_sha256={p.name:c.file_sha(p) for p in ROOT.glob('*.py')},contract_sha256=c.file_sha(ROOT/'CONTRACT.json'),frozen_blobs=c.check_frozen_baseline_files(),cache_sha256=im['sha256']))
        tests=gates.synth();save_csv(out/'SYNTHETIC_GATES.csv',tests)
        models,records,ledger=train_models(p0,lut,caches)
        save_csv(out/'RF_S_RANGE_DEPENDENCE.csv',records);save_csv(out/'TRAINING_FOLD_LEDGER.csv',ledger)
        priors,parity=prepare_priors(p0,caches,out)
        for name in ('H3_GEOMETRY_JACOBIAN_DECOMPOSITION','H3_INVERSE_VS_MAP','H3_MULTIMODAL_POSTERIOR','H3_RANGE_GEOMETRY_PAIRED'):
            streams[name]=Stream(out/(name+'.csv'))
        for case in p0['cases']:
            for condition,level in C['conditions']:
                for seed in C['seeds']:
                    t,tr,poses,covs=priors[(case['id'],condition,level,seed)]
                    for k in np.flatnonzero(t>=C['evaluation_start_s']):
                        base=dict(case=case['id'],route=case['route'],condition=condition,level=level,seed=seed,sample=int(k),t_s=float(t[k]))
                        x,P=poses[k],covs[k];context=dict(base,phase='geometry')
                        streams['H3_GEOMETRY_JACOBIAN_DECOMPOSITION'].append(geometry_row(lut,x,P,tr[k],case,base))
                        for channel,rm in C['RF_pairs']:
                            data=caches[(case['id'],channel)];zs,zr=float(data['s'][k]),float(data[rm][k]);b=dict(base,channel=channel,range_model=rm)
                            context=dict(b,phase='inverse_and_MAP')
                            parity_error=h.baseline_parity(lut,x,P,zs,case)
                            inv=h.legacy(lut,x,P,zs,case,tr[k]);post=h.posterior(h.fixed_logfun(lut,x,P,zs,case));score=h.scored(post,tr[k,2])
                            streams['H3_INVERSE_VS_MAP'].append(dict(b,prior_heading_error_deg=float(h.wrap(x[2]-tr[k,2])*h.RAD),inverse_heading_error_deg=float(h.wrap(inv['selected']-tr[k,2])*h.RAD),inverse_status=inv['status'],root_count=inv['root_count'],nearest_root_error_deg=None if inv['nearest'] is None else float(h.wrap(inv['nearest']-tr[k,2])*h.RAD),oracle_root_error_deg=None if inv['oracle'] is None else float(h.wrap(inv['oracle']-tr[k,2])*h.RAD),oracle_label='ORACLE_DIAGNOSTIC_ONLY',MAP_heading_error_deg=score['heading_error_deg'],MAP_rotation_from_prior_deg=float(h.wrap(post['MAP']-x[2])*h.RAD),inverse_rotation_from_prior_deg=float(h.wrap(inv['selected']-x[2])*h.RAD),inverse_opposite_branch=int(abs(h.wrap(inv['selected']-tr[k,2]))>np.pi/2),MAP_opposite_branch=score['opposite_branch'],MAP_vs_root_delta_deg=None if inv['nearest'] is None else float(h.wrap(post['MAP']-inv['nearest'])*h.RAD),parity_abs=parity_error))
                            streams['H3_MULTIMODAL_POSTERIOR'].append(dict(b,**score))
                            for rfmodel,mu,R in [('FROZEN_R0_ZERO_MEAN',np.zeros(2),np.diag([c.RS,c.RR])),('OOF_GAUSSIAN_JOINT_MEAN_COVARIANCE',*models[(case['route'],channel,rm)])]:
                                context=dict(b,phase='range_geometry',RF_model=rfmodel)
                                # Fixed-position G0 matches stage2 exactly for R0.
                                pp=post if rfmodel=='FROZEN_R0_ZERO_MEAN' else h.posterior(h.fixed_logfun(lut,x,P,zs,case,mu[0],R[0,0]))
                                streams['H3_RANGE_GEOMETRY_PAIRED'].append(dict(b,RF_model=rfmodel,method='G0_DR_GEOMETRY',range_gate='not_used',geometry_status='valid',heading_prior_shift_deg=0.,**h.scored(pp,tr[k,2])))
                                height=case['anchor'][2]-case['robot_z_m'];radius=zr-mu[1]
                                if radius<=0 or radius<abs(height):
                                    g1=dict(h.scored(pp,tr[k,2]));g1={key:None for key in g1};status='unrealizable_slant_range'
                                else:
                                    theta=float(np.arctan2(np.sqrt(max(radius**2-height**2,0)),height)*h.RAD)
                                    g1=h.scored(h.posterior(h.fixed_logfun(lut,x,P,zs,case,mu[0],R[0,0],theta)),tr[k,2]);status='partial_geometry_diagnostic'
                                streams['H3_RANGE_GEOMETRY_PAIRED'].append(dict(b,RF_model=rfmodel,method='G1_THETA_ONLY',range_gate='not_applied',geometry_status=status,heading_prior_shift_deg=0.,**g1))
                                for full_cross in (False,True):
                                    method='G2_FULL_CROSS' if full_cross else 'G2_HEADING_FIXED'
                                    context.update(method=method)
                                    xp,px,gate=h.range_update(x,P,zr,case,mu[1],R[1,1],full_cross)
                                    # Rejected range is absent from posterior. Conditioning
                                    # on an unused range would otherwise reintroduce it.
                                    if gate=='rejected_NIS':
                                        rr=np.diag([R[0,0],R[1,1]])
                                        po=h.integrated_posterior(lut,x,P,zs,zr,case,mu,rr,True)
                                    else:po=h.integrated_posterior(lut,xp,px,zs,zr,case,mu,R,True)
                                    streams['H3_RANGE_GEOMETRY_PAIRED'].append(dict(b,RF_model=rfmodel,method=method,range_gate=gate,geometry_status='EKF_range_approximation_conditional_s_once',heading_prior_shift_deg=float(h.wrap(xp[2]-x[2])*h.RAD),**h.scored(po,tr[k,2])))
                                context.update(method='G3_JOINT_HEADING_MARGINAL')
                                po=h.integrated_posterior(lut,x,P,zs,zr,case,mu,R)
                                streams['H3_RANGE_GEOMETRY_PAIRED'].append(dict(b,RF_model=rfmodel,method='G3_JOINT_HEADING_MARGINAL',range_gate='likelihood_no_gate',geometry_status='position_integrated',heading_prior_shift_deg=0.,**h.scored(po,tr[k,2])))
                            completed+=1
                        if (k%25)==0:
                            for stream in streams.values():stream.flush()
                            print(json.dumps(dict(context,completed_pairs=completed,elapsed_s=time.time()-start)),flush=True)
                        stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
                        if stop and Path(stop).exists():raise RuntimeError('Managed stop requested')
                    print('completed cell',case['id'],condition,level,seed,flush=True)
        receipt.update(status='PASS',exit_code=0,full_experiment='PASS',D0_parity_cells=len(parity),completed_pairs=completed,elapsed_s=time.time()-start)
    except Exception as exc:
        receipt.update(status='FAIL_CLOSED',exit_code=1,full_experiment='INCOMPLETE',failure_reason=str(exc),failure_type=type(exc).__name__,failure_context=context,completed_pairs=completed,elapsed_s=time.time()-start)
        traceback.print_exc()
    finally:
        for stream in streams.values():stream.close()
        receipt['output_rows']={name:s.n for name,s in streams.items()}
        c.atomic_json(out/'VALIDATION_RECEIPT.json',receipt)
    return receipt['exit_code']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default='FULL_01');args=parser.parse_args();sys.exit(main(args))
