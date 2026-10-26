"""Synthetic RF -> archive -> original T2 pose loader -> Office labels.

Frozen original loader functions are used without mocking the loader. The full
motion CSV is supplied; this test does not qualify the route-generator branch.
"""
import json
import shutil
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from office_transfer_core import load_lock,sha256,restore_release_snapshot,source_dataset_one,expected_frequencies


@pytest.mark.parametrize('bad_clock',[False,True])
def test_original_t2_pose_and_label_pipeline(tmp_path,bad_clock):
    audit=tmp_path/'audit'
    loader=audit/'research/POWERJOINT_AUDIT_RERUN_20261020/T2_NEW_ROUTE_BASELINE'
    loader.mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent/'fixtures/t2_prepare_inputs.py',loader/'prepare_inputs.py')
    # Exact fields used by prepare_new_route from upstream PROTOCOL_LOCK revision 3.
    (loader/'PROTOCOL_LOCK.json').write_text(json.dumps({'motion_dt_s':.25,
        'motion_time_tolerance_s':1e-9,'legacy_euler_lateral_tolerance_m':2e-6}))
    raw=tmp_path/'raw';case=raw/'O01/CASES/O01_O0_M45_FULL';case.mkdir(parents=True)
    motion=pd.DataFrame({'route_id':['O01']*5,'pose_id':np.arange(5),'t_s':np.arange(5)*.25,
        'x_m':np.arange(5)*.1,'y_m':0.,'z_m':.45,'yaw_body_deg':0.,'yaw_antenna_deg':45.,
        'rf_sample':[1,0,1,0,1]})
    radio=motion.iloc[[0,2,4]].copy()
    if bad_clock:motion.loc[1,'t_s']+=.01
    motion.to_csv(raw/'O01/ROUTE_POSE.csv',index=False)
    radio.to_csv(case/'RADIO_POSE.csv',index=False)
    wave=np.exp(-2j*np.pi*np.arange(257)*25/(4*257))
    h=np.zeros((3,257,2,2),complex);h[:,:,0,0]=wave;h[:,:,1,0]=.5*wave
    los=h.copy();los[1]=0
    for name,value in [('H_FULL.npy',h),('H_DIRECT_LOS.npy',los),
                       ('LOS_EXISTS.npy',np.array([True,False,True])),
                       ('FREQUENCIES_HZ.npy',expected_frequencies(load_lock()))]:
        np.save(case/name,value)
    archive=tmp_path/'route.tar.gz'
    with tarfile.open(archive,'w:gz') as ar:ar.add(raw/'O01',arcname='O01')
    out=restore_release_snapshot(archive,tmp_path/'extracted',sha256(archive))
    lock=load_lock();meta=lock['paths']['O01'];meta.update(rf_n=3,motion_n=5,archive_sha256=sha256(archive))
    for name in meta['files']:meta['files'][name]=sha256(case/name)
    class SyntheticSource:
        def batch(self,states,case,gradient=False):
            return np.tile([2.,.6],(len(states),1)),None
    if bad_clock:
        with pytest.raises(ValueError,match='MOTION_NOT_FULL_QUARTER_SECOND_CLOCK'):
            source_dataset_one(out,'O01',audit,SyntheticSource(),lock)
        return
    frame,qa=source_dataset_one(out,'O01',audit,SyntheticSource(),lock)
    assert frame.pose_id.tolist()==[0,2,4]
    assert frame.valid_for_training.tolist()==[True,False,True]
    assert np.isnan(frame.loc[1,'e_s'])
    assert qa['model_vs_direct_los_max_abs']<1e-12
