import unittest
import numpy as np
from pilot import choose, polar, observe

class FrozenSelectorTests(unittest.TestCase):
    def sample(self):
        strong=np.zeros((1,1028))
        strong[0,23]=.16
        strong[0,25]=.4
        strong[0,30]=1.
        return strong,np.array([1.]),np.array([25])

    def test_correct_late_first_path_with_supported_cir(self):
        strong,peak,raw=self.sample()
        selected,status=choose(raw,strong,peak,np.array([23*.14955]),np.array([.2]),.14955)
        self.assertEqual(int(selected[0]),23)
        self.assertEqual(int(status[0]),1)

    def test_do_not_change_plausible_baseline(self):
        strong,peak,raw=self.sample()
        selected,status=choose(raw,strong,peak,np.array([25*.14955]),np.array([.2]),.14955)
        self.assertEqual(int(selected[0]),25)
        self.assertEqual(int(status[0]),0)

    def test_invalid_or_unreliable_prior_must_not_force(self):
        strong,peak,raw=self.sample()
        for p,s in [(float('nan'),.2),(23*.14955,.9)]:
            selected,status=choose(raw,strong,peak,np.array([p]),np.array([s]),.14955)
            self.assertEqual(int(selected[0]),25)
            self.assertEqual(int(status[0]),2)

    def test_no_direct_evidence_no_fabricated_candidate(self):
        strong,peak,raw=self.sample()
        strong[0,23]=0
        selected,status=choose(raw,strong,peak,np.array([23*.14955]),np.array([.2]),.14955)
        self.assertEqual(int(selected[0]),25)

    def test_signed_pol_power_bounds(self):
        c=np.zeros((2,1028,2),complex)
        c[0,10]=[2.,1.]
        c[1,11]=[1.,2.]
        np.testing.assert_allclose(polar(c,np.array([10,11])),[.6,-.6])

    def test_ifft_shapes_and_leading_edge(self):
        h=np.ones((1,257,2),complex)
        cir,strong,peak,tap=observe(h)
        self.assertEqual(cir.shape,(1,1028,2))
        self.assertEqual(int(tap[0]),0)

if __name__=='__main__':unittest.main()
