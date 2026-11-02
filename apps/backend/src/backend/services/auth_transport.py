"""Authenticated encryption for the short-lived inbox-to-worker PIN transport."""

import base64
import hashlib
import json

from cryptography.fernet import Fernet


def _cipher(session_secret):
    value = (
        session_secret.get_secret_value()
        if hasattr(session_secret, "get_secret_value")
        else str(session_secret)
    )
    key = hashlib.sha256(b"agil.auth.transport.v1\0" + value.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal_auth(payload, session_secret):
    return (
        _cipher(session_secret)
        .encrypt(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
        .decode()
    )


def unseal_auth(token, session_secret):
    """Only call in a worker; never log the token, plaintext or decoder exceptions."""
    return json.loads(_cipher(session_secret).decrypt(token.encode()))
