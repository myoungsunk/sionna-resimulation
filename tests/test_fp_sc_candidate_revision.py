import importlib.util,pathlib,unittest
import numpy as np
from qclean_uwb.fp_sc.candidate_revision import generate_revision,ARMS
from qclean_uwb.fp_sc.candidates import generate_pools,CandidateConfig
R=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('r1check',R/'scripts/check_fp_sc_candidate_revision.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
def waveform(x,y=()):
    c=np.zeros((1028,2),complex);c[:len(x),0]=x;c[:len(y),1]=y;return c

class RevisionTests(unittest.TestCase):
    def verify(self,c):
        for arm in ARMS:
            actual=generate_revision(c,arm);reference=checker.scalar(c,arm)
            for mode,p in actual.items():
                self.assertEqual(p['candidate_taps'],reference['pools'][mode]['taps'])
                self.assertEqual(p['supported_taps'],reference['pools'][mode]['supported_taps'])
                self.assertEqual(p['overflow'],reference['pools'][mode]['overflow'])
        self.assertEqual(generate_revision(c,'V0'),generate_pools(c))
    def test_broad_rising_one_port_null(self):
        c=waveform([0,.1,.2,.3,.5,.7,.9,1,.5,0]);self.verify(c)
        self.assertEqual(generate_revision(c,'VA')['TWO_PORT_UNION']['supported_taps'],list(range(2,8)))
    def test_shallow_right_valley(self):
        c=waveform([0,.1,.2,.35,.5,.48,.7,1,.2,0]);self.verify(c)
        p=generate_revision(c,'VB')['TWO_PORT_UNION']
        self.assertEqual(next(l for l in p['lobes'] if l['peak_tap']==4)['reason'],'LEFT_RISE_SUPPORTED')
        self.assertIn(2,p['supported_taps'])
    def test_plateau_boundary_weak_direct(self):
        self.verify(waveform([1,.1,0,.01,.03,.01,0,.1,.3,.6,1,1,.4,0]))
        self.assertNotIn(11,generate_revision(waveform([0,.1,.2,.3,.5,.7,.9,1,1,0]),'VAB')['TWO_PORT_UNION']['supported_taps'])
    def test_zero(self):self.verify(waveform([]))
    def test_nonfinite(self):
        c=waveform([0,1,0]);c[3,1]=np.nan
        for arm in ARMS:self.assertEqual(generate_revision(c,arm)['TWO_PORT_UNION']['candidate_taps'],[])
    def test_noise_only_below_floor(self):
        c=waveform([0,.01,.03,.01,0]);config=CandidateConfig(noise_var_per_bin=1.)
        for arm in ARMS:self.assertEqual(generate_revision(c,arm,config)['TWO_PORT_UNION']['candidate_taps'],[])
    def test_overflow_not_truncated(self):
        c=waveform(np.tile([0,.2,.4,.6,.8,1,.4,0],100));self.verify(c)
        p=generate_revision(c,'VAB')['TWO_PORT_UNION'];self.assertTrue(p['overflow']);self.assertGreater(len(p['candidate_taps']),64)
    def test_two_port_overlap_groups_and_phase(self):
        c=waveform([0,.1,.3,.6,1,.4,0],[0,.3,.7,1,.4,.1,0]);c[:,1]*=1j;self.verify(c)
    def test_v0_unchanged_and_superset(self):
        c=waveform([0,.1,.3,.7,1,.98,1.2,.1,0]);self.verify(c)
        original=generate_pools(c)
        for arm in ARMS:
            for mode,p in generate_revision(c,arm).items():self.assertTrue(set(original[mode]['candidate_taps'])<=set(p['candidate_taps']))

if __name__=='__main__':unittest.main()
