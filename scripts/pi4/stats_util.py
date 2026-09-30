"""Small statistics helpers for the Pi comparison scripts (no third-party packages).

The runs of one image are near-deterministic (spread well under 0.1%), so the interval
is mostly a guard against a stray outlier or a drifting board rather than a claim about
a random population. Runs within one boot share the boot's cache and predictor state, so
treat the interval as "how repeatable is this measurement", not as a proof of independence.
"""

from __future__ import annotations

import math
import statistics

# Two-sided 95% Student t critical values, df = 1..30 (df above 30: 1.96).
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
        2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
        2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t95(df: float) -> float:
    d = int(round(df))
    if d < 1:
        return float("inf")
    return _T95[d - 1] if d <= 30 else 1.96


def mean_ci95(vals: list[float]) -> tuple[float, float]:
    """(mean, half-width of the 95% CI of the mean)."""
    n = len(vals)
    m = statistics.mean(vals)
    if n < 2:
        return m, float("inf")
    return m, t95(n - 1) * statistics.stdev(vals) / math.sqrt(n)


def welch_delta_pct(base: list[float], other: list[float]) -> tuple[float, float, bool]:
    """Change of `other` against `base` as (percent, 95% CI half-width in percentage
    points, significant?). Welch's unequal-variance interval on the difference of means;
    significant means the interval excludes zero."""
    mb, mo = statistics.mean(base), statistics.mean(other)
    nb, no = len(base), len(other)
    if nb < 2 or no < 2 or mb == 0:
        return 100.0 * (mo - mb) / mb if mb else float("nan"), float("inf"), False
    vb, vo = statistics.variance(base) / nb, statistics.variance(other) / no
    se = math.sqrt(vb + vo)
    if se == 0.0:
        diff = mo - mb
        return 100.0 * diff / mb, 0.0, diff != 0.0
    df = (vb + vo) ** 2 / ((vb ** 2) / (nb - 1) + (vo ** 2) / (no - 1))
    half = t95(df) * se
    diff = mo - mb
    return 100.0 * diff / mb, 100.0 * half / mb, abs(diff) > half


def fmt_delta(base: list[float], other: list[float]) -> str:
    pct, half, sig = welch_delta_pct(base, other)
    tag = "significant" if sig else "NOT significant"
    return f"{pct:+.2f}% (95% CI +-{half:.2f} pp, {tag})"
