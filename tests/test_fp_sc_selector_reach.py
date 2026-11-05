"""Synthetic calls of the real selector, never E1-02/E2 stage dispatch."""
import json,unittest,subprocess,pathlib,types,sys
from dataclasses import asdict,replace
from unittest.mock import patch
import numpy as np
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter, RECIPE_SHA
from qclean_uwb.fp_sc.followup.contracts import Policy, Support, STEP_M, ContractError, digest
from qclean_uwb.fp_sc.followup import selection as s

def wave(x):
    c=np.zeros((1028,2),complex);c[:len(x),0]=x;return c
def evidence(x=None):
    return RevisionEvidenceAdapter().evidence(wave(x or [0,.1,.2,.3,.5,.7,.9,1,.5,0]))
def binding(e,p):
    i=json.loads(e.bridge_identity_json)
    return s.SelectionBinding(i['arm'],i['mode'],i['candidate_config_sha256'],RECIPE_SHA,p.sha)
def probe(e,p):return s.SyntheticSelectionProbe(binding(e,p),digest(asdict(e)))
def support(tap):return Support(tap*STEP_M,tap*STEP_M,.02,'SYNTHETIC_TEST_ONLY')

class SelectorReachTests(unittest.TestCase):
    def test_legacy_decisions_exactly_match_pinned_selector(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        code=subprocess.check_output(['git','show','486f0b6c008e7a953ada75a03a941ffa46994985:src/qclean_uwb/fp_sc/followup/selection.py'],cwd=root)
        name='qclean_uwb.fp_sc.followup._reach_legacy_reference'
        old=types.ModuleType(name);old.__package__='qclean_uwb.fp_sc.followup'
        sys.modules[name]=old;exec(compile(code,name,'exec'),old.__dict__)
        rng=np.random.default_rng(192731)
        for i in range(200):
            cs=tuple(s.Candidate(n,float(rng.uniform(-1,1)),float(rng.uniform(0,1)),(n%3,),bool(rng.integers(2))) for n in range(10,16))
            e=s.Evidence(12,cs[2].signed_s,True,i%17==0,cs,'SYNTHETIC_LEGACY')
            prior=support(int(rng.integers(10,16)));motion=support(int(rng.integers(10,16)))
            for mode in ('B0','C','P','M','PM'):
                kw=dict(prior=None if i%7==0 else prior,motion=None if i%11==0 else motion)
                self.assertEqual(asdict(s.select(e,mode,Policy(),**kw)),asdict(old.select(e,mode,Policy(),**kw)))
    def call(self,e,mode='PM',p=Policy(),prior=None,motion=None):
        trace=[]
        d=s.select(e,mode,p,prior=prior,motion=motion,synthetic_probe=probe(e,p),candidate_trace=trace.append)
        self.assertEqual(len(trace),1)
        return d,trace[0]
    def test_real_selector_uses_shared_set_and_selects_edge_plus_two(self):
        e=evidence();p=Policy();prior=support(5)
        with patch.object(s,'prepare_candidate_set',wraps=s.prepare_candidate_set) as shared:
            d,t=self.call(e,prior=prior,motion=prior);self.assertEqual(shared.call_count,1)
        self.assertIn(5,t['eligible_taps']);self.assertEqual(d.selected_tap,5)
        self.assertEqual(d.action,'REPLACE_SUPPORTED');self.assertEqual(d.reason,'SUPPORTED')
        self.assertLess(next(c.legacy_support for c in e.candidates if c.tap==5),.15)
    def test_real_selector_selects_left_rise_candidate(self):
        e=evidence([0,.1,.2,.35,.5,.48,.7,1,.2,0]);prior=support(2)
        d,t=self.call(e,prior=prior,motion=prior)
        self.assertIn(2,t['eligible_taps']);self.assertEqual(d.selected_tap,2)
        self.assertEqual(d.action,'REPLACE_SUPPORTED')
    def test_low_rf_score_does_not_remove_valid_candidate(self):
        e=evidence([0,.03,.05,.08,.1,.05,0,0,.3,.6,1,0]);prior=support(4)
        self.assertLess(next(c.support for c in e.candidates if c.tap==4),.15)
        d,t=self.call(e,prior=prior,motion=prior)
        self.assertIn(4,t['eligible_taps']);self.assertEqual(d.selected_tap,4)
        self.assertEqual(d.reason,'SUPPORTED')
    def test_prior_and_history_holds_are_not_candidate_exclusion(self):
        e=evidence()
        for prior,reason in ((None,'HOLD_PRIOR'),(support(5),'HOLD_HISTORY')):
            d,t=self.call(e,prior=prior)
            self.assertEqual(d.reason,reason);self.assertEqual(t['stage'],'NOT_REACHED')
    def test_invalid_and_overflow_hold(self):
        for c,reason in ((np.zeros((1028,2),complex),'ORIGINAL_INVALID'),
            (wave(np.tile([0,.2,.4,.6,.8,1,.4,0],100)),'CANDIDATE_OVERFLOW')):
            e=RevisionEvidenceAdapter().evidence(c);d,t=self.call(e,mode='C')
            self.assertEqual(d.reason,reason);self.assertEqual(t['stage'],'NOT_REACHED')
            built=s.prepare_candidate_set(e,'C',Policy(),binding=binding(e,Policy()))
            self.assertEqual(built.eligible,());self.assertEqual(built.status,reason)
    def test_unsupported_and_invalid_s_never_enter_actual_set(self):
        for changes in (dict(supported=False,selection_eligible=False),
                        dict(polarization_valid=False,selection_eligible=False,source_signed_s=None,signed_s=0.)):
            e=evidence();e=replace(e,candidates=tuple(replace(c,**changes) if c.tap==5 else c for c in e.candidates))
            d,t=self.call(e,prior=support(5),motion=support(5))
            self.assertNotIn(5,t['eligible_taps']);self.assertNotEqual(d.selected_tap,5)
    def test_same_group_and_cross_group_ties_abstain(self):
        for distinct in (False,True):
            e=evidence();cs=[]
            for c in e.candidates:
                if c.tap in (e.raw_tap,5,7):
                    cs.append(replace(c,support=.8,groups=(1 if distinct and c.tap==7 else 0,)) if c.tap!=e.raw_tap else c)
            e=replace(e,candidates=tuple(cs));prior=Support(5*STEP_M,7*STEP_M,.02,'SYNTHETIC_TEST_ONLY')
            d,t=self.call(e,prior=prior,motion=prior)
            self.assertEqual(d.reason,'ABSTAIN_AMBIGUOUS');self.assertEqual(d.selected_tap,e.raw_tap)
    def test_raw_only_support_does_not_enter_eligible(self):
        e=evidence();e=replace(e,candidates=tuple(replace(c,supported=False,selection_eligible=False,support=0.) if c.tap==e.raw_tap else c for c in e.candidates))
        built=s.prepare_candidate_set(e,'C',Policy(),binding=binding(e,Policy()))
        self.assertIn(e.raw_tap,[r['tap'] for r in built.rows]);self.assertNotIn(e.raw_tap,[r['tap'] for r in built.eligible])
    def test_versions_and_policy_fail_closed(self):
        e=evidence();p=Policy();b=binding(e,p)
        for bad in (None,replace(b,arm='VB'),replace(b,mode='STRONGEST_ONLY'),replace(b,candidate_config_sha256='a'*64),
                    replace(b,bridge_recipe_sha256='a'*64),replace(b,policy_sha256='a'*64),replace(b,selector_recipe='OLD')):
            with self.assertRaises(ContractError):s.prepare_candidate_set(e,'C',p,binding=bad)
    def test_boolean_cannot_enable_real_selector_or_history(self):
        e=replace(evidence(),selector_ready=True)
        with self.assertRaises(ContractError):s.select(e,'C',Policy())
        with self.assertRaises(ContractError):s.TrustedHistory().observe(e,None,0,0,None,Policy())
    def test_missing_identity_or_forged_eligibility_rejected(self):
        e=evidence();p=Policy()
        with self.assertRaises(ContractError):s.prepare_candidate_set(replace(e,bridge_identity_json=None),'C',p)
        bad=replace(e,candidates=tuple(replace(c,supported=False,selection_eligible=True) for c in e.candidates))
        with self.assertRaises(ContractError):s.prepare_candidate_set(bad,'C',p,binding=binding(e,p))
    def test_probe_binding_and_negative_control_cannot_bypass(self):
        e=evidence();p=Policy()
        for bad in (replace(probe(e,p),evidence_sha256='a'*64),replace(probe(e,p),purpose='REAL_RUN')):
            with self.assertRaises(ContractError):s.select(e,'C',p,synthetic_probe=bad)
        for mode in ('PM-FORCE','NN-HARD'):
            with self.assertRaises(ContractError):s.select(e,mode,p,synthetic_probe=probe(e,p))
    def test_same_set_for_C_P_M_PM_when_context_ready(self):
        e=evidence();p=Policy();expected={c.tap for c in e.candidates if c.selection_eligible}
        for mode in ('C','P','M','PM'):
            d,t=self.call(e,mode=mode,prior=support(5),motion=support(5))
            self.assertEqual(set(t['eligible_taps']),expected)

if __name__=='__main__':unittest.main()
