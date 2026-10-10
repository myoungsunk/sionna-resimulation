"""Saved-data polar boundary diagnosis, with independent yaw geometry only."""
from pathlib import Path
import json, numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/DRIVE_SIM_L1_STAGE3_20261008'
rows=json.loads((OUT/'DIAGNOSTIC_SUMMARY.json').read_text(encoding='utf-8'))['pole_details']
S=np.load(OUT/'inputs/hs_lut_2deg.npy')
def yaw(p):
    t,a=np.deg2rad(p[:2]); d=np.diag([1.,-1.,-1.])@np.array([np.sin(t)*np.cos(a),np.sin(t)*np.sin(a),np.cos(t)])
    return float((np.rad2deg(np.arctan2(-d[1],-d[0]))-p[2]+180)%360-180)
result=[]
for r in rows:
    if r['angles'][0]!=.001:continue
    same=[x for x in rows if x['angles'][0]==0 and abs((yaw(x['angles'])-yaw(r['angles'])+180)%360-180)<1e-8]
    assert same
    match=same[0]; th,tx,rx=r['angles']; j=int((tx+180)/2)%180;k=int((rx+180)/2)%180
    result.append(dict(angles=r['angles'],same_tuple_zero_yaw=yaw([0,tx,rx]),near_yaw=yaw(r['angles']),
        original_error=r['delta'],tap=r['index'],matched_zero_angles=match['angles'],matched_zero_yaw=yaw(match['angles']),
        matched_zero_tap=match['index'],matched_zero_s=match['s_direct'],near_s=r['s_direct'],matched_physical_yaw_difference=abs(r['s_direct']-match['s_direct']),
        grid_zero_s=float(S[0,j,k]),grid_two_s=float(S[1,j,k]),zero_weight=1-th/2))
out=dict(method='No new LoS. Independent geometry yaw plus saved zero/near-pole H-derived s and legacy LUT values.',
    max_same_tuple_near_error=max(abs(r['delta']) for r in rows if r['angles'][0]==.001),
    max_matched_physical_yaw_s_difference=max(x['matched_physical_yaw_difference'] for x in result),
    same_tap_all=all(x['tap']==x['matched_zero_tap'] for x in result),cases=result)
(OUT/'POLAR_BOUNDARY_DIAG.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
