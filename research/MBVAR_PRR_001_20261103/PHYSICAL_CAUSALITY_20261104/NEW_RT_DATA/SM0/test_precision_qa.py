"""Synthetic only: checks archival-precision and independent-closure gates.

No Sionna/solver invocation. Ground-truth archive in this synthetic fixture
is generated with the original complex64 expression; no numerical threshold
has been changed.
"""
import unittest
import numpy as np
from precision_qa import evaluate_precision

THRESHOLDS = {
    "reconstruction_relative_l2": 1e-8,
    "reconstruction_max_normalized": 1e-8,
    "archive_full_relative_l2": 1e-3,
    "archive_los_relative_l2": 1e-5,
}


def synthetic_arrays():
    n = 257
    freq = 6.25e9 + np.arange(n, dtype=np.float64) * 5e5
    delay_direct = np.float32(6.067e-8)
    delay_refl = np.float32(6.217e-8)
    tau = np.tile(np.array([delay_direct, delay_refl], dtype=np.float32), n)
    a = np.zeros((2*n, 2, 2), dtype=np.complex64)
    a[::2, :, 0] = np.asarray([1.+0.4j, 0.6-0.1j], np.complex64)
    a[1::2, :, 0] = np.asarray([0.2-0.13j, -0.05+0.04j], np.complex64)
    original = np.empty((2*n, 2), dtype=np.complex64)
    groups = np.zeros((2, n, 2), dtype=np.complex128)
    for i, f in enumerate(freq):
        aa = a[2*i:2*i+2, :, 0].T
        tt = tau[2*i:2*i+2]
        # Keep exactly the old expression AND operation order.
        old = aa * np.exp(-2j*np.pi*np.float64(f)*tt)[None, :]
        if old.dtype != np.complex64:
            raise ValueError("Fixture requires pinned NumPy 1.26.4 complex64 promotion")
        original[2*i:2*i+2] = old.T
        modern = aa.astype(np.complex128) * np.exp(
            -2j*np.pi*float(f)*tt.astype(np.float64))[None,:]
        groups[:,i] = modern.T
    return {
        "a":a, "tau":tau, "original_field":original,
        "offsets":np.arange(n+1,dtype=np.int64)*2,
        "direct_source_index":np.zeros(n,dtype=np.int32),
        "group_fields":groups, "group_count":np.ones((2,n),dtype=np.int32),
        "direct_group":np.int32(0),
        "native_f64":groups.sum(axis=0),
        "native_original32":original.reshape(n,2,2).sum(axis=1),
        "archive_los":original[::2].astype(np.complex128),
        "archive_full":groups.sum(axis=0).copy(),
    }


class PrecisionGates(unittest.TestCase):
    def test_original_expression_matches_archive_but_f64_phase_differs(self):
        a=synthetic_arrays()
        result=evaluate_precision(a,THRESHOLDS)
        self.assertTrue(result["pass_all"])
        self.assertEqual(result["schema"], "SM0_DUAL_PRECISION_V2")
        self.assertFalse(result["f64_los_is_gate"])
        self.assertEqual(result["archive_los_primary_legacy32"]["relative_l2"],0.0)
        self.assertGreater(result["archive_los_diagnostic_f64"]["relative_l2"],1e-6)
        self.assertLess(result["reconstruction_primary_f64"]["relative_l2"],1e-12)
        self.assertLess(result["archive_full_primary_f64"]["relative_l2"],1e-12)

    def test_dont_hide_true_archive_los_mismatch(self):
        a=synthetic_arrays()
        a["archive_los"] *= np.exp(1j*0.002)
        self.assertFalse(evaluate_precision(a,THRESHOLDS)["pass_all"])

    def test_corrupt_f64_reconstruction_must_fail(self):
        a=synthetic_arrays()
        a["group_fields"][1]*=1.01
        self.assertFalse(evaluate_precision(a,THRESHOLDS)["pass_all"])

    def test_delay_precision_or_direct_index_cannot_change_silently(self):
        a=synthetic_arrays()
        a["tau"]=a["tau"].astype(np.float64)
        with self.assertRaises(ValueError):evaluate_precision(a,THRESHOLDS)
        b=synthetic_arrays()
        b["direct_source_index"]=np.ones(257,dtype=np.int32)
        self.assertFalse(evaluate_precision(b,THRESHOLDS)["pass_all"])

    def test_archive_full_threshold_not_relaxed(self):
        a=synthetic_arrays()
        a["archive_full"]*=1.01
        self.assertFalse(evaluate_precision(a,THRESHOLDS)["pass_all"])


if __name__ == "__main__":
    unittest.main()
