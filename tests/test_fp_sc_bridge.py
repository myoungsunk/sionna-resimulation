import copy
import json
import math
import unittest
from dataclasses import asdict, replace
from unittest.mock import Mock
import numpy as np
from qclean_uwb.fp_sc.candidate_revision import generate_revision
from qclean_uwb.fp_sc.candidates import CandidateConfig
from qclean_uwb.fp_sc.followup.bridge import (BridgeConfig, RevisionEvidenceAdapter, adapt_pool, candidate_config_sha)
from qclean_uwb.fp_sc.followup.contracts import ContractError, Policy
from qclean_uwb.fp_sc.followup.engine import OriginalAdapter
from qclean_uwb.fp_sc.followup.selection import from_pool, select, TrustedHistory

def wave(x, y=()):
    c = np.zeros((1028,2),complex); c[:len(x),0]=x; c[:len(y),1]=y
    return c

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.c = wave([0,.1,.2,.3,.5,.7,.9,1,.5,0])
    def bridge(self, cir=None, arm='VAB', config=CandidateConfig()):
        p=generate_revision(self.c if cir is None else cir,arm,config)['TWO_PORT_UNION']
        cfg=BridgeConfig(arm,p['mode'],candidate_config_sha(arm,p['config']))
        return p,adapt_pool(p,cfg),cfg
    def test_edge_plus_two_is_eligible(self):
        p,e,_=self.bridge(); c=next(c for c in e.candidates if c.tap==5)
        self.assertTrue(c.selection_eligible); self.assertLess(c.legacy_support,.15)
        self.assertAlmostEqual(c.support,.7); self.assertAlmostEqual(c.legacy_support,math.exp(-2))
    def test_left_rise_not_bilateral_score(self):
        p,e,_=self.bridge(wave([0,.1,.2,.35,.5,.48,.7,1,.2,0]))
        c=next(c for c in e.candidates if c.tap==2)
        self.assertTrue(c.selection_eligible);self.assertAlmostEqual(c.support,.2)
        self.assertLess(c.legacy_support,.15)
        self.assertTrue(any(s['support_kind']=='LEFT_RISE' for s in json.loads(c.support_records_json)))
    def test_all_modes_and_arms(self):
        for arm in ('V0','VA','VB','VAB'):
            for mode,p in generate_revision(self.c,arm).items():
                e=adapt_pool(p,BridgeConfig(arm,mode,candidate_config_sha(arm,p['config'])))
                self.assertEqual([c.tap for c in e.candidates],p['candidate_taps'])
                self.assertEqual([c.tap for c in e.candidates if c.supported],p['supported_taps'])
                self.assertEqual(json.loads(e.bridge_identity_json)['raw_json'],p['raw'])
    def test_null_port_phase_flag(self):
        p,e,_=self.bridge(); self.assertTrue(all(not c.phase_available for c in e.candidates))
        live=RevisionEvidenceAdapter().evidence(self.c)
        self.assertTrue(all(c.phase_available and c.signed_s==1 for c in live.candidates))
    def test_two_rx_provenance(self):
        p,e,_=self.bridge(wave([0,.1,.3,.6,1,.4,0],[0,.3,.7,1,.4,.1,0]))
        for r,c in zip(p['candidates'],e.candidates):
            self.assertEqual(json.loads(c.support_records_json),r['support_records'])
            self.assertEqual(list(c.groups),r['group_ids'])
    def test_zero_nonfinite_and_noise(self):
        bad=self.c.copy();bad[0,1]=np.nan
        for cir,cfg in ((wave([]),CandidateConfig()),(bad,CandidateConfig()),
                        (wave([0,.01,.03,.01,0]),CandidateConfig(noise_var_per_bin=1.))):
            p,e,_=self.bridge(cir,config=cfg);self.assertFalse(e.valid);self.assertEqual(e.candidates,())
    def test_overflow_not_truncated(self):
        p,e,_=self.bridge(wave(np.tile([0,.2,.4,.6,.8,1,.4,0],100)))
        self.assertTrue(e.overflow);self.assertGreater(len(e.candidates),64)
        self.assertFalse(any(c.selection_eligible for c in e.candidates))
    def test_64_65_boundary(self):
        p,_,cfg=self.bridge(); template=copy.deepcopy(p['candidates'][0])
        for count in (64,65):
            q=copy.deepcopy(p);q['candidates']=[]
            for n in range(count):
                r=copy.deepcopy(template);r['tap']=n;q['candidates'].append(r)
            q['candidate_taps']=list(range(count));q['overflow']=count>64
            e=adapt_pool(q,cfg);self.assertEqual(sum(c.selection_eligible for c in e.candidates),64 if count==64 else 0)
    def test_raw_only_preserved(self):
        p,_,cfg=self.bridge();r=next(r for r in p['candidates'] if r['tap']==p['raw']['tap'])
        r.update(supported=False,support_records=[],group_ids=[],lobe_ids=[],support_ports=[])
        e=adapt_pool(p,cfg);c=next(c for c in e.candidates if c.tap==e.raw_tap)
        self.assertFalse(c.selection_eligible);self.assertEqual(c.exclusion_reason,'NO_CIR_SUPPORT')
    def test_invalid_polarization_explicit(self):
        p,_,cfg=self.bridge();r=next(r for r in p['candidates'] if r['tap']!=p['raw']['tap'])
        r.update(signed_s=None,polarization_valid=False,supported=False)
        c=next(c for c in adapt_pool(p,cfg).candidates if c.tap==r['tap'])
        self.assertIsNone(c.source_signed_s);self.assertEqual(c.exclusion_reason,'POLARIZATION_INVALID')
    def test_unknown_kind_rejected(self):
        p,_,cfg=self.bridge();p['candidates'][0]['support_records'][0]['support_kind']='BAD'
        with self.assertRaises(ContractError):adapt_pool(p,cfg)
    def test_identity_fail_closed(self):
        p,_,cfg=self.bridge()
        for other in (replace(cfg,mode='STRONGEST_ONLY'),replace(cfg,arm='VB'),
                      replace(cfg,recipe_sha256='a'*64),replace(cfg,candidate_config_sha256='a'*64)):
            with self.assertRaises(ContractError):adapt_pool(p,other)
        del p['support_semantics_version']
        with self.assertRaises(ContractError):adapt_pool(p,cfg)
    def test_bad_group_and_duplicate(self):
        p,_,cfg=self.bridge();p['candidates'][0]['group_ids']=[999]
        with self.assertRaises(ContractError):adapt_pool(p,cfg)
        p,_,cfg=self.bridge();p['candidates'].append(p['candidates'][0]);p['candidate_taps'].append(p['candidate_taps'][0])
        with self.assertRaises(ContractError):adapt_pool(p,cfg)
    def test_legacy_no_revision_silent_fallback(self):
        p,_,_=self.bridge()
        with self.assertRaises(ContractError):from_pool(p,self.c)
    def test_legacy_v0_score_and_b0(self):
        p,e,_=self.bridge(arm='V0');legacy=from_pool(p,self.c)
        self.assertEqual([c.legacy_support for c in e.candidates],[c.support for c in legacy.candidates])
        self.assertEqual(select(legacy,'B0',Policy()).selected_tap,p['raw']['tap'])
    def test_real_adapter_delegates_without_physics(self):
        adapter=OriginalAdapter.__new__(OriginalAdapter);adapter.revision_evidence=RevisionEvidenceAdapter()
        adapter._generate=Mock(side_effect=AssertionError('legacy called'))
        e=adapter.evidence(self.c);self.assertFalse(e.selector_ready);adapter._generate.assert_not_called()
    def test_selection_and_history_are_closed(self):
        _,e,_=self.bridge()
        for mode in ('B0','C','P','M','PM','PM-FORCE','NN-HARD'):
            with self.assertRaisesRegex(ContractError,'BRIDGE_ONLY'):select(e,mode,Policy())
        with self.assertRaisesRegex(ContractError,'BRIDGE_ONLY'):TrustedHistory().observe(e,None,0,0,None,Policy())
        self.assertFalse(any(c.history_trust_eligible for c in e.candidates))
    def test_plateau_boundary_and_ties_remain_candidates(self):
        p,e,_=self.bridge(wave([1,.1,0,.1,.3,.6,1,1,.4,0]))
        self.assertEqual(len(e.candidates),len(p['candidates']))
        self.assertFalse(e.selector_ready)  # no fabricated tap/group confidence

if __name__=='__main__':unittest.main()
