from common import *
from run_a import arrays,metric_rows
import traceback
MODES=['UNCUT','CUT_ALL','CUT_AZ','CUT_EL','CUT_R']
class ReplayGeometry:
 def __init__(self,model,truth,specs):self.model=model;self.truth=truth;self.specs=specs;self.k=0
 def batch(self,x,case):
  self.model.gt=self.truth[self.k];self.model.modes=[s['geometry'] for s in self.specs];self.model.explicit=None;self.k+=1
  return self.model.batch(x,case)
def cache_inputs():
 feat=pd.read_csv(S.one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(S.one('OOF_PARAMETERS.csv.gz'));mr=pd.read_csv(S.PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(S.PKG/'results_hgate/HG_SERIES.csv.gz')
 cache=[]
 for case in V.MANIFEST['cases']:
  for bias in ['B0','L2']:
   inp=S.load_case(case,bias,feat,par,mr,hg);ref=load(E1/'E1'/f'{case["id"]}_{bias}.npz');check('t',inp['t'],ref['t_s'],0);check('ids',inp['ids'],ref['pose_id'],0)
   mask=np.column_stack([ref['acc'][:,0],ref['acc'][:,-1]]);check('fixed_mask',mask[:,0],mask[:,1],0)
   cache.append((case,bias,inp,ref,mask))
 return cache
def exact_compare(label,out,j,ref,jr):
 for k in ['x','P','prior','Pprior','h','H','K','mu','R','nu','acc']:
  check(label+'_'+k,out[k][:,j],ref[k][:,jr])
def main():
 assert json.loads((ROOT/'A_GATE.json').read_text())['status']=='PASS';preserve()
 write('C_CODE_LOCK.json',{str(p):S.sha(p) for p in [Path(__file__),ROOT/'run_a.py',ROOT/'PROTOCOL.md']})
 _,model=models();cache=cache_inputs();control_specs=[dict(name='UNCUT_'+str(a),alpha=a,geometry='UNCUT') for a in [0,1]];scores=[];decomp=[]
 old_scores=pd.read_csv(E1/'SCORES.csv')
 for case,bias,inp,ref,mask in cache:
  proxy=ReplayGeometry(model,ref['truth_scoring_only'],control_specs);out=E.replay(case,inp,proxy,control_specs,mask)
  for j,jr in [(0,0),(1,4)]:exact_compare('C_control',out,j,ref,jr)
  sc=E.score('C_CONTROL',case,bias,inp,out,control_specs,0)
  for row in sc:
   old=old_scores[(old_scores.stage=='E1')&(old_scores.case==case['id'])&(old_scores.bias==bias)&(old_scores.alpha==row['alpha'])].iloc[0]
   for key in ['heading_rmse_deg','heading_bias_deg','heading_std_deg','heading95_deg','heading_nees','state4_nees','range_rmse_cm','xy_rmse_m','accepted_all','scoring_n']:check('C_score_'+key,row[key],old[key])
  S.event('C_CONTROL_CASE_PASS',case=case['id'],bias=bias)
 write('C_CONTROL_GATE.json',dict(status='PASS',conditions=14));write('C_CONTROL_CHECKS.json',S.checks)
 specs=[dict(name=mode+'_'+str(alpha),alpha=alpha,geometry=mode) for mode in MODES for alpha in [0,1]]
 for case,bias,inp,ref,mask in cache:
  proxy=ReplayGeometry(model,ref['truth_scoring_only'],specs);out=E.replay(case,inp,proxy,specs,mask)
  for j,jr in [(0,0),(1,4)]:exact_compare('C_uncut',out,j,ref,jr)
  scores.extend(E.score('C',case,bias,inp,out,specs,0));pd.DataFrame(scores).to_csv(ROOT/'C_SCORES.csv',index=False)
  z=dict(t_s=inp['t'],truth_scoring_only=ref['truth_scoring_only'],**out);a,_,_,_=arrays(z,case);decomp.extend(metric_rows(a,case,bias,[s['name'] for s in specs],[s['alpha'] for s in specs]));pd.DataFrame(decomp).to_csv(ROOT/'C_DECOMPOSITION.csv',index=False)
  write('C_CHECKS.json',S.checks);S.event('C_CASE_PASS',case=case['id'],bias=bias)
 gaps=[];interaction=[]
 for (case,bias),g in pd.DataFrame(scores).groupby(['case','bias']):
  g=g.set_index('arm');G={mode:float(g.loc[mode+'_1','heading_bias_deg']-g.loc[mode+'_0','heading_bias_deg']) for mode in MODES};uncut=G['UNCUT']
  for mode in MODES[1:]:
   valid=abs(uncut)>=.01;fm=1-abs(G[mode])/abs(uncut) if valid else None;fs=1-G[mode]/uncut if valid else None
   gaps.append(dict(case=case,bias=bias,mode=mode,G_uncut=uncut,G_cut=G[mode],f_magnitude=fm,f_signed=fs,sign_reversal=uncut*G[mode]<0 if valid else None,decision='NOT_IDENTIFIABLE' if not valid else 'STRONG' if fm>=.7 else 'PARTIAL' if fm>=.3 else 'WEAK'))
  interaction.append(dict(case=case,bias=bias,all_change=G['CUT_ALL']-uncut,sum_individual_changes=sum(G[m]-uncut for m in ['CUT_AZ','CUT_EL','CUT_R']),interaction=(G['CUT_ALL']-uncut)-sum(G[m]-uncut for m in ['CUT_AZ','CUT_EL','CUT_R'])))
 pd.DataFrame(gaps).to_csv(ROOT/'C_GAP_REDUCTIONS.csv',index=False);pd.DataFrame(interaction).to_csv(ROOT/'C_INTERACTIONS.csv',index=False)
 preserve();write('C_GATE.json',dict(status='PASS',conditions=14,score_rows=len(scores),oracle=True));S.event('C_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('C_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
