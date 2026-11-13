from pathlib import Path
import json
import numpy as np
from v32_filter import Calibration, GRID, simulate as v32
from v33_filter import simulate as v33
from v33_observation import snap_xy, stationary_xy

rng = np.random.default_rng(990122)
dr = np.cumsum(rng.normal(0, .486, (6, 17)), axis=1)
curves = (GRID[None,None,:] - rng.uniform(-10, 10, (17, 6, 1)))**2
rho, cases = [.0, .51], np.arange(6) % 2
cals = [Calibration(10., 1.2, 12., .0, 6, 6), Calibration(20., 2., 23., .0, 6, 6)]
curve_at = lambda i: (curves[i], curves[i], np.full(6,19))
a = v32(curve_at, dr, cases, rho, cals)
b = v33(curve_at, dr, cases, rho, cals)
assert set(a) == set(b)
for key in a:
    assert np.array_equal(a[key], b[key]), key

u = np.array([[-.3,-.275], [.275,.3], [np.nextafter(.3,1.),.22], [.025,-.025]])
rounded, index, direct = snap_xy(u)
assert index.tolist() == [[0,0],[11,12],[12,10],[6,5]]
assert direct.tolist() == [False,False,True,False]
assert np.array_equal(rounded, np.array([[-.3,-.3],[.25,.3],u[2],[0.,-.05]]))
paths = stationary_xy(np.random.default_rng(804), 4, 17)
rng = np.random.default_rng(804)
manual = np.empty_like(paths)
for i in range(len(paths)):
    p = rng.standard_normal(2) * .13
    for k in range(17):
        p = .9 * p + .13 * np.sqrt(1 - .9**2) * rng.standard_normal(2)
        manual[i,k] = p
assert np.array_equal(paths,manual)

log = dict(filter_finite_fixture_output="bit_equal_to_v32",
           equal_outputs=sorted(a), grid_boundary_and_tie="pass", manual_xy_recursion="bit_equal")
print(json.dumps(log, indent=2))
