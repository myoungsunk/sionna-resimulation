"""R3 fixed-failure numerical tests from the immutable P2 preflight artifact.

Four original failures are loaded byte-for-byte from Actions archive. The
original 1e-8 stationarity criterion, objective and covariances are unchanged.
"""
import io
import json
import os
from pathlib import Path
import zipfile
import numpy as np
import pytest
from core import map_update,SyntheticRF
from d3_pre_audit import METADATA, path_for, sha

@pytest.mark.parametrize('route,algorithm,step,nsha,jsha',METADATA)
def test_frozen_four_cases(route,algorithm,step,nsha,jsha):
    archive=os.environ.get('EKF4_R3_FROZEN_ARCHIVE')
    assert archive and Path(archive).is_file()
    with zipfile.ZipFile(archive) as z:
        raw=z.read(path_for(route,algorithm,'FAILED_STEP.npz'))
        assert sha(raw)==nsha
        with np.load(io.BytesIO(raw),allow_pickle=False) as arr:
            mu,P,obs,R=(arr[k].copy() for k in ('prior_x','prior_P','z','R'))
        result=map_update(mu,P,obs,SyntheticRF(),R,max_iter=80,gradient_tol=1e-8)
        assert result.status=='CONVERGED', (route,algorithm,result.status,result.gradient_inf)
        assert result.gradient_inf<=1e-8
        assert np.linalg.eigvalsh(result.P)[0]>0
        assert len(result.history)<=81

def test_genuine_uphill_direction_cannot_be_accepted():
    from stable_descent import verified_step_r3
    def ev(y):
        # Constant flat objective with a deliberately spurious descent g
        # cannot certify positive numerical progress via flat gradients.
        return 2.,np.array([1.]),np.eye(1)
    y=np.array([0.]);d=np.array([1e-8]);g=np.array([1.])
    out=verified_step_r3(ev,y,d,2.,g,2.+1e-14,g,np.eye(1))
    assert out is None
