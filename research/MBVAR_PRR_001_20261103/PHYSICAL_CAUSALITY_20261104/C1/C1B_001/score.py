"""Post-update descriptive scoring only; never imported by the gate core."""
import numpy as np
from conditional import ARMS


def errors(x, truth):
    xy = np.linalg.norm(x[:, :, :2]-truth[:, None, :2], axis=2)
    yaw = x[:, :, 2]-truth[:, None, 2]
    heading = np.abs(np.degrees((yaw+np.pi) % (2*np.pi)-np.pi))
    return xy, heading


def evaluate(result, c1a, truth, t, ids, gates, route, bias, seed):
    xy, heading = errors(result['x'], truth)
    ax, ah = errors(c1a['x'], truth)
    rows, summaries = [], []
    primary = t >= 30.
    for j, arm in enumerate(ARMS):
        for k in range(len(t)):
            rows.append((route,bias,seed,int(ids[k]),float(t[k]),arm,
                         bool(gates[k,j]),bool(gates[k,0]),float(xy[k,j]),float(heading[k,j]),
                         float(xy[k,j]-xy[k,0]),float(heading[k,j]-heading[k,0]),
                         float(xy[k,j]-ax[k,j]),float(heading[k,j]-ah[k,j])))
        summaries.append(dict(route=route,bias=bias,seed=seed,arm=arm,n=int(primary.sum()),
            mean_xy_m=float(xy[primary,j].mean()),median_xy_m=float(np.median(xy[primary,j])),
            mean_heading_deg=float(heading[primary,j].mean()),median_heading_deg=float(np.median(heading[primary,j])),
            mean_delta_xy_vs_FF=float((xy[primary,j]-xy[primary,0]).mean()),
            mean_delta_heading_vs_FF=float((heading[primary,j]-heading[primary,0]).mean()),
            mean_delta_xy_vs_C1a=float((xy[primary,j]-ax[primary,j]).mean()),
            mean_delta_heading_vs_C1a=float((heading[primary,j]-ah[primary,j]).mean()),
            accepted_all=int(gates[:,j].sum()),
            accepted_primary=int(gates[primary,j].sum()),
            newly_accepted_all=int((gates[:,j] & ~gates[:,0]).sum()),
            newly_rejected_all=int((~gates[:,j] & gates[:,0]).sum()),
            newly_accepted_primary=int((gates[primary,j] & ~gates[primary,0]).sum()),
            newly_rejected_primary=int((~gates[primary,j] & gates[primary,0]).sum())))
    return rows, summaries
