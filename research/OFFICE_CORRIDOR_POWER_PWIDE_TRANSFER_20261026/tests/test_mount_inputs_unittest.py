"""Mount-aware input, masking, observer and leakage regression checks; no fit."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import office_mount_inputs as M


class Model:
    def __init__(self):
        self.mounts = []

    def batch(self, states, conf, gradient=False):
        self.mounts.append(conf['mount_deg'])
        distance = np.sqrt((states[:, 0]-5)**2 + (states[:, 1]-2.2)**2 + 2.2**2)
        return np.c_[distance + M.__dict__.get('B_OLD', -.5315983906250129),
                     np.full(len(states), .6 if conf['mount_deg'] == 45 else 0.)], None

    def fit(self, *args, **kwargs):
        raise AssertionError('Fitting is prohibited')


def fixture(root, mount):
    folder = root / f'O01_O0_M{mount}_FULL'
    folder.mkdir()
    n = 4
    pose = pd.DataFrame({'route_id':['O01']*n, 'pose_id':np.arange(n), 't_s':np.arange(n)*.25,
        'x_m':np.arange(n)+.5, 'y_m':np.full(n,.75), 'z_m':np.full(n,.45),
        'yaw_body_deg':np.zeros(n), 'yaw_antenna_deg':np.full(n,float(mount)),
        'phase':['STRAIGHT']*n, 'rf_sample':np.ones(n,int)})
    pose.to_csv(folder/'RADIO_POSE.csv',index=False)
    motion=root/f'motion_{mount}.csv';pose.to_csv(motion,index=False)
    h=np.ones((n,257,2,2),np.complex128)
    if mount == 45:h[:,:,0,:]=2
    flags=np.array([True,True,True,False])
    los=h.copy();los[~flags]=0
    for name in M.CHANNELS:np.save(folder/(name+'.npy'),h if name=='H_FULL' else los)
    freq=6250400000+1950000*np.arange(257)
    np.save(folder/'FREQUENCIES_HZ.npy',freq)
    np.save(folder/'LOS_EXISTS.npy',flags)
    np.save(folder/'LOS_EXISTS_BY_BIN.npy',np.broadcast_to(flags[:,None],(n,257)))
    observed=M.observe_port(h[:,:,:,0],freq)
    pd.DataFrame({'channel':['FULL']*n,'pose_id':pose.pose_id,'t_s':pose.t_s,
        'fp_tap':observed.fp_full,'s':observed.s_fp,'range_raw_m':observed.range_m}).to_csv(folder/'FIRST_PATH.csv',index=False)
    (folder/'SCENE_METADATA.json').write_text('{}')
    (folder/'QA_RECEIPT.json').write_text(json.dumps({'status':'FULL_CASE_QA_PASS',
        'case':{'case_id':folder.name,'mount_deg':mount,'anchor_m':[5,2.2,2.65]}}))
    (folder/'SHA256SUMS.txt').write_text(''.join(M.sha256(p)+'  '+p.name+'\n' for p in sorted(folder.iterdir())))
    return {'case':folder.name,'route':'O01','mount_deg':mount,'folder':str(folder),
            'rf_n':n,'motion_n':n,'motion_path':str(motion),'files':M.sealed_files(folder)}


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_both_mounts_reach_model_and_blocked_labels_masked(self):
        model=Model()
        for mount in [0,45]:
            frame,qa=M.build_case(fixture(self.root,mount),model)
            self.assertEqual(qa['n_train_valid'],3)
            self.assertLess(qa['model_vs_direct_los_max_abs'],1e-12)
            self.assertTrue(frame.loc[3,['e_r','e_s','d0_gt_source','h_s_gt_source']].isna().all())
            self.assertTrue(np.isfinite(frame.loc[3,'s_fp']))
        self.assertEqual(model.mounts,[0.,45.])
    def test_features_exclude_gt_and_split_groups_share_mounts(self):
        frames=[M.build_case(fixture(self.root,m),Model())[0] for m in [0,45]]
        frame=pd.concat(frames,ignore_index=True)
        features,labels,groups=M.tables(frame)
        self.assertEqual(len(features),8)
        self.assertFalse(set(['e_r','e_s','x_eval','s_direct_los_audit_only','los_exists']) & set(features))
        self.assertEqual(groups.spatial_group.iloc[:4].tolist(),groups.spatial_group.iloc[4:].tolist())
        self.assertTrue(groups.partition.eq('UNASSIGNED_NO_TRAINING').all())
    def test_wrong_mount_rejected(self):
        case=fixture(self.root,0);case['mount_deg']=45
        with self.assertRaisesRegex(ValueError,'BODY_ANTENNA_MOUNT_CHANGED'):M.validate_case(case)
    def test_legacy_mount45_receipt_without_mount_field(self):
        case=fixture(self.root,45);path=Path(case['folder'])/'QA_RECEIPT.json'
        qa=M.read(path);del qa['case']['mount_deg'];M.write(path,qa)
        M.validate_case(case)
        qa['case']['mount_deg']=0;M.write(path,qa)
        with self.assertRaisesRegex(ValueError,'RF_GEOMETRY'):M.validate_case(case)
    def test_mount0_receipt_requires_explicit_mount(self):
        case=fixture(self.root,0);path=Path(case['folder'])/'QA_RECEIPT.json'
        qa=M.read(path);del qa['case']['mount_deg'];M.write(path,qa)
        with self.assertRaisesRegex(ValueError,'RF_GEOMETRY'):M.validate_case(case)
    def test_motion_timeline_preserves_both_mounts_and_clock(self):
        cases=[fixture(self.root,m) for m in [0,45]]
        timeline=M.motion_timeline({'cases':cases})
        self.assertEqual(len(timeline),8)
        for case in cases:
            rows=timeline[timeline.case==case['case']]
            self.assertTrue(rows.mount_deg.eq(case['mount_deg']).all())
            pd.testing.assert_frame_equal(rows.drop(columns=['case','mount_deg']).reset_index(drop=True),
                                          pd.read_csv(case['motion_path']))
    def test_duplicate_or_reversed_time_rejected(self):
        case=fixture(self.root,0);path=Path(case['folder'])/'RADIO_POSE.csv'
        pose=pd.read_csv(path);pose.loc[1,'t_s']=0;pose.to_csv(path,index=False)
        with self.assertRaisesRegex(ValueError,'TIME_NOT_STRICT'):M.validate_case(case)
    def test_hash_tamper_rejected(self):
        case=fixture(self.root,0);path=Path(case['folder'])/'H_FULL.npy'
        with path.open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'CASE_SEAL_HASH'):M.sealed_files(path.parent)
    def test_blocked_direct_cannot_be_fabricated(self):
        case=fixture(self.root,0);path=Path(case['folder'])/'H_DIRECT_LOS.npy'
        arr=np.load(path);arr[-1]=1;np.save(path,arr)
        with self.assertRaisesRegex(ValueError,'BLOCKED_DIRECT_NOT_ZERO'):M.build_case(case,Model())
    def test_duplicate_key_rejected(self):
        frame=M.build_case(fixture(self.root,0),Model())[0]
        with self.assertRaisesRegex(ValueError,'COMPOSITE_KEY_DUPLICATE'):M.tables(pd.concat([frame,frame]))
    def test_parity_threshold_cannot_change(self):
        with self.assertRaisesRegex(ValueError,'PARITY_THRESHOLD_CHANGED'):
            M.validate_manifest({'schema':'OFFICE_MOUNT_INPUT_V1','source_audit_commit':M.SOURCE_COMMIT,
                                 'source_los_model_max_abs_tol':1})


if __name__ == '__main__':
    unittest.main()
