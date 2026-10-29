#!/usr/bin/env python3
"""Geometric crosscheck of 25 original Sionna ray departure directions.
Checks finite reflection facets and ray-angle consistency. This tests path
geometry against the specified ideal rectangular scene, not material Fresnel/EM.
"""
import argparse,collections,csv,hashlib,io,itertools,json,math,pathlib,zipfile
import numpy as np
from qclean_uwb.features.reflection_attribution import image_delays
from qclean_uwb.drivesim.paths import path_residuals
C=299792458.;STRICT=5e-14
PLANES={"floor":(2,0.),"ceiling":(2,2.7),"wall_y_neg":(1,-1.2),
        "wall_y_pos":(1,1.2),"end_x_min":(0,0.),"end_x_max":(0,20.)}
def virtual(rx,seq):
 img=rx.copy()
 for s in reversed(seq):
  axis,val=PLANES[s];img[axis]=2*val-img[axis]
 return img
def direction(theta,phi):
 return np.array([math.sin(theta)*math.cos(phi),math.sin(theta)*math.sin(phi),math.cos(theta)])
def valid_geometry(tx,rx,seq):
 img=virtual(rx,seq)
 length=np.linalg.norm(img-tx)
 if length==0:return dict(valid=False,reason="ZERO_LENGTH",depart=np.zeros(3))
 start=tx.copy();d=(img-tx)/length
 orig=d.copy();travel=0.
 for surf in seq:
  ax,val=PLANES[surf]
  if abs(d[ax])<1e-14:return dict(valid=False,reason="PARALLEL_WALL",depart=orig)
  t=(val-start[ax])/d[ax]
  if t<=1e-8:return dict(valid=False,reason="NONFORWARD_INTERSECTION",depart=orig)
  hit=start+d*t
  if not (-1e-6<=hit[0]<=20+1e-6 and -1.2-1e-6<=hit[1]<=1.2+1e-6 and -1e-6<=hit[2]<=2.7+1e-6):
   return dict(valid=False,reason="OUTSIDE_FACE",depart=orig)
  travel+=t
  d=d.copy();d[ax]=-d[ax];start=hit
 remaining=rx-start
 scalar=float(remaining@d)
 perpendicular=float(np.linalg.norm(remaining-scalar*d))
 if scalar<=0:return dict(valid=False,reason="WRONG_FINAL_DIRECTION",depart=orig)
 if perpendicular>1e-6:return dict(valid=False,reason="MISSED_RX",depart=orig)
 travel+=scalar
 if abs(travel-length)>5e-5:return dict(valid=False,reason="INCONSISTENT_LENGTH",depart=orig)
 return dict(valid=True,reason="FINITE_FACET_SPECULAR",depart=orig)
def main(args):
 out=args.out;out.mkdir(parents=True,exist_ok=True)
 lock=json.loads(args.lock.read_text())
 rows=[]
 with zipfile.ZipFile(args.zip) as z:
  for item in lock["items"]:
   case=item["case"];tag=item["tag"]; path=item["original_relpath"]
   with np.load(io.BytesIO(z.read(path)),allow_pickle=False) as data:
    tau=np.asarray(data["tau"],float);ang=data["ang"];x=float(data["x"]);y=float(data["y"])
   tx=np.array([4 if case.endswith("_aA") else 10,0.,2.65],float);rx=np.array([x,y,.45])
   tab=image_delays(tx,rx,20,1.2,2.7)
   res,_,_,_=path_residuals(tau,tx,rx,20.,1.2,2.7)
   bad=np.flatnonzero(res>STRICT)
   if len(bad)!=item["expected_n_strict_paths"]:raise ValueError("ERR_BAD_RAY_COUNT "+case+tag)
   for rid in bad:
    raw_tau=float(tau[rid]);dep=direction(float(ang[0,rid]),float(ang[1,rid]))
    allcand=[]
    for seq,dt in tab.items():
     dif=abs(raw_tau-dt)
     if dif>STRICT:continue
     g=valid_geometry(tx,rx,seq)
     angle=float(math.degrees(math.acos(np.clip(dep@g["depart"],-1.,1.))))
     allcand.append(dict(seq=seq,dt=dt,dif=dif,geometry_valid=g["valid"],angle_deg=angle,reason=g["reason"]))
    if not allcand:raise ValueError("ERR_NO_UNMERGED_CANDIDATE")
    best_delay=min(allcand,key=lambda r:r["dif"])
    best_angle=min(allcand,key=lambda r:r["angle_deg"])
    valid=[x for x in allcand if x["geometry_valid"]]
    valid_best=min(valid,key=lambda r:r["angle_deg"]) if valid else None
    vals={n:True for n in []}
    row=dict(case=case,tag=tag,ray_index=int(rid),raw_tau_s=raw_tau,
      n_images_within_strict=len(allcand),n_physically_finite_specular=len(valid),
      nearest_delay_seq=">".join(best_delay["seq"]) if best_delay["seq"] else "LOS",
      nearest_delay_valid=best_delay["geometry_valid"],nearest_delay_angle_deg=best_delay["angle_deg"],
      best_angle_seq=">".join(best_angle["seq"]) if best_angle["seq"] else "LOS",
      best_angle_deg=best_angle["angle_deg"],best_angle_valid=best_angle["geometry_valid"],
      best_valid_seq=">".join(valid_best["seq"]) if valid_best and valid_best["seq"] else ("LOS" if valid_best else "MISSING"),
      best_valid_angle_deg=valid_best["angle_deg"] if valid_best else None,
      angle_matches_finite_specular=bool(valid_best and valid_best["angle_deg"]<0.1),
      nominal_direction_source="original_trace_angular_theta_t_phi_t",
      raw_ray_physical_material="UNASSESSED_SIONNA_FRESNEL")
    rows.append(row)
 assert len(rows)==25
 with (out/"G3_25_ANGLE_SPECULAR_GEOMETRY.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
 summary=dict(status="SPECULAR_GEOMETRY_CHECK_NOT_FULL_EM_VALIDATION",n=25,
   n_finite_specular_candidate=sum(r["n_physically_finite_specular"]>0 for r in rows),
   n_departure_angle_match=sum(r["angle_matches_finite_specular"] for r in rows),
   n_nearest_delay_invalid=sum(not r["nearest_delay_valid"] for r in rows),
   max_best_valid_angle_deg=max((r["best_valid_angle_deg"] for r in rows if r["best_valid_angle_deg"] is not None),default=None),
   nonmatching_cases=[{k:r[k] for k in ("case","tag","ray_index","nearest_delay_seq","best_valid_seq","best_valid_angle_deg")} for r in rows if not r["angle_matches_finite_specular"]],
   limitations="Ray direction/finite planar specular test only. Does not independently validate solver phase, Jones/Fresnel material, diffraction, path amplitude or all 354410 paths.",
   source="original delivered 23 NPZ, original theta_t/phi_t")
 (out/"G3_25_SPECULAR_GEOMETRY_QA.json").write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary))
if __name__=="__main__":
 ap=argparse.ArgumentParser()
 for k in ("zip","lock","out"):ap.add_argument("--"+k,required=True,type=pathlib.Path)
 main(ap.parse_args())
