import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rf_residual_structure import pairs, unique_rows, fit_ar1, CRITERIA


def row(k,e=1):
    return dict(case='one',channel='full',pose_id=str(k),sample_index=k,t_s=k*.2,
                true_x_m=k*.1,true_y_m=0,true_heading_rad=0,error_s=e)


def test_filtered_gaps_do_not_create_temporal_pairs():
    assert len(pairs([row(0),row(2),row(3)],'error_s',0))==1


def test_repeated_pose_not_independent_training_draw():
    a=row(0); b=row(1);b['pose_id']='0'
    assert len(unique_rows([a,b]))==1


def test_stationary_decay_identifies_numeric_tau_without_admitting_t1():
    rows=[row(k,.8**k) for k in range(12)]
    result=fit_ar1(rows,'error_s',0)
    assert np.isclose(result['rho'],.8)
    assert np.isclose(result['tau_s'],-.2/np.log(.8))
    assert CRITERIA['temporal_intervention_required']
