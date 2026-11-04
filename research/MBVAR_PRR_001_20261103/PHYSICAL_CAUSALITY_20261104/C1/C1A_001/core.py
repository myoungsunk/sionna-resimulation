"""Truth-free, nonrecursive C1a update of immutable archived Full priors."""
import numpy as np

ARMS = ('FF', 'LF', 'FL', 'LL')


def wrap(angle):
    return (angle + np.pi) % (2 * np.pi) - np.pi


def update(prior, covariance, h, jacobian, mean, noise, accepted, full, los):
    n = len(prior)
    shapes = ((prior, (n, 4)), (covariance, (n, 4, 4)),
              (h, (n, 2)), (jacobian, (n, 2, 4)), (mean, (n, 2)),
              (noise, (n, 2, 2)), (accepted, (n,)),
              (full, (n, 2)), (los, (n, 2)))
    for array, shape in shapes:
        if array.shape != shape or not np.isfinite(array).all():
            raise ValueError('shape/nonfinite input')
    if accepted.dtype != np.dtype(bool):
        raise ValueError('boolean original mask required')
    hp = jacobian @ covariance
    innovation_covariance = hp @ jacobian.swapaxes(-1, -2) + noise
    innovation_covariance = (innovation_covariance + innovation_covariance.swapaxes(-1, -2)) * .5
    gain = np.linalg.solve(innovation_covariance, hp).swapaxes(-1, -2)
    gain = np.where(accepted[:, None, None], gain, 0.)
    z = np.stack((full, np.column_stack((los[:, 0], full[:, 1])),
                  np.column_stack((full[:, 0], los[:, 1])), los), axis=1)
    innovation = z - h[:, None, :] - mean[:, None, :]
    unwrapped = prior[:, None, :] + np.einsum('nij,naj->nai', gain, innovation)
    state = unwrapped.copy()
    state[:, :, 2] = wrap(state[:, :, 2])
    # Rejection in the frozen original returns the prior without another wrap.
    state[~accepted] = prior[~accepted, None, :]
    a = np.eye(4) - gain @ jacobian
    post = a @ covariance @ a.swapaxes(-1, -2) + gain @ noise @ gain.swapaxes(-1, -2)
    post = (post + post.swapaxes(-1, -2)) * .5
    post[~accepted] = covariance[~accepted]
    return dict(x=state, u=unwrapped, P=post, K=gain,
                S=innovation_covariance, innovation=innovation)
