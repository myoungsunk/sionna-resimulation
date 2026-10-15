"""Negative controls for Q0 gates and independent archived-posterior scoring."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import numpy as np
import q0


class InputGates(unittest.TestCase):
    def test_hash_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_bytes(b'original');expected=q0.digest(p)
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
                q0.exact_file(p,expected)

    def test_git_blob_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source';p.write_bytes(b'abc')
            self.assertEqual(q0.digest(p,True),hashlib.sha1(b'blob 3\0abc').hexdigest())

    def test_duplicate_archive_member_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('a/data.json','{}');z.writestr('b/data.json','{}')
        with zipfile.ZipFile(b) as z:
            with self.assertRaisesRegex(ValueError,'NOT_UNIQUE'):
                q0.member(z,'data.json')

    def test_ids_and_times_must_both_match(self):
        with self.assertRaisesRegex(ValueError,'BINDING_MISMATCH'):
            q0.check_binding(np,np.array([1,2]),np.array([0.,.2]),np.array([1,2]),np.array([0.,.3]))

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):
            q0.check_binding(np,np.array([1,1]),np.array([0.,.2]),np.array([1,1]),np.array([0.,.2]))

    def test_nonmonotonic_time_rejected(self):
        with self.assertRaisesRegex(ValueError,'MONOTONIC'):
            q0.check_binding(np,np.array([1,2]),np.array([.2,0]),np.array([1,2]),np.array([.2,0]))

    def test_nan_cannot_pass_numeric_parity(self):
        with self.assertRaisesRegex(ValueError,'NONFINITE'):
            q0.close(np,[np.nan],[np.nan],1e-8)


class ScoreGates(unittest.TestCase):
    def setUp(self):
        self.t=np.arange(979)*.2
        self.x=np.zeros((979,4));self.truth=np.zeros((979,3))
        self.P=np.tile(np.diag([1.,2.,.25,.01]),(979,1,1))
        self.status=np.full(979,'APPLIED')

    def test_warmup_excluded_and_cholesky_nees(self):
        self.x[:150,2]=1.;self.x[150:,0]=2.;self.x[150:,2]=.5
        v=q0.score_archive(np,self.x,self.P,self.status,self.t,self.truth,0.)
        self.assertEqual(v['frames'],829)
        self.assertAlmostEqual(v['pose_nees'],5.)
        self.assertAlmostEqual(v['heading_nees'],1.)
        self.assertEqual(v['rf_applied'],829)

    def test_yaw_wrap(self):
        self.x[:,2]=2*np.pi+.1
        v=q0.score_archive(np,self.x,self.P,self.status,self.t,self.truth,0.)
        self.assertAlmostEqual(v['heading_rmse_deg'],np.degrees(.1))

    def test_wrong_window_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'EVALUATION_WINDOW'):
            q0.score_archive(np,self.x,self.P,self.status,self.t+10,self.truth,0.)

    def test_negative_covariance_is_rejected(self):
        self.P[300,0,0]=-1
        with self.assertRaisesRegex(ValueError,'COV_NOT_PD'):
            q0.score_archive(np,self.x,self.P,self.status,self.t,self.truth,0.)

    def test_nonsymmetric_covariance_is_rejected(self):
        self.P[300,0,1]=.3
        with self.assertRaisesRegex(ValueError,'SYMMETRIC'):
            q0.score_archive(np,self.x,self.P,self.status,self.t,self.truth,0.)


class DerivativeGates(unittest.TestCase):
    def setUp(self):
        self.case=dict(anchor=[4.,0.,2.65],mount_deg=0.,robot_z_m=.45)
        self.x=np.array([1.213,-.473,.3123,0.])
        self.tol=json.loads((Path(__file__).parent/'q0_lock.json').read_text())['tolerances']

    class LinearLut:
        def model(self,x,case):
            # Periodic yaw and a smooth nontrivial x/y response.
            h=np.array([x[0]+2*x[1],x[0]+3*x[1]+np.sin(x[2])])
            H=np.array([[1.,2.,0.,0.],[1.,3.,np.cos(x[2]),0.]])
            return h,H

    def test_bad_jacobian_is_detected(self):
        class Wrong(self.LinearLut):
            def model(self,x,case):
                h,H=super().model(x,case);H[1,2]*=-1;return h,H
        with self.assertRaisesRegex(ValueError,'JACOBIAN'):
            q0.fd_check(np,Wrong(),self.case,self.x,self.tol)

    def test_smooth_jacobian(self):
        self.assertEqual(q0.fd_check(np,self.LinearLut(),self.case,self.x,self.tol)['status'],'PASS')

    def test_anchor_pole_is_indeterminate(self):
        x=np.array([4.,0.,.3123,0.])
        self.assertEqual(q0.fd_check(np,self.LinearLut(),self.case,x,self.tol)['status'],'INDETERMINATE_POLE')

    def test_knot_is_not_mislabeled_as_smooth_pass(self):
        x=self.x.copy();u=x[0]-4;v=x[1]
        x[2]=np.arctan2(-v,-u)-np.deg2rad(24.)
        self.assertEqual(q0.fd_check(np,self.LinearLut(),self.case,x,self.tol)['status'],
                         'INDETERMINATE_KNOT_OR_SEAM')


if __name__=='__main__':
    unittest.main()
