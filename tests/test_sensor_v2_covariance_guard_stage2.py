"""Targeted recorded-input checks for the stage2 numerical validation guard."""
import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/drive_sim'))
import validate_sensor_v2_stage2 as V

class GuardChecks(unittest.TestCase):
    def replay(self,name):
        arm=next(a for a in V.arms() if a['name']==name)
        with np.load(V.OUT/'raw'/f'{name}_81000.npz') as z:
            inp={k[7:]:z[k] for k in z.files if k.startswith('sensor_')}
            out=V.run_filter_v2(V.config(arm),None,inp,{}, {},z['initial_state'],z['initial_prior'])
            return out,z['estimate_state'].copy(),z['covariance_full'].copy()
    def test_invalid_noiseless_calibration_rejected(self):
        with self.assertRaisesRegex(FloatingPointError,'covariance invalid at sample'):
            self.replay('D_bias_asymmetry')
    def test_measured_noise_replay_unchanged(self):
        out,x,P=self.replay('B3_pair_measured')
        np.testing.assert_array_equal(out['est'],x)
        np.testing.assert_array_equal(out['cov_full'],P)
    def test_cancelled_gyro_posterior_roundoff_allowed(self):
        out,x,P=self.replay('B1_gyro_wheel_update')
        np.testing.assert_array_equal(out['est'],x)
        np.testing.assert_array_equal(out['cov_full'],P)
    def test_prior_noise_execution_valid(self):
        out,_,_=self.replay('B4_prior_matched')
        self.assertTrue(np.isfinite(out['cov_full']).all())

if __name__=='__main__':unittest.main()
