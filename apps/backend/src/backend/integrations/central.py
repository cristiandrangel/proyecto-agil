"""Role-scoped HTTP boundary. No central database access belongs in the backend."""

from __future__ import annotations

from typing import Any

import httpx
from agil_shared.errors import DomainError


class CentralClient:
    def __init__(self, settings: Any, role: str = "agent", *, transport=None):
        if role not in {"agent", "operator"}:
            raise ValueError("Unknown central role")
        self.settings = settings
        self.role = role
        self.transport = transport

    async def request(self, method: str, path: str, **kwargs) -> Any:
        if not path.startswith("/") or path.startswith("//") or ".." in path or "?" in path:
            raise ValueError("Central paths must be relative API paths without query strings")
        token = getattr(self.settings, f"central_{self.role}_token")
        token = token.get_secret_value() if hasattr(token, "get_secret_value") else str(token)
        headers = dict(kwargs.pop("headers", {}))
        # Authentication is always selected by the server, never by a tool argument.
        headers = {k: v for k, v in headers.items() if k.lower() != "authorization"}
        headers["Authorization"] = f"Bearer {token}"
        if grant := kwargs.pop("grant", None):
            headers["X-Customer-Grant"] = grant
        if key := kwargs.pop("idempotency_key", None):
            headers["Idempotency-Key"] = key
        base = str(self.settings.central_api_url).rstrip("/")
        if base.endswith("/internal/v1"):
            base = base[: -len("/internal/v1")]
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport, follow_redirects=False
            ) as client:
                response = await client.request(
                    method, base + "/internal/v1" + path, headers=headers, **kwargs
                )
        except httpx.RequestError:
            raise DomainError(
                "central_unavailable",
                "La central no está disponible. Intenta de nuevo.",
                status=503,
                retryable=True,
            ) from None
        if response.is_error or response.is_redirect:
            code, message = "central_error", "La central no pudo completar la operación."
            try:
                data = response.json()
                # The central contract guarantees safe messages; never return the HTTP body.
                if isinstance(data, dict) and isinstance(data.get("code"), str):
                    code = data["code"][:100]
                    message = str(data.get("message", message))[:250]
            except (ValueError, TypeError):
                pass
            status = (
                response.status_code
                if response.status_code in {400, 401, 403, 404, 409, 410, 422, 423, 429, 503}
                else 503
            )
            raise DomainError(code, message, status=status, retryable=status in {429, 503})
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise DomainError(
                "central_invalid_response",
                "La central devolvió una respuesta inválida.",
                status=503,
                retryable=True,
            ) from None
