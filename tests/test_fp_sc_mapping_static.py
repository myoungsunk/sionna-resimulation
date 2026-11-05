import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from qclean_uwb.fp_sc.followup.contracts import Policy,ContractError,sha256
from qclean_uwb.fp_sc.followup.selection import native_support
from qclean_uwb.fp_sc.followup.static_detection import load_static,evaluate_static,StaticObservation,StaticReference,validate_static_specs
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter

class MappingMathTests(unittest.TestCase):
    def test_linear_map_has_analytic_axis_extrema(self):
        x=np.array([1.,2.,3.,0.]);P=np.diag([.01,.04,.09,.001]);a=np.array([2.,-3.,1.,0.])
        def native(points):return points@a,np.zeros(len(points))
        s,_=native_support(x,P,native,Policy())
        center=x@a;radius=2*max(abs(a[:3])*np.sqrt(np.diag(P)[:3]))
        self.assertAlmostEqual(s.low,center-radius-.15);self.assertAlmostEqual(s.high,center+radius+.15)

    def test_zero_covariance_duplicates_center(self):
        seen=[]
        def native(points):seen.append(points);return np.full(7,4.),np.full(7,3.)
        s,o=native_support(np.ones(4),np.zeros((4,4)),native,Policy())
        np.testing.assert_array_equal(seen[0],np.ones((7,4)))
        self.assertAlmostEqual(s.low,3.85);self.assertAlmostEqual(s.high,4.15);self.assertEqual(o,1.)

    def test_invalid_inputs_fail_before_model(self):
        for x,P in [(np.array([np.nan,0,0,0]),np.eye(4)),(np.zeros(4),-np.eye(4)),
                    (np.zeros(4),np.array([[1,1,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1.]]))]:
            with self.assertRaises(ContractError):
                native_support(x,P,lambda p:self.fail('MODEL_CALLED'),Policy())

    def test_coordinate_permutation_and_sign_symmetry(self):
        x=np.array([1.,2.,3.,0.]);P=np.diag([.01,.04,.09,.001]);a=np.array([2.,-3.,1.,0.])
        s,_=native_support(x,P,lambda p:(p@a,np.zeros(len(p))),Policy())
        order=[2,0,1,3];s2,_=native_support(x[order],P[np.ix_(order,order)],lambda p:(p@a[order],np.zeros(len(p))),Policy())
        self.assertAlmostEqual(s.low,s2.low);self.assertAlmostEqual(s.high,s2.high)

    def test_future_state_does_not_affect_current_mapping(self):
        xs=np.zeros((2,4));P=np.eye(4)*.01
        native=lambda p:(p[:,0]+10,np.zeros(len(p)))
        before=native_support(xs[0],P,native,Policy());xs[1]=1000
        self.assertEqual(before,native_support(xs[0],P,native,Policy()))

class StaticPreparationTests(unittest.TestCase):
    def test_loader_separates_reference_and_rejects_fake_time(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=np.ones((257,2),complex)
            np.savez(root/'o.npz',Hrf=a);np.savez(root/'e.npz',reference_H=a*2)
            spec=dict(condition_id='SYNTHETIC',channel='Full',online_npz='o.npz',evaluator_npz='e.npz')
            lock={n:sha256(root/n) for n in ('o.npz','e.npz')}
            online,ev=load_static(root,spec,lock)
            self.assertFalse(hasattr(online,'t'));self.assertFalse(hasattr(online,'prior'))
            np.testing.assert_array_equal(ev.spectrum,a*2)
            np.savez(root/'o.npz',Hrf=a,t=np.array([0.]));lock['o.npz']=sha256(root/'o.npz')
            with self.assertRaises(ContractError):load_static(root,spec,lock)

    def test_static_c_only_keeps_raw_without_model_or_select(self):
        a=np.ones((257,2),complex);adapter=RevisionEvidenceAdapter()
        with patch('qclean_uwb.fp_sc.followup.selection.select',side_effect=AssertionError):
            result=evaluate_static(StaticObservation('SYNTHETIC','Full',a),StaticReference(a),adapter,Policy())
        self.assertEqual(result['raw_tap'],result['selected_tap']);self.assertIsNone(result['history'])
        for mode in ('P','M','PM'):
            with self.assertRaises(ContractError):evaluate_static(None,None,None,Policy(),mode)

    def test_incomplete_grid_rejected(self):
        with self.assertRaises(ContractError):
            validate_static_specs(Path('.'),dict(static_cases={'x':{}},execution_profile='VAB_DETECTION_ONLY_R1',expected_static_cases=48))

    def test_reference_cannot_change_online_decision(self):
        a=np.ones((257,2),complex);observed=StaticObservation('SYNTHETIC','Full',a)
        changed=a*np.exp(-2j*np.pi*np.arange(257)*20/1028)[:,None]
        r1=evaluate_static(observed,StaticReference(a),RevisionEvidenceAdapter(),Policy())
        r2=evaluate_static(observed,StaticReference(changed),RevisionEvidenceAdapter(),Policy())
        self.assertEqual(r1['decision'],r2['decision'])
        self.assertNotEqual(r1['reference_tap'],r2['reference_tap'])

if __name__=='__main__':unittest.main()
