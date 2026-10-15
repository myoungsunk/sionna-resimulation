import numpy as np
import pandas as pd
import pytest
from stage_b import split_masks,site_weights,predictor_table,scores

def test_split_removes_other_route_same_xy():
 d=pd.DataFrame({'route':['R2','R2','R4','R4','R5'],'x_eval':[0,1,0.00001,2,3],'y_eval':[0]*5})
 tr,te,dist=split_masks(d,'R2')
 assert te.tolist()==[1,1,0,0,0]
 assert tr.tolist()==[0,0,0,1,1]
def test_site_weights():
 d=pd.DataFrame({'x_eval':[0,0,1],'y_eval':[0,0,0]})
 np.testing.assert_array_equal(site_weights(d),[.5,.5,1.])
def test_oracle_forbidden():
 with pytest.raises(ValueError):predictor_table(pd.DataFrame({'e_total_eval':[1]}),['e_total_eval'])
def test_calibration_moments_independent():
 e=np.array([-1.,1.,-1.,1.]);r=np.ones(4);w=np.ones(4)
 m=scores(e,r,w)
 assert m['normalized_error2_mean']==1 and m['error95_coverage']==1
 assert abs(m['Gaussian_NLL']-(.5*np.log(2*np.pi)+.5))<1e-12

def test_nonfinite_data_not_silently_imputed():
 with pytest.raises(ValueError):predictor_table(pd.DataFrame({'range_m':[np.nan]}),['range_m'])

def test_training_invariant_to_test_labels():
 from stage_b import fit_train
 d=pd.DataFrame({'route':['R2']*50+['R4']*100,'range_m':np.linspace(1,5,150),
                 'x_eval':np.arange(150),'y_eval':np.zeros(150),'e_total_eval':np.sin(np.arange(150))})
 tr=d.route!='R2';m1=fit_train(d,tr,['range_m'])
 d.loc[~tr,'e_total_eval']=10000
 m2=fit_train(d,tr,['range_m'])
 np.testing.assert_array_equal(m1.predict([[1.],[3.]]),m2.predict([[1.],[3.]]))
