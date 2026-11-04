"""Synthetic controls, no native path solver or scientific inputs."""
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from native_math import independent_sum, vector_fields, grouped_spectra, label_chain
from producer import extract, authorize


class NativeMathTests(unittest.TestCase):
    def test_independent_ungrouped_reference(self):
        rng = np.random.default_rng(194)
        a = (rng.normal(size=(2, 2, 31)) + 1j*rng.normal(size=(2, 2, 31))).astype(np.complex64)
        tau = rng.uniform(1e-8, 2e-7, 31).astype(np.float32)
        f = 6.2504e9
        np.testing.assert_allclose(independent_sum(a,tau,f), vector_fields(a,tau,f).sum(0), rtol=1e-11, atol=1e-11)

    def test_permutation_and_missing_groups(self):
        bins = [dict(labels=['DIRECT','[["floor",1]]','[["floor",1]]'],fields=np.array([[1,2],[3,4],[5,6]],complex)),
                dict(labels=['[["floor",1]]','DIRECT','[["wall_y_neg",1]]'],fields=np.array([[7,8],[1,2],[9,10]],complex))]
        out=grouped_spectra(bins); labels=out['group_labels'].tolist()
        np.testing.assert_array_equal(out['group_fields'][labels.index('[["floor",1]]')],[[8,10],[7,8]])
        self.assertEqual(out['group_count'][labels.index('[["floor",1]]'),0],2)
        self.assertTrue(out['group_missing'][labels.index('[["wall_y_neg",1]]'),0])
        self.assertEqual(len(set(out['group_ids'])),3)

    def test_unknown_source_rejected_and_order_preserved(self):
        self.assertEqual(label_chain([4,9],[1,2],{4:'floor',9:'wall_y_pos'},True),'[["floor",1],["wall_y_pos",2]]')
        with self.assertRaises(ValueError):label_chain([4],[1],{},True)
        self.assertEqual(label_chain([4294967295],[0],{},True),'DIRECT')

    def test_raw_metadata_and_direct_identity(self):
        raw=np.arange(12,dtype=np.float32).reshape(1,2,1,2,3)+1
        tau=np.array([1e-8,2e-8,3e-8],np.float32).reshape(1,1,3)
        path=SimpleNamespace(a=(raw,raw/3),tau=tau,
             objects=np.array([[4294967295,4,9]],np.uint32),
             interactions=np.array([[0,1,1]],np.uint32),primitives=np.array([[4294967295,0,1]],np.uint32),
             vertices=np.arange(9,dtype=np.float32).reshape(1,1,1,3,3),
             valid=np.ones((1,2,1,2,3),bool),theta_t=tau,phi_t=tau,theta_r=tau,phi_r=tau)
        out=extract(path,6.2504e9,{4:'floor',9:'wall_y_neg'},float(tau.flat[0]))
        self.assertEqual(out['direct_index'],0)
        self.assertEqual(out['a'].dtype,np.dtype('complex64'))
        self.assertEqual(out['vertices'].shape,(3,1,3))
        np.testing.assert_array_equal(out['source_index'],[0,1,2])
        self.assertEqual(out['valid'].shape,(3,4))
        with self.assertRaises(ValueError):extract(path,6.2504e9,{4:'floor',9:'wall_y_neg'},1.)

    def test_go_rejects_unlisted_pose_and_changed_code(self):
        lock={k:{} for k in ('code_sha256','source_sha256','bank_sha256','thresholds')}
        lock['primary_reference']='F64 primary independent; legacy32 archive comparator'
        lock['precision_contract']='SM0_DUAL_PRECISION_V2'
        lock['archive_los_reference']='legacy_original_expression_complex64'
        lock['coherent_sum_reference']='independent_scalar_float64'
        lock['runtime_lock_sha256']='runtime manifest hash'
        go=dict(schema='SM0_GO_V2',decision='GO',authorized=[dict(case='R4_aB_m0',pose_id=194)],**lock)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'GO.json';p.write_text(json.dumps(go))
            self.assertEqual(len(authorize(p,lock,'R4_aB_m0',194)),64)
            old=dict(go,schema='SM0_GO_V1')
            p.write_text(json.dumps(old))
            with self.assertRaises(ValueError):authorize(p,lock,'R4_aB_m0',194)
            p.write_text(json.dumps(go))
            with self.assertRaises(ValueError):authorize(p,lock,'R4_aB_m0',168)
            wrong=dict(lock,code_sha256={'producer.py':'changed'})
            with self.assertRaises(ValueError):authorize(p,wrong,'R4_aB_m0',194)


if __name__=='__main__':unittest.main()
