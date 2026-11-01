import re
from decimal import Decimal, InvalidOperation

from .errors import DomainError


def parse_usd(value: str) -> int:
    """USD decimal estricto a centavos; rechaza floats, exponente y precisión extra."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value):
        raise DomainError("invalid_amount", "Usa un importe USD positivo con hasta dos decimales.", 422)
    try:
        cents = int(Decimal(value) * 100)
    except (InvalidOperation, ValueError):
        raise DomainError("invalid_amount", "Importe USD inválido.", 422) from None
    if cents <= 0 or cents > 999_999_999:
        raise DomainError("invalid_amount", "Importe USD fuera de rango.", 422)
    return cents


def format_usd(cents: int) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0:
        raise ValueError("Se requieren centavos enteros no negativos")
    return f"{cents // 100}.{cents % 100:02d}"


def discount_allowed(base_cents: int, offer_cents: int) -> bool:
    return 0 < offer_cents < base_cents and offer_cents * 100 >= base_cents * 80
