"""Synthetic-only verification. No RF archive, FFD bank, hardware, or network.

The adapter below is intentionally NOT the physical SourceFFD model. It tests
interfaces/causality/Joseph arithmetic and cannot establish scientific efficacy.
"""
from dataclasses import asdict, replace
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from qclean_uwb.fp_sc.followup.contracts import *
from qclean_uwb.fp_sc.followup.selection import *
from qclean_uwb.fp_sc.followup.numerics import *
from qclean_uwb.fp_sc.followup.evaluation import *
from qclean_uwb.fp_sc.followup.engine import OnlineCase, ArmProcessor, open_loop, run_arms
from qclean_uwb.fp_sc.followup.runtime import Arrival, DeadlineRunner, arrivals
from qclean_uwb.fp_sc.followup.study import *
from qclean_uwb.fp_sc.followup.data import load_case, ONLINE_ARRAYS, TRACE_FIELDS, META
from qclean_uwb.fp_sc.followup.runner import plan, run, code_paths


class SyntheticAdapter:
    anchor = np.array([10., 0.])

    def observe(self, x):
        r = np.sqrt(np.sum((x[:2]-self.anchor)**2)+2.2**2)
        h = np.array([r-.5315983906250129, .05*x[0]+.1*x[2]])
        H = np.array([[(x[0]-10.)/r, x[1]/r, 0., 0.], [.05, 0., .1, 0.]])
        return h, H

    def native(self, points):
        geometry = np.sqrt(np.sum((points[:, :2]-self.anchor)**2, axis=1)+2.2**2)
        return np.rint((geometry-.53)/STEP_M)*STEP_M, geometry

    def predict(self, x, P, k, case):
        if k == 0:
            return x.copy(), P.copy()
        out = x.copy()
        out[0] += case.ds[k]*math.cos(x[2])
        out[1] += case.ds[k]*math.sin(x[2])
        out[2] += case.gy[k]-x[3]*case.dt[k]
        F = np.eye(4)
        F[0, 2] = -case.ds[k]*math.sin(x[2])
        F[1, 2] = case.ds[k]*math.cos(x[2])
        F[2, 3] = -case.dt[k]
        return out, F@P@F.T+np.diag([1e-5, 1e-5, 1e-6, 1e-8])

    def evidence(self, cir, variance=0.):
        tap, _, z = raw_detection(cir)
        if z is None:
            return Evidence(tap, None, False, False, (), "SYNTHETIC_INVALID")
        candidate = []
        for n, support in ((tap, .8), (min(tap+1, 1027), .4)):
            zz = measurement(cir, n, n)
            if zz is not None and n not in [c.tap for c in candidate]:
                candidate.append(Candidate(n, float(zz[1]), support, (0,), True))
        return Evidence(tap, float(z[1]), True, False, tuple(candidate), "SYNTHETIC_POOL")

    def legacy(self, cir, e, prior, P):
        return e.raw_tap  # no claim of B37 numerical parity in synthetic tests

    def original_replay(self, case):
        # Independent small reference follows the original W0 ordering. It does
        # not call new update(), ArmProcessor, or the selector.
        x, P = case.x0.copy(), case.P0.copy()
        sx, sp = x.copy(), P.copy()
        out = {k: [] for k in ("x", "P", "prior", "Pprior", "h", "H", "Reff", "K", "mask")}
        for k, z in enumerate(case.z):
            sx, sp = self.predict(sx, sp, k, case)
            sh, sH = self.observe(sx)
            sv = z-sh-case.muBASE[k]
            SS = sH@sp@sH.T+case.R[k]
            allowed = bool(sv@np.linalg.solve(SS, sv) <= GATE)
            if allowed:
                kg = np.linalg.solve(SS, sH@sp).T
                sx += kg@sv
                sx[2] = (sx[2]+np.pi)%(2*np.pi)-np.pi
                A = np.eye(4)-kg@sH
                sp = A@sp@A.T+kg@case.R[k]@kg.T
                sp = (sp+sp.T)*.5
            rho = np.linalg.norm(x[:2]-self.anchor)
            sigma = np.interp(rho, [0.,1.5,3.,6.,10.], [.011,.020,.050,.120,.240])
            xp, pp = self.predict(x, P, k, case)
            h, H = self.observe(xp)
            rr = case.R[k].copy()
            rr[1,1] += sigma**2
            S = H@pp@H.T+rr
            S = (S+S.T)*.5
            K = np.linalg.solve(S, H@pp).T if allowed else np.zeros((4,2))
            x = xp+K@(z-h-case.muMB[k])
            if allowed:
                x[2] = (x[2]+np.pi)%(2*np.pi)-np.pi
                A = np.eye(4)-K@H
                P = A@pp@A.T+K@rr@K.T
                P = (P+P.T)*.5
            else:
                P = pp.copy()
            for key, value in dict(x=x, P=P, prior=xp, Pprior=pp, h=h, H=H, Reff=rr, K=K, mask=allowed).items():
                out[key].append(copy.deepcopy(value))
        return {k: np.asarray(v) for k,v in out.items()}


def case_fixture(n=8, route="R4", split="SYNTHETIC"):
    f = np.arange(257)
    h = np.exp(-2j*np.pi*f*35/1028)[:, None]*np.array([[1., .6]])
    Hrf = np.tile(h, (n, 1, 1))
    z = np.stack([raw_detection(cir_from_spectrum(h))[2] for _ in range(n)])
    case = OnlineCase(case_id="synthetic_"+route, route=route, bias="B0", channel="Full", sensor_seed=10,
                     split=split, Hrf=Hrf, t=np.arange(n)*.2, pose_id=np.arange(n),
                     ds=np.r_[0., np.full(n-1, .04)], gy=np.zeros(n), dt=np.full(n, .2),
                     x0=np.array([5., .5, .1, 0.]), P0=np.diag([.3,.3,.1,.01]),
                     z=z, muMB=np.zeros((n,2)), muBASE=np.zeros((n,2)),
                     R=np.tile(np.array([[.04, .005],[.005,.04]]), (n,1,1)), D=np.zeros(n),
                     prior=np.tile([5.,.5,.1,0.],(n,1)), Pprior=np.tile(np.diag([.3,.3,.1,.01]),(n,1,1)))
    adapter = SyntheticAdapter()
    trace = adapter.original_replay(case)
    case.prior, case.Pprior, case.baseline_trace = trace["prior"], trace["Pprior"], trace
    truth = np.tile([5., .5, .1, 0.], (n,1))
    truth[:,0] += np.arange(n)*.04
    return case, Evaluator(case, Hrf.copy(), truth, adapter), adapter


def model_fixture(policy=Policy(), target="R4"):
    models = {}
    residual = np.array([[-.02, -.01], [0., .01], [.02, .0]])
    values = np.tile(residual, (3,1))
    bins = sum(([key]*3 for key in ("unchanged", "changed_low", "changed_high")), [])
    for extractor in ("F00", "F01", "F11"):
        models[extractor] = fit_residual_model(values, bins, [f"fit_{i}" for i in range(9)],
                ["R2"]*9, target_route=target, split="TRAIN", extractor=extractor,
                policy_sha=policy.sha, min_samples=2, variance_floor=(.01,.01),domain=dict(bias="B0",channel="Full",noise_variance=0.))
    return models


def example_rows():
    out=[]
    for i, (raw, selected, reference) in enumerate(((1,1,1),(2,1,1),(1,2,1),(3,2,1))):
        out.append(dict(case_id="test", pose_id=i, t=i*.2, raw_valid=True, reference_valid=True,
             raw_tap=raw, selected_tap=selected, reference_tap=reference, flag=raw!=reference,
             wrong_score=float(raw), confidence_score=.6, reference_in_usable_pool=True,
             raw_range_error=float(raw-reference), selected_range_error=float(selected-reference),
             raw_s_error=float(raw-reference), selected_s_error=float(selected-reference), reason="SUPPORTED"))
    return out


class ContractsTest(unittest.TestCase):
    def test_policy_reject_nan(self):
        with self.assertRaises(ContractError): Policy(margin=float("nan"))
    def test_policy_reject_bad_integer(self):
        with self.assertRaises(ContractError): Policy(bootstrap_packets=1.5)
    def test_policy_grid_27_unique(self):
        self.assertEqual(len({p.sha for p in policy_grid(Policy())}),27)
    def test_support_distance(self):
        s=Support(1.,2.,.2,"tested")
        self.assertEqual(s.residual(1.5),0.)
        self.assertAlmostEqual(s.residual(2.4),2.)
    def test_bad_support(self):
        with self.assertRaises(ContractError): Support(2.,1.,1.,"tested")
    def test_covariance_negative(self):
        with self.assertRaises(ContractError): covariance(np.diag([1.,-1.]),2)
    def test_covariance_asymmetric(self):
        with self.assertRaises(ContractError): covariance([[1.,.1],[0.,1.]],2)
    def test_pd_zero_rejected(self):
        with self.assertRaises(ContractError): covariance(np.zeros((2,2)),2,positive=True)
    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ContractError): rooted(Path(d),"../escape")
    def test_lfs_pointer_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x";p.write_text("version https://git-lfs.github.com/spec/v1\n")
            with self.assertRaises(ContractError): verify_files(Path(d),{"x":sha256(p)})
    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"x";p.write_text("payload")
            with self.assertRaises(ContractError): verify_files(Path(d),{"x":"0"*64})
    def test_default_execution_block_before_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(__file__).resolve().parents[1];m=Path(d)/"m.json";a=Path(d)/"a.json"
            write_json(m,{});write_json(a,{"execute_science":False})
            output=Path(d)/"not_created"
            with patch("qclean_uwb.fp_sc.followup.contracts.verify_files") as verify:
                with self.assertRaisesRegex(ContractError,"SCIENCE_EXECUTION_NOT_AUTHORIZED"):
                    run(root,m,a,output,["E1-02"])
                verify.assert_not_called()
            with self.assertRaisesRegex(ContractError,"EXECUTING_CODE_OUTSIDE_DECLARED_REPOSITORY"):
                run(Path(d),m,a,output,["E1-02"])
            self.assertFalse(output.exists())
    def test_prerequisite_negative_preserved(self):
        r={"E1-01":{"execution_status":"COMPLETE","numerical_qa_pass":True,"scientific_gate":"NOT_SUPPORTED"}}
        with self.assertRaises(ContractError): prerequisite("E1-02",r,{})
        self.assertTrue(prerequisite("E1-02",r,{"exploratory_after_nonpass":["E1-01"]}))
        self.assertEqual(r["E1-01"]["scientific_gate"],"NOT_SUPPORTED")
    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ContractError): jsonable({"metric":np.nan})
    def test_complete_stage_plan(self):
        self.assertEqual(len(plan()["steps"]),16)
        self.assertFalse(plan()["execute_science"])
    def test_unsafe_case_id(self):
        c,_,_=case_fixture()
        with self.assertRaises(ContractError): replace(c,case_id="../../escape")
    def test_timeline_mismatch(self):
        c,_,_=case_fixture()
        with self.assertRaises(ContractError): replace(c,dt=np.ones(len(c.t)))


class ReceiverSelectionTest(unittest.TestCase):
    def evidence(self):
        return Evidence(10,.2,True,False,(Candidate(10,.2,.1,(0,),True),Candidate(8,.1,.8,(1,),True)),"fixture")
    def test_amplitude_threshold_not_power(self):
        c=np.zeros((1028,2),complex);c[10,0]=.35;c[20,0]=1
        self.assertEqual(raw_detection(c)[0],10)
    def test_tie_earliest_rx(self):
        c=np.zeros((1028,2),complex);c[10,0]=1;c[12,1]=1
        self.assertEqual(raw_detection(c)[:2],(10,0))
    def test_zero_signal_invalid(self):
        self.assertIsNone(raw_detection(np.zeros((1028,2),complex))[2])
    def test_direct_idft(self):
        h=np.ones((257,2),complex);c=cir_from_spectrum(h)
        for n in (0,20,100):
            direct=np.sum(np.hanning(257)*np.exp(2j*np.pi*np.arange(257)*n/1028))*257/1028
            self.assertAlmostEqual(abs(c[n,0]-direct),0.,places=11)
    def test_noise_packet_determinism(self):
        h=np.ones((257,2),complex)
        a,ha=inject_noise(h,variance=.1,namespace="test",packet_id="p",seed=1)
        b,hb=inject_noise(h,variance=.1,namespace="test",packet_id="p",seed=1)
        self.assertTrue(np.array_equal(a,b));self.assertEqual(ha,hb)
    def test_noise_different_packet(self):
        h=np.ones((257,2),complex)
        self.assertNotEqual(inject_noise(h,variance=.1,namespace="t",packet_id="a",seed=1)[1],
                            inject_noise(h,variance=.1,namespace="t",packet_id="b",seed=1)[1])
    def test_noise_zero_unchanged(self):
        h=np.ones((257,2),complex)
        self.assertTrue(np.array_equal(inject_noise(h,variance=0.,namespace="t",packet_id="p",seed=1)[0],h))
    def test_baseline_keeps_original(self):
        self.assertEqual(select(self.evidence(),"B0",Policy()).selected_tap,10)
    def test_p_missing_holds(self):
        self.assertEqual(select(self.evidence(),"P",Policy()).reason,"HOLD_PRIOR")
    def test_pm_missing_history_holds(self):
        s=Support(1.,1.3,.1,"t")
        self.assertEqual(select(self.evidence(),"PM",Policy(),prior=s).reason,"HOLD_HISTORY")
    def test_overflow_holds(self):
        e=replace(self.evidence(),overflow=True)
        self.assertEqual(select(e,"C",Policy()).reason,"CANDIDATE_OVERFLOW")
    def test_supported_replacement(self):
        s=Support(8*STEP_M,8*STEP_M,.1,"t")
        d=select(self.evidence(),"P",Policy(),prior=s)
        self.assertEqual(d.selected_tap,8)
        self.assertEqual(d.action,"REPLACE_SUPPORTED")
    def test_unsupported_never_selected(self):
        e=Evidence(10,.2,True,False,(Candidate(10,.2,.1,(0,),False),),"t")
        self.assertEqual(select(e,"C",Policy()).reason,"NO_SUPPORTED_PATH")
    def test_equal_scores_abstain(self):
        e=Evidence(10,.2,True,False,(Candidate(10,.2,.01,(0,),True),Candidate(8,.1,.8,(1,),True),Candidate(9,.1,.8,(2,),True)),"t")
        self.assertEqual(select(e,"C",Policy(wrong_cut=0.)).reason,"ABSTAIN_AMBIGUOUS")
    def test_no_gt_argument(self):
        with self.assertRaises(TypeError): select(self.evidence(),"C",Policy(),GT=8)
    def test_duplicate_candidate_rejected(self):
        with self.assertRaises(ContractError): Evidence(10,.2,True,False,(Candidate(10,.2,1.,(),True),)*2,"t")
    def test_from_original_pool_schema(self):
        c=np.zeros((1028,2),complex);c[10]=[1.,.5]
        pool=dict(raw=dict(tap=10,signed_s=.6,valid=True,peak=1.),overflow=False,pool_hash="test",candidates=[
          dict(tap=10,signed_s=.6,group_ids=[0],supported=True,support_records=[dict(prominence=.8,edge_tap=10)])])
        self.assertEqual(from_pool(pool,c).candidates[0].support,.8)
    def test_no_fixed_four_cm_after_gap(self):
        h=TrustedHistory(t=0.,detector_m=2.,offset_m=0.,streak=2)
        p=Policy();s=h.support(1.,0.,p)
        self.assertGreaterEqual(s.high-s.low,.4)
    def test_stale_history_holds(self):
        h=TrustedHistory(t=0.,detector_m=2.)
        self.assertIsNone(h.support(3.,0.,Policy()))
    def test_duplicate_history_rejected(self):
        h=TrustedHistory();h.advance(0.,1,0.,Policy())
        with self.assertRaises(ContractError): h.advance(0.,1,0.,Policy())
    def test_dr_slip_resets_trust(self):
        h=TrustedHistory(t=0.,detector_m=2.);h.advance(0.,1,0.,Policy());h.advance(.2,2,2.,Policy())
        self.assertIsNone(h.t)
    def test_future_suffix_invariance(self):
        c,_,a=case_fixture();p=Policy()
        before=open_loop(c,a,p,"PM")
        H=c.Hrf.copy();H[-2:,:,1]*=.1
        after=open_loop(replace(c,Hrf=H),a,p,"PM")
        for i in range(len(c.t)-2):
            self.assertEqual(asdict(before[i]["decision"]),asdict(after[i]["decision"]))
    def test_static_yaws_never_form_history(self):
        c,_,a=case_fixture();out=open_loop(replace(c,corpus="static_g4"),a,Policy(),"M")
        self.assertTrue(all(r["decision"].reason=="HOLD_HISTORY" for r in out))
    def test_gt_poison_does_not_change_selector(self):
        c,e,a=case_fixture();p=Policy();r1,_=labelled(c,e,a,p,"C")
        e.truth[:]=1e6;r2,_=labelled(c,e,a,p,"C")
        self.assertEqual([r["selected_tap"] for r in r1],[r["selected_tap"] for r in r2])


class NumericsAndCalibrationTest(unittest.TestCase):
    def test_factorial_preserves_raw_range(self):
        c,_,_=case_fixture();cir=cir_from_spectrum(c.Hrf[0]);n=raw_detection(cir)[0]
        f=factorial(cir,n,n+1)
        self.assertEqual(f["F00"][0].tobytes(),f["F01"][0].tobytes())
        self.assertEqual(f["F00"][1],f["F10"][1])
    def test_residual_decomposition_closure(self):
        c,_,_=case_fixture();full=cir_from_spectrum(c.Hrf[0]);direct=full.copy();direct[:,1]*=.7;n=raw_detection(full)[0]
        r=residual_decomposition(full,direct,n,n+1,n)
        self.assertLessEqual(r["closure_max"],1e-12)
        self.assertNotEqual(float(r["same_reference_tap"][1]),0.)
    def test_joseph_matches_information_form(self):
        P=np.diag([.3,.2,.1,.01]);H=np.array([[1.,.1,0.,0.],[0.,.2,1.,.5]])
        R=np.array([[.2,.03],[.03,.1]]);x=np.zeros(4)
        result=update(x,P,np.zeros(2),H,np.array([.1,.2]),np.zeros(2),R)
        alternative=np.linalg.inv(np.linalg.inv(P)+H.T@np.linalg.solve(R,H))
        np.testing.assert_allclose(result["P"],alternative,rtol=1e-12,atol=1e-14)
    def test_rejected_gain_vs_pre_mask(self):
        r=update(np.zeros(4),np.eye(4),np.zeros(2),np.eye(2,4),np.ones(2),np.zeros(2),np.eye(2),permitted=False)
        self.assertTrue(np.all(r["K"]==0));self.assertGreater(np.linalg.norm(r["pre_gate_K"]),0.)
        np.testing.assert_array_equal(r["P"],np.eye(4))
    def test_factorial_fixed_P_Kdelta(self):
        obs={"F00":np.array([1.,.1]),"F10":np.array([2.,.1]),"F01":np.array([1.,.3]),"F11":np.array([2.,.3])}
        r=same_prior_factorial(np.zeros(4),np.eye(4),np.zeros(2),np.eye(2,4),obs,np.zeros(2),np.eye(2),True)
        self.assertTrue(all(v["P_exact_equal"] for v in r["checks"].values()))
    def test_calibration_target_leakage(self):
        with self.assertRaises(ContractError): fit_residual_model(np.ones((2,2)),["x"]*2,["1","2"],["R4"]*2,
                  target_route="R4",split="TRAIN",extractor="F00",policy_sha=Policy().sha,min_samples=2)
    def test_calibration_sealed_rejected(self):
        with self.assertRaises(ContractError): fit_residual_model(np.ones((2,2)),["x"]*2,["1","2"],["R2"]*2,
                  target_route="R4",split="SEALED",extractor="F00",policy_sha=Policy().sha,min_samples=2)
    def test_calibration_cross_covariance_retained(self):
        vals=np.array([[-1.,-2.],[0.,0.],[1.,2.]])
        m=fit_residual_model(vals,["unchanged"]*3,["1","2","3"],["R2"]*3,target_route="R4",split="TRAIN",extractor="F00",policy_sha=Policy().sha,min_samples=2)
        self.assertGreater(m["strata"]["unchanged"]["R"][0][1],0.)
    def test_model_hash_mutation_rejected(self):
        m=model_fixture()["F00"];m["min_samples"]=1
        with self.assertRaises(ContractError): apply_residual_model(m,target_route="R4",extractor="F00",policy_sha=Policy().sha,sample_id="new",bin_name="unchanged",original_mu=np.zeros(2))
    def test_missing_stratum_not_fallback(self):
        m=model_fixture()["F00"]
        with self.assertRaises(ContractError): apply_residual_model(m,target_route="R4",extractor="F00",policy_sha=Policy().sha,sample_id="new",bin_name="unseen",original_mu=np.zeros(2))
    def test_covariance_stress_psd(self):
        x=np.array([5.,1.,.1,0.]);P=np.array([[1.,.1,0.,0.],[.1,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])
        _,p=perturb_prior(x,P,[10.,0.],"P_radial_scale",.25)
        self.assertGreater(np.linalg.eigvalsh(p).min(),0.)
    def test_clean_no_fake_original_snr(self):
        self.assertFalse(any(r["kind"]=="snr_delta_db" for r in stress_grid(0.)))


class EvaluationAndPipelineTest(unittest.TestCase):
    def test_zero_denominator_not_success(self):
        r=selection_summary([]);self.assertIsNone(r["rescue_rate"]);self.assertFalse(r["observed_numeric_gate"])
    def test_confusion_counts(self):
        r=selection_summary(example_rows())
        self.assertEqual((r["normal"],r["wrong"],r["false_corrections"],r["rescues"]),(2,2,1,1))
    def test_unknown_reference_kept(self):
        rows=example_rows();rows[0]["reference_valid"]=False
        self.assertEqual(selection_summary(rows)["reference_unknown"],1)
    def test_no_action_not_pass(self):
        rows=example_rows()
        for r in rows:r["selected_tap"]=r["raw_tap"]
        self.assertFalse(selection_summary(rows)["observed_numeric_gate"])
    def test_sealed_curve_forbidden(self):
        with self.assertRaises(ContractError): detection_curve(example_rows(),split="SEALED")
    def test_detection_curve_ties(self):
        r=detection_curve(example_rows(),split="CAL")
        self.assertEqual(len(r),4)
    def test_bootstrap_pair_keys(self):
        with self.assertRaises(ContractError): paired_seed_bootstrap({"a":1.},{"b":1.})
    def test_bootstrap_single_seed_inconclusive(self):
        self.assertEqual(paired_seed_bootstrap({"a":1.},{"a":1.})["status"],"INCONCLUSIVE_SUPPORT")
    def test_block_bootstrap_small_inconclusive(self):
        self.assertEqual(moving_block_bootstrap([1.,2.],block_length=2)["status"],"INCONCLUSIVE_SUPPORT")
    def test_chi_square_thresholds(self):
        for dof,expected in ((1,3.841458820694124),(2,5.991464547107979),(4,9.487729036781154)):
            self.assertAlmostEqual(chi2_threshold(.95,dof),expected,places=10)
    def test_singular_covariance_not_fake_nees(self):
        with self.assertRaises(ContractError): trajectory_metrics(np.zeros((2,4)),np.zeros((2,4,4)),np.zeros((2,4)),np.array([0.,.2]))
    def test_six_arms_independent_noop(self):
        c,_,a=case_fixture();p=Policy(wrong_cut=1e9);models=model_fixture(p)
        out=run_arms(c,a,p,models)
        for x,y in (("A","D"),("B","E"),("B","F")):
            np.testing.assert_allclose([r["x"] for r in out[x]],[r["x"] for r in out[y]],rtol=0,atol=1e-12)
        self.assertEqual(len(out),6)
    def test_calibration_no_double_sigma(self):
        c,_,a=case_fixture();p=Policy();m=model_fixture(p)
        r=ArmProcessor(c,a,p,"B",m).step(0)
        np.testing.assert_array_equal(r["R"],m["F00"]["strata"]["unchanged"]["R"])
    def test_packet_single_update_enforced(self):
        c,_,a=case_fixture();p=ArmProcessor(c,a,Policy(),"A");p.step(0)
        with self.assertRaises(ContractError): p.step(0)
    def test_e3_original_trace_fixed_mask(self):
        c,e,a=case_fixture();r=e3_one_step(c,e,a,Policy(),model_fixture())
        self.assertEqual(len(r["rows"]),len(c.t))
        self.assertTrue(all(r["fixed"]["valid"] for r in r["rows"]))
    def test_e3_missing_archive_blocked(self):
        c,e,a=case_fixture();c.baseline_trace=None
        with self.assertRaises(ContractError): e3_one_step(c,e,a,Policy(),model_fixture())
    def test_e1_and_e2_small_synthetic_interface(self):
        c,e,a=case_fixture();r=e1_detection(c,e,a,Policy());s=e2_select(c,e,a,Policy())
        self.assertEqual(set(r),{"C","P","M","PM"});self.assertEqual(len(s),9)
        self.assertEqual(r["PM"]["summary"]["corrected"],0)
    def test_history_and_confidence_interfaces(self):
        c,e,a=case_fixture()
        self.assertEqual(set(e2_history(c,e,a,Policy())),{"teacher_forced","self_updated"})
        self.assertFalse(e2_confidence(c,e,a,Policy())["probability_calibrated"])
    def test_factorial_and_residual_stage_interfaces(self):
        c,e,a=case_fixture()
        self.assertEqual(len(e3_observations(c,e,a,Policy())["rows"]),len(c.t))
        self.assertEqual(len(e3_observations(c,e,a,Policy(),decomposition=True)["rows"]),len(c.t))
    def test_stress_small_synthetic_interface(self):
        c,e,a=case_fixture(4);r=stress(c,e,a,Policy(),detect_only=True)
        self.assertGreater(len(r["one_factor_at_a_time"]),20)
        self.assertEqual(r["new_RT_calls"],0)
    def test_policy_selection_rejects_sealed(self):
        with self.assertRaises(ContractError): select_policy_from_calibration({},split="SEALED",expected_strata={"R4"})
    def test_full_e4_grid_not_faked_by_one_case(self):
        c,_,_=case_fixture()
        with self.assertRaises(ContractError): validate_trajectory_grid([c],"E4-01")
    def test_canonical_npz_roundtrip(self):
        c,e,a=case_fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);op=root/"o.npz";ep=root/"e.npz"
            np.savez(op,**{k:getattr(c,k) for k in ONLINE_ARRAYS},**{"trace_"+k:c.baseline_trace[k] for k in TRACE_FIELDS})
            np.savez(ep,clean_H=e.clean_H,truth=e.truth,t=c.t,pose_id=c.pose_id)
            spec={"online_npz":"o.npz","evaluator_npz":"e.npz","expected_rows":len(c.t),"metadata":{k:getattr(c,k) for k in META}}
            cc,ee=load_case(root,spec,{"o.npz":sha256(op),"e.npz":sha256(ep)},a)
            np.testing.assert_array_equal(cc.Hrf,c.Hrf);np.testing.assert_array_equal(ee.truth,e.truth)


class FakeClock:
    def __init__(self):self.t=0
    def clock(self):return self.t
    def sleep(self,s):self.t+=round(s*1e9)
    def sink(self,value):self.t+=1_000_000


class RuntimeTest(unittest.TestCase):
    def test_synthetic_timing_not_hardware_pass(self):
        c,_,a=case_fixture();clock=FakeClock();p=ArmProcessor(c,a,Policy(),"A")
        r=DeadlineRunner(p,clock_ns=clock.clock,sleep=clock.sleep,sink=clock.sink,synthetic_clock=True).run(arrivals(c))
        self.assertEqual(r["status"],"SYNTHETIC_TIMING_NOT_HARDWARE")
        self.assertAlmostEqual(r["latency_ms"]["p99"],1.)
    def test_duplicate_and_reorder_do_not_double_update(self):
        for fault in ("DUPLICATE","REORDER","DELAY"):
            with self.subTest(fault=fault):
                c,_,a=case_fixture();cl=FakeClock();p=ArmProcessor(c,a,Policy(),"A")
                r=DeadlineRunner(p,clock_ns=cl.clock,sleep=cl.sleep,sink=cl.sink,synthetic_clock=True).run(arrivals(c,fault))
                self.assertEqual(r["unique_outputs"],len(c.t))
                self.assertTrue(any(x["status"]=="REJECT_DUPLICATE_OR_LATE" for x in r["records"]))
    def test_dropouts_predict_without_rf_update(self):
        c,_,a=case_fixture();cl=FakeClock();p=ArmProcessor(c,a,Policy(),"A")
        r=DeadlineRunner(p,clock_ns=cl.clock,sleep=cl.sleep,sink=cl.sink,synthetic_clock=True).run(arrivals(c,"DROP_2"))
        missing=[x for x in r["records"] if x["status"]=="HOLD_NO_MEASUREMENT"]
        self.assertEqual(len(missing),2);self.assertTrue(all(not x["updated"] for x in missing))
    def test_runtime_bad_identity_rejected(self):
        c,_,a=case_fixture();cl=FakeClock();p=ArmProcessor(c,a,Policy(),"A")
        events=arrivals(c);events[0]=replace(events[0],pose_id=999)
        r=DeadlineRunner(p,clock_ns=cl.clock,sleep=cl.sleep,sink=cl.sink,synthetic_clock=True).run(events)
        self.assertEqual(r["records"][0]["status"],"REJECT_SOURCE_IDENTITY")
    def test_hardware_id_required(self):
        c,_,a=case_fixture();p=ArmProcessor(c,a,Policy(),"A")
        with self.assertRaises(ContractError): DeadlineRunner(p).run(arrivals(c))
    def test_unknown_runtime_fault_rejected(self):
        c,_,_=case_fixture()
        with self.assertRaises(ContractError): arrivals(c,"MYSTERY")



class AdditionalIntegrationTest(unittest.TestCase):
    def test_static_control_never_calls_native_prior(self):
        c,e,a=case_fixture();c=replace(c,corpus="static_g4")
        with patch.object(a,"native",side_effect=AssertionError("static prior forbidden")):
            result=e1_detection(c,e,a,Policy())
        self.assertEqual(result["P_M_PM"]["status"],"NOT_APPLICABLE_NO_CAUSAL_STATIC_PRIOR")

    def test_model_domain_mismatch_rejected(self):
        with self.assertRaises(ContractError):
            apply_residual_model(model_fixture()["F00"],target_route="R4",extractor="F00",policy_sha=Policy().sha,
                 sample_id="new",bin_name="unchanged",original_mu=np.zeros(2),domain=dict(bias="L2",channel="Full",noise_variance=0.))

    def test_fake_clock_cannot_claim_hardware(self):
        c,_,a=case_fixture();clock=FakeClock()
        with self.assertRaises(ContractError):
            DeadlineRunner(ArmProcessor(c,a,Policy(),"A"),clock_ns=clock.clock,hardware_id="pretend")

    def test_low_support_fit_not_promoted(self):
        m=fit_residual_model(np.ones((2,2)),["x","x"],["a","b"],["R2","R2"],
               target_route="R4",split="TRAIN",extractor="F00",policy_sha=Policy().sha,min_samples=20)
        self.assertEqual(m["strata"]["x"]["status"],"INSUFFICIENT_SUPPORT")

    def test_grid_metadata_120_and_240(self):
        from itertools import product
        c,_,_=case_fixture(2)
        for stage,seeds,split in (("E4-01",range(10),"TRAIN"),("E4-02",range(40,60),"SEALED")):
            cases=[replace(c,case_id=f"{r}_{b}_{h}_{s}",route=r,bias=b,channel=h,sensor_seed=s,split=split)
                   for r,b,h,s in product(("R2","R4","R5"),("B0","L2"),("Full","Native_LoS"),seeds)]
            validate_trajectory_grid(cases,stage)
            with self.assertRaises(ContractError):validate_trajectory_grid(cases+[cases[0]],stage)

    def test_ten_stage_synthetic_dispatch_artifact_roundtrip(self):
        import shutil
        import qclean_uwb.fp_sc.followup.runner as runner_module
        source_root=Path(runner_module.__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for relative in code_paths(source_root):
                dst=root/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source_root/relative,dst)
            for relative in runner_module.SOURCES_REQUIRED:
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("SYNTHETIC_TEST_STAND_IN_NOT_EXECUTED\n")
            inputs={};specs={}
            for route,split in (("R2","TRAIN"),("R4","SYNTHETIC"),("R5","TRAIN")):
                c,e,a=case_fixture(4,route,split);op=root/(route+"_online.npz");ep=root/(route+"_eval.npz")
                np.savez(op,**{k:getattr(c,k) for k in ONLINE_ARRAYS},**{"trace_"+k:c.baseline_trace[k] for k in TRACE_FIELDS})
                np.savez(ep,clean_H=e.clean_H,truth=e.truth,t=c.t,pose_id=c.pose_id)
                inputs[op.name]=sha256(op);inputs[ep.name]=sha256(ep)
                specs[c.case_id]=dict(online_npz=op.name,evaluator_npz=ep.name,expected_rows=4,metadata={k:getattr(c,k) for k in META})
            for bank in ("LP_plus45_bank.npz","LP_minus45_bank.npz"):
                (root/bank).write_text("SYNTHETIC_STAND_IN_NOT_FFD\n");inputs[bank]=sha256(root/bank)
            prerequisite_path=root/"parent.json"
            write_json(prerequisite_path,dict(study_id="FP-SC-001",stage="E1-01",execution_status="COMPLETE",
                      numerical_qa_pass=True,scientific_gate="PASS",scope="SYNTHETIC_ONLY"))
            inputs[prerequisite_path.name]=sha256(prerequisite_path)
            stages=list(STAGES[:10]);policy=Policy()
            config={s:dict(case_ids=["synthetic_R4"]) for s in stages}
            config["E3-03"].update(calibration_case_ids=["synthetic_R2","synthetic_R5"],min_samples=2)
            manifest=dict(schema="FP_SC_FOLLOWUP_STUDY_V1",code_files={r:sha256(root/r) for r in code_paths(root)},
                 input_files=inputs,baseline_sources={r:sha256(root/r) for r in runner_module.SOURCES_REQUIRED},
                 environment={"python":platform.python_version(),"numpy":np.__version__},policy=asdict(policy),
                 policy_sha256=policy.sha,mapping_reviewed=True,cases=specs,stage_config=config,
                 prerequisite_receipts={"E1-01":"parent.json"})
            mp=root/"manifest.json";ap=root/"approval.json";write_json(mp,manifest)
            approval=dict(execute_science=True,manifest_sha256=sha256(mp),code_lock_sha256=digest(manifest["code_files"]),
                    stages=stages,actor="SYNTHETIC_TEST_ONLY",issued_utc="2026-11-05T00:00:00Z",
                    exploratory_after_nonpass=stages,optional_stages=[])
            write_json(ap,approval)
            with patch.object(runner_module,"OriginalAdapter",return_value=SyntheticAdapter()), \
                 patch.object(runner_module,"__file__",str(root/"src/qclean_uwb/fp_sc/followup/runner.py")):
                receipt=run(root,mp,ap,root/"output",stages)
            from qclean_uwb.fp_sc.followup.audit import audit_directory
            checked=audit_directory(root/"output")
            self.assertGreater(checked["checks"]["summaries"],0)
            self.assertFalse(checked["external_independent_accept"])
            self.assertEqual(receipt["status"],"COMPLETE_TECHNICAL_ONLY")
            self.assertEqual(len(receipt["stages"]),10)
            self.assertFalse(receipt["external_independent_accept"])
            for stage in stages:
                r=json.loads((root/"output"/stage/"STAGE_RECEIPT.json").read_text())
                self.assertEqual(r["scientific_gate"],"HOLD_RESULT_REVIEW")
                self.assertEqual(r["execution_status"],"COMPLETE")



class StoredAuditTest(unittest.TestCase):
    def test_independent_joseph_checker(self):
        from qclean_uwb.fp_sc.followup.audit import check_update
        c,_,a=case_fixture();record=ArmProcessor(c,a,Policy(),"A").step(0)
        self.assertLessEqual(check_update(record)["max_normalized_error"],1e-10)
    def test_bad_posterior_detected(self):
        from qclean_uwb.fp_sc.followup.audit import check_update
        c,_,a=case_fixture();record=ArmProcessor(c,a,Policy(),"A").step(0);record["P"][0,0]+=1.
        with self.assertRaises(ValueError):check_update(record)
    def test_summary_denominator_detected(self):
        from qclean_uwb.fp_sc.followup.audit import check_denominators
        rows=example_rows();summary=selection_summary(rows);summary["wrong"]+=1
        with self.assertRaises(ValueError):check_denominators(rows,summary)
    def test_artifact_hash_mutation_detected(self):
        from qclean_uwb.fp_sc.followup.audit import audit_directory
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);f=p/"payload.txt";f.write_text("first");write_json(p/"ARTIFACT_HASHES.json",{"payload.txt":sha256(f)})
            f.write_text("changed")
            with self.assertRaises(ValueError):audit_directory(p)

if __name__ == "__main__":unittest.main()
