"""No-science tests: staged SHA approvals, review chaining, 3D truth handling."""
import importlib.util
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from qclean_uwb.fp_sc.followup.contracts import ContractError, Policy
from qclean_uwb.fp_sc.followup.evaluation import trajectory_metrics
from qclean_uwb.fp_sc.followup.study import Evaluator


def script_module():
    path=Path(__file__).resolve().parents[1]/"scripts/fp_sc_vab_shadow_stages.py"
    spec=importlib.util.spec_from_file_location("fp_shadow_stages_no_science",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StageContractTests(unittest.TestCase):
    def setUp(self):
        self.m=script_module()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=Policy()
        self.case=dict(online_npz="online.npz",evaluator_npz="evaluator.npz",
                       expected_rows=3,metadata={"case_id":"SYNTH","corpus":"dynamic"})
        self.manifest=dict(schema="FP_SC_VAB_SHADOW_STAGES_V1",
             stage=self.m.STAGES[0],case_id="SYNTH",source_commit="e416cf62c0cde15151a1851168231da73a0cbfff",
             candidate_arm="VAB",candidate_mode="TWO_PORT_UNION",case=self.case,
             policy=asdict(p),policy_sha256=p.sha,
             code_files={name:"a"*64 for name in self.m.CODE_REQUIRED},
             baseline_sources={name:"b"*64 for name in self.m.BASELINE_REQUIRED},
             model_files={name:"e"*64 for name in self.m.MODEL_REQUIRED},
             input_files={"online.npz":"c"*64,"evaluator.npz":"d"*64},
             previous={})
        self.path=self.root/"manifest.json"

    def save(self):
        self.path.write_text(json.dumps(self.manifest))

    def inspect(self):
        self.save()
        with patch.object(self.m,"verify_files"):
            return self.m.inspect_manifest(self.path)

    def test_plan_has_no_science_or_closed_loop_stage(self):
        p=self.m.plan()
        self.assertEqual(p["status"],"CODE_ONLY_NO_SCIENCE_RUN")
        self.assertEqual(len(p["stages"]),3)
        self.assertNotIn("E4",self.m.STAGES)

    def test_common_identity_rejects_changed_payload_code_and_model(self):
        from copy import deepcopy
        original=self.m.identity(self.manifest)
        for group,key in (("input_files","online.npz"),("input_files","evaluator.npz"),
                          ("code_files",self.m.CODE_REQUIRED[0]),
                          ("baseline_sources",self.m.BASELINE_REQUIRED[0]),("model_files",self.m.MODEL_REQUIRED[0])):
            changed=deepcopy(self.manifest);changed[group][key]="f"*64
            self.assertNotEqual(original,self.m.identity(changed),(group,key))

    def test_stage_artifacts_do_not_change_common_identity(self):
        original=self.m.identity(self.manifest)
        self.manifest["stage"]=self.m.STAGES[1]
        self.manifest["input_files"]["s1_result.json.gz"]="f"*64
        self.assertEqual(original,self.m.identity(self.manifest))

    def test_missing_model_lock_is_rejected(self):
        self.manifest.pop("model_files")
        with self.assertRaisesRegex(ContractError,"MODEL_LOCK_EMPTY"):
            self.inspect()

    def test_s2_rejects_changed_common_input_after_reviewed_s1(self):
        m=self.manifest
        stage=self.m.STAGES[0]
        receipt=dict(stage=stage,status='COMPLETE_TECHNICAL_ONLY',
                     identity_sha256=self.m.identity(m),result_sha256='f'*64)
        review=dict(stage=stage,decision='ACCEPT_TO_NEXT_STAGE',
                    receipt_sha256='a'*64,reviewer='SYNTHETIC',reviewed_at='SYNTHETIC')
        (self.root/'receipt.json').write_text(json.dumps(receipt))
        (self.root/'review.json').write_text(json.dumps(review))
        m['stage']=self.m.STAGES[1]
        m['previous']={stage:dict(result_path='result.gz',result_sha256='f'*64,
            receipt_path='receipt.json',receipt_sha256='a'*64,
            review_path='review.json',review_sha256='b'*64)}
        m['input_files'].update({'result.gz':'f'*64,'receipt.json':'a'*64,'review.json':'b'*64})
        with patch.object(self.m,'ROOT',self.root):
            self.inspect()  # stage-specific artifacts are allowed
            m['input_files']['online.npz']='0'*64
            with self.assertRaisesRegex(ContractError,'PREVIOUS_RESULT_OR_IDENTITY_BAD'):
                self.inspect()

    def test_stage_s1_preflight_structure_can_be_inspected_without_authorization(self):
        m,p=self.inspect()
        self.assertEqual(m["candidate_arm"],"VAB")
        self.assertEqual(m["stage"],"S1_SHADOW_SELECT")

    def test_stage_s2_cannot_skip_reviewed_s1(self):
        self.manifest["stage"]=self.m.STAGES[1]
        with self.assertRaisesRegex(ContractError,"PREVIOUS_GATES"):
            self.inspect()

    def test_stage_s3_cannot_claim_ekf_without_archived_context(self):
        self.manifest["stage"]=self.m.STAGES[2]
        with self.assertRaisesRegex(ContractError,"CONTEXT_NOT_REVIEWED"):
            self.inspect()

    def test_no_blanket_authority_and_no_stale_manifest(self):
        self.save()
        receipt=self.root/"approval.json"
        a=dict(execute_shadow_science=False,stage=self.m.STAGES[0],
               case_id="SYNTH",manifest_sha256=self.m.sha256(self.path),
               code_lock_sha256=self.m.digest(self.manifest["code_files"]),
               actor="SYNTHETIC",issued_utc="SYNTHETIC")
        receipt.write_text(json.dumps(a))
        with self.assertRaisesRegex(ContractError,"APPROVAL_MISSING"):
            self.m.authorize(self.path,receipt,self.manifest)
        a["execute_shadow_science"]=True
        a["execute_science"]=True
        receipt.write_text(json.dumps(a))
        with self.assertRaisesRegex(ContractError,"SCOPE_EXCEEDED"):
            self.m.authorize(self.path,receipt,self.manifest)

    def test_shallow_manifest_cannot_swap_VAB_for_old_generator(self):
        self.manifest["candidate_arm"]="V0"
        with self.assertRaisesRegex(ContractError,"VAB_BINDING"):
            self.inspect()


class ThreeStateTruthTests(unittest.TestCase):
    def test_three_column_truth_never_fabricates_gyro_bias_or_nees4(self):
        n=3
        x=np.zeros((n,4));x[:,2]=.1
        P=np.tile((np.eye(4)*.04)[None,:,:],(n,1,1))
        truth=np.zeros((n,3))
        metric=trajectory_metrics(x,P,truth,np.array([0.,30.,30.2]))["all"]
        self.assertIsNone(metric["nees4_mean"])
        self.assertIsNone(metric["coverage"]["0.95"]["state4"])
        self.assertEqual(metric["bias_truth_status"],"NOT_TESTED_NO_TRUE_GYRO_BIAS")
        self.assertIsNotNone(metric["coverage"]["0.95"]["heading"])

    def test_four_column_truth_retains_4d_metrics(self):
        n=3;x=np.zeros((n,4));P=np.tile((np.eye(4)*.04)[None,:,:],(n,1,1))
        metric=trajectory_metrics(x,P,np.zeros((n,4)),np.array([0.,30.,30.2]))["all"]
        self.assertEqual(metric["nees4_mean"],0.)
        self.assertEqual(metric["coverage"]["0.95"]["state4"],1.)
        self.assertEqual(metric["bias_truth_status"],"EVALUATED")

    def test_three_column_truth_requires_explicit_evaluator_opt_in(self):
        n=2
        c=type("C",(),{"t":np.arange(n)})()
        h=np.ones((n,257,2),complex);truth=np.zeros((n,3))
        with self.assertRaises(ContractError):
            Evaluator(c,h,truth,None)
        ev=Evaluator(c,h,truth,None,allow_partial_truth=True)
        self.assertEqual(ev.truth.shape,(n,3))


if __name__=="__main__":
    unittest.main()
