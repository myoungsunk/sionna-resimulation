from __future__ import annotations


def require_probability(name: str, value: float) -> float:
    prob = float(value)
    if prob < 0.0 or prob > 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")
    return prob


def q_clean_path2h(p_nolos: float, p_rd: float) -> float:
    """Frozen PATH-2H q_clean formula."""
    nolos = require_probability("p_NoLoS", p_nolos)
    rd = require_probability("p_RD", p_rd)
    return (1.0 - nolos) * (1.0 - rd)


def q_clean_path3h(p_nolos: float, p_hb_near: float, p_hb_prior: float) -> float:
    """Frozen PATH-3H q_clean formula."""
    nolos = require_probability("p_NoLoS", p_nolos)
    hb_near = require_probability("p_HB_near", p_hb_near)
    hb_prior = require_probability("p_HB_prior", p_hb_prior)
    return (1.0 - nolos) * (1.0 - hb_near) * (1.0 - hb_prior)
