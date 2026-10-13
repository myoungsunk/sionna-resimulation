import json,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repair_short_range import *
H=Path(__file__).resolve().parents[1]
def model():
 root=H/'out/i2_s0_run_01/A2_3_GAUSS_LEVEL_R2_d2_s8000'
 with np.load(root/'RANGE_0.05_5_public.npz') as f:p={k:f[k][:2] for k in f.files}
 c=json.loads((root/'RANGE_0.05_5_config.json').read_text());return IndependentOneStep(p,c),S0BatchTarget(p,c,'RANGE')
def test_independent_density():
 m,t=model();x=m.prior_draw(np.random.default_rng(6).uniform(size=(100,7)))
 a=m.full(x);b=np.array([production_full(t,v) for v in x]);assert np.max(abs(a-b))<1e-8
 assert not t.mask[0] and t.range_count==1

def test_radial_inverse():
 m,t=model();u=np.linspace(.0001,.9999,1001);a=m.radial_inverse(u);b=np.interp(u,t.table.cdf,t.table.grid);assert max(abs(a-b))<1e-5
 assert t.table.diagnostics['numerical_tail_mass_bound']<1e-12

def test_proposal_balance_and_jacobian():
 m,t=model();x,y=draw_proposal(t,np.random.default_rng(8),2);lx,ly=production_full(t,x),production_full(t,y);qx,qy=proposal_log(t,x),proposal_log(t,y);lr=mh_log_ratio(ly,lx,qx,qy)
 # pi(x) q(y|x) alpha(x,y) equals reverse flux in log units.
 assert abs(lx+qy+min(0,lr)-(ly+qx+min(0,-lr)))<1e-10
 correction=lambda a:float(t.table.logpdf(a[0])-radial_proposal_log(t.table.grid,t.table.cdf,a[0]))
 assert abs(lr-(t.evaluate(y[:5],y[5:].reshape(2,1))-t.evaluate(x[:5],x[5:].reshape(2,1))+correction(y)-correction(x)))<1e-10
 z=x[:5].copy();z[0]=np.log(x[0]);assert abs(log_rho_density(t,z,x[5:].reshape(2,1))-(lx+z[0]))<1e-10

def test_diagnostics_detect_stuck_chains():
 x=np.random.default_rng(4).normal(size=(4,1000,7));x[:,:,0]=np.abs(x[:,:,0])+1;assert diagnostics(x)['passes']
 x[0,:,2]+=10;assert not diagnostics(x)['passes']

def test_ess_ar1_and_zero():
 rng=np.random.default_rng(9);a=np.zeros((4,16000))
 for i in range(1,a.shape[1]):a[:,i]=.8*a[:,i-1]+rng.normal(size=4)
 expected=a.size*(1-.8)/(1+.8);assert .65*expected<ess1(a)<1.4*expected
 assert ess1(np.ones((4,100)))==0

def test_constant_diagnostics_fail_closed():
 assert not diagnostics(np.ones((4,1000,7)))['passes']

def test_batch_mcse_finite():
 s=batch_mcse(np.random.default_rng(4).normal(size=(8000,7)));assert np.all(np.array(s['mean'])>0)


def test_actual_piecewise_inverse_density():
 grid=np.array([0.,1.,3.]);cdf=np.array([0.,.25,1.]);assert np.allclose(np.exp(radial_proposal_log(grid,cdf,np.array([.3,2.]))),[.25,.375])
 assert not np.isclose(radial_proposal_log(grid,cdf,.3),radial_proposal_log(grid,cdf,2.))

def test_invalid_support_zero_density():
 m,t=model();x=draw_proposal(t,np.random.default_rng(18),1);x[0,3]=-2/m.std[1];assert np.isneginf(m.full(x)[0]);assert np.isneginf(production_full(t,x[0]))
