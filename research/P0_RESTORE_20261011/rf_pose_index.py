"""RF bank rows are NOT timeline indices. No inferred or nearest-pose fallback."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd

POSITION_ATOL_M=5.1e-7
YAW_ATOL_DEG=5.1e-7

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): h.update(b)
    return h.hexdigest()

class PoseIndex:
    def __init__(self,samples,n_h_rows):
        if len(samples)!=n_h_rows: raise ValueError('RF_SAMPLE_ROW_COUNT')
        self.samples=list(samples)
        ids=[int(s['pose_id']) for s in self.samples]
        if len(ids)!=len(set(ids)): raise ValueError('DUPLICATE_BANK_POSE_ID')
        self.by_id={pid:i for i,pid in enumerate(ids)}

    def timeline(self,timeline,case,channel_sha='',frequency_sha=''):
        if not np.isfinite(timeline.t_s).all() or np.any(np.diff(timeline.t_s)<=0):
            raise ValueError('NONMONOTONE_RF_TIME')
        rows=[];receipts=[]
        for k,r in enumerate(timeline.itertuples(index=False)):
            pid=int(r.pose_id)
            if pid not in self.by_id: raise ValueError(f'RF_POSE_MISSING:{pid}')
            i=self.by_id[pid];s=self.samples[i]
            dx=float(r.x)-float(s['x']);dy=float(r.y)-float(s['y'])
            da=(float(r.yaw_body_deg)-float(s['yaw_body_deg'])+180)%360-180
            if abs(dx)>POSITION_ATOL_M or abs(dy)>POSITION_ATOL_M or abs(da)>YAW_ATOL_DEG:
                raise ValueError(f'RF_POSE_GEOMETRY_MISMATCH:k={k},pid={pid},d={dx,dy,da}')
            rows.append(i)
            receipts.append(dict(case=case,timeline_k=k,time_s=float(r.t_s),phase=r.phase,
                packet_id=f'{case}:{k}:{pid}',requested_pose_id=pid,H_row=i,H_pose_id=int(s['pose_id']),
                x_requested_m=float(r.x),y_requested_m=float(r.y),yaw_requested_deg=float(r.yaw_body_deg),
                x_H_m=float(s['x']),y_H_m=float(s['y']),yaw_H_deg=float(s['yaw_body_deg']),
                max_xy_difference_m=max(abs(dx),abs(dy)),yaw_difference_deg=da,
                channel_sha256=channel_sha,frequency_sha256=frequency_sha))
        out=pd.DataFrame(receipts)
        if out.packet_id.duplicated().any(): raise ValueError('DUPLICATE_RF_PACKET')
        return np.asarray(rows,dtype=int),out

def regression_tests():
    # Bank IDs need not be monotone or equal row index; timeline may revisit a pose.
    samples=[dict(pose_id=99,x=0.,y=1.,yaw_body_deg=180.),dict(pose_id=7,x=1.,y=2.,yaw_body_deg=10.)]
    time=pd.DataFrame([dict(t_s=i*.2,pose_id=p,x=x,y=y,yaw_body_deg=a,phase='probe')
        for i,(p,x,y,a) in enumerate([(7,1,2,10),(99,0,1,-180),(7,1,2,10)])])
    rows,rec=PoseIndex(samples,2).timeline(time,'synthetic')
    assert rows.tolist()==[1,0,1] and rec.packet_id.nunique()==3
    tests=['shuffled_noncontiguous_bank','repeated_pose_return','yaw_seam','unique_packet_ids']
    for expected,fn in [
      ('DUPLICATE_BANK_POSE_ID',lambda:PoseIndex([samples[0],samples[0]],2)),
      ('RF_SAMPLE_ROW_COUNT',lambda:PoseIndex(samples,3)),
      ('RF_POSE_MISSING',lambda:PoseIndex(samples,2).timeline(time.assign(pose_id=123),'x')),
      ('NONMONOTONE_RF_TIME',lambda:PoseIndex(samples,2).timeline(time.assign(t_s=0),'x')),
      ('RF_POSE_GEOMETRY_MISMATCH',lambda:PoseIndex(samples,2).timeline(time.assign(x=80),'x'))]:
        try:fn()
        except ValueError as e:
            assert expected in str(e);tests.append(expected)
        else:raise AssertionError('Missing fail-closed:'+expected)
    return tests
