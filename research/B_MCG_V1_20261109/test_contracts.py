import unittest,copy,json
from dataclasses import replace
import numpy as np
from numerics import OnlineSeries,update,effective_R,wrap,paths
from monitor import Monitor,MonitorConfig,weights

class ToyCore:
    @staticmethod
    def transition(x,ds,gy,dt):
        x=x.copy();a=gy-x[3]*dt;phi=x[2]+a/2
        dx=ds*np.array([np.cos(phi),np.sin(phi)])
        y=x.copy();y[:2]+=dx;y[2]=wrap(y[2]+a)
        F=np.eye(4);F[:2,2]=[-dx[1],dx[0]];F[:2,3]=F[:2,2]*(-dt/2);F[2,3]=-dt
        return y,F,np.zeros((4,3))
class ToyModel:
    def batch(self,q,spec,gradient=True):
        h=np.column_stack([q[:,0],q[:,2]+.1*q[:,1]])
        H=np.zeros((len(q),2,4));H[:,0,0]=1;H[:,1,1]=.1;H[:,1,2]=1
        return h,H if gradient else None

def toy(n=26,offset=0.):
    t=np.arange(n)*.2;ds=np.zeros(n);gy=np.zeros(n);dt=np.r_[0,np.diff(t)]
    z=np.column_stack([np.ones(n),np.full(n,offset)])
    s=OnlineSeries(t,ds,gy,dt,z,np.zeros((n,2)),np.tile(np.diag([.01**2,.01**2]),(n,1,1)),np.array([1.,0.,0.,0.]),np.diag([.01,.01,.05,.00001]),np.zeros((n,2)))
    pri=np.tile(s.x0,(n,1));P=np.tile(s.P0,(n,1,1))
    return s,pri,P

class Contracts(unittest.TestCase):
    def test_beta_covariance_and_no_mutation(self):
        rng=np.random.default_rng(42)
        for j in range(80):
            A=rng.normal(size=(4,4));P=A@A.T+.1*np.eye(4);x=rng.normal(size=4);H=rng.normal(size=(2,4));v=rng.normal(size=2)
            B=rng.normal(size=(2,2));R=B@B.T+.1*np.eye(2)
            copies=[a.copy() for a in [P,x,H,v,R]]
            y,C,K,_=update(x,P,H,v,R,True)
            for beta in [(.25,1),(1,.25),(0,1),(1,0),(0,0)]:
                yy,CC,KK,ids=update(x,P,H,v,R,True,beta)
                self.assertGreater(np.linalg.eigvalsh(CC-C).min(),-1e-10)
                self.assertTrue(np.allclose(CC,CC.T))
                self.assertGreater(np.linalg.eigvalsh(CC).min(),-1e-10)
            for a,b in zip(copies,[P,x,H,v,R]):self.assertTrue(np.array_equal(a,b))
    def test_skip_and_reject(self):
        x=np.arange(4.);P=np.eye(4);H=np.ones((2,4));R=np.eye(2)
        for beta,allow in [((0,0),True),((1,1),False)]:
            y,C,K,_=update(x,P,H,np.ones(2),R,allow,beta)
            self.assertTrue(np.array_equal(x,y));self.assertTrue(np.array_equal(P,C));self.assertFalse(K.any())
    def test_invalid_beta(self):
        for b in [(-1,1),(2,1),(np.nan,1)]:
            with self.assertRaises(ValueError):effective_R(np.eye(2),b)
    def test_no_calibration_no_active(self):
        with self.assertRaises(ValueError):weights([1,1,1],[True,True],None)
    def test_unknown_is_not_clean(self):
        self.assertTrue(np.array_equal(weights([99,99,99],[False,False],2),[1,1]))
    def test_online_allowlist(self):
        s,_,_=toy()
        with self.assertRaises(TypeError):OnlineSeries(**s.__dict__,truth=np.zeros((len(s.t),3)))
    def test_timestamps(self):
        s,_,_=toy();t=s.t.copy();t[2]=t[1]
        with self.assertRaises(ValueError):replace(s,t=t)
    def test_current_future_exclusion(self):
        s,p,P=toy();z=s.z.copy();z[20:,1]=10.
        a=Monitor(ToyCore(),ToyModel(),s,np.array([.2,.2,.5,.01]),MonitorConfig(max_nfev=40))
        b=Monitor(ToyCore(),ToyModel(),replace(s,z=z),np.array([.2,.2,.5,.01]),MonitorConfig(max_nfev=40))
        aa=a.assess(20,p,P);bb=b.assess(20,p,P)
        self.assertEqual(aa['support_end'],19);self.assertEqual(aa['support_hash'],bb['support_hash'])
        self.assertTrue(np.allclose(a.profile.candidates,b.profile.candidates))
        self.assertGreater(bb['score'][1],aa['score'][1]+100)
    def test_rigid_alignment_keeps_correction(self):
        s,p,P=toy(offset=.15)
        m=Monitor(ToyCore(),ToyModel(),s,np.array([.2,.2,.5,.01]),MonitorConfig(max_nfev=40))
        a=m.assess(20,p,P)
        self.assertLess(a['score'][1],.1)
        self.assertGreater(abs(a['theta'][2]),.05)
    def test_history_poisoning_counterexample(self):
        s,p,P=toy(offset=.15);z=s.z.copy();z[20:,1]=0.
        m=Monitor(ToyCore(),ToyModel(),replace(s,z=z),np.array([.2,.2,.5,.01]),MonitorConfig(max_nfev=40))
        a=m.assess(20,p,P)
        self.assertGreater(a['score'][1],5.)
        # Expected structural failure: good target looks inconsistent with bad history.
    def test_coherent_bias_blind_spot(self):
        s,p,P=toy(offset=.15);m=Monitor(ToyCore(),ToyModel(),s,np.array([.2,.2,.5,.01]),MonitorConfig(max_nfev=40))
        a=m.assess(20,p,P)
        self.assertLess(a['score'][1],.1)
        # Compatibility is explicitly not truth/reliability certification.
    def test_relative_motion_and_wrap(self):
        x=np.array([0.,0.,np.pi-.01,0.]);q,_=paths(ToyCore(),x,[0,0],[0,.03],[0,.2],0,1)
        self.assertLess(q[-1,2],-3.)
    def test_window_never_future(self):
        s,p,P=toy();m=Monitor(ToyCore(),ToyModel(),s,np.array([.2,.2,.5,.01]))
        a=m.assess(15,p,P);self.assertLess(a['support_end'],15)
        with self.assertRaises(ValueError):m.assess(15,p,P)

if __name__=='__main__':unittest.main(verbosity=2)
