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


if __name__=='__main__': unittest.main()
