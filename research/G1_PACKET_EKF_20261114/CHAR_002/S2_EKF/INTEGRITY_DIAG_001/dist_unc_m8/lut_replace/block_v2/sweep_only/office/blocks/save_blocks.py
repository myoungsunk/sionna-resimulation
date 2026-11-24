"""Save the SWB-O, SWB-C and SWB-C0 blocks as plain data (CSV / JSON) so they can be reused without rebuilding from the sweeps.
  SWB_O_COEFS.csv   : Office LoS stations x 19 psi harmonics (complex rfft coefficients of the 36-yaw curve, samples at psi = -180..170 deg)
  SWB_C_COEFS.csv   : Corridor block station coefficients (40 x-columns x 5 y-lines x 19 harmonics) after the distance-dependent processing
  TABLE_*.json      : variance tables; RANGE_CAL_*.csv: per-route range calibration (mu_r, Rrr) used by each arm
  BLOCK_CONFIGS.json: how each arm is assembled (block, interpolation, mapping, table, range calibration, mean correction)"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/lut8"); sys.path.insert(0, "/home/claude/lut5")
import office_swb as OS, sw_block as SB
out = sys.argv[1]; rows = []
for i, st in OS.ST.iterrows():
    for k in range(OS.K): rows.append(dict(station=st.station, x=st.x, y=st.y, rho=st.rho, k=k, re=OS.COEF[i, k].real, im=OS.COEF[i, k].imag))
pd.DataFrame(rows).to_csv(f"{out}/SWB_O_COEFS.csv", index=False, float_format="%.12g")
C, _ = SB.build_station_coefs(); rows = []
for i, x in enumerate(SB.XS):
    for j, y in enumerate(SB.YS):
        for k in range(SB.K): rows.append(dict(col=i, line=j, x=x, y=y, rho=SB.RHO[i, j], k=k, re=C[i, j, k].real, im=C[i, j, k].imag))
pd.DataFrame(rows).to_csv(f"{out}/SWB_C_COEFS.csv", index=False, float_format="%.12g")
json.dump(json.load(open("/home/claude/lut8/TABLE_SWBO.json")), open(f"{out}/TABLE_SWB_O.json", "w"), indent=1)
json.dump(json.load(open("/home/claude/lut5/TABLE_SWB_FULLCO.json")), open(f"{out}/TABLE_SWB_C.json", "w"), indent=1)
CAL = np.load("/home/claude/office/O3_CAL.npz")
for tag in ("T1", "T0"):
    rr = []
    for r in ("O01", "O02", "O03L"):
        for n, (mr, rv) in enumerate(zip(CAL[f"{r}/{tag}/mu_r"], CAL[f"{r}/{tag}/Rrr"])): rr.append(dict(route=r, packet=n, mu_r=mr, Rrr=rv))
    pd.DataFrame(rr).to_csv(f"{out}/RANGE_CAL_{tag}.csv", index=False, float_format="%.12g")
cfg = {
 "common": {"psi_samples_deg": "-180:10:170", "harmonics": "k = 0..18 of numpy rfft over the 36 samples; s(psi) = sum_k w_k Re(c_k exp(i k (psi + pi))), w = [1, 2..2, 1] / 36",
            "filter": "F2 replay (m8_replay.py, unchanged); h and Jacobian replaced through h_ref.SwapS; mean correction mu_s = 0"},
 "SWB-O": {"space": "Office", "block": "SWB_O_COEFS.csv (25 LoS stations, raw station curves)", "interpolation": "Delaunay-linear in (x, y), nearest station outside the hull; d/dx, d/dy central difference 1 mm",
           "table": "TABLE_SWB_O.json (leave-one-station-out)", "range_calibration": "RANGE_CAL_T1.csv (Office sweep)", "code": "../code/office_swb.py"},
 "SWB-C": {"space": "Corridor block used in the Office", "block": "SWB_C_COEFS.csv (Corridor processed station curves)", "interpolation": "cubic spline in x per y-line, linear in y (corridor coordinates)",
           "mapping": "Office (x, y, psi) -> Corridor (10 + s*rho, 0, psi); rho = |(x, y) - (5, 2.2)|, s = sign(x - 5); chain-rule Jacobian", "table": "TABLE_SWB_C.json (Corridor full column-out)",
           "range_calibration": "RANGE_CAL_T1.csv (Office sweep)", "code": "../code/corr2office.py"},
 "SWB-C0": {"space": "Corridor block used in the Office", "block": "same as SWB-C", "table": "TABLE_SWB_C.json", "range_calibration": "RANGE_CAL_T0.csv (Corridor sweep)", "code": "../code/corr2office.py"}}
json.dump(cfg, open(f"{out}/BLOCK_CONFIGS.json", "w"), indent=1)
