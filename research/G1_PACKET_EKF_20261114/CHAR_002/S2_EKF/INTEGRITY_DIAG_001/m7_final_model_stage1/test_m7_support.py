"""Data-free M7 scope/input-config/donor-fit unit tests, never production runs."""
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

import m7_h5prime as fit
import m7_inputs as inputs
import m7_spec as spec


@dataclass(frozen=True)
class FakeSensorConfig:
    level: int = 1
    condition: str = "all"
    common_scale: float = 0.
    bias_rw_rad_s_sqrt_s: float = 0.
    gyro_N_rad_sqrt_s: float = math.radians(.015)


class ScopeTests(unittest.TestCase):
    def test_complete_grid_and_aliases(self):
        cells = spec.expected_cells()
        self.assertEqual(spec.validate_cell_index(cells),
                         dict(cells=1470, physical_replays=1440, input_packets=120))
        self.assertEqual(sum(r["mode"] == "fixed" for r in cells), 210)
        self.assertEqual(sum(r["condition"] == spec.STRESS for r in cells), 420)
        aliases = [r for r in cells if r["trace_alias_of"] is not None]
        self.assertEqual(len(aliases), 30)
        for row in aliases:
            self.assertEqual(row["arm"], "H0")
            self.assertIn("/own/", row["trace_alias_of"])
        self.assertFalse(any(r["mode"] == "fixed" and r["condition"] == spec.STRESS for r in cells))

    def test_missing_duplicate_and_relabelled_cells_rejected(self):
        cells = spec.expected_cells()
        for bad in (cells[:-1], [*cells, cells[0]]):
            with self.assertRaises(ValueError):
                spec.validate_cell_index(bad)
        cells[0] = dict(cells[0], decision_role="REPORT_ONLY")
        with self.assertRaises(ValueError):
            spec.validate_cell_index(cells)

    def test_default_authorization_is_hold(self):
        policy = spec.execution_policy()
        self.assertEqual(set(policy["authorization"].values()), {"HOLD"})
        with self.assertRaises(ValueError):
            inputs._configuration(policy)

    def test_only_gyro_white_coefficient_changes(self):
        fake = SimpleNamespace(SensorV2Config=FakeSensorConfig)
        b0, l2 = inputs.paired_configs(fake, spec.execution_policy()["paired_gyro_noise"])
        self.assertEqual(b0.level, l2.level)
        self.assertEqual(b0.condition, "noise_pair")
        self.assertEqual(l2.condition, "noise_pair")
        self.assertEqual({key for key in asdict(b0) if asdict(b0)[key] != asdict(l2)[key]},
                         {"gyro_N_rad_sqrt_s"})
        self.assertEqual(l2.gyro_N_rad_sqrt_s, 4 * b0.gyro_N_rad_sqrt_s)
        with self.assertRaises(ValueError):
            inputs.paired_configs(fake, dict(b0_N_deg_sqrt_s=.05, l2_N_deg_sqrt_s=.20))

    def test_stress_resolves_to_same_input_record(self):
        record = dict(path="synthetic/not_created.npz", sha256="not_an_evidence_hash")
        index = {"L2_GYRO_ARW": {"10": {"R2": record}}}
        self.assertIs(inputs.resolve_input(index, spec.STRESS, 10, "R2"), record)
        with self.assertRaises(ValueError):
            inputs.resolve_input(index, spec.STRESS, 30, "R2")


class H5PrimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Loading source definitions is not loading donor/RF/trajectory data.
        parent = Path(__file__).resolve().parent.parent
        candidates = (parent / "G1_GM_THETA_M6_20261116/characterize.py",
                      parent / "gm_theta_m6/characterize.py")
        path = next(path for path in candidates if path.is_file())
        record = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        cls.module = fit.load_characterizer(record)

    @staticmethod
    def cases(distance=4., count=125):
        t = np.arange(count) * .2
        result = {}
        for i, route in enumerate(spec.ROUTES):
            result[route] = dict(t=t, mask=np.ones(count, bool), prior_distance=np.full(count, distance),
                                 raw_s=np.full(count, .03 * (i + 1)), a_ref=np.full(count, 1. + i),
                                 arc=np.arange(count) * (.01 * (i + 1)**2),
                                 yaw_arc=np.zeros(count), route_mean_s=np.array(0.))
        return result

    @staticmethod
    def direct_donor_ratio(data):
        # Independent nested loops make the bin/block/pair weighting explicit.
        numerator, denominator = [], []
        t = data["t"]
        block_ids = np.floor((t - t[0]) / 10.).astype(int)
        for block in sorted(set(block_ids)):
            ids = np.flatnonzero(block_ids == block)
            products, kernels2 = [], []
            for i in ids:
                for j in ids:
                    if i < j and .4 <= t[j] - t[i] <= 5.:
                        k = math.exp(data["arc"][i] - data["arc"][j])
                        products.append(k * data["raw_s"][i] * data["raw_s"][j])
                        kernels2.append(k * k)
            if len(products) >= 10:
                numerator.append(sum(products) / len(products))
                denominator.append(sum(kernels2) / len(kernels2))
        if len(numerator) < 2:
            return None
        return sum(numerator) / len(numerator), sum(denominator) / len(denominator)

    def test_original_sigma_zero_and_independent_ratio(self):
        cases = self.cases()
        result = fit.fit_h5_prime(cases, self.module)
        for held in spec.ROUTES:
            terms = [self.direct_donor_ratio(cases[r]) for r in spec.ROUTES if r != held]
            expected = max(0., sum(n for n, d in terms) / sum(d for n, d in terms))
            self.assertAlmostEqual(result["fit"]["folds"][held]["q_s"][2], expected, places=13)
        terms = [self.direct_donor_ratio(cases[r]) for r in ("R4", "R5")]
        pooled = sum(n for n, d in terms) / sum(d for n, d in terms)
        mean_ratios = sum(n / d for n, d in terms) / 2
        self.assertGreater(abs(pooled - mean_ratios), 1e-6)

    def test_holdout_does_not_change_own_table(self):
        cases = self.cases()
        original = fit.fit_h5_prime(cases, self.module)
        cases["R2"]["raw_s"] *= 100
        changed = fit.fit_h5_prime(cases, self.module)
        self.assertEqual(original["fit"]["folds"]["R2"], changed["fit"]["folds"]["R2"])

    def test_near_bin_not_forced_to_zero(self):
        result = fit.fit_h5_prime(self.cases(distance=1.), self.module)
        for fold in result["fit"]["folds"].values():
            self.assertTrue(fold["supported_bins"][0])
            self.assertGreater(fold["q_s"][0], 0.)

    def test_unsupported_bins_and_nonfinite_donors(self):
        cases = self.cases(count=20)
        result = fit.fit_h5_prime(cases, self.module)
        self.assertTrue(all(f["status"] == "NOT_ESTIMABLE" for f in result["fit"]["folds"].values()))
        cases["R2"]["raw_s"][1] = np.nan
        with self.assertRaises(ValueError):
            fit.fit_h5_prime(cases, self.module)


if __name__ == "__main__":
    unittest.main()
