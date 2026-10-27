from common import *
from helpers import cache_inputs,exact_compare
from decompose import arrays,metric_rows
from common import wrap
import traceback
def main():
 freeze()
 write('B_CODE_LOCK.json',{str(p):S.sha(p) for p in [Path(__file__),ROOT/'helpers.py',ROOT/'decompose.py',ROOT/'PROTOCOL.md']})
 model=V.SourceFFD();cache=cache_inputs();means={};records=[]
 for case,bias,inp,ref,mask in cache:
  delta=inp['pred']-inp['mu'][:,0];c=float(delta[mask[:,0]].mean());v=delta-c
  check('mean_v',v[mask[:,0]].mean(),0,1e-12);means[(case['id'],bias)]=c;records.append(dict(case=case['id'],bias=bias,c_m=c,accepted=int(mask[:,0].sum()),v_mean=float(v[mask[:,0]].mean())))
 pd.DataFrame(records).to_csv(ROOT/'B_COMPONENTS.csv',index=False)
 paired=[]
 for case in V.MANIFEST['cases']:
  refs={bias:ref for cc,bias,inp,ref,mask in cache if cc['id']==case['id']}
  paired.append(dict(case=case['id'],c_B0=means[(case['id'],'B0')],c_L2=means[(case['id'],'L2')],difference_m=means[(case['id'],'L2')]-means[(case['id'],'B0')],mask_differences=int(np.count_nonzero(refs['B0']['acc'][:,0]!=refs['L2']['acc'][:,0]))))
 pd.DataFrame(paired).to_csv(ROOT/'B_PAIRED_DESCRIPTIVE.csv',index=False)
 write('B_COMPONENT_GATE.json',dict(status='PASS'));scores=[];metrics=[];interactions=[]
 for case,bias,inp,ref,mask in cache:
  c=means[(case['id'],bias)];out_by={};delta=inp['pred']-inp['mu'][:,0]
  for mode in ['CONST','VAR','FULL']:
   alphas=[0,.25,.5,.75,1] if mode!='FULL' else [1];specs=[dict(name=mode+'_'+str(a),alpha=a) for a in alphas];ip=inp.copy();ip['pred']=inp['mu'][:,0]+(c if mode=='CONST' else delta-c if mode=='VAR' else delta)
   out=E.replay(case,ip,model,specs,mask);out_by[mode]=out
   exact_compare(mode+'_control',out,0,ref,4 if mode=='FULL' else 0)
   scores.extend(E.score('B_'+mode,case,bias,ip,out,specs,0));z=dict(t_s=inp['t'],truth_scoring_only=ref['truth_scoring_only'],**out);a,_,_,_=arrays(z,case);metrics.extend(metric_rows(a,case,bias,[s['name'] for s in specs],alphas))
  maskscore=inp['t']>=30;truth=ref['truth_scoring_only'][maskscore,2];full=wrap(np.degrees(ref['x'][maskscore,:,2]-truth[:,None]));const=wrap(np.degrees(out_by['CONST']['x'][maskscore,:,2]-truth[:,None]));var=wrap(np.degrees(out_by['VAR']['x'][maskscore,:,2]-truth[:,None]));bb=full[:,0]
  for j,alpha in enumerate([0,.25,.5,.75,1]):
   fb=float(full[:,j].mean()-bb.mean());cb=float(const[:,j].mean()-bb.mean());vb=float(var[:,j].mean()-bb.mean());ib=fb-cb-vb;valid=abs(fb)>=.05;ratio=abs(ib)/abs(fb) if valid else None
   interactions.append(dict(case=case['id'],bias=bias,alpha=alpha,delta_FULL=fb,delta_CONST=cb,delta_VAR=vb,I_bias=ib,I_bias_normalized=ratio,s_const=cb/fb if valid else None,s_var=vb/fb if valid else None,I_MSE=float(np.mean(full[:,j]**2-const[:,j]**2-var[:,j]**2+bb**2)),I_timeseries_rms=float(np.sqrt(np.mean(wrap(full[:,j]-const[:,j]-var[:,j]+bb)**2))),shares_interpretable=valid and ratio<=.3))
  pd.DataFrame(scores).to_csv(ROOT/'B_SCORES.csv',index=False);pd.DataFrame(metrics).to_csv(ROOT/'B_DECOMPOSITION.csv',index=False);pd.DataFrame(interactions).to_csv(ROOT/'B_INTERACTIONS.csv',index=False);write('B_CHECKS.json',S.checks);S.event('B_CASE_PASS',case=case['id'],bias=bias)
 preserve();write('B_GATE.json',dict(status='PASS',conditions=14));S.event('B_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('B_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
