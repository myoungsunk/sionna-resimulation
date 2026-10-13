import sys
from pathlib import Path
import numpy as np
from scipy.special import log_ndtr
sys.path.insert(0,str(Path(__file__).parents[1]))
from repair_r1_tail_v2 import tail_certificate
from repair_r1_dr import DRReference
from test_repair_r1_dr import inputs

def test_interval_lower_and_upper_against_density_points():
    p,c=inputs();center=np.array([.1,-.2,.3]);r=tail_certificate(p,c,center,10)
    ref=DRReference(p,c);vol=(2e-4)**3
    for z in center+np.random.default_rng(10).uniform(-1e-4,1e-4,(100,3)):
        assert r['log_evidence_lower_bound']<=ref.direct_logdensity(z)+np.log(vol)
        ll=ref.direct_logdensity(z)+.5*(z@z+3*np.log(2*np.pi))
        assert ll<=r['log_likelihood_upper_bound']
    assert 0 < r['posterior_tail_upper_bound'] < 1

def test_mills_union_bound_and_precision():
    p,c=inputs();a=tail_certificate(p,c,[0,0,0],10,digits=30);b=tail_certificate(p,c,[0,0,0],10,digits=50)
    assert abs(a['log_posterior_tail_upper_bound']-b['log_posterior_tail_upper_bound'])<1e-10
    mills=np.log(4)-50-np.log(10)-.5*np.log(2*np.pi)
    assert mills>=np.log(4)+log_ndtr(-10)

