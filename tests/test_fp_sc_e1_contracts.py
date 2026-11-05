"""Material E1 restrictions reject authorization reuse and changed scope."""
import json
from pathlib import Path
import tempfile
import unittest
from qclean_uwb.fp_sc.e1_contracts import verify_e1_lock, SCOPE, _path


class E1ContractTest(unittest.TestCase):
    def _reject(self, lock, approval, pattern):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'lock.json').write_text(json.dumps(lock))
            (root/'approval.json').write_text(json.dumps(approval))
            with self.assertRaisesRegex(ValueError, pattern):
                verify_e1_lock(root, root/'lock.json', root/'approval.json')

    def test_e0_go_cannot_authorize_e1(self):
        self._reject({'schema':'FP_SC_E0_EXECUTION_LOCK_V1','stage':'E0'}, {}, 'WRONG_STAGE')

    def test_only_one_candidate_family_without_filter_is_allowed(self):
        base = {'schema':'FP_SC_E1_01_EXECUTION_LOCK_V1','stage':'E1-01','implementation_commit':'a'*40}
        for key, value in [('parameter_settings',27),('ekf_runs',1),('selector_runs',1),('new_rt',1)]:
            self._reject(dict(base,run_scope={**SCOPE,key:value}), {}, 'SCOPE_DRIFT')

    def test_specific_owner_scope_is_required(self):
        self._reject({'schema':'FP_SC_E1_01_EXECUTION_LOCK_V1','stage':'E1-01',
            'implementation_commit':'a'*40,'run_scope':SCOPE},
            {'schema':'FP_SC_E0_OWNER_SCOPED_EXECUTION_V1','GO_E0':True}, 'AUTHORIZATION_SCOPE')

    def test_paths_cannot_escape_the_reviewed_repository(self):
        for path in ('../outside.json','/tmp/outside.json'):
            with self.assertRaisesRegex(ValueError,'PATH_OUTSIDE'):
                _path(Path('/tmp/repo'),path)


if __name__ == '__main__':
    unittest.main()
