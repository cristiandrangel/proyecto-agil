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
    ("Cristian Pérez", "10000001", "Nombre: C••••••n\nDocumento: CC 10000001"),
    ("Ana Martínez López", "10000001", "Nombre: A•a\nDocumento: CC 10000001"),
    ("  María Pérez", "12345678", "Nombre: M•••a\nDocumento: CC 12345678"),
    ("Li Torres", "12", "Nombre: ••\nDocumento: CC 12"),
    ("A López", "1", "Nombre: •\nDocumento: CC 1"),
    ("", "", "Nombre: •\nDocumento: CC "),
])
def test_identity_hint_masks_name_and_keeps_document_visible(name, document, expected):
    assert masked_identity_hint(name, "CC", document) == expected
