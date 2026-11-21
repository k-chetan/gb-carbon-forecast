"""Evaluation metrics and dependence-aware significance tests.

Half-hourly forecast errors are strongly autocorrelated, so plain iid tests
overstate significance. Two remedies are provided: a moving-block bootstrap
with day-length blocks, and a HAC (Bartlett/Newey-West) corrected
Diebold-Mariano statistic.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DAY_STEPS = 48  # half-hour steps per day
BUCKETS = [(0.0, 6.0, "01_06h"), (6.0, 24.0, "07_24h"), (24.0, 48.0, "25_48h")]


def bucket_of(horizons: pd.Series) -> pd.Series:
    """Horizon bucket label per sample (None outside 0 < h <= 48)."""

    def lookup(h: float) -> str | None:
        for low, high, name in BUCKETS:
            if low < h <= high:
                return name
        return None

    return horizons.map(lookup)


def mae(errors: pd.Series | np.ndarray) -> float:
    arr = np.asarray(errors, dtype=float)
    arr = arr[~np.isnan(arr)]
    return float(np.mean(np.abs(arr)))


def pinball_loss(actual: np.ndarray, predicted: np.ndarray, quantile: float) -> float:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    diff = actual - predicted
    loss = np.where(diff >= 0, quantile * diff, (quantile - 1) * diff)
    return float(np.nanmean(loss))


def interval_coverage(
    actual: np.ndarray, lower: np.ndarray, upper: np.ndarray
) -> float:
    actual = np.asarray(actual, dtype=float)
    inside = (actual >= np.asarray(lower, dtype=float)) & (
        actual <= np.asarray(upper, dtype=float)
    )
    return float(np.mean(inside))


def _phi(x: float) -> float:
    """Standard normal CDF via erf (no scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def block_bootstrap_test(
    differential: np.ndarray,
    block_len: int = DAY_STEPS,
    n_boot: int = 2000,
    seed: int = 42,
) -> dict:
    """Moving-block bootstrap test of H0: mean(differential) = 0.

    ``differential`` is loss(A) - loss(B) per window, time-ordered. Returns
    the mean, a bootstrap standard error from day-length blocks, a normal
    two-sided p-value, and the 2.5/97.5 percentile interval of the mean.
    """
    d = np.asarray(differential, dtype=float)
    d = d[~np.isnan(d)]
    n = len(d)
    if n < block_len * 2:
        raise ValueError(f"need at least two blocks of {block_len}; got n={n}")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block_len))
    starts = rng.integers(0, n - block_len + 1, size=(n_boot, n_blocks))
    offsets = np.arange(block_len)
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = (starts[i][:, None] + offsets[None, :]).ravel()[:n]
        means[i] = d[idx].mean()
    point = float(d.mean())
    se = float(means.std(ddof=1))
    z = point / se if se > 0 else math.inf
    p = 2.0 * (1.0 - _phi(abs(z)))
    low, high = np.percentile(means, [2.5, 97.5])
    return {
        "mean": point,
        "se": se,
        "z": float(z),
        "p_value": float(p),
        "ci95": (float(low), float(high)),
        "n": n,
        "block_len": block_len,
    }


def dm_test_hac(loss_a: np.ndarray, loss_b: np.ndarray, horizon_steps: int) -> dict:
    """Diebold-Mariano with Bartlett/HAC variance.

    Negative statistic means A has the lower loss. Truncation lag defaults to
    the forecast-horizon MA order, floored at one day to absorb the diurnal
    error correlation of half-hourly data.
    """
    a = np.asarray(loss_a, dtype=float)
    b = np.asarray(loss_b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    d = a[mask] - b[mask]
    n = len(d)
    if n < DAY_STEPS * 2:
        raise ValueError(f"need at least {DAY_STEPS * 2} paired losses; got {n}")
    lag = max(horizon_steps - 1, DAY_STEPS)
    lag = min(lag, n - 1)
    centred = d - d.mean()
    gamma0 = float(np.mean(centred**2))
    variance = gamma0
    for k in range(1, lag + 1):
        gamma_k = float(np.mean(centred[k:] * centred[:-k]))
        variance += 2.0 * (1.0 - k / (lag + 1.0)) * gamma_k
    variance = max(variance, 1e-12)
    stat = d.mean() / math.sqrt(variance / n)
    p = 2.0 * (1.0 - _phi(abs(stat)))
    return {
        "dm_stat": float(stat),
        "p_value": float(p),
        "mean_diff": float(d.mean()),
        "lag": int(lag),
        "n": int(n),
    }
