from datetime import date

from src.application.analytics import _get_fallback_rate


def test_fallback_returns_same_month_rate():
    rate_lookup = {
        ("USD", date(2025, 1, 10)): 42.0,
        ("USD", date(2025, 2, 5)): 41.5,
    }
    result = _get_fallback_rate("USD", date(2025, 1, 15), rate_lookup)
    assert result == 42.0


def test_fallback_returns_closest_across_months():
    """When no same-month rate exists, return closest from any month."""
    rate_lookup = {
        ("USD", date(2025, 2, 5)): 41.5,
    }
    result = _get_fallback_rate("USD", date(2025, 1, 15), rate_lookup)
    assert result == 41.5


def test_fallback_picks_closest_in_month():
    rate_lookup = {
        ("USD", date(2025, 1, 3)): 42.0,
        ("USD", date(2025, 1, 20)): 43.0,
    }
    result = _get_fallback_rate("USD", date(2025, 1, 18), rate_lookup)
    assert result == 43.0


def test_fallback_no_rates_at_all():
    result = _get_fallback_rate("USD", date(2025, 1, 15), {})
    assert result is None


def test_fallback_cross_month_picks_nearest():
    """Closest rate may be several months away."""
    rate_lookup = {
        ("USD", date(2025, 3, 1)): 40.0,
        ("USD", date(2025, 6, 15)): 39.0,
    }
    # March 1 is closer to Jan 15 than June 15
    result = _get_fallback_rate("USD", date(2025, 1, 15), rate_lookup)
    assert result == 40.0
