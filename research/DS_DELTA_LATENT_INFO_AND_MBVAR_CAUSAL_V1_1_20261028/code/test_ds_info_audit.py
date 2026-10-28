import unittest
import math
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import ds_info_audit as a

class Tests(unittest.TestCase):
    def test_real_case_frame_aggregation(self):
        frames=[pd.DataFrame({'case':[case,case], 'pose_id':[10,12],
                              'accepted':[True,False]}) for case in a.CASE_IDS]
        result=a.combine_case_frames(frames)
        pd.testing.assert_frame_equal(result,pd.concat(frames,ignore_index=True))
        self.assertEqual(len(result),2*len(a.CASE_IDS))
        self.assertEqual(result.index.tolist(),list(range(len(result))))
        with self.assertRaisesRegex(RuntimeError,'MISSING_CASES'):
            a.combine_case_frames(frames[:-1])

    def test_centered_native_gap(self):
        t=np.array([0.,.2,.4,5.,5.2,5.4])
        v=np.array([1.,1.,1.,9.,9.,9.])
        sm=a.centered_time_mean(t,v,1.0)
        np.testing.assert_allclose(sm,v)
    def test_positive_correlated_covariance(self):
        c=np.array([[1.,.1,-.6],[.1,2.,-.7],[-.6,-.7,1.]])
        stabilized=a.stabilize_cov(c)
        self.assertTrue(np.linalg.eigvalsh(stabilized).min()>0)
        self.assertLess(stabilized[0,2],0)
        self.assertLess(stabilized[1,2],0)
    def test_loro_no_leakage(self):
        r=np.random.default_rng(13)
        pieces=[]
        for route in ('R2','R4','R5'):
            bias=r.normal(0,.2,200)
            ds=.4*bias+r.normal(0,.01,len(bias))
            pieces.append(pd.DataFrame({'case':route+'_1','route':route,'accepted':True,
                'bias_slow':bias,'delta1':ds,'e_s':bias+r.normal(0,.01,200),'e_r':r.normal(0,.04,200)}))
        df=pd.concat(pieces,ignore_index=True)
        f=a.fit_fold(df,'R2')
        self.assertTrue(.32<f.slope<.5)
        df.loc[df.route=='R2','delta1']+=500
        f2=a.fit_fold(df,'R2')
        self.assertEqual(f.intercept,f2.intercept)
        self.assertEqual(f.slope,f2.slope)
        self.assertEqual(f.cov.tolist(),f2.cov.tolist())
    def test_extra_nonnegative_info(self):
        rng=np.random.default_rng(90)
        for _ in range(20):
            t=rng.normal(size=(5,5));p=t@t.T/100
            p[4,4]+=0.04
            H2=rng.normal(size=(2,5));H3=np.vstack([H2,rng.normal(size=(1,5))])
            zz=rng.normal(size=(3,3));R=zz@zz.T+np.eye(3)*.2
            k=a.conditional_info(p,H2,H3,R)
            self.assertGreaterEqual(k['relative_precision_gain'],-1e-10)
    def test_zero_new_info(self):
        P=np.diag([1.,1.,.01,1.,.2])
        H2=np.zeros((2,5));H2[0,0]=1;H2[1,2]=4.;H2[1,4]=1.
        H3=np.vstack([H2,np.zeros((1,5))])
        R=np.diag([.01,.02,.01])
        v=a.conditional_info(P,H2,H3,R)
        self.assertAlmostEqual(v['relative_precision_gain'],0,places=12)
    def test_synthetic_full_command(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'new'
            self.assertEqual(a.synthetic_smoke(p),0)
            self.assertTrue((p/'SYNTHETIC_INFORMATION.csv').is_file())
            with self.assertRaises(FileExistsError):a.synthetic_smoke(p)
    def test_fp_delta_chain(self):
        nf=257;idx=np.arange(nf)
        h=np.ones((10,nf,2),np.complex128)
        h[:,:,0]=np.exp(-2j*np.pi*idx[None,:]*.23)
        h[:,:,1]=.6*np.exp(-2j*np.pi*idx[None,:]*.245)
        win=.5-.5*np.cos(2*np.pi*idx/(nf-1))
        s,delta,tap=a.spectrum_to_shape(h,win)
        self.assertEqual(delta.shape,(10,3))
        self.assertTrue(np.isfinite(delta).all())
        s2,d2,t2=a.spectrum_to_shape(h,win,tap_lock=tap)
        np.testing.assert_allclose(s,s2)
        np.testing.assert_allclose(delta,d2)
        np.testing.assert_array_equal(tap,t2)
if __name__=='__main__':unittest.main()
