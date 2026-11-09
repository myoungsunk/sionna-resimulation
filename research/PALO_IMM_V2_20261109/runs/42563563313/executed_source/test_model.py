"""Independent algebra and adversarial functional checks; no experiment labels."""
import unittest,numpy as np,math
from scipy.special import logsumexp
import imm_model_a as m
class Checks(unittest.TestCase):
    def setUp(self):self.rng=np.random.default_rng(20261109)
    def test_asymmetric_transition_orientation(self):
        T=np.array([[.97,.03],[.14,.86]]);mu=np.array([.1,.9]);xs=np.zeros((2,4));xs[1,0]=3;Ps=np.stack([np.eye(4),2*np.eye(4)])
        mx,P,lp,w=m.interact(xs,Ps,np.log(mu),T)
        self.assertTrue(np.allclose(np.exp(lp),mu@T,atol=1e-14))
        for j in range(2):self.assertTrue(np.allclose(w[:,j],mu*T[:,j]/(mu@T)[j]));self.assertAlmostEqual(mx[j,0],3*w[1,j])
    def test_covariance_independent_information_form(self):
        for _ in range(150):
            A=self.rng.normal(size=(4,4));P=A@A.T+.1*np.eye(4);x=self.rng.normal(size=4)*.01;H=self.rng.normal(size=4);R=float(np.exp(self.rng.normal()))
            y,C,d=m.gaussian(x,P,.2,.1,H,R);alt=np.linalg.inv(np.linalg.inv(P)+np.outer(H,H)/R)
            ax=x+alt@H*.1/R;ax[2]=m.wrap(ax[2]);self.assertLess(abs(C-alt).max(),1e-11);self.assertLess(abs(y-ax).max(),1e-11)
    def test_two_modes_never_deleted_and_return(self):
        def pred(x,P,c,k):return x.copy(),P+.001*np.eye(4)
        def obs(x):return 0.,np.zeros(4),False
        z=np.r_[np.ones(20)*.8,np.zeros(60)]
        r=m.run(z,{},np.zeros(4),.001*np.eye(4),pred,obs,np.array([[.97,.03],[.05,.95]]),[.5,.5],.16)
        self.assertEqual(r['mode_X'].shape,(80,2,4));self.assertLess(r['weights'][19,0],.05);self.assertGreater(r['weights'][-1,0],.5);self.assertGreater(r['weights'].min(),0)
    def test_circular_mean(self):
        x=np.zeros((2,4));x[:,2]=np.deg2rad([179,-179]);P=np.stack([.01*np.eye(4)]*2)
        mean,C,_=m.moments(x,P,[.5,.5]);self.assertLess(abs(abs(mean[2])-math.pi),1e-12);self.assertLess(C[2,2],.011)
    def test_same_states_no_artificial_spread(self):
        x=self.rng.normal(size=4);P=np.eye(4);_,C,_=m.moments(np.stack([x,x]),np.stack([P,P]),[.001,.999]);self.assertLess(abs(C-P).max(),1e-12)
    def test_log_normalization_extreme(self):
        for l in (np.array([-1e6,-1e6-1000]),np.array([-1e4,-.1])):self.assertAlmostEqual(np.exp(l-logsumexp(l)).sum(),1)
    def test_invalid_inputs(self):
        x=np.zeros((2,4));P=np.stack([np.eye(4)]*2)
        with self.assertRaises(ValueError):m.interact(x,P,np.log([.5,.5]),np.array([[.9,.1],[.8,.3]]))
        with self.assertRaises(ValueError):m.moments(x,P,[1,1])
    def test_one_step_matches_full_enumeration(self):
        xs=np.array([[.1,.2,0.,0.],[.8,-.1,0.,0.]]);Ps=np.stack([np.eye(4)*.2,np.eye(4)*.3]);mu=np.array([.3,.7]);T=np.array([[.8,.2],[.1,.9]])
        mx,CP,lp,W=m.interact(xs,Ps,np.log(mu),T)
        for j in range(2):
            den=sum(mu[i]*T[i,j] for i in range(2));w=[mu[i]*T[i,j]/den for i in range(2)];av=sum(w[i]*xs[i] for i in range(2));C=sum(w[i]*(Ps[i]+np.outer(xs[i]-av,xs[i]-av)) for i in range(2))
            self.assertLess(abs(av-mx[j]).max(),1e-12);self.assertLess(abs(C-CP[j]).max(),1e-12)
if __name__=='__main__':unittest.main()
