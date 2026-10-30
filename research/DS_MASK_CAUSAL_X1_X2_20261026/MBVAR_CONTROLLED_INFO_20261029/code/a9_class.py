"""AMENDMENT-009 F1: convergence class v3.1 (pure function; no FFD import so it is unit-testable in the gate job)."""
TAU = 0.01            # chi^2: a probe descent larger than this means the point is not a certified local minimum
DEC_TOL = 1e-10       # analytic Newton decrement for smooth convergence (= filters.V2_DEC_TOL)


def class_v31(dec_A: float, dmin: float, tau: float = TAU, dec_tol: float = DEC_TOL) -> str:
    """A probe descent overrides the analytic decrement (fixes the A008 short-circuit)."""
    if not dmin >= -tau:                      # also catches NaN probe results
        return "NOT_CERTIFIED"
    return "CONVERGED_SMOOTH" if dec_A <= dec_tol else "LOCAL_MIN_CERTIFIED"


def class_v3_a008(dec_A: float, dmin: float, tau: float = TAU, dec_tol: float = DEC_TOL) -> str:
    """The AMENDMENT-008 rule, reproduced for the W1 comparison."""
    if dec_A <= dec_tol:
        return "CONVERGED_SMOOTH"
    return "LOCAL_MIN_CERTIFIED" if dmin >= -tau else "NOT_CERTIFIED"
