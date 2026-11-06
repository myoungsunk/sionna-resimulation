import unittest
import numpy as np
from qclean_uwb.fp_sc.followup.contracts import Policy,Support,STEP_M,ContractError
from qclean_uwb.fp_sc.followup.bridge import RevisionEvidenceAdapter
from qclean_uwb.fp_sc.followup.detection import binding_for
from qclean_uwb.fp_sc.followup.selection import prepare_candidate_set
from qclean_uwb.fp_sc.followup.integrity import PriorIntegrity
from qclean_uwb.fp_sc.followup.input_sensitivity import raw_score_grid,scenario_grid,build_intervals

class SensitivityTests(unittest.TestCase):
    def test_actual_score_equivalence(self):
        cir=np.zeros((1028,2),complex);cir[:10,0]=[0,.1,.2,.3,.5,.7,.9,1,.5,0]
        e=RevisionEvidenceAdapter().evidence(cir);policy=Policy();binding=binding_for(e,policy)
        c=next(r['score'] for r in prepare_candidate_set(e,'C',policy,binding=binding).rows if r['tap']==e.raw_tap)
        rng=np.random.default_rng(20261106);p=[];m=[]
        for _ in range(200):
            center=e.raw_tap*STEP_M+rng.uniform(-1,1);width=rng.uniform(0,2)
            p.append([center-width/2,center+width/2]);m.append([center-.2,center+.2])
        p=np.array(p);m=np.array(m);p[0]=np.nan;m[1]=np.nan
        scores,flags,status=raw_score_grid(e.raw_tap,c,p,m,policy)
        for k in range(len(p)):
            ps=None if np.isnan(p[k]).any() else Support(*p[k],.15,'SYNTHETIC')
            ms=None if np.isnan(m[k]).any() else Support(*m[k],.15,'SYNTHETIC')
            for i,mode in enumerate(('C','P','M','PM')):
                actual=prepare_candidate_set(e,mode,policy,prior=ps,motion=ms,binding=binding)
                raw=next((r for r in actual.rows if r['tap']==e.raw_tap),None)
                if raw is None:self.assertEqual(flags[k,i],-1)
                else:
                    self.assertAlmostEqual(scores[k,i],raw['score'],places=12)
                    self.assertEqual(flags[k,i],int(raw['score']>=2))

    def test_hand_calculated_boundary_and_width_hold(self):
        r=10*STEP_M;p=np.array([[r+.15,r+.3],[r-.1,r+.1],[r-1,r+1]])
        scores,flags,status=raw_score_grid(10,1.,p,p,Policy())
        self.assertAlmostEqual(scores[0,1],2.,places=12)
        self.assertEqual(scores[1,1],1.)
        self.assertEqual(flags[2,1],-1);self.assertEqual(flags[2,2],0)

    def test_no_valid_bypass(self):
        with self.assertRaises(ContractError):PriorIntegrity('VALID','DIAGNOSTIC','SPOOF')

    def test_history_causality_and_age(self):
        t=np.arange(20)*.2;raw=np.ones(20,dtype=int)*10;lo=np.ones(20);hi=lo+.3;off=np.zeros(20)
        grid=[g for g in scenario_grid() if g['legacy'] is None]
        before=build_intervals(12,t,np.zeros(20),raw,lo,hi,off,{},grid,Policy())
        raw[12:]=100;off[13:]=100
        after=build_intervals(12,t,np.zeros(20),raw,lo,hi,off,{},grid,Policy())
        for x,y in zip(before,after):np.testing.assert_equal(x,y)
        idx=next(i for i,g in enumerate(grid) if g['id']=='M_LAG_2.2')
        self.assertTrue(np.isnan(before[1][idx]).all())
        zero=build_intervals(0,t,np.zeros(20),raw,lo,hi,off,{},grid,Policy())
        self.assertTrue(np.isnan(zero[1]).all())

if __name__=='__main__':unittest.main()
