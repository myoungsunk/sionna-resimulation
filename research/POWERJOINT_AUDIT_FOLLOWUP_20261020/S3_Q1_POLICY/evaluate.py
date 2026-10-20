"""288 locked evaluation rows; callbacks receive only own current prior and RF."""
import argparse,traceback
from common import *
sys.path.insert(0,str(AUDIT/'T2_NEW_ROUTE_BASELINE'))
from prepare_inputs import prepare_new_route,build_canonical_controls
def choose(pred,margin,arm):
 if arm=='POLICY_NO_MARGIN':adjusted=pred.copy()
 else:adjusted=np.array([pred[j]-margin[x]['delta'] if margin[x]['enabled_v3'] else -np.inf for j,x in enumerate(NONPOWER)])
 j=int(np.argmax(adjusted));return NONPOWER[j] if adjusted[j]>0 else 'POWER'
def main():
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--models',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);(a.out/'traces').mkdir(exist_ok=True)
 rows=[];aux=[];checks=[];action_summary=[];errors=[];attempt=None;proof={}
 expected=pd.read_csv(HERE/'EVALUATION_MATRIX.csv');expected=expected[expected.route==a.route]
 try:
  lock,model=runtime(a.out);assert os.getenv('GITHUB_SHA'),'COMMITTED_ACTIONS_REQUIRED'
  record=json.loads(a.models.read_text());marginrecord=json.loads((a.models.parent/'MARGINS.json').read_text());assert record['feature_names']==FEATURES and record['actions']==NONPOWER and record['protocol_sha256']==marginrecord['protocol_sha256']==sha(HERE/'PROTOCOL_LOCK.json')
  fold=a.route if a.route.startswith('R') else 'ALL_OLD';ests=[deserialize(x) for x in record['models'][fold]['estimators']];reloaded=[deserialize(x) for x in record['models'][fold]['estimators']];margin=marginrecord['margins'][fold]
  meta=json.loads((HERE/'CASE_METADATA.json').read_text());data=[];root=SOURCE.parent
  if a.route.startswith('R'):
   raw=original.frozen_inputs();labels=pd.read_csv(root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz');cached=pd.read_csv(root/'reference_ae/OOF_PARAMETERS.csv.gz')
   for case in meta['legacy']:
    if case['route']!=a.route:continue
    for channel in ['full']+(['los'] if case['id'] in ['R2_aA_m0','R2_aA_m45'] else []):
     cid=case['id'];frame=labels[(labels.case==cid)&(labels.channel==channel)].merge(cached[(cached.case==cid)&(cached.channel==channel)][['pose_id','mu_r','mu_s','C00','C01','C11']],on='pose_id',validate='one_to_one')
     for bias in original.BIAS_LEVELS:
      d=data_old(raw,frame,case,bias,0,channel=channel)
      reference=root/'reference_ae/traces'/f'{cid}_{bias}.npz' if channel=='full' else next((root/'references').rglob(f'{cid}_los_{bias}_POWER1.npz'))
      data.append((case,channel,bias,d,reference))
  else:
   prepared=prepare_new_route(root/'source_route',a.route);t=prepared['motion_t'];ri=prepared['rf_motion_indices'];radio=np.zeros(len(t),bool);radio[ri]=True
   sys.path.insert(0,str(HERE.parent/'S2_N2_GEOMETRY'));from model import PowerModel
   allold=PowerModel(json.loads((HERE.parent/'S2_N2_GEOMETRY/TRAIN_PARAMS.json').read_text())['ALL_OLD']['models']['Q_POWER1'])
   for rec in prepared['cases']:
    cid=rec['case_id'];case=next(c for c in meta['new'] if c['id']==cid);h=np.load(rec['full_path'],allow_pickle=False);frame=pd.concat([pd.DataFrame(original.extract(h[i:i+64,:,:,0],model.freqs)) for i in range(0,len(h),64)],ignore_index=True)
    z=np.zeros((len(t),2));z[ri]=frame[['range_m','s_fp']].to_numpy();measured=np.zeros((len(t),17));measured[ri]=frame[MEASURED].to_numpy();q=np.zeros(len(t));q[ri]=frame.log_fp_power.to_numpy();mu,C=allold.predict(q[:,None],q)
    for bias in original.BIAS_LEVELS:
     controls,initial,sensor=build_canonical_controls(prepared,bias,0,SOURCE);d=dict(t=t,truth=prepared['motion_truth'],z=z,mu=mu,C=C,controls=controls,initial=initial,radio=radio,measured=measured,los_exists=rec['los_exists'])
     reference=next((root/'references').rglob(f'{cid}_{bias}.npz'));ref=load(reference)
     assert np.array_equal(t,ref['t']) and np.array_equal(z,ref['observations']) and np.array_equal(d['truth'],ref['truth_for_offline_scoring_only']) and np.array_equal(radio,ref['radio_mask'])
     assert np.array_equal(initial,ref['initial_pose']) and all(np.array_equal(controls[k],ref[v]) for k,v in [('dt_s','controls_dt'),('ds_odom','controls_ds'),('dtheta_gyro','controls_dyaw')]),'T2_SENSOR_IDENTITY'
     assert max(float(abs(mu[radio]-ref['mu_input'][radio]).max()),float(abs(C[radio]-ref['C_input'][radio]).max()))<=1e-10,'ALL_OLD_MU_C_PARITY'
     data.append((case,'full',bias,d,reference))
  key=pd.read_csv(SOURCE/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
  for case,channel,bias,d,reference in data:
   cid=case['id'];attempt=dict(case=cid,channel=channel,bias=bias,seed=0);action_rows=[]
   def callback(i,prior,P,h,H,mu,C,spec):
    arm=spec['name']
    if arm=='POWER1':return 'POWER'
    if arm=='R0':return 'R0'
    f=internal_features(d['measured'][i],P,h,H,mu,C,d['z'][i]);pred=np.array([e.predict(f[None])[0] for e in ests]);action=choose(pred,margin,arm)
    action_rows.append(dict(**attempt,arm=arm,frame=i,t_s=float(d['t'][i]),action=action,prior_x=float(prior[0]),prior_y=float(prior[1]),prior_yaw_rad=float(prior[2]),prior_bg_rad_s=float(prior[3]),**dict(zip(FEATURES,map(float,f))),**{'predicted_utility_'+x:float(pred[j]) for j,x in enumerate(NONPOWER)}))
    return action
   arms=['POWER1','R0','POLICY_V3','POLICY_NO_MARGIN'];r=recurse(model,d,case,[dict(name=x,base='power') for x in arms],callback);stem=f'{cid}_{channel}_{bias}_seed0';save_trace(a.out/'traces'/f'{stem}.npz',r,d)
   eig=finite_spd(r);assert not r['accepted'][~d['radio']].any(),'NONRADIO_UPDATE'
   baseline=recurse(model,d,case,[dict(name='POWER1',base='power')]);sd,cd,gd=parity(r,0,baseline,0);assert max(sd,cd)<=1e-10 and gd==0,('ALWAYS_POWER_CALLBACK',sd,cd,gd)
   checks.append(dict(**attempt,check='ALWAYS_POWER_CALLBACK',state_max=sd,cov_max=cd,gate_mismatches=gd,minimum_eigenvalue=eig,nonradio_updates=0,status='PASS'))
   old=load(reference);j=list(old['names'].astype(str)).index('POWER1');mask=d['t']>=30;metric=metrics(r,0,d['truth'],original.BIAS_LEVELS[bias],mask);old_rmse=np.sqrt(np.mean(np.degrees((old['state'][mask,j,2]-d['truth'][mask,2]+np.pi)%(2*np.pi)-np.pi)**2));hd=abs(metric['heading_rmse_deg']-float(old_rmse));gates=int(np.count_nonzero(r['accepted'][:,0]!=old['accepted'][:,j]));assert hd<=1e-6 and gates==0,('HISTORICAL_POWER',hd,gates)
   proof[str(reference)]=sha(reference);checks.append(dict(**attempt,check='HISTORICAL_POWER',heading_difference_deg=hd,gate_mismatches=gates,reference_sha256=sha(reference),status='PASS'))
   if channel=='full' and bias=='B0' and a.route.startswith('R'):
    kr=key[(key.case==cid)&(key.method=='POWER1')];assert len(kr)==1;kd=abs(metric['heading_rmse_deg']-float(kr.iloc[0].heading_rmse_deg));assert kd<=1e-6;checks.append(dict(**attempt,check='KEY_B0',heading_difference_deg=kd,status='PASS'))
   for j,arm in enumerate(arms):
    for scope,mask in [('motion',d['t']>=30),('radio',(d['t']>=30)&d['radio'])]:
     row=dict(**attempt,route=a.route,scope=scope,arm=arm,status='TECHNICAL_PASS',**metrics(r,j,d['truth'],original.BIAS_LEVELS[bias],mask));(rows if scope=='motion' else aux).append(row)
   acts=pd.DataFrame(action_rows);assert len(acts)==int(d['radio'].sum())*2,'RADIO_CALLBACK_COUNT'
   X=acts[FEATURES].to_numpy();after=np.column_stack([e.predict(X) for e in reloaded]);before=acts[['predicted_utility_'+x for x in NONPOWER]].to_numpy();assert np.array_equal(before,after),'RELOAD_PREDICTIONS'
   assert [choose(v,margin,arm) for v,arm in zip(after,acts.arm)]==acts.action.tolist(),'RELOAD_ACTIONS'
   for i,row in acts.iterrows():
    j=arms.index(row.arm);prior=r['prior'][int(row.frame),j,:4];assert np.array_equal(prior,np.array([row.prior_x,row.prior_y,row.prior_yaw_rad,row.prior_bg_rad_s])),'OWN_PRIOR_IDENTITY'
    acts.loc[i,'gate_accept']=bool(r['accepted'][int(row.frame),j])
   acts.to_csv(a.out/f'ACTIONS_{stem}.csv',index=False)
   for arm,g in acts.groupby('arm'):
    for scope,part in [('all_radio',g),('t30_radio',g[g.t_s>=30])]:
     for action in ACTIONS:
      selected=part.action==action;action_summary.append(dict(**attempt,arm=arm,scope=scope,action=action,n_radio=len(part),n_selected=int(selected.sum()),selection_fraction=float(selected.mean()),n_gate_accepted=int(part.loc[selected,'gate_accept'].sum()),gate_accept_fraction_all_radio=float(part.gate_accept.astype(bool).mean())))
   checks.append(dict(**attempt,check='OWN_PRIOR_FEATURES_RELOAD_ACTIONS',rows=len(acts),status='PASS'))
   pd.DataFrame(rows).to_csv(a.out/'POLICY_RESULTS.csv',index=False);print('S3_EVAL_CELL',cid,channel,bias,flush=True)
 except Exception as e:errors.append(dict(attempt=attempt,error=str(e),traceback=traceback.format_exc(),retry=False,affected_route_stopped=True))
 present={(x['case'],x['channel'],x['bias'],x['arm']) for x in rows}
 for x in expected.to_dict('records'):
  if (x['case'],x['channel'],x['bias'],x['arm']) not in present:rows.append(dict(x,status='NOT_EXECUTED_AFTER_TECHNICAL_FAILURE'))
 for name,items in [('POLICY_RESULTS',rows),('RF_ONLY_RESULTS',aux),('CHECKS',checks),('ACTION_RATES',action_summary)]:pd.DataFrame(items).to_csv(a.out/f'{name}.csv',index=False)
 manifest(a.out,'evaluate',errors,route=a.route,n_valid=sum(x.get('status')=='TECHNICAL_PASS' for x in rows),inputs=proof,models_sha256=sha(a.models))
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
