"""Scoring after C1a updates. No truth enters the update core."""
import numpy as np
from core import ARMS, wrap


def score(result, truth, t, pose_id, route, bias, seed):
    x = result['x']
    xy = np.linalg.norm(x[:, :, :2] - truth[:, None, :2], axis=2)
    heading = np.abs(np.degrees(wrap(x[:, :, 2] - truth[:, None, 2])))
    rows = []
    summaries = []
    for j, arm in enumerate(ARMS):
        for k in range(len(t)):
            rows.append((route, bias, seed, int(pose_id[k]), float(t[k]), arm,
                         float(xy[k, j]), float(heading[k, j]),
                         float(xy[k, j] - xy[k, 0]), float(heading[k, j] - heading[k, 0])))
        eligible = t >= 30.
        summaries.append(dict(route=route, bias=bias, seed=seed, arm=arm,
                              n=int(eligible.sum()),
                              mean_xy_m=float(xy[eligible, j].mean()),
                              median_xy_m=float(np.median(xy[eligible, j])),
                              mean_heading_deg=float(heading[eligible, j].mean()),
                              median_heading_deg=float(np.median(heading[eligible, j])),
                              mean_delta_xy_m=float((xy[eligible, j]-xy[eligible, 0]).mean()),
                              mean_delta_heading_deg=float((heading[eligible, j]-heading[eligible, 0]).mean())))
    return rows, summaries
