from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

EPSILON = 1e-6


@dataclass(frozen=True)
class AnxietyEstimate:
    score: float
    label: str
    method: str
    theta_beta_ratio: float
    alpha_sum_ratio: float
    high_freq_ratio: float


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _safe_power(value: Optional[float]) -> float:
    if value is None or not math.isfinite(float(value)):
        return 0.0
    return max(float(value), 0.0)


def _linear_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp(((value - low) / (high - low)) * 100.0)


def anxiety_label(score: float) -> str:
    if score < 33.0:
        return "low"
    if score < 66.0:
        return "medium"
    return "high"


def calculate_anxiety_estimate(
    *,
    delta: float,
    theta: float,
    alpha: float,
    beta: Optional[float] = None,
    gamma: Optional[float] = None,
) -> AnxietyEstimate:
    """Compute a non-clinical qEEG anxiety estimate from band-power ratios.

    The reference PDF emphasizes that real anxiety classification should be
    trained against psychometric labels. This heuristic keeps the runtime demo
    aligned with those biomarkers by combining Theta/Beta, inverse Alpha/Sum,
    and fast-wave dominance rather than trusting an incoming "anxiety" channel.
    """

    delta_power = _safe_power(delta)
    theta_power = _safe_power(theta)
    alpha_power = _safe_power(alpha)
    beta_power = _safe_power(beta)
    gamma_power = _safe_power(gamma)

    if not any((delta_power, theta_power, alpha_power, beta_power, gamma_power)):
        return AnxietyEstimate(
            score=0.0,
            label="no signal",
            method="insufficient signal",
            theta_beta_ratio=0.0,
            alpha_sum_ratio=0.0,
            high_freq_ratio=0.0,
        )

    high_power = beta_power if beta_power > 0.0 else gamma_power
    method = "qEEG band-ratio estimate"
    if beta_power <= 0.0 and gamma_power > 0.0:
        method = "qEEG band-ratio estimate (gamma proxy for beta)"
    elif beta_power <= 0.0 and gamma_power <= 0.0:
        method = "qEEG alpha-theta estimate (limited bands)"

    total_power = delta_power + theta_power + alpha_power + high_power
    theta_beta_ratio = theta_power / (high_power + EPSILON)
    alpha_sum_ratio = alpha_power / (total_power + EPSILON)
    high_freq_ratio = high_power / (alpha_power + high_power + EPSILON)

    tbr_score = _linear_score(theta_beta_ratio, 0.6, 2.8)
    alpha_score = clamp((1.0 - (alpha_sum_ratio / 0.48)) * 100.0)
    high_freq_score = _linear_score(high_freq_ratio, 0.28, 0.72)
    slow_wave_score = _linear_score((delta_power + theta_power) / (total_power + EPSILON), 0.28, 0.72)

    score = (
        (0.35 * tbr_score)
        + (0.35 * alpha_score)
        + (0.20 * high_freq_score)
        + (0.10 * slow_wave_score)
    )
    score = clamp(score)

    return AnxietyEstimate(
        score=score,
        label=anxiety_label(score),
        method=method,
        theta_beta_ratio=theta_beta_ratio,
        alpha_sum_ratio=alpha_sum_ratio,
        high_freq_ratio=high_freq_ratio,
    )
