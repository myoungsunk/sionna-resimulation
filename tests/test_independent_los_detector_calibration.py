"""No Sionna or RF flight tests. Pure mathematical/source contract checks."""
import json
import hashlib
import numpy as np
import pytest

from scripts.drive_sim import calibrate_body_range_los as C
from scripts.drive_sim import replay_independent_los_range_calibration as R


def test_hann_firstarrival_has_large_early_detector_bias_even_without_antenna():
    f=np.linspace(6.2504e9,6.7496e9,257)
    d=3.72155881319
    measured=C.flat_los_detected_range(d,f)
    assert -0.85 < measured-d < -0.55
    assert abs(measured-d) > 0.5


def test_calibration_constant_is_fit_from_training_only_and_scored_on_disjoint_sites():
    train=[dict(x_m=2.,y_m=0.,ffd_los_bias_m=-.66,flat_detector_bias_m=-.7,ffd_minus_flat_detector_m=.04),
           dict(x_m=3.,y_m=0.,ffd_los_bias_m=-.62,flat_detector_bias_m=-.7,ffd_minus_flat_detector_m=.08),
           dict(x_m=4.,y_m=0.,ffd_los_bias_m=-.70,flat_detector_bias_m=-.7,ffd_minus_flat_detector_m=0.)]
    hold=[dict(x_m=11.,y_m=.2,ffd_los_bias_m=-.65),
          dict(x_m=12.,y_m=-.2,ffd_los_bias_m=-.68)]
    m=C.robust_fit_and_validation(train,hold)
    assert m["range_offset_m"]==pytest.approx(-.66)
    assert m["n_train_sites"]==3 and m["n_holdout_sites"]==2
    assert m["holdout_residual_rmse_m"]==pytest.approx(np.sqrt((.01**2+.02**2)/2))
    assert m["independent_site_validation_pass"]


def test_evaluation_xy_is_protected_even_before_antenna_patterns_accessed():
    with pytest.raises(ValueError,match="CALIBRATION_SITE_TOO_CLOSE"):
        C.calibrate(None,exclude_xy=C.TRAIN_SITES[0],mounts_deg=(0.,))
    with pytest.raises(ValueError,match="CALIBRATION_SITE_TOO_CLOSE"):
        C.calibrate(None,exclude_xy=C.VALID_SITES[0],mounts_deg=(0.,))


def test_replay_fails_closed_on_calibration_hash_and_invalid_sign(tmp_path):
    meta=dict(schema_version="INDEPENDENT_FFD_LOS_DETECTOR_CAL_V1",
        true_evaluation_RF_input="NOT_USED",
        mount_models={"0":{"range_offset_m":-.66}})
    canonical=json.dumps(meta,sort_keys=True,separators=(",",":"),allow_nan=False)
    meta["calibration_sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
    f=tmp_path/"model.json"
    f.write_text(json.dumps(meta))
    _,model,value=R.load_calibration(f,0.)
    assert value==pytest.approx(-.66)
    meta["mount_models"]["0"]["range_offset_m"]=-.58
    f.write_text(json.dumps(meta))
    with pytest.raises(ValueError,match="SHA_MISMATCH"):
        R.load_calibration(f,0.)


def test_replay_score_reports_not_just_nees_mean():
    x=np.zeros((3,6));true=np.zeros((3,3))
    P=np.broadcast_to(np.eye(6), (3,6,6)).copy()
    s=R.score(x,P,true,np.array([True,True,True]))
    assert s["pose_95_coverage_descriptive"]==1.0
    assert s["pose_nees_lower_025_fraction"]==1.0
    assert s["heading_RMSE_deg"]==0.
