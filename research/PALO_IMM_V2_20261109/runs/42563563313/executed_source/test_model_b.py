"""Adversarial revised-model tests, including exact white-noise nesting."""
import unittest,numpy as np
import imm_model_a as A
import imm_model_b as B
class RevisedChecks(unittest.TestCase):
    def setUp(self):self.rng=np.random.default_rng(901109)
    def test_white_limit_matches_original_v2a(self):
        z=self.rng.normal(0,.15,50);H=np.array([.1,-.05,.6,0.])
        def obs(x):return H@x,H,False
        def pred(x,P,c,k):return x.copy(),P+(np.eye(4)*1e-6 if k else 0)
        for kind in ('imm','collapse'):
            args=(z,{},np.zeros(4),np.eye(4)*.01,pred,obs,np.array([[.97,.03],[.12,.88]]),[.8,.2],.14)
            a=A.run(*args,kind=kind);b=B.run(*args,kind=kind,rho=0,jacobian=lambda x,c,k:np.eye(4))
            self.assertLess(abs(a['X']-b['X'][:,:4]).max(),1e-11)
            self.assertLess(abs(a['P']-b['P'][:,:4,:4]).max(),1e-11)
            self.assertLess(abs(a['weights']-b['weights']).max(),1e-11)
    def test_mode_reset_is_no_physical_information(self):
        A0=self.rng.normal(size=(5,5));P=A0@A0.T+.01*np.eye(5);x=self.rng.normal(size=5)
        y,V=B.predict5(x,P,{},0,0,.9,.2,lambda x,P,c,k:(x,P))
        self.assertTrue(np.array_equal(y[:4],x[:4]));self.assertTrue(np.array_equal(V[:4,:4],P[:4,:4]));self.assertTrue(np.all(V[:4,4]==0));self.assertEqual(y[4],0)
    def test_covariance_stationary_and_cross(self):
        P=np.eye(5);P[0,4]=P[4,0]=.1;x=np.zeros(5);c={'ds_odom':np.zeros(2),'dtheta_gyro':np.zeros(2),'dt_s':np.ones(2)*.2}
        y,V=B.predict5(x,P,c,1,1,.9,1.,lambda x,P,c,k:(x,P),jacobian=lambda x,c,k:np.eye(4))
        self.assertAlmostEqual(V[4,4],1);self.assertAlmostEqual(V[0,4],.09);self.assertGreater(np.linalg.eigvalsh(V).min(),0)
    def test_motion_jacobian_finite_difference(self):
        def motion(x,c,k):
            ds=c['ds_odom'][k];dt=c['dt_s'][k];a=c['dtheta_gyro'][k]-x[3]*dt;v=np.sinc(a/(2*np.pi));y=x.copy();ph=x[2]+a/2;y[:2]+=ds*v*np.array([np.cos(ph),np.sin(ph)]);y[2]+=a;return y
        for _ in range(50):
            x=self.rng.normal(size=4)*.1;c={'ds_odom':np.array([0,.04]),'dt_s':np.array([0,.2]),'dtheta_gyro':np.array([0,self.rng.normal()*.01])}
            F=B.motion_F(x,c,1);num=np.column_stack([(motion(x+np.eye(4)[j]*1e-6,c,1)-motion(x-np.eye(4)[j]*1e-6,c,1))/2e-6 for j in range(4)])
            self.assertLess(abs(F-num).max(),1e-8)
    def test_persistent_offset_covariance_remains_valid(self):
        N=80;z=np.r_[np.zeros(20),np.full(40,.3),np.zeros(20)];c={'ds_odom':np.zeros(N),'dtheta_gyro':np.zeros(N),'dt_s':np.ones(N)*.2}
        H=np.array([0,0,1.,0]);obs=lambda x:(x[2],H,False);pred=lambda x,P,c,k:(x.copy(),P+1e-6*np.eye(4))
        a=B.run(z,c,np.zeros(4),np.eye(4)*.001,pred,obs,np.array([[.97,.03],[.12,.88]]),[.8,.2],.14,rho=.97,jacobian=lambda x,c,k:np.eye(4))
        self.assertTrue(np.isfinite(a['X']).all());self.assertGreater(np.linalg.eigvalsh(a['mode_P']).min(),0);self.assertTrue(np.allclose(a['weights'].sum(1),1));self.assertTrue(np.all(a['prior_P'][:,0,:4,4]==0))
if __name__=='__main__':unittest.main()
