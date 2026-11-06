"""Synthetic-only contract tests for staged VAB shadow evaluation.

No SourceFFD banks, real RF experiment, GT inside selector, EKF recursion,
or science-stage approval is required to run this suite.
"""
import unittest
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.contracts import ContractError, Policy, STEP_M, Support, digest
from qclean_uwb.fp_sc.followup.detection import binding_for
from qclean_uwb.fp_sc.followup.selection import select, SyntheticSelectionProbe
from qclean_uwb.fp_sc.followup.vab_shadow import (
    MODES, SHADOW_SCOPE, shadow_decision, shadow_select_case,
    compare_shadow_observations, same_prior_shadow_one_step)


def synthetic_cir():
    a = np.zeros((1028, 2), complex)
    a[:10, 0] = [0., .1, .2, .3, .5, .7, .9, 1., .5, 0.]
    return a


def prior(tap):
    x = tap * STEP_M
    return Support(x, x, .02, "SYNTHETIC_TEST_ONLY")


class FakeAdapter:
    def __init__(self):
        self.revision_evidence = RevisionEvidenceAdapter(arm="VAB", mode="TWO_PORT_UNION")
        self.e = self.revision_evidence.evidence(synthetic_cir())
    def evidence(self, cir, variance=0.):
        return self.e
    def native(self, points):
        r = np.full(len(points), 5*STEP_M) + np.asarray(points)[:, 0]*.01
        return r, r
    def observe(self, x):
        return np.array([2., .3]), np.array([[.7,.1,0.,0.],[.1,0.,.2,0.]])


def fake_case(n=3):
    z = np.ones((n,257,2), complex)
    P = np.tile((np.eye(4)*.005)[None,:,:],(n,1,1))
    H = np.tile(np.array([[[.7,.1,0.,0.],[.1,0.,.2,0.]]]), (n,1,1))
    return SimpleNamespace(
        corpus="dynamic", case_id="SYNTHETIC", t=np.arange(n)*.2,
        pose_id=np.arange(n), Hrf=z, noise_variance=0.,
        ds=np.zeros(n), prior=np.zeros((n,4)), Pprior=P,
        muMB=np.zeros((n,2)),
        baseline_trace=dict(h=np.tile(np.array([2.,.3]),(n,1)), H=H,
                            prior=np.zeros((n,4)), Pprior=P,
                            Reff=np.tile((np.eye(2)*.2)[None,:,:],(n,1,1)),
                            mask=np.ones(n,dtype=bool)))


class VabShadowTests(unittest.TestCase):
    def setUp(self):
        self.adapter=FakeAdapter()
        self.e=self.adapter.e
        self.policy=Policy()

    def test_revised_candidates_use_actual_pure_selector_logic(self):
        for mode in MODES:
            s=prior(5)
            shadow=shadow_decision(self.e,mode,self.policy,prior=s,motion=s)
            probe=SyntheticSelectionProbe(binding_for(self.e,self.policy),digest(asdict(self.e)))
            original=select(self.e,mode,self.policy,prior=s,motion=s,synthetic_probe=probe)
            self.assertEqual(shadow["decision"],asdict(original))
            self.assertFalse(shadow["valid_provider"])
            self.assertTrue(shadow["counterfactual"])

    def test_strong_edge_candidate_is_selectable_without_forced_mode(self):
        s=prior(5)
        d=shadow_decision(self.e,"PM",self.policy,prior=s,motion=s)["decision"]
        self.assertEqual(d["action"],"REPLACE_SUPPORTED")
        self.assertNotEqual(d["selected_tap"],d["raw_tap"])

    def test_no_implicit_trusted_history_or_active_provider(self):
        case=fake_case()
        rows=shadow_select_case(case,self.adapter,self.policy)
        self.assertEqual(len(rows),3*4)
        self.assertTrue(all(r["scope"]==SHADOW_SCOPE and
                            r["provider_allowed"] is False and
                            r["integrity"]["state"]=="UNKNOWN" for r in rows))
        self.assertEqual(rows[3]["prepared_status"],"HOLD_HISTORY")
        self.assertIsNone(rows[3]["m_interval"])
        self.assertNotIn("truth",rows[0])

    def test_raw_history_only_looks_backward(self):
        case=fake_case(4)
        before=shadow_select_case(case,self.adapter,self.policy)
        case.prior[-1,0]=7.
        after=shadow_select_case(case,self.adapter,self.policy)
        self.assertEqual(before[:-4],after[:-4])

    def test_reference_never_enters_s1_and_only_enters_s2(self):
        case=fake_case(2)
        online=shadow_select_case(case,self.adapter,self.policy)
        ref=np.ones_like(case.Hrf)
        evaluated=compare_shadow_observations(case,online,ref)
        self.assertEqual(len(evaluated),len(online))
        self.assertTrue(all(x["scope"].startswith("EVALUATOR_POSTHOC") for x in evaluated))
        self.assertTrue(all(x["reference_valid"] for x in evaluated))
        self.assertNotIn("reference_tap",online[0])

    def test_shadow_s2_refuses_missing_or_operational_rows(self):
        case=fake_case(1)
        rows=shadow_select_case(case,self.adapter,self.policy)
        with self.assertRaises(ContractError):
            compare_shadow_observations(case,rows[:-1],case.Hrf)
        rows[0]["provider_allowed"]=True
        with self.assertRaises(ContractError):
            compare_shadow_observations(case,rows,case.Hrf)

    def test_zero_fp_replacement_does_not_fabricate_s_change(self):
        case=fake_case(1)
        rows=shadow_select_case(case,self.adapter,self.policy)
        c=next(r for r in rows if r["mode"]=="C")
        self.assertEqual(c["raw_tap"],c["hypothetical_selected_tap"])
        self.assertEqual(c["observations"]["F00"],c["observations"]["F01"])
        self.assertEqual(c["observations"]["F00"],c["observations"]["F11"])

    def test_single_update_wont_use_truth_or_feedback(self):
        case=fake_case(2)
        online=shadow_select_case(case,self.adapter,self.policy)
        with patch("qclean_uwb.fp_sc.followup.engine.ArmProcessor.step",
                   side_effect=AssertionError("LIVE_EKF_CALLED")):
            rows=same_prior_shadow_one_step(case,online,self.adapter,mode="PM")
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r["valid"] for r in rows))
        self.assertTrue(all(all(v["P_exact_equal"] for v in r["checks"].values()) for r in rows))

    def test_one_step_requires_original_trace(self):
        case=fake_case(1);case.baseline_trace=None
        rows=shadow_select_case(case,self.adapter,self.policy)
        with self.assertRaisesRegex(ContractError,"ARCHIVED_CONTEXT"):
            same_prior_shadow_one_step(case,rows,self.adapter)

    def test_wrong_adapter_and_unapproved_modes_fail_closed(self):
        bad=FakeAdapter();bad.revision_evidence.mode="STRONGEST_ONLY"
        with self.assertRaisesRegex(ContractError,"TWO_PORT"):
            shadow_select_case(fake_case(),bad,self.policy)
        with self.assertRaisesRegex(ContractError,"SHADOW_NO_FORCED"):
            shadow_decision(self.e,"PM-FORCE",self.policy,prior=prior(5),motion=prior(5))


if __name__ == "__main__":
    unittest.main()
