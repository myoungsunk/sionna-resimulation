"""Exact detector-tap range adapter. No fitted offset or hidden smoothing.

The frozen range observation is quantized. Its derivative is zero within an
unchanged tap cell, undefined at a jump. This adapter intentionally does not
reuse the old geometric distance Jacobian for the new observation equation.
"""
import numpy as np


class SourceTapRange:
    def __init__(self, source):
        self.source = source
        self.freqs = source.freqs

    def batch(self, states, case, gradient=True, return_diagnostics=False):
        pred, J, diag = self.source.batch(states, case, gradient=gradient,
                                          return_diagnostics=True)
        pred = pred.copy()
        pred[:, 0] = diag['native_range']
        if J is not None:
            J = J.copy()
            J[:, 0, :] = 0.
        # The existing s row uses the identical detected tap and source field.
        diag = dict(diag, range_jacobian_kind='piecewise_constant_active_tap',
                    interpolation='none')
        return (pred, J, diag) if return_diagnostics else (pred, J)

    def model(self, state, case):
        pred, J = self.batch(np.asarray(state)[None, :], case)
        return pred[0], J[0]


class RefitOffsetRange:
    """Separately labelled B_REFIT_ONLY control; offset must be train-only."""
    def __init__(self, source, offset_m, old_offset_m=-.5315983906250129):
        self.source, self.offset_m, self.old_offset_m = source, offset_m, old_offset_m
        self.freqs = source.freqs

    def batch(self, states, case, gradient=True, return_diagnostics=False):
        pred, J, diag = self.source.batch(states, case, gradient=gradient,
                                          return_diagnostics=True)
        pred = pred.copy(); pred[:, 0] += self.offset_m-self.old_offset_m
        return (pred, J, diag) if return_diagnostics else (pred, J)

    def model(self, state, case):
        pred, J = self.batch(np.asarray(state)[None, :], case)
        return pred[0], J[0]
