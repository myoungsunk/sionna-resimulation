"""Every locked packet, four biases, actual seed controls. No subsampling."""
import argparse,traceback,time
from common import *
def main():
 p=argparse.ArgumentParser();p.add_argument('--outer',required=True);p.add_argument('--case',required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);(a.out/'traces').mkdir(exist_ok=True)
 rows=[];checks=[];errors=[];attempt=None;started=time.time()
 try:
  lock,model=runtime(a.out);assert os.getenv('GITHUB_SHA'),'COMMITTED_ACTIONS_REQUIRED'
  raw=original.frozen_inputs();df=pd.read_csv(SOURCE.parent/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz');full=df[df.channel=='full'].copy();inner=a.case.split('_')[0];target=full[full.route==inner]
  folds=json.loads((HERE/'TRAIN_FOLDS.json').read_text());fit=folds['folds'][a.outer][inner];keys=pd.MultiIndex.from_tuples([tuple(k) for k in fit['training_keys']],names=['case','pose_id']);train=full.set_index(['case','pose_id']).loc[keys].reset_index();assert digest(train[['case','pose_id']].values.tolist())==fit['training_key_sha256']
  assert a.outer not in set(train.route) and inner not in set(train.route),'NESTED_ROUTE_LEAK'
  fitted=ScalarPower(train,train.log_fp_power.to_numpy(),original.site_weights(np,pd,train),original.GROUPS);p1=serialize(fitted)
  dump(a.out/'P1_MODEL.json',dict(outer=a.outer,inner_route=inner,training=fit,model=p1,feature_names=['log_fp_power']))
  frame=target[target.case==a.case];case=next(c for c in json.loads((HERE/'CASE_METADATA.json').read_text())['legacy'] if c['id']==a.case);ordered=frame.set_index('pose_id').loc[raw[a.case,'full']['pose_id']];mu,C=fitted.predict(ordered.log_fp_power.to_numpy())
  np.testing.assert_allclose(deserialize(p1).predict(ordered.log_fp_power.to_numpy())[0],mu,rtol=0,atol=0)
  index=pd.read_csv(HERE/f'LABEL_PACKET_INDEX_{a.outer}_{a.case}.csv');index=index[(index.seed==a.seed)&(index.status=='INCLUDED')]
  for bias,bias_dps in original.BIAS_LEVELS.items():
   d=data_old(raw,frame,case,bias,a.seed,mu,C);zero=data_old(raw,frame,case,bias,0,mu,C);diff=max(float(abs(d['controls'][k]-zero['controls'][k]).max()) for k in d['controls']);assert a.seed==0 or diff>0,'SEED_CONTROLS_NOT_APPLIED'
   chash=controls_hash(d);baseline=recurse(model,d,case,[dict(name='POWER',base='power')]);eig=finite_spd(baseline);save_trace(a.out/'traces'/f'{a.case}_{bias}_seed{a.seed}_nested.npz',baseline,d)
   checks.append(dict(check='ACTUAL_SEED_CONTROLS',case=a.case,bias=bias,seed=a.seed,controls_sha256=chash,seed0_max_abs_difference=diff,minimum_eigenvalue=eig,status='PASS'))
   shard=[]
   for rec in index[index.bias==bias].to_dict('records'):
    attempt=rec;i=rec['frame'];end=rec['end_frame_exclusive'];prior=baseline['prior'][i,0,:4];P=baseline['prior_cov'][i,0,:4,:4];feature=internal_features(d['measured'][i],P,baseline['h'][i,0],baseline['H'][i,0,:,:4],mu[i],C[i],d['z'][i])
    sub={k:d[k][i:end] for k in ('t','truth','z','mu','C','radio')};sub.update(initial=d['initial'],controls={k:v[i:end] for k,v in d['controls'].items()})
    branch=recurse(model,sub,case,[dict(name=x,base='power',first_action=x) for x in ACTIONS],lambda k,x,p,h,H,m,c,s:s['first_action'] if k==0 else 'POWER',initial_state4=prior,initial_cov=P)
    try:
     eig=finite_spd(branch);sd=float(abs(branch['state'][:,0,:4]-baseline['state'][i:end,0,:4]).max());cd=float(abs(branch['cov'][:,0,:4,:4]-baseline['cov'][i:end,0,:4,:4]).max());gd=int(np.count_nonzero(branch['accepted'][:,0]!=baseline['accepted'][i:end,0]));assert max(sd,cd)<=1e-10 and gd==0,('POWER_RESTART_PARITY',sd,cd,gd)
    except Exception:
     save_trace(a.out/'traces'/f'FAILED_{bias}_seed{a.seed}_frame{i}.npz',branch,sub);raise
    mask=sub['t']>d['t'][i];assert int(mask.sum())==rec['horizon_samples'] and mask.sum()>0
    err=np.degrees((branch['state'][mask,:,2]-sub['truth'][mask,2,None]+np.pi)%(2*np.pi)-np.pi);mse=np.mean(err**2,axis=0)
    row=dict(rec,label_class='ORACLE_OFFLINE_TRAINING_LABEL',horizon_s=10.,p1_model_sha256=p1['sha256'],controls_sha256=chash,power_restart_state_max=sd,power_restart_cov_max=cd,power_restart_gate_mismatch=gd,minimum_eigenvalue=eig,**dict(zip(FEATURES,map(float,feature))))
    for j,action in enumerate(ACTIONS):row['mse_'+action]=float(mse[j]);row['utility_'+action]=float(mse[0]-mse[j])
    shard.append(row);rows.append(row)
   pd.DataFrame(shard).to_csv(a.out/f'UTILITY_LABELS_{a.outer}_{a.case}_{bias}_seed{a.seed}.csv',index=False)
   print('LABEL_BIAS_COMPLETE',a.outer,a.case,bias,a.seed,len(shard),'elapsed',time.time()-started,flush=True)
  assert len(rows)==len(index),'LOCKED_LABEL_COUNT'
 except Exception as e:errors.append(dict(attempt=attempt,error=str(e),traceback=traceback.format_exc(),retry=False))
 # Preserve already computed rows even when the current bias stops mid-shard.
 if rows:
  for bias,g in pd.DataFrame(rows).groupby('bias'):g.to_csv(a.out/f'UTILITY_LABELS_{a.outer}_{a.case}_{bias}_seed{a.seed}.csv',index=False)
 pd.DataFrame(checks).to_csv(a.out/'CHECKS.csv',index=False)
 pd.DataFrame([dict(outer=a.outer,case=a.case,seed=a.seed,n_valid=len(rows),elapsed_s=time.time()-started)]).to_csv(a.out/'LABELS_SUMMARY.csv',index=False)
 manifest(a.out,'labels',errors,outer=a.outer,case=a.case,seed=a.seed,n_valid=len(rows))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
