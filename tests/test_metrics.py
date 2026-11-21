import numpy as np
import pytest

from gbcarbon import metrics


def test_pinball_loss_known_values():
    actual = np.array([10.0, 10.0])
    predicted = np.array([8.0, 12.0])
    # tau=0.5 -> half the MAE
    assert metrics.pinball_loss(actual, predicted, 0.5) == pytest.approx(1.0)
    # tau=0.9 punishes under-prediction harder
    under = metrics.pinball_loss(np.array([10.0]), np.array([8.0]), 0.9)
    over = metrics.pinball_loss(np.array([10.0]), np.array([12.0]), 0.9)
    assert under == pytest.approx(1.8)
    assert over == pytest.approx(0.2)


def test_interval_coverage():
    actual = np.array([1.0, 2.0, 3.0, 4.0])
    lower = np.zeros(4)
    upper = np.array([2.0, 2.0, 2.0, 5.0])
    assert metrics.interval_coverage(actual, lower, upper) == pytest.approx(0.75)


def test_block_bootstrap_detects_a_clear_difference():
    rng = np.random.default_rng(0)
    diff = -1.0 + rng.normal(0, 0.5, size=48 * 60)  # A clearly better
    result = metrics.block_bootstrap_test(diff, n_boot=500)
    assert result["p_value"] < 0.01
    assert result["ci95"][1] < 0


def test_block_bootstrap_near_null_is_insignificant():
    rng = np.random.default_rng(1)
    diff = rng.normal(0, 1.0, size=48 * 60)
    result = metrics.block_bootstrap_test(diff, n_boot=500)
    assert result["p_value"] > 0.05


def test_dm_hac_sign_and_null():
    rng = np.random.default_rng(2)
    base = np.abs(rng.normal(10, 2, size=48 * 30))
    better = base - 1.0
    out = metrics.dm_test_hac(better, base, horizon_steps=48)
    assert out["dm_stat"] < 0
    assert out["p_value"] < 0.05

    same = base + rng.normal(0, 0.1, size=len(base))
    out_null = metrics.dm_test_hac(same, base, horizon_steps=48)
    assert out_null["p_value"] > 0.01


def test_dm_hac_requires_enough_data():
    with pytest.raises(ValueError):
        metrics.dm_test_hac(np.ones(10), np.zeros(10), horizon_steps=4)
