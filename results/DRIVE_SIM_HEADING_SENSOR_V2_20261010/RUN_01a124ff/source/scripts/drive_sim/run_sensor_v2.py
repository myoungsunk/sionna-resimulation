"""Explicit, serial sensor-v2 CPU runner; outputs never overwrite legacy results."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.drivesim.evaluation_v2 import evaluate
from qclean_uwb.drivesim.sensor_v2 import CONDITIONS, SensorV2Config
from qclean_uwb.drivesim.filters import FilterConfig

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--model-version',choices=('sensor-v2','legacy'),required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed-start',type=int,default=200)
    p.add_argument('--runs',type=int,default=48)
    p.add_argument('--dt',type=float,default=.2)
    p.add_argument('--sensor-config',type=Path,help='explicit JSON SensorV2Config; defaults are neutral for uncalibrated new terms')
    p.add_argument('--filter-config',type=Path,help='separate JSON FilterConfig; sensor truth is never copied into inference')
    p.add_argument('--condition',choices=tuple(CONDITIONS),default='all')
    p.add_argument('--level',type=int,choices=(0,1,2),default=1)
    p.add_argument('--initial',choices=('exact','legacy-prior'),nargs='+',default=['exact','legacy-prior'])
    p.add_argument('--wheelbase',choices=('matched','unknown'),nargs='+',default=['matched','unknown'])
    a=p.parse_args()
    if a.model_version=='legacy':p.error('legacy uses run_experiments.py/run_route_experiments.py; this runner requires v2 raw inputs')
    if a.runs<1:p.error('runs must be positive')
    sensor=SensorV2Config(**json.loads(a.sensor_config.read_text())) if a.sensor_config else None
    filt=FilterConfig(**json.loads(a.filter_config.read_text())) if a.filter_config else None
    if filt and filt.model_version!='sensor-v2':p.error('filter config must explicitly specify sensor-v2')
    evaluate(a.out,a.seed_start,a.runs,tuple(a.initial),tuple(a.wheelbase),a.condition,a.level,a.dt,sensor,filt)
