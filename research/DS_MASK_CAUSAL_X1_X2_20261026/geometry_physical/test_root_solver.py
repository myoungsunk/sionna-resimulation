from run_a import equivalent
from common import np,check,write
class Mock:
 def batch(self,x,case,gradient=False):
  angle=x[:,2];kind=x[:,1].astype(int);h=np.zeros((len(x),2));J=np.zeros((len(x),2,4))
  for k in range(len(x)):
   if kind[k]==0:h[k,1]=np.sin(angle[k]+np.radians(x[k,0]));J[k,1,2]=np.cos(angle[k]+np.radians(x[k,0]))
   elif kind[k]==1:h[k,1]=1.;J[k,1,2]=0.
   elif kind[k]==2:h[k,1]=1e-5*angle[k];J[k,1,2]=1e-5
   elif kind[k]==3:h[k,1]=-1 if angle[k]<np.radians(.71) else 1;J[k,1,2]=0
   else:h[k,1]=(angle[k]-np.radians(1.2))*(angle[k]+np.radians(1.8));J[k,1,2]=2*angle[k]+np.radians(.6)
  return h,J if gradient else None
x=np.zeros((6,4));x[:,0]=[2.3,-3.7,0,0,0,0];x[:,1]=[0,0,1,2,3,4]
a,res,sl,why=equivalent(Mock(),dict(id='UNIT_ROOT'),x,np.zeros(6),np.zeros(6))
check('root_known',a[[0,1,5]],[-2.3,3.7,1.2],1e-6)
assert np.isnan(a[2:5]).all();assert why[2]=='NO_ROOT' and why[3]=='LOW_SLOPE' and why[4]=='NO_ROOT'
write('ROOT_SOLVER_TEST.json',dict(status='PASS',roots=[float(v) if np.isfinite(v) else None for v in a],reasons=why.tolist()))
print('Root solver test PASS: nearest root, no root, low slope, discontinuity')
