from common import *
from helpers import cache_inputs,exact_compare
from decompose import arrays,metric_rows
import traceback
PRIMARY=['R2_aA_m45','R4_aA_m0','R4_aB_m0'];original=E.update

def blocked(x,P,z,h,H,mu,R,mode,ut):
 assert np.all((mode==0)|(mode==1))
 v=z-h-mu;hp=H@P;cov=hp@H.swapaxes(-1,-2)+R;cov=.5*(cov+cov.swapaxes(-1,-2));K=np.linalg.solve(cov,hp).swapaxes(-1,-2)
 K[:,:2,0]-=np.einsum('ni,i->n',K[:,:2,0],ut)[:,None]*ut[None,:]
 delta=np.einsum('nij,nj->ni',K,v);y=x+delta;y[:,2]=V.MC.wrap(y[:,2]);A=np.eye(4)[None]-K@H;cp=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);cp=.5*(cp+cp.swapaxes(-1,-2));yes=mode>0
 return np.where(yes[:,None],y,x),np.where(yes[:,None,None],cp,P),K

def main():
 files=json.loads((ROOT.parent/'DS_COMPONENT_AZIMUTH_20261027/INPUT_LOCK.json').read_text())['files']
 for r in files:assert S.sha(r['path'])==r['sha256']
 files+= [dict(path=str(p),sha256=S.sha(p)) for p in ROOT.glob('*.py')]+[dict(path=str(ROOT/'PROTOCOL.md'),sha256=S.sha(ROOT/'PROTOCOL.md'))]
 write('INPUT_LOCK.json',dict(files=files));cache=[r for r in cache_inputs() if r[0]['id'] in PRIMARY];model=V.SourceFFD();specs=[dict(name='A0',alpha=0),dict(name='A1',alpha=1)];scores=[];metrics=[];mapping=[]
 for case,bias,inp,ref,mask in cache:
  out=E.replay(case,inp,model,specs,mask);exact_compare(case['id']+bias+'OFF0',out,0,ref,0);exact_compare(case['id']+bias+'OFF1',out,1,ref,4);S.event('OFF_PASS',case=case['id'],bias=bias)
 write('OFF_GATE.json',dict(status='PASS',conditions=6))
 for case,bias,inp,ref,mask in cache:
  rad=ref['truth_scoring_only'][:,:2]-np.asarray(case['anchor'])[:2];ur=rad/np.linalg.norm(rad,axis=1)[:,None];ut=np.c_[-ur[:,1],ur[:,0]];counter=[0]
  def proxy(x,P,z,h,H,mu,R,mode):
   k=counter[0];counter[0]+=1
   # Tie call state and measurement to the scheduled packet; record source ID.
   check('packet_measurement',z,np.tile(inp['z'][k],(2,1)),0)
   mapping.append(dict(case=case['id'],bias=bias,k=k,pose_id=int(inp['ids'][k]),GT_source_pose_id=int(ref['pose_id'][k]),t_s=float(inp['t'][k])))
   return blocked(x,P,z,h,H,mu,R,mode,ut[k])
  E.update=proxy
  try:out=E.replay(case,inp,model,specs,mask)
  finally:E.update=original
  assert counter[0]==len(inp['t']);check('mask',out['acc'],ref['acc'][:,[0,4]],0)
  displacement=out['K'][:,:,:2,0]*out['nu'][:,:,0,None]*out['acc'][:,:,None]
  check('range_tangent_removed',np.einsum('nji,ni->nj',displacement,ut),np.zeros(out['acc'].shape))
  check('actual_update',(out['K']*out['nu'][:,:,None,:]).sum(axis=-1)[:,:,:2]*out['acc'][:,:,None],out['x'][:,:,:2]-out['prior'][:,:,:2])
  scores.extend(E.score('CUT_RT',case,bias,inp,out,specs,0))
  for field in ['x','prior']:
   z=dict(t_s=inp['t'],truth_scoring_only=ref['truth_scoring_only'],x=out[field]);a,*_=arrays(z,case);metrics.extend([dict(state=field,**r) for r in metric_rows(a,case,bias,['A0','A1'],[0,1])])
  pd.DataFrame(scores).to_csv(ROOT/'SCORES.csv',index=False);pd.DataFrame(metrics).to_csv(ROOT/'DECOMPOSITION.csv',index=False);write('CHECKS.json',S.checks);S.event('CUT_RT_CASE_PASS',case=case['id'],bias=bias)
 pd.DataFrame(mapping).to_csv(ROOT/'PACKET_MAPPING.csv',index=False)
 for r in files:assert S.sha(r['path'])==r['sha256']
 write('GATE.json',dict(status='PASS',conditions=6,replay_cells=12,off_cells=12));S.event('COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
