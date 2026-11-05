"""Synthetic preparation tests; no stage dispatch or real RF evaluation."""
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.contracts import Policy, Support, STEP_M, ContractError
from qclean_uwb.fp_sc.followup.detection import detect, detection_loop, RawDetectionHistory
from qclean_uwb.fp_sc.followup.selection import select, TrustedHistory


class DetectionPreparationTests(unittest.TestCase):
    def setUp(self):
        cir = np.zeros((1028, 2), complex)
        cir[:10, 0] = [0,.1,.2,.3,.5,.7,.9,1,.5,0]
        self.e = RevisionEvidenceAdapter().evidence(cir)
        self.p = Policy()
        self.support = Support(5*STEP_M, 5*STEP_M, .02, 'SYNTHETIC')

    def test_candidate_can_win_but_never_replaces_raw(self):
        d, s = detect(self.e, 'PM', self.p, prior=self.support, motion=self.support)
        self.assertEqual(s.eligible[0]['tap'], 5)
        self.assertNotEqual(self.e.raw_tap, 5)
        self.assertEqual(d.selected_tap, self.e.raw_tap)
        self.assertEqual(d.action, 'KEEP_ORIGINAL')
        self.assertEqual(d.wrong_score, next(r['score'] for r in s.rows if r['tap']==self.e.raw_tap))

    def test_holds_have_no_detection_score(self):
        for mode, prior, reason in [('P',None,'HOLD_PRIOR'),('PM',self.support,'HOLD_HISTORY')]:
            d,_ = detect(self.e, mode, self.p, prior=prior)
            self.assertEqual(d.reason, reason)
            self.assertIsNone(d.wrong_score)

    def test_forced_and_e2_modes_rejected(self):
        for mode in ('PM-FORCE','NN-HARD','B0','E2'):
            with self.assertRaises(ContractError): detect(self.e,mode,self.p)

    def test_general_selector_and_history_stay_locked(self):
        with self.assertRaises(ContractError): select(self.e,'C',self.p)
        with self.assertRaises(ContractError):
            TrustedHistory().observe(self.e,detect(self.e,'C',self.p)[0],0,0,self.support,self.p)

    def test_new_ranking_not_used_as_history_confidence(self):
        e=replace(self.e,candidates=tuple(replace(c,support=1.,legacy_support=0.) for c in self.e.candidates))
        history=RawDetectionHistory()
        support=Support(e.raw_tap*STEP_M,e.raw_tap*STEP_M,.02,'SYNTHETIC')
        for k in range(3):
            history.advance(float(k),k,0,self.p)
            history.observe_raw(e,float(k),0,support,self.p)
        self.assertIsNone(history.detector_m)

    def test_raw_history_bootstrap_and_expiry(self):
        e=replace(self.e,candidates=tuple(replace(c,legacy_support=1.) for c in self.e.candidates))
        support=Support(e.raw_tap*STEP_M,e.raw_tap*STEP_M,.02,'SYNTHETIC')
        history=RawDetectionHistory()
        for k in range(2):
            history.advance(float(k),k,0,self.p)
            history.observe_raw(e,float(k),0,support,self.p)
        self.assertEqual(history.detector_m,e.raw_tap*STEP_M)
        self.assertIsNone(history.support(10.,0,self.p))

    def test_loop_never_calls_selector_filter_or_native_for_c(self):
        case=SimpleNamespace(corpus='dynamic',t=np.arange(3.),pose_id=np.arange(3),
             Hrf=np.ones((3,257,2),complex),noise_variance=0.)
        adapter=SimpleNamespace(evidence=lambda *args:self.e,native=lambda *args:(_ for _ in ()).throw(AssertionError()))
        with patch('qclean_uwb.fp_sc.followup.selection.select',side_effect=AssertionError), \
             patch('qclean_uwb.fp_sc.followup.engine.open_loop',side_effect=AssertionError), \
             patch('qclean_uwb.fp_sc.followup.numerics.update',side_effect=AssertionError):
            rows=detection_loop(case,adapter,self.p,'C')
        self.assertEqual(len(rows),3)
        for r in rows: self.assertEqual(r['decision'].selected_tap,self.e.raw_tap)

    def test_static_no_temporal_mapping(self):
        with self.assertRaises(ContractError):
            detection_loop(SimpleNamespace(corpus='static_g4'),None,self.p,'PM')

    def test_non_vab_rejected(self):
        import json
        identity=json.loads(self.e.bridge_identity_json);identity['arm']='VA'
        with self.assertRaises(ContractError):
            detect(replace(self.e,bridge_identity_json=json.dumps(identity)),'C',self.p)

    def test_detection_truth_preserves_three_columns_without_guessing_bias(self):
        from qclean_uwb.fp_sc.followup.study import Evaluator
        case=SimpleNamespace(t=np.arange(2.))
        truth=np.zeros((2,3));los=np.ones((2,257,2),complex)
        ev=Evaluator(case,los,truth,None,detection_only=True)
        self.assertTrue(np.array_equal(ev.truth,truth))
        with self.assertRaises(ContractError): ev.label([],detect_only=False)
        with self.assertRaises(ContractError): Evaluator(case,los,truth,None)

    def test_pm_loop_causal_raw_only_and_no_selection(self):
        case=SimpleNamespace(corpus='dynamic',t=np.arange(4.)*.2,pose_id=np.arange(4),
            Hrf=np.ones((4,257,2),complex),noise_variance=0.,ds=np.zeros(4),
            prior=np.zeros((4,4)),Pprior=np.tile(np.eye(4)[None]*.001,(4,1,1)))
        e=replace(self.e,candidates=tuple(replace(c,legacy_support=1.) for c in self.e.candidates))
        def native(states):
            v=np.full(7,e.raw_tap*STEP_M)+states[:,0]
            return v,v
        adapter=SimpleNamespace(evidence=lambda *args:e,native=native)
        with patch('qclean_uwb.fp_sc.followup.selection.select',side_effect=AssertionError), \
             patch.object(TrustedHistory,'observe',side_effect=AssertionError):
            before=detection_loop(case,adapter,self.p,'PM')
            case.prior[-1,0]=100
            after=detection_loop(case,adapter,self.p,'PM')
        self.assertEqual(before[0]['decision'].reason,'HOLD_HISTORY')
        for a,b in zip(before[:-1],after[:-1]): self.assertEqual(a['decision'],b['decision'])
        for r in before: self.assertEqual(r['decision'].selected_tap,e.raw_tap)
        self.assertEqual(before[2]['history']['detector_m'],e.raw_tap*STEP_M)

class MappingAuthorizationTests(unittest.TestCase):
    def test_boolean_cannot_replace_mapping_evidence(self):
        import tempfile,json,platform
        from pathlib import Path
        from qclean_uwb.fp_sc.followup.contracts import authorize,sha256,digest
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);m=root/'manifest.json';a=root/'approval.json';p=Policy()
            (root/'fixture.txt').write_text('SYNTHETIC_TEST_ONLY')
            lock={'fixture.txt':sha256(root/'fixture.txt')}
            manifest=dict(schema='FP_SC_FOLLOWUP_STUDY_V1',execution_profile='VAB_DETECTION_ONLY_R1',
                policy=__import__('dataclasses').asdict(p),policy_sha256=p.sha,
                environment=dict(python=platform.python_version(),numpy=np.__version__),
                mapping_reviewed=True,code_files=lock,input_files=lock)
            m.write_text(json.dumps(manifest))
            a.write_text(json.dumps(dict(execute_science=True,manifest_sha256=sha256(m),
                stages=['E1-02'],actor='SYNTHETIC_UNIT_TEST',issued_utc='SYNTHETIC',code_lock_sha256=digest(lock))))
            with self.assertRaisesRegex(ContractError,'MAPPING_EVIDENCE_NOT_LOCKED'):
                authorize(root,m,a,['E1-02'],['fixture.txt'])

    def test_vab_profile_rejects_e2_even_with_synthetic_approval(self):
        import tempfile,json,platform
        from pathlib import Path
        from dataclasses import asdict
        from qclean_uwb.fp_sc.followup.contracts import authorize,sha256,digest
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);m=root/'manifest.json';a=root/'approval.json';p=Policy()
            (root/'fixture.txt').write_text('SYNTHETIC_TEST_ONLY')
            lock={'fixture.txt':sha256(root/'fixture.txt')}
            m.write_text(json.dumps(dict(schema='FP_SC_FOLLOWUP_STUDY_V1',execution_profile='VAB_DETECTION_ONLY_R1',
                policy=asdict(p),policy_sha256=p.sha,environment=dict(python=platform.python_version(),numpy=np.__version__),
                mapping_reviewed=True,code_files=lock,input_files=lock)))
            a.write_text(json.dumps(dict(execute_science=True,manifest_sha256=sha256(m),
                stages=['E2-01'],actor='SYNTHETIC_UNIT_TEST',issued_utc='SYNTHETIC',code_lock_sha256=digest(lock))))
            with self.assertRaisesRegex(ContractError,'VAB_DETECTION_SINGLE_STAGE_ONLY'):
                authorize(root,m,a,['E2-01'],['fixture.txt'])

if __name__ == '__main__': unittest.main()
