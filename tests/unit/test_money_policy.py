import pytest
from agil_shared.errors import DomainError
from agil_shared.money import discount_allowed, format_usd, parse_usd


@pytest.mark.parametrize("value", ["1.001", "1e2", "NaN", "-1", "0", "1,00", 1.5])
def test_rejects_ambiguous_or_invalid_money(value):
    with pytest.raises(DomainError):
        parse_usd(value)


def test_exact_discount_boundary_and_roundtrip():
    assert parse_usd("79.99") == 7999
    assert format_usd(7999) == "79.99"
    assert not discount_allowed(10000, 7999)
    assert discount_allowed(10000, 8000)
    assert discount_allowed(10000, 9000)
    assert not discount_allowed(10000, 10000)
