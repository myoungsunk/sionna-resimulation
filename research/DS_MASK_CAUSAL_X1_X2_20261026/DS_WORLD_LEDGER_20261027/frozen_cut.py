from common import *
from helpers import cache_inputs,exact_compare
from decompose import arrays,metric_rows
import core,traceback
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0']
original=V.predict_one

def cut_predict(x,P,ds,gyro,dt,psi_gt):
 q=np.diag([2e-5*abs(ds),np.radians(.015)**2*dt,0.])
 xx=x.copy();xx[2]=psi_gt
 y,F,G=core.transition(xx,ds,gyro,dt);F[:2,2]=0
 y[2]=core.wrap(x[2]+gyro-x[3]*dt)
 return y,core.covariance(F@P@F.T+G@q@G.T,4),F,G

def main():
 files=json.loads((ROOT.parent/'DS_COMPONENT_AZIMUTH_20261027/INPUT_LOCK.json').read_text())['files']
 for r in files:assert S.sha(r['path'])==r['sha256'],r['path']
 files=files+[dict(path=str(p),sha256=S.sha(p)) for p in ROOT.glob('*.py')]+[dict(path=str(ROOT/'PROTOCOL.md'),sha256=S.sha(ROOT/'PROTOCOL.md'))]
 write('INPUT_LOCK.json',dict(files=files,source_commit='0686b23ceeefb696bc158b32b39f8077c564ef5d'))
 x=np.array([1.,2.,.3,.02]);P=np.eye(4);ds=.12;gyro=.03;dt=.2;gt=.2
 y,pp,F,G=cut_predict(x,P,ds,gyro,dt,gt);eps=1e-6
 fd=np.column_stack([(cut_predict(x+np.eye(4)[j]*eps,P,ds,gyro,dt,gt)[0]-cut_predict(x-np.eye(4)[j]*eps,P,ds,gyro,dt,gt)[0])/(2*eps) for j in range(4)])
 check('cut_F_finite_difference',F,fd,1e-8)
 y0,p0=original(x,P,ds,gyro,dt);check('heading_mean_preserved',y[2:],y0[2:]);assert np.linalg.eigvalsh(pp).min()>0
 cache=[r for r in cache_inputs() if r[0]['id'] in PRIMARY];model=V.SourceFFD();specs=[dict(name='A0',alpha=0),dict(name='A1',alpha=1)];scores=[];metrics=[]
 for case,bias,inp,ref,mask in cache:
  out=E.replay(case,inp,model,specs,mask)
  exact_compare(case['id']+bias+'OFF0',out,0,ref,0);exact_compare(case['id']+bias+'OFF1',out,1,ref,4)
  S.event('OFF_PASS',case=case['id'],bias=bias)
 write('OFF_GATE.json',dict(status='PASS',conditions=6,tolerance=1e-10))
 for case,bias,inp,ref,mask in cache:
  counter=[0]
  def proxy(x,P,ds,gyro,dt):
   k=counter[0]//2+1;counter[0]+=1
   return cut_predict(x,P,ds,gyro,dt,float(ref['truth_scoring_only'][k-1,2]))[:2]
  V.predict_one=proxy
  try:out=E.replay(case,inp,model,specs,mask)
  finally:V.predict_one=original
  assert counter[0]==2*(len(inp['t'])-1)
  check('cut_mask',out['acc'],ref['acc'][:,[0,4]],0)
  scores.extend(E.score('CUT_ODO',case,bias,inp,out,specs,0))
  for field in ['x','prior']:
   z=dict(t_s=inp['t'],truth_scoring_only=ref['truth_scoring_only'],x=out[field]);a,*_=arrays(z,case);rr=metric_rows(a,case,bias,['A0','A1'],[0,1]);metrics.extend([dict(state=field,**r) for r in rr])
  pd.DataFrame(scores).to_csv(ROOT/'SCORES.csv',index=False);pd.DataFrame(metrics).to_csv(ROOT/'DECOMPOSITION.csv',index=False)
  write('CHECKS.json',S.checks);S.event('CUT_ODO_CASE_PASS',case=case['id'],bias=bias)
 for r in files:assert S.sha(r['path'])==r['sha256'],r['path']
 write('GATE.json',dict(status='PASS',conditions=6,replay_cells=12,off_control_cells=12));S.event('COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
