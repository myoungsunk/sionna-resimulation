#!/usr/bin/env python3
"""Validation-only fix: SAMPLES JSON is rounded to six decimal m/deg,
while original trajectory CSV contains full floating precision. No state, sensor,
RF, model parameter, split, or metric is changed. Reject beyond quantization.
"""
from pathlib import Path
import os,hashlib,json
p=Path(__file__).with_name('experiment.py');s=p.read_text()
old="    assert np.max(abs(d.x_eval.to_numpy()-truth[:,0]))<1e-9 and np.max(abs(wrap(d.yaw_eval_rad.to_numpy()-truth[:,2])))<1e-9"
new="""    xy_error=float(np.max(abs(d[['x_eval','y_eval']].to_numpy()-truth[:,:2])))
    yaw_error=float(np.max(abs(wrap(d.yaw_eval_rad.to_numpy()-truth[:,2]))))
    assert xy_error<=5.1e-7 and yaw_error<=9.0e-9,('POSE_MAPPING_NOT_ROUNDING',cm,xy_error,yaw_error)
    dump(OUT/f'{cm}_{ch}_{bias}_POSE_QUANTIZATION_QA.json',{'max_abs_xy_m':xy_error,'max_abs_yaw_rad':yaw_error,'source_decimal_precision':6,'input_or_filter_changed':False,'pose_ids_preserved':True})
    print('POSE_ROUNDING_VERIFIED',cm,ch,bias,xy_error,yaw_error,flush=True)"""
assert s.count(old)==1
s=s.replace(old,new)
out=Path(os.environ['PJ_OUT']);out.mkdir(parents=True,exist_ok=True)
(out/'ACTUAL_REPLAY_EXECUTED.py').write_text(s)
(out/'POSE_ROUNDING_FIX.json').write_text(json.dumps({'original_script_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_script_sha256':hashlib.sha256(s.encode()).hexdigest(),'only_changed':'pose correspondence acceptance for original six-decimal serialization','original_samples_edited':False,'original_timeline_edited':False,'scientific_formula_changed':False},indent=2))
exec(compile(s,str(p),'exec'),{'__name__':'__main__','__file__':str(p)})
