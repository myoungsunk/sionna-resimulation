"""Synthetic contract tests only. These are NOT RF simulation/research results."""
from __future__ import annotations
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import json
import numpy as np
import pandas as pd

from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.common import *
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.numerics import *
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.runtime_features import *
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.replay import update,simulate
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.oracle_scoring import Truth,OracleCorrector,error_arrays,score_trace,all4_budget
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.diagnostics import common_prior,branch_effects,s1,summarize_residual
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.native import spectrum_profile,NativeAssets
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.training import FitLineage,LearningData,fit_one,feature_names,teacher_values,stable_fold,group_ids
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.temporal import fit_spectral_metric,spectral_covariance,window_design,nonlinear_profile,bias_forecast_diagnostic
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.scorecard import compare,ledger
from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.cli import main

class Model:
    mutable_runtime=False
    def observe(self,x):
        r=np.sqrt(x[0]**2+x[1]**2+4.)
        return np.array([r,.2*x[0]-.1*x[1]+.5*np.sin(x[2])]),np.array([[x[0]/r,x[1]/r,0.,0.],[.2,-.1,.5*np.cos(x[2]),0.]])
    def profile(self,x,fixed_fp=None):
        o=np.array(OFFSETS);q=.1*x[0]*(1+.03*o)+.07*x[1]*(1+.02*o**2)+.4*np.sin(x[2])*(1+.01*o**2)
        q[0]=self.observe(x)[0][1]
        return q,np.isfinite(q),10 if fixed_fp is None else fixed_fp
    def transition(self,x,u):
        ds,dg,dt=u;c,s=np.cos(x[2]),np.sin(x[2]);y=x.copy();y[:2]+=ds*np.array([c,s]);y[2]=wrap(x[2]+dg-x[3]*dt)
        F=np.eye(4);F[0,2]=-ds*s;F[1,2]=ds*c;F[2,3]=-dt
        G=np.zeros((4,3));G[:2,0]=[c,s];G[2,1]=1.;G[3,2]=1.
        return y,F,G
    def predict(self,x,P,u):
        y,F,G=self.transition(x,u);Q=np.diag([2e-5*abs(u[0]),np.deg2rad(.015)**2*u[2],0.])
        return y,F@P@F.T+G@Q@G.T,F,G,Q
    def reference_increments(self,t,truth):
        ds=np.zeros(len(t));dg=ds.copy()
        for k in range(1,len(t)):
            ds[k]=(truth[k,:2]-truth[k-1,:2])@np.array([np.cos(truth[k-1,2]),np.sin(truth[k-1,2])]);dg[k]=wrap(truth[k,2]-truth[k-1,2])
        return ds,dg

class Constant:
    diagnostic=False;model_hash='SYNTHETIC_ONLY'
    def __init__(self,c=0,name='TEST'):self.c=c;self.name=name
    def __call__(self,p,x,h,m):return self.c,{'profile_status':'TEST'}


def fixture(n=21,dt=.2,seed=0,anchor=(0,0,2),large_residual=False):
    model=Model();u=np.tile([.02,.002,dt],(n,1));u[0]=0.;truth=np.empty((n,4));truth[0]=[1.,.2,.1,0.]
    for k in range(1,n):truth[k]=model.transition(truth[k-1],u[k])[0]
    packets=[];sl=[]
    for k in range(n):
        h,H=model.observe(truth[k]);q,mask,fp=model.profile(truth[k]);q=q+.01*np.sin(k*.1);q[0]=h[1]+(.6 if large_residual else .01*np.sin(k*.1))
        features=np.r_[q[0],0.,fp,q[1:],q[1:]-q[0]]
        packets.append(Packet(k,k*dt,h+np.array([.003,q[0]-h[1]]),np.array([.001,.002]),np.diag([.01,.02]),features,q,mask,fp,np.ones(9)))
        sl.append(h[1])
    inp=Inputs('R2_aA_m0','R2','B0','full',seed,seed,tuple(packets),u,truth[0]+[.03,-.02,np.deg2rad(1),0.],np.diag([.02,.02,.01,.00001]),np.array(anchor),0.,'SYNTHETIC')
    return inp,model,Truth(truth,np.array(sl),np.zeros(n))


def strict_reference(x,P,p,h,H,c,eta=1):
    """Independent literal strict_common Joseph formula (not calling new update)."""
    z=p.z.copy();z[1]-=c;HP=H@P;HPHt=HP@H.T;Sg=HPHt+p.R;Sg=.5*(Sg+Sg.T);v=z-h-p.mu
    nis=float(v@np.linalg.solve(Sg,v));yes=nis<=9.210340371976184
    if not yes:return x.copy(),P.copy(),nis,yes
    Se=HPHt+eta*p.R;Se=.5*(Se+Se.T);K=np.linalg.solve(Se,HP).T
    out=x+K@v;out[2]=wrap(out[2]);A=np.eye(4)-K@H;C=A@P@A.T+K@(eta*p.R)@K.T
    return out,.5*(C+C.T),nis,yes

class Contracts(unittest.TestCase):
    def test_zero_correction_full_trace(self):
        i,m,t=fixture();a=simulate(i,m,Corrector('BASE'));b=simulate(i,m,Constant())
        for key in a.arrays:np.testing.assert_array_equal(a.arrays[key],b.arrays[key]) if key!='profile_status' else None
    def test_original_formula_all_updates(self):
        i,m,t=fixture();tr=simulate(i,m,Constant(.01))
        for k,p in enumerate(i.packets):
            a=tr.arrays;x,P,nis,yes=strict_reference(a['x_minus'][k],a['P_minus'][k],p,a['h'][k],a['H'][k],.01)
            np.testing.assert_allclose(x,a['x_plus'][k],atol=1e-14);np.testing.assert_allclose(P,a['P_plus'][k],atol=1e-14)
            self.assertEqual(yes,bool(a['accepted'][k]))
    def test_eta_update_only(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(i.x0);a=update(i.x0,i.P0,p,h,H,0);b=update(i.x0,i.P0,p,h,H,0,eta=2)
        self.assertEqual(a['nis'],b['nis']);np.testing.assert_array_equal(a['R_gate'],b['R_gate']);np.testing.assert_array_equal(b['R_update'],2*p.R)
        x,P,_,_=strict_reference(i.x0,i.P0,p,h,H,0,eta=2);np.testing.assert_allclose(x,b['x']);np.testing.assert_allclose(P,b['P'])
    def test_mu_once_and_oracle(self):
        i,m,t=fixture();o=OracleCorrector(i,t)
        for k,p in enumerate(i.packets):
            h,H=m.observe(t.state[k]);c,_=o(p,t.state[k],h,m)
            self.assertAlmostEqual(p.z[1]-p.mu[1]-c-t.s_los[k],0.)
    def test_native_los_oracle_target_is_minus_mu(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(t.state[0]);p2=Packet(p.pose_id,p.t,np.array([h[0],t.s_los[0]]),p.mu,p.R,p.cir_features,p.profile,p.profile_valid,p.fp,p.profile_power)
        ii=Inputs(i.case,i.route,i.bias,'los',i.seed_idx,i.seed,(p2,),np.zeros((1,3)),i.x0,i.P0,i.anchor,0.,'SYNTHETIC')
        o=OracleCorrector(ii,Truth(t.state[:1],t.s_los[:1],np.zeros(1)));self.assertAlmostEqual(o(p2,i.x0,h,m)[0],-p.mu[1])
    def test_oracle_requires_diagnostic_permission(self):
        i,m,t=fixture()
        with self.assertRaises(ContractError):simulate(i,m,OracleCorrector(i,t))
    def test_forbidden_field_mutation(self):
        i,m,t=fixture();p=i.packets[0];mapping={f.name:getattr(p,f.name) for f in __import__('dataclasses').fields(p)}
        a=Packet.from_mapping(mapping);mapping.update(truth=[99]*4,s_los=100,fp_shift=10,future=[999],heading_error=7)
        b=Packet.from_mapping(mapping);np.testing.assert_array_equal(build_features(a,i.x0,m.observe(i.x0)[0],m,'P2_DB')[0],build_features(b,i.x0,m.observe(i.x0)[0],m,'P2_DB')[0])
    def test_future_tail_mutation(self):
        i,m,t=fixture();a=simulate(i,m,Constant(.01));p=list(i.packets);old=p[-1]
        p[-1]=Packet(old.pose_id,old.t,old.z+[.1,.1],old.mu,old.R,old.cir_features,old.profile,old.profile_valid,old.fp,old.profile_power)
        j=Inputs(i.case,i.route,i.bias,i.channel,i.seed_idx,i.seed,tuple(p),i.controls,i.x0,i.P0,i.anchor,0.,'TEST');b=simulate(j,m,Constant(.01))
        np.testing.assert_array_equal(a.arrays['x_plus'][:-1],b.arrays['x_plus'][:-1])
    def test_immutable_inputs(self):
        i,m,t=fixture()
        with self.assertRaises(ValueError):i.controls[1,0]=3
        with self.assertRaises(ValueError):i.packets[0].z[0]=3
    def test_branch_copies(self):
        i,m,t=fixture();orig=i.checksum();a=simulate(i,m,Corrector('BASE'));x=a.arrays['x_minus'][3].copy();P=a.arrays['P_minus'][3].copy()
        b=simulate(i,m,Constant(.1),start=3,x_prior=x,P_prior=P);b.arrays['x_plus'][0]=999
        self.assertEqual(i.checksum(),orig);np.testing.assert_array_equal(x,a.arrays['x_minus'][3]);np.testing.assert_array_equal(P,a.arrays['P_minus'][3])
    def test_no_double_prediction_at_branch(self):
        i,m,t=fixture();a=simulate(i,m,Corrector('BASE'));b=simulate(i,m,Corrector('BASE'),start=4,x_prior=a.arrays['x_minus'][4],P_prior=a.arrays['P_minus'][4])
        np.testing.assert_allclose(a.arrays['x_plus'][4:],b.arrays['x_plus'],atol=1e-13)
    def test_future_derived_prior_recomputed(self):
        i,m,t=fixture();a=simulate(i,m,Corrector('BASE'));b=simulate(i,m,Constant(.1),active_end=np.nextafter(i.t[0],np.inf))
        self.assertNotEqual(a.arrays['d0'][1],b.arrays['d0'][1]);self.assertEqual(b.arrays['correction'][1],0.)
    def test_invalid_time_rejected(self):
        i,m,t=fixture();u=i.controls.copy();u[1,2]=.7
        with self.assertRaises(ContractError):Inputs(i.case,i.route,i.bias,i.channel,i.seed_idx,i.seed,i.packets,u,i.x0,i.P0,i.anchor,0.,'TEST')
    def test_duplicate_join_rejected(self):
        with self.assertRaises(ContractError):exact_rows(pd.DataFrame({'id':[1,1],'v':[2,3]}),['id'],pd.DataFrame({'id':[1]}))
    def test_missing_join_rejected(self):
        with self.assertRaises(ContractError):exact_rows(pd.DataFrame({'id':[1],'v':[2]}),['id'],pd.DataFrame({'id':[2]}))
    def test_join_preserves_requested_order(self):
        a=exact_rows(pd.DataFrame({'id':[1,2],'v':[3,4]}),['id'],pd.DataFrame({'id':[2,1]}));self.assertEqual(a.v.tolist(),[4,3])
    def test_trace_checksum(self):
        i,m,t=fixture();a=simulate(i,m,Corrector('BASE'))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.npz';a.save(p);b=Trace.load(p);np.testing.assert_array_equal(a.arrays['K'],b.arrays['K'])
            with p.open('ab') as f:f.write(b'bad')
            with self.assertRaises(ContractError):Trace.load(p)
    def test_feature_dimensions(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(i.x0)
        for mode in ('PCIR3','CIR_ONLY','PWIDE_NOES','WIDE_NOES',*CANDIDATES):
            X,flag=build_features(p,i.x0,h,m,mode,np.eye(9));self.assertEqual(len(X),len(feature_names(mode)))
    def test_db_transform_invertible(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(i.x0)
        a,_=build_features(p,i.x0,h,m,'P1_MU');b,_=build_features(p,i.x0,h,m,'P2_DB')
        self.assertAlmostEqual(a[-2],b[-2]+b[-1]);self.assertEqual(a[-1],b[-1])

class Mathematics(unittest.TestCase):
    def test_residual_benefit_identity(self):
        r=np.array([0.,.1,-.3]);c=np.array([.2,.1,.1]);np.testing.assert_allclose(r*r-(r-c)**2,2*r*c-c*c)
        self.assertLess((2*r*c-c*c)[0],0)
    def test_common_prior_closure(self):
        i,m,t=fixture();tr=simulate(i,m,Corrector('BASE'));r=common_prior(i,t,m,[tr],[Constant(.01)])
        self.assertTrue(all(x['closure']<1e-8 for x in r if x['gate_policy']=='common'))
    def test_rejected_common_gate_zero_gain(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(i.x0);r=update(i.x0,i.P0,p,h,H,.1,gate='common',common_accept=False)
        np.testing.assert_array_equal(r['K'],np.zeros((4,2)));np.testing.assert_array_equal(r['x'],i.x0)
    def test_force_accept(self):
        i,m,t=fixture(large_residual=True);p=i.packets[0];h,H=m.observe(i.x0);r=update(i.x0,i.P0,p,h,H,0.,gate='force_accept');self.assertTrue(r['accepted'])
    def test_heading_wrap(self):
        d=delta(np.array([0,0,-np.pi+.01,0]),np.array([0,0,np.pi-.01,0]));self.assertAlmostEqual(d[2],.02)
    def test_finite_jacobian_units(self):
        m=Model();x=np.array([1.,.2,.3,0.]);J=finite_jacobian(lambda v:m.observe(v)[0],x);np.testing.assert_allclose(J,m.observe(x)[1][:,:3],atol=1e-8)
    def test_moments_centered(self):
        Y=np.array([[1.,4.],[3.,8.],[2.,6.]]);mu,C,M=moments(Y);np.testing.assert_allclose(M,C+np.outer(mu,mu));self.assertNotEqual(C[0,0],M[0,0])
    def test_projection_state_invariance(self):
        rng=np.random.default_rng(3);J=rng.normal(size=(8,3));d=rng.normal(size=8);v=rng.normal(size=3)
        a,P,W,info=projector(d,J,np.eye(8),np.ones(3));b,*_=projector(d+J@v,J,np.eye(8),np.ones(3));np.testing.assert_allclose(a,b,atol=1e-12)
    def test_projection_column_rotation(self):
        rng=np.random.default_rng(3);J=rng.normal(size=(8,3));Q,_=np.linalg.qr(rng.normal(size=(3,3)));d=rng.normal(size=8)
        a,*_=projector(d,J,np.eye(8),np.ones(3));b,*_=projector(d,J@Q,np.eye(8),np.ones(3));np.testing.assert_allclose(a,b,atol=1e-12)
    def test_d0_only_no_orthogonal_information(self):
        u,P,W,meta=projector(np.array([.3]),np.array([[2.]]),np.eye(1),np.ones(1));np.testing.assert_allclose(u,0,atol=1e-15);self.assertEqual(meta['residual_rank'],0)
    def test_state_parallel_bias_removed(self):
        J=np.array([[1.,0.],[0.,1.],[1.,1.]]);u,*_=projector(J@np.array([.2,.3]),J,np.eye(3),np.ones(2));np.testing.assert_allclose(u,0,atol=1e-14)
    def test_duplicate_taps_do_not_add_information(self):
        j=np.array([1.,2.,3.]);G=np.eye(3);U=np.ones((3,1));v=information(j,U,G)['information']
        T=np.vstack([np.eye(3),np.eye(3)]);v2=information(T@j,T@U,T@G@T.T)['information'];self.assertAlmostEqual(v,v2,places=10)
    def test_small_denominator_response_undefined(self):
        r=response_pair(1,1,2,3);self.assertFalse(r['ratio_defined']);self.assertTrue(np.isnan(r['G']))
    def test_discontinuous_predictor_response_detected(self):
        r=response_pair(.1,-.1,-.1,.1);self.assertTrue(r['sign_reversal'])
    def test_invalid_psd_rejected(self):
        with self.assertRaises(ContractError):psd(np.array([[1.,2.],[2.,1.]]))
    def test_no_silent_covariance_floor(self):
        with self.assertRaises(ContractError):solve_spd(np.zeros((2,2)),np.ones(2))
    def test_correlated_noise_sign(self):
        P=np.array([[2.]]);H=np.array([[.5]]);R=np.array([[1.]]);C=np.array([[.2]])
        S,K,post=correlated_update_moments(P,H,R,C);self.assertAlmostEqual(S[0,0],1.3);self.assertAlmostEqual(K[0,0],.8/1.3)
    def test_correlated_noise_bad_joint(self):
        with self.assertRaises(ContractError):correlated_update_moments(np.eye(1),np.eye(1),np.eye(1),np.array([[2.]]))
    def test_constant_sensitivity_unidentifiable(self):
        r=information(np.ones(10)*2,np.ones((10,1)),np.eye(10));self.assertLess(r['information'],1e-20)
    def test_varying_sensitivity_information_formula(self):
        g=np.array([1.,2.,4.,8.]);w=np.array([1.,2.,3.,4.]);v=np.sum(w*(g-np.sum(w*g)/w.sum())**2)
        self.assertAlmostEqual(information(g,np.ones((4,1)),np.diag(1/w))['information'],v)
    def test_free_packet_bias_removes_information(self):
        r=information(np.arange(10),np.eye(10),np.eye(10));self.assertLess(r['information'],1e-20)
    def test_motion_covariance_has_cross_time(self):
        n=4;F=np.tile(np.eye(1),(n,1,1));G=F.copy();Q=F.copy();H=F.copy();cov=motion_observation_covariance(F,G,Q,H)
        self.assertAlmostEqual(cov[2,3],2.);self.assertAlmostEqual(cov[0,0],0.)
    def test_budget_all4_closure_and_shares(self):
        i,m,t=fixture();c=Constant(.01);tr=simulate(i,m,c);rows,M,Y=all4_budget(i,t,m,tr,c)
        np.testing.assert_allclose(Y.sum(1),delta(tr.arrays['x_plus'],t.state),atol=1e-10)
        f=pd.DataFrame(rows)
        for _,d in f.groupby('component'):self.assertAlmostEqual(d.share_mse.sum(),1.,places=7)
    def test_range_only_no_polarization_column(self):
        i,m,t=fixture();p=i.packets[0];h,H=m.observe(i.x0);r=update(i.x0,i.P0,p,h,H,.9,mode='range_only')
        np.testing.assert_array_equal(r['K'][:,1],0.)

class ObserverAndStatistics(unittest.TestCase):
    def test_zero_power_mask(self):
        q,mask,fp,power=spectrum_profile(np.zeros((16,2),complex));self.assertFalse(mask.any());self.assertEqual(fp,-1);self.assertTrue(np.isnan(q).all())
    def test_fp_edge_not_clipped_to_valid(self):
        H=np.ones((16,2),complex);q,mask,fp,p=spectrum_profile(H,fixed_fp=0)
        for j,o in enumerate(OFFSETS):
            if o<0:self.assertFalse(mask[j]);self.assertTrue(np.isnan(q[j]))
    def test_power_profile_bounds(self):
        rng=np.random.default_rng(2);H=rng.normal(size=(32,2))+1j*rng.normal(size=(32,2));q,m,fp,p=spectrum_profile(H)
        self.assertTrue((abs(q[m])<=1).all());self.assertTrue((p>=0).all())
    def test_paired_bootstrap_not_ratio_of_means(self):
        r=paired_bootstrap(np.array([1.,10.,2.]),np.array([2.,5.,1.]),draws=100)
        self.assertAlmostEqual(r['ratio_mean'],1.);self.assertNotEqual(r['ratio_mean'],8/13)
    def test_bootstrap_rejects_nonfinite(self):
        with self.assertRaises(ContractError):paired_bootstrap(np.array([1.,2.]),np.array([1.,np.nan]))
    def test_bootstrap_uncertainty_not_pass(self):
        r=paired_bootstrap(np.ones(12),np.r_[np.ones(6)*.5,np.ones(6)*1.5],draws=1000);self.assertEqual(r['conclusion'],'INCONCLUSIVE')
    def test_time_block_insufficient(self):
        r=time_block_sensitivity(np.arange(21)*.2,np.ones(21));self.assertTrue(all(x['status']=='INSUFFICIENT_BLOCKS' for x in r))
    def test_episode_uses_real_time(self):
        r=episode_curve(np.array([0.,.1,1.,2.]),np.array([0.,2.,2.,2.]),[1])[0];self.assertAlmostEqual(r['duration_total_s'],1.9);self.assertTrue(r['right_censored'])
    def test_branch_right_censor(self):
        i,m,t=fixture(n=6,dt=.3);base=simulate(i,m,Corrector('BASE'));rows,cr,lin=branch_effects(i,t,m,base,[Constant(0.)])
        self.assertTrue(any(r['right_censored'] for r in rows if r['horizon_requested']==120))
        self.assertTrue(all(abs(r['heading_deg_integrated_delta_mse'])<1e-12 for r in rows))
    def test_score_all4_not_sum_of_marginals(self):
        i,m,t=fixture();tr=simulate(i,m,Constant(.01));scores,ep=score_trace(i,t,tr)
        r=next(x for x in scores if x['window']=='all');self.assertIn('all4_nees',r);self.assertIn('pose_cov95',r)
    def test_anchor_projection_explicit_undefined(self):
        i,m,t=fixture(anchor=(1.,.2,2.));tr=simulate(i,m,Corrector('BASE'));E=error_arrays(i,t,tr)
        self.assertFalse(E['radial_valid'][0]);self.assertTrue(np.isnan(E['radial_cm'][0]))
    def test_s1_populations(self):
        i,m,t=fixture();tr=simulate(i,m,Corrector('BASE'));r=s1(i,t,m,[tr],[Corrector('BASE'),Constant(.01)])
        self.assertIn('S1_STRATA.csv',r);self.assertTrue(len(r['S1_RESIDUAL.csv.gz'])==2*len(i.packets))
    def test_spectral_metric_train_only(self):
        f=pd.DataFrame({'route':['R4']*16,'case':['R4_aA_m0']*16,'t_s':np.arange(16)*.2,'target':np.sin(np.arange(16))})
        metric=fit_spectral_metric(f,'R2');C=spectral_covariance(metric,np.array([.1,.4,.7]));self.assertGreaterEqual(np.linalg.eigvalsh(C).min(),-1e-12)
        with self.assertRaises(ContractError):fit_spectral_metric(f,'R4')
    def test_motion_only_window_no_rf_update(self):
        i,m,t=fixture();des=window_design(i,m,0,5,i.x0);x=i.x0.copy()
        for k in range(1,6):x=m.transition(x,i.controls[k])[0]
        np.testing.assert_allclose(des['states'][-1],x)
    def test_nonlinear_profile_executes(self):
        i,m,t=fixture(n=6);D=window_design(i,m,0,5,i.x0)
        rr,summary=nonlinear_profile(i,m,0,5,i.x0,np.eye(6),np.ones((6,1)),i.P0,grid_degrees=np.array([-1.,0.,1.]))
        self.assertEqual(len(rr),3);self.assertTrue(all(np.isfinite(r['cost']) for r in rr))
    def test_forecast_truth_only_label(self):
        t=np.arange(20)*.2;r=bias_forecast_diagnostic(t,np.sin(t),10,1.,1.,'constant')
        self.assertEqual(r['classification'],'TRUTH_LABEL_BIAS_MODEL_DIAGNOSTIC_ONLY')

class LeakageAndExecution(unittest.TestCase):
    def test_lineage_outer_held_rejected(self):
        l=FitLineage('R2')
        with self.assertRaises(ContractError):l.record('imputer',pd.DataFrame({'key':['a'],'route':['R2']}))
    def test_lineage_inner_validation_rejected(self):
        l=FitLineage('R2',['a'])
        with self.assertRaises(ContractError):l.record('POWER',pd.DataFrame({'key':['a'],'route':['R4']}))
    def test_lineage_parent_required(self):
        l=FitLineage('R2');l.record('residual',pd.DataFrame({'key':['a'],'route':['R4']}),parents=['missing'])
        with self.assertRaises(ContractError):l.check()
    def test_group_same_location_same_fold(self):
        g=group_ids(np.array([[.01,.02],[.01,.02],[.8,.9]]));self.assertEqual(g[0],g[1]);self.assertEqual(stable_fold(g[0]),stable_fold(g[1]))
    def test_teacher_target_difference(self):
        e=np.array([.2,.3]);mu1=np.array([.1,.5]);mu2=np.array([.3,-.2]);np.testing.assert_allclose((e-mu2)-(e-mu1),mu1-mu2)
    def test_native_missing_assets_blocked(self):
        with self.assertRaises(BlockedError):NativeAssets({})
    def test_cli_stage_requires_explicit_execute(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';write_json(p,{'work_dir':d})
            with self.assertRaises(ContractError):main(['stage','--stage','S0','--config',str(p)])
            self.assertFalse((Path(d)/'S0').exists())
    def test_plan_never_instantiates_native(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';write_json(p,{'work_dir':d})
            with patch('research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.native.NativeAssets',side_effect=AssertionError('must not instantiate')):
                self.assertEqual(main(['plan','--config',str(p)]),0)
    def test_receipt_fingerprint_and_asset_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(Path(d),{'a':1});(Path(d)/'S0').mkdir();p=Path(d)/'S0'/'a';p.write_text('first');w.finish('S0');w.require_stage('S0');p.write_text('second')
            with self.assertRaises(ContractError):w.require_stage('S0')
    def test_receipt_wrong_config_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(Path(d),{'a':1});w.finish('S0')
            with self.assertRaises(ContractError):Workspace(Path(d),{'a':2}).require_stage('S0')
    def test_missing_arm_not_dropped(self):
        rows=[dict(case='a',bias='B0',channel='full',seed_idx=s,arm='BASE',window='stable_30_plus',status='PASS') for s in [0,1]]
        r,c=compare(rows,['BASE','P2_DB'],cases=['a'],biases=['B0'],seeds=[0,1]);self.assertEqual(r[0]['conclusion'],'BLOCKED')
    def test_oracle_not_candidate_verdict(self):
        rows=[dict(arm='ORACLE',metric='heading_deg_mse',conclusion='SUPPORT')]
        out=ledger(rows,candidates=['P2_DB']);self.assertNotEqual(out[0]['overall_outcome'],'SUPPORT')


class FakeAssets:
    def __init__(self,frame):
        self.obs=frame.copy();self.obs['channel']='full';self.obs['e_s']=frame.e_true;self.obs['e_r']=0.
    def power_predict(self,train,target):
        # Synthetic teacher exposes exactly which labels were used; no reference repository data.
        o=target[['case','pose_id']].copy();o['mu_s']=float(train.e_s.mean());o['Vs']=float(train.e_s.var()+.01);return o


def learning_fixture(n=180):
    rng=np.random.default_rng(5);m=Model();st=np.zeros((n,4));st[:,:2]=rng.uniform(-.4,.4,(n,2));st[:,2]=rng.uniform(-.1,.1,n)
    labels=.04+.05*rng.normal(size=n);q=[];X=[];gr=[];gg=[]
    for k in range(n):
        qq,_,_=m.profile(st[k]);qq=qq+labels[k];q.append(qq);X.append(np.r_[qq[0],rng.normal(),10,qq[1:],qq[1:]-qq[0]])
        psi=st[k,2]+np.radians(np.arange(-30,31));gr.append(.2*st[k,0]-.1*st[k,1]+.5*np.sin(psi));gg.append(.5*np.cos(psi)*np.pi/180)
    routes=np.where(np.arange(n)<n//2,'R4','R5');cases=np.array([r+'_aA_m0' for r in routes]);groups=group_ids(st[:,:2],.15)
    F=pd.DataFrame({'case':cases,'route':routes,'pose_id':np.arange(n),'key':[f'{cases[k]}:{k}' for k in range(n)],'group':groups,
                    'e_true':labels,'x_eval':st[:,0],'y_eval':st[:,1],'t_s':np.arange(n)*.2})
    data=LearningData(F,np.array(X),np.array(q),np.ones((n,9)),st,np.array(gr),np.array(gg),{c:m for c in set(cases)})
    return data,FakeAssets(F)

class TrainingIntegration(unittest.TestCase):
    def test_all_six_learners_fit_and_predict(self):
        data,assets=learning_fixture()
        from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.training import design_matrix
        for mode in CANDIDATES:
            lin=FitLineage('R2');c,prep=fit_one(assets,data,'R2',mode,lin)
            X,_=design_matrix(data,mode,prep['mu'],prep['vs'],prep['idx'],prep['state'],prep['hs'],c.omega)
            pred=c.estimator.predict(pd.DataFrame(np.where(np.isfinite(X),X,c.medians),columns=feature_names(mode)))
            self.assertTrue(np.isfinite(pred).all());self.assertEqual(len(pred),3*len(data.frame));self.assertTrue(lin.check())
    def test_fixed_design_fits_reproducibly(self):
        data,assets=learning_fixture();a,pa=fit_one(assets,data,'R2','P2_DB',FitLineage('R2'));b,pb=fit_one(assets,data,'R2','P2_DB',FitLineage('R2'))
        np.testing.assert_array_equal(pa['offset'],pb['offset']);np.testing.assert_array_equal(pa['y'],pb['y']);self.assertEqual(a.model_hash,b.model_hash)
    def test_outer_labels_do_not_affect_teacher(self):
        data,assets=learning_fixture();a=teacher_values(assets,data,'R2',FitLineage('R2'))[0]
        extra=assets.obs.iloc[:10].copy();extra['route']='R2';extra['case']='R2_aA_m0';extra['e_s']=1e6
        assets.obs=pd.concat([assets.obs,extra],ignore_index=True);b=teacher_values(assets,data,'R2',FitLineage('R2'))[0]
        np.testing.assert_array_equal(a,b)
    def test_crossfit_teacher_excludes_target_group(self):
        data,assets=learning_fixture();lin=FitLineage('R2');mu,vs,ids=teacher_values(assets,data,'R2',lin,crossfit=True)
        events={v['id']:v for v in lin.events}
        for k,row in data.frame.iterrows():
            target_fold=stable_fold(row.group);fit_keys=set(events[ids[k]]['fit_keys'])
            permitted=set(data.frame.loc[data.frame.group.map(stable_fold)!=target_fold,'key'])
            self.assertTrue(fit_keys<=permitted);self.assertNotIn(row.key,fit_keys)
    def test_nested_validation_teacher_never_fits_validation(self):
        data,assets=learning_fixture();val=np.arange(len(data.frame))%5==0;train=data.take(~val);test=data.take(val);lin=FitLineage('R2',test.frame.key)
        teacher_values(assets,train,'R2',lin,prediction_only=test.frame);self.assertTrue(lin.check())
    def test_model_roundtrip_metadata_and_hash(self):
        from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.training import load_candidate
        data,assets=learning_fixture()
        with tempfile.TemporaryDirectory() as d:
            c,_=fit_one(assets,data,'R2','P1_MU',FitLineage('R2'),out=Path(d));cc=load_candidate(Path(d),'R2','P1_MU')
            self.assertEqual(c.model_hash,cc.model_hash)
            p=Path(d)/'R2__P1_MU.joblib'
            with p.open('ab') as f:f.write(b'x')
            with self.assertRaises(ContractError):load_candidate(Path(d),'R2','P1_MU')
    def test_partial_scope_not_full_claim(self):
        rr=[]
        for met in ('heading_deg_mse','xy_cm_mse','heading_deg_q99'):
            rr.append(dict(arm='P2_DB',metric=met,conclusion='SUPPORT'))
        out=ledger(rr,candidates=['P2_DB'],population='2 paired synthetic seeds',complete_protocol=False)
        self.assertFalse(out[0]['complete_protocol']);self.assertEqual(out[0]['population'],'2 paired synthetic seeds')
    def test_s7_simple_comparator_is_eta2(self):
        # Missing the eta2 arm must be BLOCKED, even when BASE exists.
        r=[dict(case='a',bias='B0',channel='full',seed_idx=s,arm='BASE',window='stable_30_plus',status='PASS') for s in (0,1)]
        rows,complete=compare(r,['BASE_ETA2','P2_DB'],cases=['a'],biases=['B0'],seeds=(0,1),reference_arm='BASE_ETA2')
        self.assertEqual(rows[0]['reference_arm'],'BASE_ETA2');self.assertEqual(rows[0]['conclusion'],'BLOCKED')


class FinalAuditRegression(unittest.TestCase):
    def test_readonly_output_disjoint(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ContractError):Workspace(Path(d)/'source'/'out',{'source_root':str(Path(d)/'source')})
            with self.assertRaises(ContractError):Workspace(Path(d),{'artifact_root':str(Path(d)/'artifacts')})
    def test_information_unit_invariance(self):
        rng=np.random.default_rng(23);U=rng.normal(size=(20,3));j=rng.normal(size=20);G=np.eye(20)
        x=information(j,U,G);y=information(j,U*np.array([1e-8,1e7,.01]),G)
        self.assertAlmostEqual(x['information'],y['information'],places=10)
    def test_coverage_and_episode_are_scored(self):
        i,m,t=fixture();tr=simulate(i,m,Corrector('BASE'));rows,_=score_trace(i,t,tr)
        r=next(r for r in rows if r['window']=='all')
        self.assertIn('heading_cov95_deviation',r);self.assertIn('xy_cm_above_20_duration_s',r)
        self.assertAlmostEqual(r['heading_cov95_deviation'],abs(r['heading_cov95']-.95))
    def test_all_stages_import_without_native(self):
        import importlib
        stages=importlib.import_module('research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.stages')
        for stage in range(8):self.assertTrue(callable(getattr(stages,f'run_s{stage}')))
    def test_common_gate_not_inherited_from_source_arm(self):
        i,m,t=fixture();tr=simulate(i,m,Constant(.5,'SOURCE'))
        out=s1(i,t,m,[tr],[Corrector('BASE')])['S1_RESIDUAL.csv.gz']
        for r in out:
            k=int(r['k']);a=tr.arrays;p=i.packets[k]
            zero=update(a['x_minus'][k],a['P_minus'][k],p,a['h'][k],a['H'][k],0.)
            self.assertEqual(r['common_accepted'],zero['accepted'])
    def test_one_seed_not_certified_safe(self):
        i,m,t=fixture(n=170);a=simulate(i,m,Corrector('BASE'));b=simulate(i,m,Constant(0.,'P2_DB'))
        rows=score_trace(i,t,a)[0]+score_trace(i,t,b)[0]
        out,_=compare(rows,['BASE','P2_DB'],cases=[i.case],biases=[i.bias],seeds=[0])
        self.assertTrue(all(r['conclusion']=='INCONCLUSIVE' for r in out))
    def test_failed_stage_receipt_blocks_followup(self):
        with tempfile.TemporaryDirectory() as d:
            w=Workspace(Path(d),{});self.assertEqual(w.provenance('AUDIT')['classification'],'SYNTHETIC_UNIT_TESTS_ONLY');w.receipt('S0','QA_FAIL',reason='test')
            with self.assertRaises(BlockedError):w.require_stage('S0')



class AdditionalSafetyTests(unittest.TestCase):
    def test_nonfinite_update_not_silent_rejection(self):
        i,m,t=fixture();h,H=m.observe(i.x0)
        with self.assertRaises(ContractError):update(i.x0,i.P0,i.packets[0],h,H,np.nan)
        with self.assertRaises(ContractError):update(i.x0,i.P0,i.packets[0],h,H,0.,mode='typo')
    def test_rng_is_deep_copied(self):
        class RandomCorrector:
            name='SYNTHETIC_RANDOM';diagnostic=False;model_hash='test'
            def __init__(self):self.rng=np.random.default_rng(42)
            def __call__(self,*args):return float(self.rng.normal(0,.01)),{}
        i,m,t=fixture();c=RandomCorrector();state=digest(c.rng.bit_generator.state)
        a=simulate(i,m,c);b=simulate(i,m,c)
        np.testing.assert_array_equal(a.arrays['x_plus'],b.arrays['x_plus']);self.assertEqual(state,digest(c.rng.bit_generator.state))
    def test_cross_port_constant_phase_is_not_a_feature(self):
        rng=np.random.default_rng(35);H=rng.normal(size=(64,2))+1j*rng.normal(size=(64,2))
        q,mask,fp,p=spectrum_profile(H);qq,mm,ff,pp=spectrum_profile(H*np.exp(1j*np.array([.7,-1.3])))
        np.testing.assert_array_equal(mask,mm);self.assertEqual(fp,ff);np.testing.assert_allclose(q,qq,atol=1e-12);np.testing.assert_allclose(p,pp,rtol=1e-12)
    def test_process_mean_square_is_not_variance(self):
        from research.PJ_BASE_PRESERVE_IDENTIFIABILITY_20261023.oracle_scoring import process_noise_statistics
        i,m,t=fixture();rows=process_noise_statistics(i,t,m)
        for r in rows:
            if r['status']=='EMPTY_WINDOW':continue
            self.assertAlmostEqual(r['mean_square'],r['variance']+r['mean']**2,places=12)

if __name__=='__main__':unittest.main()
