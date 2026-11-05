"""Fail-closed prior integrity, separate from numerical mapping validity.

No reviewed integrity provider exists in R1. VALID is reserved, never inferred
from covariance, interval width, CIR agreement, or a caller's boolean.
"""
from dataclasses import dataclass
import math
import numpy as np
from .contracts import ContractError, covariance, finite

INTEGRITY_RECIPE = 'PRIOR_INTEGRITY_R1_UNKNOWN_UNLESS_REVIEWED_PROVIDER'


@dataclass(frozen=True)
class PriorIntegrity:
    state: str = 'UNKNOWN'
    reason: str = 'NO_REVIEWED_INTEGRITY_PROVIDER'
    source: str = 'ARCHIVED_PREMEASUREMENT_PRIOR'

    def __post_init__(self):
        self.validate()

    def validate(self):
        if self.state == 'VALID':
            raise ContractError('PRIOR_VALID_PROVIDER_NOT_IMPLEMENTED')
        if self.state not in ('UNKNOWN', 'INVALID') or not self.reason or not self.source:
            raise ContractError('INVALID_PRIOR_INTEGRITY_RECORD')


def assess_prior(x, P, t, previous_t=None):
    """Structural checks only. Valid numerical input still returns UNKNOWN."""
    try:
        finite(x, (4,), 'PRIOR')
        covariance(P, 4)
        if not math.isfinite(t) or (previous_t is not None and
                (not math.isfinite(previous_t) or t <= previous_t)):
            raise ContractError('INVALID_PRIOR_TIME')
    except (ContractError, ValueError, TypeError, np.linalg.LinAlgError) as exc:
        return PriorIntegrity('INVALID', str(exc) or type(exc).__name__)
    return PriorIntegrity()


def checked_integrity(value):
    if value is None:
        return PriorIntegrity()
    if type(value) is not PriorIntegrity:
        raise ContractError('PRIOR_INTEGRITY_RECORD_REQUIRED')
    value.validate()
    return value
