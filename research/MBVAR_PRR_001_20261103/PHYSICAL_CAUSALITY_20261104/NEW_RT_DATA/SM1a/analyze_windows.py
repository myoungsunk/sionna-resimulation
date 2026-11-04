import csv, hashlib, io, itertools, json, math, subprocess, tarfile
from pathlib import Path
import numpy as np

root=Path(__file__).resolve().parent
b1=root.parent/"SM0B/B1"
sm2=root.parent/"SM2a"
sm2.mkdir(exist_ok=True)
def read(name):
    return list(csv.DictReader((root/name).open()))
def save(path,rows):
    with path.open("w",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
def sha(data):
    return hashlib.sha256(data).hexdigest()
with tarfile.open(b1/"evidence.tar.gz") as t:
    h=np.load(io.BytesIO(t.extractfile("out/R4B_168_LoS/RAW_H.npz").read()))
    df=np.diff(h["frequency"])
    assert np.all(df==df[0]) and h["cir"].shape==(1,1028,2)
    step=299792458/(1028*df[0])
poses={(r['route'],r['pose_id']):r for r in read("SM1_KEY_LEDGER.csv")}
rows=read("PAIRED_WINDOWS.csv")
events=[]
for route, group in itertools.groupby(rows,key=lambda r:r['route']):
    track=list(group); dist=0
    for i,r in enumerate(track):
        p=poses[route,r['pose_id']]
        xy=(float(p['x']),float(p['y']))
        if i:dist+=math.dist(prev,xy)
        prev=xy
        r.update(full_raw_m=int(r['full_tap'])*step,los_raw_m=int(r['los_tap'])*step,
                 delta_range_m=int(r['delta_tap'])*step,along_track_m=dist)
    for active,g in itertools.groupby(track,key=lambda r:int(r['delta_tap'])!=0):
        seg=list(g)
        if not active:continue
        first,last=seg[0],seg[-1]
        events.append(dict(route=route,first_s=first['t_s'],last_s=last['t_s'],samples=len(seg),
          sampled_span_s=round(float(last['t_s'])-float(first['t_s']),2),sampled_track_m=last['along_track_m']-first['along_track_m'],
          preceding_zero_s=track[track.index(first)-1]['t_s'] if first!=track[0] else 'LEFT_CENSORED',
          following_zero_s=track[track.index(last)+1]['t_s'] if last!=track[-1] else 'RIGHT_CENSORED',
          max_delta_tap=max(int(r['delta_tap']) for r in seg)))
save(root/'OBSERVATION_ERRORS.csv',rows);save(root/'TAP_EVENTS.csv',events)
lock=json.loads((b1/'INPUT_LOCK.json').read_text())['hashes']
sample=(b1.parent/'B0/SAMPLES.fixture.json').read_bytes()
assert sha(sample)==next(v for k,v in lock.items() if k.endswith('R4_aB_m0/SAMPLES.json'))
p=json.loads(sample)[168]
geom='src/qclean_uwb/scenarios/corridor.py'
code=subprocess.check_output(['git','show','594691f:'+geom])
assert sha(code)==lock[geom]
ns={'__name__':'__main__'}
exec(compile(code,geom,'exec'),ns)
setup=ns['CorridorSetup'](anchor_x_m=10.)
x,y=p['x'],p['y'];L,W,H=setup.robot_body_lwh_m
rx=setup.robot_position(x,y);tx=setup.anchor_position
assert all(0<v[0]<setup.length_m and abs(v[1])<setup.y_half and 0<v[2]<setup.height_m for v in [rx,tx])
assert len(setup.surfaces())==6 and H<rx[2]
angles=[-35.7,0.,35.7,180.,p['yaw_body_deg']]
assert len(set(a%360 for a in angles))==5
candidates=[]
for yaw in angles:
    c,s=map(abs,(math.cos(math.radians(yaw)),math.sin(math.radians(yaw))))
    dx=(L*c+W*s)/2;dy=(L*s+W*c)/2
    clearance=min(x-dx,setup.length_m-x-dx,setup.y_half-abs(y)-dy)
    assert clearance>=setup.robot_clearance_m
    candidates.append(dict(x=x,y=y,z=rx[2],yaw_deg=yaw,xy_json_sha256=sha(json.dumps([x,y],separators=(',',':')).encode()),
       min_horizontal_body_clearance_m=clearance,required_clearance_m=setup.robot_clearance_m,
       corridor_collision=False,geometric_los=True,source='B1_R4_168' if yaw==angles[-1] else 'NEW',new_calls=0 if yaw==angles[-1] else 514))
save(sm2/'YAW_CANDIDATES.csv',candidates)
print(step,events,candidates[0])
