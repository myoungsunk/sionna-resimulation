#!/usr/bin/env python3
"""Dry-run 76-configuration MBVAR-INFO PRE-P3 D1 geometry feasibility with ZERO RT.
DRAFT UNSIGNED, not a physical Sionna scene, not source-material parity.
Check original LOW/HIGH/REV60 generated pose coordinates and shared C10 plate.
"""
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np

C=299792458.
def req(b,msg):
    if not b:raise RuntimeError(msg)
def hash_json(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(pathlib.Path(args.mbvar_code).resolve()))
    import world
    windows={"LOW":"S_c7.5_A0.4_W4","HIGH":"S_c7.5_A0.8_W4","REV60":"REV60_y7_x3.0"}
    plate=dict(cx=2.75,cy=1.50,length_m=2.0,height_m=2.7,orientation_deg=0.,material_candidate="ITU_metal_5mm")
    tx=np.array([2.,2.,2.65])
    step_s=1/(1028*1.95e6)
    records=[]
    for window,key in windows.items():
        tr=world.traj_fn(key)()
        req(len(tr)>=60,"ERR_60_POINTS "+window)
        tr=tr[:60]
        ix=np.rint(np.arange(8)*59/7).astype(int) if window!="REV60" else np.arange(8)
        req(len(np.unique(ix))==8,"ERR_EIGHT_UNIQUE")
        for i,k in enumerate(ix):
            x,y,yaw=map(float,tr[k])
            rx=np.array([x,y,.45])
            pose=world.pose_checks(x,y,yaw,"A")
            req(pose["room_ok"],"ERR_ROOM_COLLISION "+window+str(k))
            d0=float(np.linalg.norm(tx-rx))
            image=np.array([tx[0],2*plate["cy"]-tx[1],tx[2]])
            s=(plate["cy"]-image[1])/(rx[1]-image[1])
            point=image+s*(rx-image)
            d1=float(np.linalg.norm(image-rx))
            dx=abs(point[0]-plate["cx"])
            inside=bool(0<s<1 and dx<plate["length_m"]/2-.10 and .10<point[2]<plate["height_m"]-.10)
            excess_taps=(d1-d0)/C/step_s
            req(inside,"ERR_PLATE_SPECULAR_CONTAINMENT "+window+":"+str(k)+":"+str(point))
            req(0<=excess_taps<=8.,"ERR_LATE_REFLECTOR "+window+":"+str(excess_taps))
            # C00=LoS, C01=LoS+floor, C10=LoS+floor+plate.
            floor_image=np.array([tx[0],tx[1],-tx[2]])
            dfloor=float(np.linalg.norm(floor_image-rx))
            for scene in ("C00_DIRECT","C01_FLOOR","C10_SHARED_PLATE"):
                records.append(dict(scene=scene,window=window,pose_index=int(k),
                    x=x,y=y,yaw_rad=yaw,tx_x=tx[0],tx_y=tx[1],tx_z=tx[2],
                    robot_z=rx[2],direct_range_m=d0,
                    floor_reflection_length_m=dfloor if scene!="C00_DIRECT" else None,
                    plate_reflection_length_m=d1 if scene=="C10_SHARED_PLATE" else None,
                    plate_excess_delay_taps=excess_taps if scene=="C10_SHARED_PLATE" else None,
                    specular_x_m=float(point[0]),specular_y_m=float(point[1]),specular_z_m=float(point[2]),
                    room_margin_m=float(pose["room_margin_m"]),plate_inside=inside,
                    original_pose_key=world.pose_key("NEW_RT_CANARY_PRE_P3_DRAFT","A",x,y,yaw),
                    source_geometry_model="ANALYTIC_IMAGE_GEOMETRY_NO_RT",
                    true_Sionna_RT_executed=False))
    req(len(records)==72,"ERR_SCOPE_72")
    # Frozen study reserved repeated T5 0°/360° identical geometry. Geometric and pose-key only.
    spin=world.t5_spin()
    for scene in ("C00_DIRECT","C01_FLOOR"):
        for i in (0,len(spin)-1):
            q=spin[i]
            records.append(dict(scene=scene,window="T5_REPEAT",pose_index=int(i),
              x=float(q[0]),y=float(q[1]),yaw_rad=float(q[2]),
              tx_x=tx[0],tx_y=tx[1],tx_z=tx[2],robot_z=.45,
              direct_range_m=float(np.linalg.norm(tx-np.r_[q[:2],.45])),
              floor_reflection_length_m=None,plate_reflection_length_m=None,
              plate_excess_delay_taps=None,specular_x_m=None,specular_y_m=None,specular_z_m=None,
              room_margin_m=None,plate_inside=True,
              original_pose_key=world.pose_key("NEW_RT_CANARY_PRE_P3_DRAFT","A",*q),
              source_geometry_model="REPEAT_QA_ONLY",true_Sionna_RT_executed=False))
    req(len(records)==76,"ERR_SCOPE_76")
    qlo=records[72:74];qhi=records[74:76]
    req(qlo[0]["original_pose_key"]==qlo[1]["original_pose_key"] and
        qhi[0]["original_pose_key"]==qhi[1]["original_pose_key"],"ERR_YAW_WRAP_REPEAT")
    keys=list(records[0])
    with (out/"RA5_PREP3_DRAFT_POSE_GEOMETRY.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(records)
    raw=[r["plate_excess_delay_taps"] for r in records if r["scene"]=="C10_SHARED_PLATE"]
    qa=dict(status="PASS_PRE_P3_DRAFT_GEOMETRY_ONLY",
       n_physical_scene_configs_proposed=72,n_repeated_pose_configs=4,total_proposed=76,
       n_analytically_checked_plate_pose=24,max_shared_plate_excess_taps=max(raw),
       min_shared_plate_excess_taps=min(raw),
       scene_geometry_proposal_sha256=hash_json(plate),
       analytic_image_source_verified=True,actual_3D_ray_tracing_calls=0,
       materials_solver_RF_parity="NOT_EVALUATED",
       signed_MBVAR_P3=False,user_numeric_RT_budget="UNAPPROVED",
       canary_max_RT_configurations_if_approved=76,
       direct_only_first_checkpoint=8,
       independent_auditor=False,science_release=False,
       utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_PREP3_NO_RT_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_PREP3_PREFLIGHT "+json.dumps(qa),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--mbvar-code",required=True);ap.add_argument("--out",required=True)
    main(ap.parse_args())
