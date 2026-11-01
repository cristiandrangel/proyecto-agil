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
