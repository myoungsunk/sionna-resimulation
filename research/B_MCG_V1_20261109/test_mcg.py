"""Independent algebra/API tests. Synthetic RF is NOT the SourceFFD model.

These tests certify numerical and causal implementation contracts, not usefulness
on R2/R4/R5. Test failures are not silently converted into scientific PASS.
"""
import copy
import inspect
import unittest
import numpy as np

from mcg import Config, Monitor, covariance_update, motion_path, profile_history, score_current, weights, wrap


class SyntheticCore:
    """Known midpoint body-frame motion with analytical transition Jacobian."""
    @staticmethod
    def transition(x, ds, gy, dt):
        x=np.asarray(x,float)
        delta=gy-x[3]*dt
        mid=x[2]+delta/2
        c,s=np.cos(mid),np.sin(mid)
        y=x.copy()
        y[:2]+=ds*np.array([c,s]);y[2]=wrap(x[2]+delta)
        F=np.eye(4)
        F[0,2]=-ds*s;F[1,2]=ds*c
        F[0,3]=ds*s*dt/2;F[1,3]=-ds*c*dt/2;F[2,3]=-dt
        return y,F,np.zeros((4,3))


class SyntheticRF:
    """Smooth range + bounded polarization-like scalar, never called SourceFFD."""
    @staticmethod
    def batch(x,spec=None,gradient=True):
        x=np.asarray(x,float)
        p=x[:,:2]-np.array([1.,-2.]);yaw=x[:,2]
        r=np.sqrt(np.sum(p*p,axis=1)+.7**2)
        a=.4*x[:,0]-.25*x[:,1]+.9*np.sin(yaw)
        s=np.tanh(a)+.1*np.cos(2*yaw)
        h=np.column_stack([r,s])
        if not gradient:return h,None
        H=np.zeros((len(x),2,4));H[:,0,:2]=p/r[:,None]
        d=1-np.tanh(a)**2
        H[:,1,0]=.4*d;H[:,1,1]=-.25*d
        H[:,1,2]=.9*np.cos(yaw)*d-.2*np.sin(2*yaw)
        return h,H


def fixture(n=16):
    t=np.arange(n)*.2
    controls=np.column_stack([np.full(n,.04),np.full(n,.025),np.full(n,.2)])
    controls[0]=[0,0,0]
    anchor=np.array([2.,1.,.35,.002])
    q,_=motion_path(SyntheticCore,anchor,controls)
    z,_=SyntheticRF.batch(q)
    mu=np.zeros((n,2));R=np.tile(np.diag([.04**2,.025**2]),(n,1,1))
    return anchor,controls,t,q,z,mu,R


class CovarianceAdapterTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(901)
        a=rng.normal(size=(4,4));self.P=a@a.T*.07+np.eye(4)*.03
        self.x=np.array([.2,-.3,3.13,.01]);self.H=rng.normal(size=(2,4))
        self.nu=np.array([.35,-.15]);self.R=np.array([[.08,.024],[.024,.05]])

    def independent(self,beta,permitted=True):
        rows=np.flatnonzero(np.array(beta)>0) if permitted else np.array([],int)
        r=self.R.copy()
        for j,b in enumerate(beta):
            if b>0:r[j,j]+=self.R[j,j]*(1/b-1)
        k=np.zeros((4,2));x=self.x.copy();p=self.P.copy()
        if len(rows):
            h=self.H[rows,:];rr=r[np.ix_(rows,rows)]
            kk=self.P@h.T@np.linalg.inv(h@self.P@h.T+rr)
            k[:,rows]=kk;x=x+kk@self.nu[rows];x[2]=(x[2]+np.pi)%(2*np.pi)-np.pi
            a=np.eye(4)-kk@h;p=a@self.P@a.T+kk@rr@kk.T
        return x,p,k,r,rows

    def test_full_partial_and_skip_against_independent_joseph(self):
        for beta in [(1.,1.),(.25,.7),(0.,1.),(1.,0.),(0.,.2),(0.,0.)]:
            with self.subTest(beta=beta):
                actual=covariance_update(self.x,self.P,self.H,self.nu,self.R,beta)
                expected=self.independent(beta)
                for a,b in zip(actual,expected):np.testing.assert_allclose(a,b,rtol=2e-13,atol=2e-14)

    def test_inputs_are_not_mutated(self):
        args=[self.x,self.P,self.H,self.nu,self.R,np.array([.3,0.])]
        originals=[a.copy() for a in args]
        covariance_update(*args)
        for a,b in zip(args,originals):np.testing.assert_array_equal(a,b)

    def test_legacy_rejection_preserves_prior_and_covariance(self):
        x,p,k,r,rows=covariance_update(self.x,self.P,self.H,self.nu,self.R,(.2,.4),False)
        np.testing.assert_array_equal(x,self.x);np.testing.assert_array_equal(p,self.P)
        np.testing.assert_array_equal(k,np.zeros((4,2)));self.assertEqual(len(rows),0)

    def test_psd_addition_and_same_prior_covariance_order(self):
        full=covariance_update(self.x,self.P,self.H,self.nu,self.R)[1]
        for beta in [(.01,1.),(1.,.1),(.3,.7),(0.,1.),(1.,0.),(0.,0.)]:
            _,p,_,re,_=covariance_update(self.x,self.P,self.H,self.nu,self.R,beta)
            self.assertGreaterEqual(np.linalg.eigvalsh(p-full).min(),-1e-12)
            self.assertGreaterEqual(np.linalg.eigvalsh(self.P-p).min(),-1e-12)
            self.assertGreaterEqual(np.linalg.eigvalsh(re-self.R).min(),-1e-12)
            self.assertGreaterEqual(np.linalg.eigvalsh(p).min(),-1e-12)
            self.assertEqual(re[0,1],self.R[0,1])

    def test_drop_channel_is_not_zeroing_full_gain(self):
        full=covariance_update(self.x,self.P,self.H,self.nu,self.R)[2]
        dropped=covariance_update(self.x,self.P,self.H,self.nu,self.R,(1.,0.))[2]
        self.assertGreater(np.linalg.norm(full[:,0]-dropped[:,0]),1e-6)

    def test_invalid_inputs_fail_before_update(self):
        badR=self.R.copy();badR[0,0]=-1
        for args in [
            (self.x,self.P,self.H,self.nu,badR),
            (self.x,self.P,self.H,np.array([np.nan,0.]),self.R),
            (self.x,self.P,self.H,self.nu,self.R,(-.1,1.)),
            (self.x,self.P,self.H,self.nu,self.R,(1.,1.1)),
        ]:
            with self.assertRaises(ValueError):covariance_update(*args)


class MotionTests(unittest.TestCase):
    def test_anchor_increment_is_not_applied_twice(self):
        anchor=np.array([1.,2.,.4,.01]);controls=np.array([[9.,9.,9.],[.2,.07,.2]])
        q,_=motion_path(SyntheticCore,anchor,controls)
        expected=SyntheticCore.transition(anchor,.2,.07,.2)[0]
        np.testing.assert_array_equal(q[0],anchor);np.testing.assert_allclose(q[1],expected)

    def test_global_yaw_rotates_relative_positions(self):
        anchor,controls,_,q,*_=fixture()
        delta=.8;shift=np.array([-.5,.3]);changed=anchor.copy()
        changed[:2]+=shift;changed[2]+=delta
        qq,_=motion_path(SyntheticCore,changed,controls)
        rot=np.array([[np.cos(delta),-np.sin(delta)],[np.sin(delta),np.cos(delta)]])
        expected=(q[:,:2]-anchor[:2])@rot.T+changed[:2]
        np.testing.assert_allclose(qq[:,:2],expected,atol=1e-14)
        np.testing.assert_allclose(wrap(qq[:,2]-q[:,2]),delta,atol=1e-14)

    def test_wrap_and_constant_bias_are_cumulative(self):
        anchor=np.array([0.,0.,np.pi-.01,.02]);controls=np.tile([0.,.03,.2],(8,1));controls[0]=0
        q,_=motion_path(SyntheticCore,anchor,controls)
        expected=wrap(anchor[2]+np.arange(8)*(.03-.02*.2))
        np.testing.assert_allclose(q[:,2],expected,atol=1e-14)
        self.assertTrue(np.all(q[:,2]>=-np.pi));self.assertTrue(np.all(q[:,2]<np.pi))

    def test_motion_anchor_and_controls_not_mutated(self):
        anchor,controls,*_=fixture();a=anchor.copy();c=controls.copy()
        motion_path(SyntheticCore,anchor,controls)
        np.testing.assert_array_equal(anchor,a);np.testing.assert_array_equal(controls,c)


class CausalityAndProfileTests(unittest.TestCase):
    def test_synthetic_observer_jacobian_matches_finite_difference(self):
        _,_,_,q,*_=fixture();h,H=SyntheticRF.batch(q)
        for j in range(4):
            plus=q.copy();minus=q.copy();plus[:,j]+=1e-6;minus[:,j]-=1e-6
            diff=(SyntheticRF.batch(plus,gradient=False)[0]-SyntheticRF.batch(minus,gradient=False)[0])/2e-6
            np.testing.assert_allclose(H[:,:,j],diff,atol=1e-8)

    def monitor_pair(self,last_delta=(0.,0.)):
        anchor,controls,t,q,z,mu,R=fixture()
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        for k in range(len(t)):
            zz=z[k].copy()
            if k==len(t)-1:zz+=last_delta
            sc,p=m.observe(k,t[k],q[k],controls[k],zz,mu[k],R[k])
        return m,sc,p

    def test_current_target_is_not_in_profile_fit(self):
        _,s0,p0=self.monitor_pair()
        _,s1,p1=self.monitor_pair((.5,-.4))
        for key in ['candidate_h','theta','singular_values','valid_channels','target_span_sigma']:
            np.testing.assert_allclose(p0[key],p1[key],equal_nan=True,atol=0,rtol=0)
        self.assertEqual(p0['profile_cost'],p1['profile_cost'])
        self.assertGreater(np.linalg.norm(s0['scores']-s1['scores']),1.)

    def test_future_and_caller_mutations_do_not_rewrite_history(self):
        anchor,controls,t,q,z,mu,R=fixture()
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        args=[q[0].copy(),controls[0].copy(),z[0].copy(),mu[0].copy(),R[0].copy()]
        m.observe(0,t[0],*args);saved=copy.deepcopy(m.records[0])
        for a in args:a[...] +=10
        for key in ['prior','controls','z','mu','R']:np.testing.assert_array_equal(m.records[0][key],saved[key])
        self.assertFalse(m.records[0]['prior'].flags.writeable)
        m.observe(1,t[1],q[1],controls[1],z[1]+50,mu[1],R[1])
        for key in ['prior','controls','z','mu','R']:np.testing.assert_array_equal(m.records[0][key],saved[key])

    def test_raw_history_keeps_every_packet_regardless_of_external_gate(self):
        m,_,p=self.monitor_pair()
        self.assertEqual(len(m.records),16);self.assertEqual(p['history_n'],15)
        self.assertEqual(p['history_end'],14);self.assertEqual(p['current_index'],15)
        self.assertNotIn('accepted',inspect.signature(Monitor.observe).parameters)

    def test_runtime_interfaces_have_no_truth_or_route_feature(self):
        forbidden={'truth','ground_truth','clean','route','evaluator','e_s_mp','true_yaw','clean_cir'}
        for fun in [Monitor.observe,profile_history,score_current,weights]:
            self.assertFalse(forbidden&set(inspect.signature(fun).parameters))
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        with self.assertRaises(TypeError):m.observe(0,0,np.zeros(4),np.zeros(3),np.zeros(2),np.zeros(2),np.eye(2),truth=np.zeros(3))

    def test_joint_conflict_cannot_be_hidden_by_separate_minima(self):
        profile={'candidate_h':np.array([[0.,2.],[2.,0.]]),'scale':np.ones(2),
                 'Rmon_target':np.eye(2),'status':'PROFILE_READY','reason':'TEST','valid_channels':np.ones(2,bool)}
        s=score_current(profile,np.zeros(2),np.zeros(2))
        np.testing.assert_array_equal(s['scores'][:2],np.zeros(2));self.assertEqual(s['scores'][2],2.)
        b,status=weights(s,Config(tau_r=1.,tau_s=1.,tau_joint=1.))
        self.assertEqual(status,'CONFLICT_JOINT_UNRESOLVED');self.assertTrue(np.all(b<1))

    def test_weighting_does_not_mutate_preinflation_score(self):
        _,score,_=self.monitor_pair((1.,1.));saved=copy.deepcopy(score)
        weights(score,Config())
        for k in ('scores','valid_channels'):np.testing.assert_array_equal(score[k],saved[k])

    def test_no_valid_profile_does_not_become_clean_assertion(self):
        score={'status':'UNKNOWN','reason':'TARGET_PROFILE_TOO_BROAD','valid_channels':np.zeros(2,bool),'scores':np.zeros(3)}
        b,status=weights(score,Config());np.testing.assert_array_equal(b,np.ones(2));self.assertEqual(status,'UNKNOWN')

    def test_nonmonotone_timestamp_is_rejected_before_recording(self):
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        args=(np.zeros(4),np.zeros(3),np.zeros(2),np.zeros(2),np.eye(2))
        m.observe(0,1.,*args)
        with self.assertRaises(ValueError):m.observe(1,.9,*args)
        self.assertEqual(len(m.records),1)

    def test_nonfinite_timestamp_is_rejected_before_recording(self):
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        args=(np.zeros(4),np.zeros(3),np.zeros(2),np.zeros(2),np.eye(2))
        with self.assertRaises(ValueError):m.observe(0,float('nan'),*args)
        self.assertEqual(len(m.records),0)

    def test_history_single_row_is_explicit_warmup(self):
        a,c,t,q,z,mu,R=fixture(1)
        p=profile_history(SyntheticCore,SyntheticRF,None,a,c,t,z[:0],mu[:0],R,Config())
        self.assertEqual(p['status'],'WARMUP');self.assertEqual(len(p['candidate_h']),0)

    def test_control_dt_must_equal_timestamp_difference(self):
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        m.observe(0,0,np.zeros(4),np.zeros(3),np.zeros(2),np.zeros(2),np.eye(2))
        with self.assertRaises(ValueError):
            m.observe(1,.2,np.zeros(4),np.array([.1,.02,.1]),np.zeros(2),np.zeros(2),np.eye(2))
        self.assertEqual(len(m.records),1)

    def test_invalid_rf_is_retained_as_invalid_without_profile_fit(self):
        m=Monitor(SyntheticCore,SyntheticRF,None,Config())
        s,p=m.observe(0,0,np.zeros(4),np.zeros(3),np.array([np.nan,0.]),np.zeros(2),np.eye(2))
        self.assertEqual(s['status'],'INVALID');self.assertFalse(m.records[0]['rf_valid'])
        b,status=weights(s,Config());np.testing.assert_array_equal(b,np.zeros(2))
        s,p=m.observe(1,.2,np.zeros(4),np.array([0.,0.,.2]),np.zeros(2),np.zeros(2),np.eye(2))
        self.assertEqual(s['status'],'UNKNOWN');self.assertEqual(p['reason'],'INVALID_HISTORY_RF')

    def test_invalid_monitor_covariance_cannot_be_compatible_or_warmup(self):
        for bad in [np.diag([-1.,1.]),np.array([[1.,2.],[0.,1.]]),np.array([[np.nan,0.],[0.,1.]])]:
            m=Monitor(SyntheticCore,SyntheticRF,None,Config())
            try:s,p=m.observe(0,0,np.zeros(4),np.zeros(3),np.zeros(2),np.zeros(2),bad)
            except ValueError:continue  # explicit fail-closed rejection is allowed
            self.assertEqual(s['status'],'INVALID')
            b,_=weights(s,Config());np.testing.assert_array_equal(b,np.zeros(2))

    def test_exact_refinement_improves_known_nonlinear_history_fit(self):
        a,c,t,q,z,mu,R=fixture(26);a=a+np.array([.3,.3,.3,0.])
        initial=profile_history(SyntheticCore,SyntheticRF,None,a,c,t,z[:-1],mu[:-1],R,
            Config(max_refinements=0,projected_gradient_per_sample_max=1e-6))
        refined=profile_history(SyntheticCore,SyntheticRF,None,a,c,t,z[:-1],mu[:-1],R,
            Config(max_refinements=3,projected_gradient_per_sample_max=1e-6))
        self.assertLess(refined['profile_cost'],initial['profile_cost']/10)
        self.assertLess(refined['stationarity_per_sample'],initial['stationarity_per_sample']/100)
        self.assertGreater(refined['refinements'],0)

    def test_nonstationary_fit_cannot_damp_a_current_target(self):
        a,c,t,q,z,mu,R=fixture(26);a=a+np.array([0.,0.,.3,0.])
        cfg=Config(max_refinements=0,projected_gradient_per_sample_max=1e-6)
        p=profile_history(SyntheticCore,SyntheticRF,None,a,c,t,z[:-1],mu[:-1],R,cfg)
        self.assertGreater(p['stationarity_per_sample'],cfg.projected_gradient_per_sample_max)
        self.assertEqual(p['status'],'UNKNOWN')
        s=score_current(p,z[-1]+np.array([1.,1.]),mu[-1]);b,status=weights(s,cfg)
        np.testing.assert_array_equal(b,np.ones(2));self.assertEqual(status,'UNKNOWN')

    def test_nuisance_boundary_can_leave_target_prediction_identifiable(self):
        a,c,t,q,z,mu,R=fixture(26);a=a+np.array([.3,.3,.3,0.])
        cfg=Config(max_refinements=3,projected_gradient_per_sample_max=1e-6)
        p=profile_history(SyntheticCore,SyntheticRF,None,a,c,t,z[:-1],mu[:-1],R,cfg)
        self.assertTrue(p['boundary_support']);self.assertFalse(p['bound_hit'])
        self.assertTrue(np.all(p['target_span_sigma']<cfg.max_prediction_span_sigma))
        self.assertEqual(p['status'],'PROFILE_READY')
        s=score_current(p,p['candidate_h'][0]+mu[-1],mu[-1]);b,status=weights(s,cfg)
        np.testing.assert_array_equal(s['scores'],np.zeros(3))
        self.assertEqual(status,'COMPATIBLE');np.testing.assert_array_equal(b,np.ones(2))


if __name__=='__main__':unittest.main(verbosity=2)
