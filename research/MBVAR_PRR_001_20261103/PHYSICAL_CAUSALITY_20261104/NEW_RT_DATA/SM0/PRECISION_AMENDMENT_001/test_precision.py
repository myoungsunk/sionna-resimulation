"""Pinned-runtime controls on retained data. Never invokes a solver."""
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
import numpy as np
from qa import evaluate_arrays, error, SUCCESS_STATUS

HERE = Path(__file__).resolve().parent


class PrecisionControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with np.load(HERE.parent/'CANARY_R4_194_001/RAW.npz',allow_pickle=False) as z:
            cls.raw = {k:z[k] for k in z.files}

    def reject(self,key,change):
        arrays = dict(self.raw)
        arrays[key] = arrays[key].copy()
        change(arrays[key])
        with self.assertRaises(ValueError):
            evaluate_arrays(arrays)

    def test_retained_pass_and_old_failure_remains_visible(self):
        result, groups = evaluate_arrays(self.raw)
        self.assertEqual(result['status'],'AMENDED_NUMERICAL_PASS')
        self.assertGreater(result['checks']['f64_archive_los_diagnostic']['relative_l2'],1e-5)
        self.assertLess(result['checks']['archive_los_legacy']['relative_l2'],1e-5)
        self.assertEqual(groups.dtype,np.complex128)

    def test_reject_altered_legacy_ray(self):
        self.reject('original_field',lambda x:x.__setitem__((0,0),x[0,0]*1.01))

    def test_reject_altered_f64_ray(self):
        self.reject('fields',lambda x:x.__setitem__((0,0),x[0,0]*1.01))

    def test_reject_altered_group(self):
        self.reject('group_fields',lambda x:x.__setitem__((0,0,0),x[0,0,0]+1e-4))

    def test_reject_los_phase_error(self):
        self.reject('archive_los',lambda x:x.__imul__(np.exp(1j*1e-3)))

    def test_reject_full_error(self):
        self.reject('archive_full',lambda x:x.__imul__(1.01))

    def test_reject_nonfinite(self):
        self.reject('tau',lambda x:x.__setitem__(0,np.nan))

    def test_reject_out_of_range_group(self):
        self.reject('source_group',lambda x:x.__setitem__(0,len(self.raw['group_labels'])))

    def test_reject_direct_index(self):
        self.reject('direct_source_index',lambda x:x.__setitem__(0,99999))

    def test_reject_changed_dtype(self):
        arrays = dict(self.raw,a=self.raw['a'].astype(np.complex128))
        with self.assertRaisesRegex(ValueError,'dtype'):
            evaluate_arrays(arrays)

    def test_reject_zero_reference(self):
        with self.assertRaisesRegex(ValueError,'zero reference'):
            error(np.ones(2),np.zeros(2))

    def test_original_go_cannot_authorize_new_code(self):
        spec = importlib.util.spec_from_file_location('amended_producer',HERE/'producer.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        go = HERE.parent/'audit/GO_SM0_CANARY.json'
        old = json.loads(go.read_text())
        lock = dict(old)
        lock['primary_reference'] = 'SM0-PRECISION-001'
        with self.assertRaisesRegex(ValueError,'GO binding'):
            module.authorize(go,lock,'R4_aB_m0',194)

    def test_old_postprocess_rejects_amended_status(self):
        spec = importlib.util.spec_from_file_location('old_postprocess',HERE.parent/'postprocess.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'MANIFEST.json').write_text(json.dumps(dict(status=SUCCESS_STATUS)))
            with self.assertRaisesRegex(ValueError,'has not passed'):
                module.main(path,path/'must_not_exist')
            self.assertFalse((path/'must_not_exist').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
