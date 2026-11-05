import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from qclean_uwb.fp_sc.followup.integrity import PriorIntegrity, assess_prior
from qclean_uwb.fp_sc.followup.detection import prepare_detection, detect, RawDetectionHistory, detection_loop
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.contracts import Policy, Support, ContractError


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        cir = np.zeros((1028, 2), complex)
        cir[:10, 0] = [0,.1,.2,.3,.5,.7,.9,1,.5,0]
        self.e = RevisionEvidenceAdapter().evidence(cir)
        self.p = Policy()
        self.s = Support(100., 100.3, .15, 'SYNTHETIC_WRONG_PRIOR')

    def test_small_covariance_cannot_prove_validity(self):
        for scale in (0., .00001, 1.):
            self.assertEqual(assess_prior(np.zeros(4),np.eye(4)*scale,0.).state,'UNKNOWN')

    def test_bad_structure_is_invalid(self):
        for x,P,t,prev in [(np.full(4,np.nan),np.eye(4),0.,None),
                            (np.zeros(4),-np.eye(4),0.,None),
                            (np.zeros(4),np.eye(4),float('nan'),None),
                            (np.zeros(4),np.eye(4),1.,1.),
                            (np.zeros(4),np.eye(4),0.,1.)]:
            self.assertEqual(assess_prior(x,P,t,prev).state,'INVALID')

    def test_valid_string_and_boolean_cannot_bypass(self):
        with self.assertRaisesRegex(ContractError,'PROVIDER_NOT_IMPLEMENTED'):
            PriorIntegrity('VALID','REVIEWED','SPOOF')
        for value in (True,{'state':'VALID'},SimpleNamespace(state='VALID')):
            with self.assertRaises(ContractError):
                prepare_detection(self.e,'P',self.p,prior=self.s,integrity=value)

    def test_large_diagnostic_never_becomes_active_score(self):
        for state in (PriorIntegrity(),PriorIntegrity('INVALID','BAD_TIME')):
            for mode in ('P','M','PM'):
                p=prepare_detection(self.e,mode,self.p,prior=self.s,motion=self.s,integrity=state)
                self.assertEqual(p.effective_mode,'HOLD')
                self.assertIsNone(p.active_wrong_score)
                self.assertGreater(min(r['score'] for r in p.diagnostic.rows),100)
                self.assertEqual({r['tap'] for r in p.active.eligible},
                                 {c.tap for c in self.e.candidates if c.selection_eligible})
                d,_=detect(self.e,mode,self.p,prior=self.s,motion=self.s,integrity=state)
                self.assertEqual(d.selected_tap,self.e.raw_tap)
                self.assertIsNone(d.wrong_score)

    def test_c_is_invariant_to_wrong_context(self):
        a=prepare_detection(self.e,'C',self.p)
        b=prepare_detection(self.e,'C',self.p,prior=self.s,motion=self.s,
                            integrity=PriorIntegrity('INVALID','BAD'))
        self.assertEqual(a.active,b.active)
        self.assertEqual(a.active_wrong_score,b.active_wrong_score)

    def test_seeded_history_is_cleared_before_use(self):
        for state in (PriorIntegrity(),PriorIntegrity('INVALID','CONFLICT')):
            h=RawDetectionHistory(t=0.,detector_m=10.,offset_m=4.,streak=10)
            self.assertIsNone(h.support(.2,100.,self.p,integrity=state))
            self.assertIsNone(h.t);self.assertIsNone(h.detector_m)
            self.assertEqual(h.offset_m,0.);self.assertEqual(h.streak,0)

    def test_bootstrap_and_refresh_are_blocked_after_recovery(self):
        h=RawDetectionHistory(t=0.,detector_m=10.,streak=8)
        for k,state in enumerate((PriorIntegrity('INVALID','BAD'),PriorIntegrity(),PriorIntegrity())):
            h.advance(float(k),k,0.,self.p)
            h.observe_raw(self.e,float(k),0.,self.s,self.p,integrity=state)
            self.assertIsNone(h.detector_m);self.assertEqual(h.streak,0)

    def test_stale_gap_and_reversed_history(self):
        h=RawDetectionHistory(t=0.,detector_m=10.)
        self.assertIsNone(h.support(100.,0.,self.p))
        h.advance(10.,10,0.,self.p)
        with self.assertRaises(ContractError):h.advance(9.,9,0.,self.p)

    def test_pm_loop_no_truth_selection_or_filter(self):
        c=SimpleNamespace(corpus='dynamic',t=np.arange(3.),pose_id=np.arange(3),
            Hrf=np.ones((3,257,2),complex),noise_variance=0.,ds=np.zeros(3),
            prior=np.zeros((3,4)),Pprior=np.tile(np.eye(4),(3,1,1)),truth='UNUSED')
        adapter=SimpleNamespace(evidence=lambda *a:self.e,native=lambda x:(np.ones(7),np.ones(7)))
        with patch('qclean_uwb.fp_sc.followup.selection.select',side_effect=AssertionError), \
             patch('qclean_uwb.fp_sc.followup.numerics.update',side_effect=AssertionError):
            a=detection_loop(c,adapter,self.p,'PM')
            c.truth='CHANGED';c.prior[-1]=100
            b=detection_loop(c,adapter,self.p,'PM')
        for x,y in zip(a[:-1],b[:-1]):
            self.assertEqual(asdict(x['decision']),asdict(y['decision']))
        for r in a:
            self.assertEqual(r['effective_mode'],'HOLD')
            self.assertIsNone(r['history']['detector_m'])
            self.assertEqual(r['decision'].selected_tap,self.e.raw_tap)

    def test_invalid_prior_skips_native_model(self):
        c=SimpleNamespace(corpus='dynamic',t=np.array([0.]),pose_id=np.array([0]),
            Hrf=np.ones((1,257,2),complex),noise_variance=0.,ds=np.zeros(1),
            prior=np.full((1,4),np.nan),Pprior=np.eye(4)[None])
        adapter=SimpleNamespace(evidence=lambda *a:self.e,native=lambda *a:self.fail('MODEL_CALLED'))
        r=detection_loop(c,adapter,self.p,'PM')[0]
        self.assertEqual(r['prior_integrity']['state'],'INVALID')
        self.assertIsNone(r['decision'].wrong_score)

    def test_evaluator_preserves_integrity_and_does_not_promote_diagnostics(self):
        from qclean_uwb.fp_sc.followup.study import Evaluator
        from qclean_uwb.fp_sc.followup.numerics import factorial
        c=SimpleNamespace(case_id='SYNTHETIC',t=np.array([0.]))
        adapter=SimpleNamespace(evidence=lambda *a:self.e)
        ev=Evaluator(c,np.ones((1,257,2),complex),np.zeros((1,3)),adapter,detection_only=True)
        d,_=detect(self.e,'P',self.p,prior=self.s)
        item=dict(k=0,pose_id=0,t=0.,evidence=self.e,decision=d,history={},
                  prior_support=asdict(self.s),motion_support=None,
                  observation=factorial(np.ones((1028,2),complex),self.e.raw_tap,self.e.raw_tap),
                  prior_integrity=asdict(PriorIntegrity()),effective_mode='HOLD',
                  diagnostic_only_scores=({'score':999.},),diagnostic_only_prior_scores=({'p':99.},),
                  diagnostic_status='BUILT')
        row=ev.label([item],detect_only=True)[0]
        self.assertIsNone(row['flag']);self.assertIsNone(row['wrong_score'])
        self.assertEqual(row['diagnostic_only_scores'],({'score':999.},))
        self.assertEqual(row['effective_mode'],'HOLD')
        self.assertEqual(row['prior_integrity']['state'],'UNKNOWN')

    def test_complete_mapping_receipt_still_cannot_claim_valid_provider(self):
        import tempfile,json,platform
        from pathlib import Path
        from qclean_uwb.fp_sc.followup.contracts import authorize,sha256,digest
        from qclean_uwb.fp_sc.followup.integrity import INTEGRITY_RECIPE
        from qclean_uwb.fp_sc.followup.detection import HISTORY_RECIPE
        from qclean_uwb.fp_sc.followup.bridge import RECIPE_SHA
        from qclean_uwb.fp_sc.followup.selection import SELECTOR_SET_RECIPE
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'fixture').write_text('SYNTHETIC_ONLY')
            lock={'fixture':sha256(root/'fixture')}
            mapping=dict(status='PASS_DYNAMIC_MAPPING_REVIEW',policy_sha256=self.p.sha,
                candidate_mode='TWO_PORT_UNION',arm='VAB',bridge_recipe_sha256=RECIPE_SHA,
                selector_recipe=SELECTOR_SET_RECIPE,history_recipe=HISTORY_RECIPE,
                integrity_recipe=INTEGRITY_RECIPE,code_lock_sha256=digest(lock),
                baseline_source_lock_sha256=digest({}),case_payload_lock_sha256=digest({}),
                evidence_files=lock,reviewer='SYNTHETIC_ONLY',provider_ready=True)
            (root/'mapping.json').write_text(json.dumps(mapping))
            manifest=dict(schema='FP_SC_FOLLOWUP_STUDY_V1',execution_profile='VAB_DETECTION_ONLY_R1',
                candidate_mode='TWO_PORT_UNION',policy=asdict(self.p),policy_sha256=self.p.sha,
                environment=dict(python=platform.python_version(),numpy=np.__version__),
                mapping_reviewed=True,mapping_receipt='mapping.json',code_files=lock,
                input_files={**lock,'mapping.json':sha256(root/'mapping.json')},cases={})
            (root/'manifest.json').write_text(json.dumps(manifest))
            (root/'approval.json').write_text(json.dumps(dict(execute_science=True,
                manifest_sha256=sha256(root/'manifest.json'),stages=['E1-02'],actor='SYNTHETIC_ONLY',
                issued_utc='SYNTHETIC',code_lock_sha256=digest(lock))))
            with self.assertRaisesRegex(ContractError,'HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING'):
                authorize(root,root/'manifest.json',root/'approval.json',['E1-02'],['fixture'])


if __name__=='__main__': unittest.main()
