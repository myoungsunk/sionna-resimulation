import sys
import time
from pathlib import Path
import numpy as np
import pytest
from scipy.optimize import brentq
sys.path.insert(0,str(Path(__file__).parents[1]))
from repair_r1_dr import DRReference
from repair_r1_cdf_v2 import AdaptiveCDF as Base
from repair_r1_cdf_v2_cached import AdaptiveCDF as Cached
from test_repair_r1_dr import inputs


def _summary(cls):
    public,cfg=inputs()
    engine=cls(DRReference(public,cfg),8.,1e-6,1e-6,0.)
    start=time.perf_counter()
    mass,error=engine.mass()
    median=brentq(lambda q:engine.mass(0,q)[0]/mass-.5,-8.,8.,xtol=1e-8,rtol=1e-10)
    result=dict(mass=mass,error=error,median=median,records=engine.records,
                evaluations=engine.evaluations,seconds=time.perf_counter()-start)
    if cls is Cached:
        result["cache_info"]=engine._integrated_cached.cache_info()._asdict()
    return result


def test_cache_preserves_normalization_and_bias_median_exactly():
    first=_summary(Base);second=_summary(Cached)
    for key in ("mass","error","median","records","evaluations"):
        assert first[key]==second[key]
    assert second["cache_info"]["hits"]>0
    assert second["cache_info"]["misses"]<second["evaluations"]
    print({"base_seconds":first["seconds"],"cached_seconds":second["seconds"],
           "speedup":first["seconds"]/second["seconds"],
           "cache_info":second["cache_info"],"exact_results":True})


def test_cache_is_engine_local_and_timeout_checked_on_hits():
    public,cfg=inputs();target=DRReference(public,cfg)
    a=Cached(target,8.,1e-6,1e-6,0.)
    b=Cached(target,8.,1e-6,1e-6,0.)
    assert a._factors(0.,0.)==a._factors(0.,0.)
    assert a._integrated_cached.cache_info().hits==1
    assert b._integrated_cached.cache_info().currsize==0
    a.deadline=0.
    with pytest.raises(TimeoutError):a._factors(0.,0.)
