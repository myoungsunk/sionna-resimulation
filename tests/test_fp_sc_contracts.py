"""Provenance controls must reject missing raw data and changed identities."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from qclean_uwb.fp_sc.contracts import inspect_payload, sha256, verify_lock, write_json


class ContractTest(unittest.TestCase):
    def test_pointer_is_recorded_as_missing_payload(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'raw.npz'
            p.write_text('version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a'*64 + '\nsize 900\n')
            record = inspect_payload(d, 'raw.npz')
            self.assertEqual(record['status'], 'LFS_POINTER_ONLY')
            self.assertEqual(record['expected_payload_size'], 900)

    def test_safe_array_schema_and_object_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'raw.npz'
            np.savez(p, H=np.zeros((3, 257, 2), dtype='complex128'))
            record = inspect_payload(d, 'raw.npz')
            self.assertEqual(record['arrays']['H']['shape'], [3,257,2])
            np.savez(p, unsafe=np.array([{'x': 2}], dtype=object))
            with self.assertRaisesRegex(ValueError, 'Object arrays'):
                inspect_payload(d, 'raw.npz')

    def test_old_or_wrong_stage_go_is_not_reused(self):
        for lock, approval in [({'schema':'OLD_GO'}, {}),
                               ({'schema':'FP_SC_E0_EXECUTION_LOCK_V1','stage':'E1'}, {})]:
            with self.assertRaisesRegex(ValueError, 'WRONG_STAGE'):
                verify_lock('.', lock, approval)

    def test_code_drift_fails_before_any_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'source.py';p.write_text('original')
            lock = {'schema':'FP_SC_E0_EXECUTION_LOCK_V1','stage':'E0','implementation_commit':'a'*40,
                    'documents':{},'code':{'source.py':sha256(p)},
                    'environment_file':'env.json','input_lock_file':'input.json','code_lock_file':'code.json'}
            for name in ('env.json','input.json'):
                write_json(Path(d)/name,{})
            write_json(Path(d)/'code.json',{'files':lock['code']})
            lock['documents']={name:sha256(Path(d)/name) for name in ('env.json','input.json','code.json')}
            approval = {'schema':'FP_SC_E0_OWNER_SCOPED_EXECUTION_V1','stage':'E0','GO_E0':True,
                        'implementation_commit':'a'*40,'external_independent_accept':False}
            p.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'CODE_DRIFT'):
                verify_lock(d, lock, approval)

    def test_reduced_code_set_cannot_reuse_full_review(self):
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d)/'code.json',{'files':{'source.py':'b'*64}})
            lock={'schema':'FP_SC_E0_EXECUTION_LOCK_V1','stage':'E0','implementation_commit':'a'*40,
                  'code':{},'documents':{'env.json':'x','input.json':'x','code.json':'x'},
                  'environment_file':'env.json','input_lock_file':'input.json','code_lock_file':'code.json'}
            approval={'schema':'FP_SC_E0_OWNER_SCOPED_EXECUTION_V1','stage':'E0','GO_E0':True,
                      'implementation_commit':'a'*40,'external_independent_accept':False}
            with self.assertRaisesRegex(ValueError,'CODE_SET_MISMATCH'):
                verify_lock(d,lock,approval)


if __name__ == '__main__':
    unittest.main()
