import pytest
from central.identity import masked_identity_hint
from central.main import create_app


def test_central_app_exports_contract_routes():
    paths = {route.path for route in create_app().routes}
    assert {
        "/health",
        "/ready",
        "/internal/v1/identity/locate",
        "/internal/v1/identity/verify",
        "/internal/v1/debts",
        "/internal/v1/orders",
        "/internal/v1/payments/verify",
    } <= paths


@pytest.mark.parametrize("name,document,expected", [
    ("Cristian Pérez", "10000001", "C******n · CC 1******1"),
    ("Ana Martínez López", "10000001", "A*a · CC 1******1"),
    ("  María Pérez", "12345678", "M***a · CC 1******8"),
    ("Li Torres", "12", "** · CC **"),
    ("A López", "1", "* · CC *"),
    ("", "", "* · CC *"),
])
def test_identity_hint_shows_only_edges_and_never_full_short_values(name, document, expected):
    assert masked_identity_hint(name, "CC", document) == expected
