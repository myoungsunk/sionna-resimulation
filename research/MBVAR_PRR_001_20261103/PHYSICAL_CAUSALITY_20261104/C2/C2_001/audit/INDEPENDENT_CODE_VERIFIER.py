import os,sys,json,copy,hashlib
from pathlib import Path
from unittest.mock import patch
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
HERE=Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001')
sys.path.insert(0,str(HERE))
import numpy as np
import test_engine as T
import engine,evaluate,authority,launch,run
class Observer:
    def batch(self,x,spec,return_diagnostics=False):
        h=np.column_stack((x[:,0]+.2*x[:,1]+.1*np.sin(x[:,2]),.1*x[:,0]+.2*x[:,1]+.5*np.sin(x[:,2])))
        H=np.zeros((len(x),2,4));H[:,0,0]=1.;H[:,0,1]=.2;H[:,0,2]=.1*np.cos(x[:,2])
        H[:,1,0]=.1;H[:,1,1]=.2;H[:,1,2]=.5*np.cos(x[:,2])
        d=dict(tap=(x[:,0]>.6).astype(int),cells=np.repeat(np.floor(10*x[:,:3]),2,axis=1),fp_margin=np.ones(len(x)))
        return (h,H,d) if return_diagnostics else (h,H)
full,los,ctl,_,_=T.fixture(30)
model=Observer();core=T.core;online=T.online;spec=T.SPEC
tr=online.replay(full,ctl,'W0',core,model,spec)
tr.update(t=full['t'].copy(),pose_id=full['pose_id'].copy())
x=np.r_[ctl['x0'],0.];P=full['P0'].copy();xs=[];Ps=[]
for k,z in enumerate(full['z']):
    x,P=online.predict(core,x,P,k,ctl);h,H=model.batch(x[None],spec);h,H=h[0],H[0]
    v=z-h-full['muBASE'][k];S=H@P@H.T+full['R'][k]
    if v@np.linalg.solve(S,v)<=9.210340371976184:
        K=np.linalg.solve(S,H@P).T;x=x+K@v;x[2]=(x[2]+np.pi)%(2*np.pi)-np.pi
        M=np.eye(4)-K@H;P=M@P@M.T+K@full['R'][k]@K.T;P=(P+P.T)/2
    xs.append(x.copy());Ps.append(P.copy())
base=dict(BASE_x=np.array(xs),BASE_P=np.array(Ps))
windows=[dict(id='zero',first_index=0,last_index=2),dict(id='early',first_index=3,last_index=7),dict(id='late',first_index=8,last_index=10)]
out,stats=engine.run(core,online,model,spec,full,los,ctl,tr,base,windows)
maximum=0.;masks=0;comparisons=0
for w in windows:
    d=out[w['id']];start=w['first_index']
    for j,(mode,arm) in enumerate(engine.BRANCHES):
        packet={k:v.copy() for k,v in full.items()}
        sl=slice(start,w['last_index']+1)
        if arm in ('LF','LL'):packet['z'][sl,0]=los['z'][sl,0]
        if arm in ('FL','LL'):packet['z'][sl,1]=los['z'][sl,1]
        ref=online.replay(packet,ctl,'W0',core,model,spec,fixed_mask=tr['mask'] if mode=='fixed' else None)
        for key in ('x','P','prior','Pprior','h','H','K','nu','S'):
            a,b=d[key][:,j],ref[key][start:]
            maximum=max(maximum,float(np.abs(a-b).max()));comparisons+=a.size
            np.testing.assert_allclose(a,b,atol=1e-12,rtol=1e-12)
        for key,rkey in [('R','Rvar'),('rho','rho_before')]:
            np.testing.assert_allclose(d[key][:,j],ref[rkey][start:],atol=1e-12,rtol=1e-12)
        assert np.array_equal(d['mask'][:,j],ref['mask'][start:])
        masks+=int(np.sum(d['mask'][:,j]!=tr['mask'][start:]))
assert masks>0
for w in windows:
    d=out[w['id']];start=w['first_index']
    for i in range(len(d['t'])):
        for j in range(6):
            rho=np.linalg.norm(d['prior'][i,j,:2]-np.asarray(spec['anchor'][:2]))
            # Contract rho is before predict; check against previous posterior instead.
            previous=(tr['x'][start-1] if start else np.r_[ctl['x0'],0.]) if i==0 else d['x'][i-1,j]
            exact=np.linalg.norm(previous[:2]-np.asarray(spec['anchor'][:2]))
            np.testing.assert_allclose(d['rho'][i,j],exact,atol=1e-14,rtol=1e-14)
A=np.array([[1.,0.,0.,0.],[.3,1.,0.,0.],[.1,-.2,1.,0.],[0.,.1,.2,1.]])
P=A@A.T*.01;x=np.array([[[.1,-.2,np.pi+.03,.006]]]);truth=dict(truth=np.array([[0.,0.,-np.pi]]),bg=np.array(.001))
s=evaluate.score_states(x,P[None,None],truth)
err=np.array([.1,-.2,.03,.005])
np.testing.assert_allclose(s['NEES3'][0,0],err[:3]@np.linalg.inv(P[:3,:3])@err[:3],atol=1e-12)
np.testing.assert_allclose(s['NEES4'][0,0],err@np.linalg.inv(P)@err,atol=1e-12)
np.testing.assert_allclose(s['XY_mahalanobis2'][0,0],err[:2]@np.linalg.inv(P[:2,:2])@err[:2],atol=1e-12)
assert evaluate.integral(np.arange(11)*.2,np.arange(11)*.2,0.,0.,2.)==2.
plan=json.loads((HERE/'PLAN.json').read_bytes())
bindings={name:authority.sha(HERE/name) for name in authority.BOUND}
good=dict(schema='C2_GO_V1',decision='GO',authorized=authority.authorization(plan,'dev'),bindings_sha256=bindings)
original=Path.read_bytes
def check_with(go):
    def reading(path):
        return json.dumps(go).encode() if path==HERE/'GO_DEV.json' else original(path)
    with patch.object(Path,'read_bytes',reading):
        return authority.check('dev')
assert check_with(good)[0]==plan
negative=0
for kind in ('phase','code','schema'):
    bad=copy.deepcopy(good)
    if kind=='phase':bad['authorized']['seeds']=[11]
    elif kind=='code':bad['bindings_sha256']['engine.py']='0'*64
    else:bad['schema']='SM0_GO_V1'
    try:check_with(bad)
    except ValueError:negative+=1
    else:raise AssertionError('bad authorization accepted '+kind)
with patch.object(launch,'check',return_value=(plan,plan['phases']['dev'],good,bindings)),patch.object(launch,'committed_revision',side_effect=ValueError('published bytes mismatch')),patch.object(launch.subprocess,'Popen') as popen,patch.object(sys,'argv',['launch.py','dev']):
    try:launch.main()
    except ValueError:pass
    else:raise AssertionError('publication mismatch accepted')
    assert not popen.called;negative+=1
rt=run.runtime(plan)
result=dict(decision='PASS',synthetic_trajectory_branches=18,scalar_reference_numeric_elements=comparisons,
    max_abs_reference_difference=maximum,gate_flips_vs_Full=masks,negative_authority_prelaunch_checks=negative,
    correlated_NEES_checks=3,runtime=rt,real_RF_model_initializations=0,science_input_packet_reads=0,files_written=0)
print('C2_INDEPENDENT_SYNTHETIC_RESULT '+json.dumps(result,sort_keys=True))
