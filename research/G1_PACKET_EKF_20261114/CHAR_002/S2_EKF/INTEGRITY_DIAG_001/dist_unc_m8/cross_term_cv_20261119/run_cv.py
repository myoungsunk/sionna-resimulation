#!/usr/bin/env python3
"""Independent, leave-one-quadrant-out cross-term audit of BLOCK_C centreline sweep.

Input: pinned STATION_SWEEP_ERRORS.csv (40 stations x 36 yaw, no added noise).
No access to estimator states, route labels, or held-out quadrant during fit.
Usage: python run_cv.py [--input PATH] [--outdir PATH]
"""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

SOURCE_REF = "1d36b227f7c6115dc26e9d3ee12ec98e3fe20fbd"
SOURCE_BLOB = "3731e4efe8dd1e839d2f637d15a88dd1ee88c881"
SOURCE_REL = "../frozen/STATION_SWEEP_ERRORS.csv"
BINS = [(0,3),(3,6),(6,10),(0,1.5),(1.5,3),(3,4.5),(4.5,6),(6,7.5),(7.5,10)]
BOOTS = 10000
BOOT_SEED = 20261119
KEYS = ("eps2","h2","other2","cross","cross_r","cross_b","res2","base2")

def mean(values):
    return sum(values)/len(values)

def quantile(vals, q):
    v=sorted(vals)
    at=(len(v)-1)*q
    lo=math.floor(at)
    t=at-lo
    return v[lo]*(1-t)+v[min(lo+1,len(v)-1)]*t

def fit(train):
    ma=mean([r["a"] for r in train])
    me=mean([r["es"] for r in train])
    va=sum((r["a"]-ma)**2 for r in train)
    assert va>0, "Non-identifiable delta"
    delta=sum((r["a"]-ma)*(r["es"]-me) for r in train)/va
    return delta,me-delta*ma

def read_input(path):
    by=defaultdict(list)
    with open(path,encoding="utf-8",newline="") as fp:
        for r in csv.DictReader(fp):
            row={k:float(v) for k,v in r.items() if k!="st"}
            row["st"]=r["st"]
            by[r["st"]].append(row)
    assert len(by)==40, "Expected all 40 central-line stations"
    assert sum(map(len,by.values()))==1440
    for station,rs in by.items():
        rs.sort(key=lambda r:r["yaw"])
        assert len(rs)==36
        assert all(r["yaw"]==-180+i*10 for i,r in enumerate(rs))
        assert all(r["y"]==0 for r in rs)
        assert len({r["x"] for r in rs})==1
        assert all(abs((r["s_full"]-r["s_los"])-r["es"])<1e-12 for r in rs)
    return by

def analyse_station(station,rs):
    out=dict(station=station,rho=abs(rs[0]["x"]-10.0),n=36)
    for key in KEYS: out[key]=0.0
    train_delta=[]
    for fold in range(4):
        train=[r for r in rs if int((r["yaw"]+180)//90)!=fold]
        test=[r for r in rs if int((r["yaw"]+180)//90)==fold]
        assert len(train)==27 and len(test)==9
        delta,b=fit(train)
        train_delta.append(delta)
        train_e=mean([r["es"] for r in train])
        for r in test:
            h=r["a"]*delta
            rem=r["es"]-h-b
            other=b+rem
            out["eps2"]+=r["es"]**2
            out["h2"]+=h**2
            out["other2"]+=other**2
            out["cross"]+=2*h*other
            out["cross_r"]+=2*h*rem
            out["cross_b"]+=2*h*b
            out["res2"]+=rem**2
            out["base2"]+=(r["es"]-train_e)**2
    for key in KEYS: out[key]/=36
    assert abs(out["eps2"]-out["h2"]-out["other2"]-out["cross"])<1e-12
    assert abs(out["cross"]-out["cross_r"]-out["cross_b"])<1e-12
    out["gamma"]=out["cross"]/out["eps2"]
    out["delta_cv_mean_deg"]=math.degrees(mean(train_delta))
    delta,b=fit(rs)
    pred=[b+delta*r["a"] for r in rs]
    center=mean([r["es"] for r in rs])
    out["r2_insample"]=1-sum((r["es"]-p)**2 for r,p in zip(rs,pred))/sum((r["es"]-center)**2 for r in rs)
    return out

def group_stats(subset):
    def m(key): return mean([r[key] for r in subset])
    base=m("eps2")
    ga=[abs(r["gamma"]) for r in subset]
    return dict(
        gamma=m("cross")/base, gamma_r=m("cross_r")/base,
        gamma_b=m("cross_b")/base,
        median_abs_gamma=quantile(ga,0.5),p90_abs_gamma=quantile(ga,0.9),
        eps_rms=math.sqrt(base),heading_rms=math.sqrt(m("h2")),
        nonheading_rms=math.sqrt(m("other2")),
        loqo_r2_vs_train_mean=1-m("res2")/m("base2"))

def xorshift32(seed):
    value=seed & 0xffffffff
    while True:
        value ^= (value << 13) & 0xffffffff
        value ^= value >> 17
        value ^= (value << 5) & 0xffffffff
        value &= 0xffffffff
        yield value

def analyse_bin(all_stations,lo,hi,idx):
    stations=[r for r in all_stations if lo <= r["rho"] < hi]
    assert stations
    stat=group_stats(stations)
    rand=xorshift32(BOOT_SEED+idx)
    boot_gamma=[]
    boot_median=[]
    for _ in range(BOOTS):
        draw=[stations[next(rand)*len(stations)//(2**32)] for __ in range(len(stations))]
        s=group_stats(draw)
        boot_gamma.append(s["gamma"])
        boot_median.append(s["median_abs_gamma"])
    result={"range_m":f"[{lo},{hi})","stations":len(stations),"poses":36*len(stations)}
    result.update(stat)
    result["gamma_ci_low"]=quantile(boot_gamma,.025)
    result["gamma_ci_high"]=quantile(boot_gamma,.975)
    result["median_abs_gamma_ci_low"]=quantile(boot_median,.025)
    result["median_abs_gamma_ci_high"]=quantile(boot_median,.975)
    return result

def write_csv(path,rows):
    with open(path,"w",newline="",encoding="utf-8") as fp:
        wr=csv.DictWriter(fp,fieldnames=list(rows[0]),lineterminator="\n")
        wr.writeheader()
        for row in rows:
            wr.writerow({k:format(v,".14g") if isinstance(v,float) else v for k,v in row.items()})

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path,default=Path(__file__).parent/SOURCE_REL)
    ap.add_argument("--outdir",type=Path,default=Path(__file__).parent/"regenerated")
    opt=ap.parse_args()
    by=read_input(opt.input)
    rows=[analyse_station(k,v) for k,v in sorted(by.items())]
    bands=[analyse_bin(rows,lo,hi,i) for i,(lo,hi) in enumerate(BINS)]
    opt.outdir.mkdir(parents=True,exist_ok=True)
    write_csv(opt.outdir/"STATIONS_CV.csv",rows)
    write_csv(opt.outdir/"BINS_CV.csv",bands)
    for b in bands:
        print(f'{b["range_m"]:>10} n={b["stations"]:2} gamma={b["gamma"]:+.4%} '
              f'CI=[{b["gamma_ci_low"]:+.4%},{b["gamma_ci_high"]:+.4%}] '
              f'median |gamma_i|={b["median_abs_gamma"]:.4%}')
    print("PASS: 40 stations, 1440 held-out yaw predictions, cross-term identity")

if __name__=="__main__":
    main()
