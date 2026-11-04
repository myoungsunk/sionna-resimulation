"""Synthetic observer closure and fail-closed entry tests, no RF data analysis."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import analyze
from diagnostics_amended import evaluate


class CodeControls(unittest.TestCase):
    def test_missing_independent_data_acceptance_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'accept.json').write_text(json.dumps(dict(decision='PENDING')))
            (p/'go.json').write_text('{}')
            with patch.object(analyze,'evaluate') as call:
                with self.assertRaisesRegex(ValueError,'complete-data acceptance'):
                    analyze.main(p/'out',p/'accept.json',p/'go.json')
                call.assert_not_called()
            self.assertFalse((p/'out').exists())

    def test_incorrect_code_go_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p/'accept.json').write_text(json.dumps(dict(decision='ACCEPT',scope='ALL_15_AMENDED_SM0_DATA')))
            (p/'go.json').write_text(json.dumps(dict(decision='GO',code_sha256={})))
            with patch.object(analyze,'evaluate') as call:
                with self.assertRaisesRegex(ValueError,'GO binding'):
                    analyze.main(p/'out',p/'accept.json',p/'go.json')
                call.assert_not_called()
            self.assertFalse((p/'out').exists())

    def test_synthetic_coherent_power_and_same_tap_identity(self):
        freq = 6.2504e9+np.arange(257)*1.95e6
        fields = np.zeros((3,257,2),np.complex128)
        for g,(delay,ports) in enumerate(((20e-9,(1.,.5)),(21e-9,(.3j,-.1)),(25e-9,(-.2,.4j)))):
            fields[g] = np.exp(-2j*np.pi*freq[:,None]*delay)*np.asarray(ports)[None,:]*1e-3
        labels = ['DIRECT','[["floor",1]]','[["floor",1],["wall_yplus",1]]']
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            result = evaluate(p,freq,fields,labels,0,fields.sum(0),fields.sum(0),fields[0])
            self.assertLess(result['native']['identity_error'],1e-12)
            for key in ('fpFull_allocation_residual','fpLoS_allocation_residual'):
                self.assertLess(max(abs(np.asarray(result[key]))),1e-14)
            with (p/'surface_removal.csv').open() as f:
                surfaces = list(csv.DictReader(f))
            floor = [r for r in surfaces if r['surface']=='floor']
            self.assertTrue(all(int(r['removed_group_count'])==2 for r in floor))

    def test_zero_counterfactual_is_undefined(self):
        freq = 6.2504e9+np.arange(257)*1.95e6
        direct = np.exp(-2j*np.pi*freq[:,None]*20e-9)*np.asarray([1.,.5])[None,:]*1e-3
        fields = np.asarray([direct,-direct,direct])
        labels = ['DIRECT','[["floor",1]]','[["wall_yplus",1]]']
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            evaluate(p,freq,fields,labels,0,fields.sum(0),fields.sum(0),fields[0])
            with (p/'attribution.csv').open() as f:
                rows = list(csv.DictReader(f))
            zero = [r for r in rows if r['group_id']==labels[2]]
            self.assertTrue(all(r['removed_s_redetected']=='' and r['removed_detected_tap']=='' for r in zero))


if __name__ == '__main__':
    unittest.main(verbosity=2)
