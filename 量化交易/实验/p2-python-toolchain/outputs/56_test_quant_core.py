
import numpy as np
import pytest

def simple_returns(prices):
    values = np.asarray(prices, dtype=float)
    if np.any(values <= 0):
        raise ValueError("prices must be positive")
    return values[1:] / values[:-1] - 1

@pytest.mark.parametrize("prices, expected", [
    ([100.0, 110.0], [0.10]),
    ([100.0], []),
    ([100.0, 90.0, 99.0], [-0.10, 0.10]),
])
def test_returns(prices, expected):
    np.testing.assert_allclose(simple_returns(prices), expected, rtol=1e-12, atol=1e-12)

def test_zero_price_rejected():
    with pytest.raises(ValueError):
        simple_returns([100.0, 0.0])

def test_signal_is_lagged_and_cost_is_monotone():
    signal = np.array([1.0, 0.0, 1.0])
    position = np.r_[0.0, signal[:-1]]
    returns = np.array([0.01, -0.02, 0.03])
    gross = position * returns
    turnover = np.abs(np.diff(np.r_[0.0, position]))
    net = gross - 0.001 * turnover
    assert position[1] == signal[0]
    assert np.prod(1 + net) <= np.prod(1 + gross)
