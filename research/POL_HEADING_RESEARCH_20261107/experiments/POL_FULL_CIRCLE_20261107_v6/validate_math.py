import model as m
import numpy as np,json
from scipy.integrate import quad
from scipy.stats import norm
p=json.loads((m.BASE/'CALIBRATION.json').read_text(encoding='utf-8'))['parameters']
# Independent numerical integration of the canonical forward LUT.
d=m.e.data('los');errors=[]
for k in [0,150,266,700]:
 x=np.r_[d['truth_for_offline_scoring_only'][k],0.];z=d['z_s'][k];tau=p['sigma_angle_rad'];lo,hi,*_=m.segments(x[None,:],9*tau)
 def integrand(delta):
  q=x.copy();q[2]=m.e.wrap(q[2]+delta);h=m.old.model(q[None,:])[0][0]
  return norm.pdf(delta,scale=tau)*norm.pdf(z,loc=h,scale=np.sqrt(p['residual_variance']))
 ref=sum(quad(integrand,a,b,epsabs=1e-10,epsrel=1e-9)[0] for a,b in zip(lo[0],hi[0]) if b>a)
 ref=(1-p['outlier_probability'])*ref+p['outlier_probability']/2
 ll,*_=m.integrated(x[None,:],z,np.zeros((3,3)),p);errors.append(abs(np.exp(ll[0])/ref-1))
assert max(errors)<1e-7
lo=np.array([[-.2]]);hi=np.array([[.3]]);mid=(lo+hi)/2;H=np.zeros((1,1,4));H[:,:,2]=2
ll,*_=m.interval_terms(lo,hi,mid,np.array([[.1]]),H,np.array([.15]),.03,np.zeros((3,3)),.12)
ref=quad(lambda q:norm.pdf(q,scale=.12)*norm.pdf(.15,loc=.1+2*(q-.05),scale=np.sqrt(.03)),-.2,.3,epsabs=1e-12)[0]
err=float(abs(np.exp(ll[0,0])-ref));assert err<1e-10
m.dump('MATH_VALIDATION.json',dict(status='PASS',canonical_integral_relative_errors=errors,linear_integral_absolute_error=err,note='Supersedes placeholder linear_integral_error=0 in TESTS.json; self-check, not independent audit.'))
print('PASS',errors,err)
