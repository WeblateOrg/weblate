# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared helpers for the Weblate GitHub app tests."""

from __future__ import annotations

import hashlib
import hmac

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_private_key() -> str:
    """
    Return a fresh RSA private key as a PEM string.

    A real key is required so the GitHub App JWT can actually be signed; the
    tests stub the HTTP responses (not the JWT/auth code) via ``responses``.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


def sign_webhook_payload(payload: str | bytes, secret: str) -> str:
    """Return the ``X-Hub-Signature-256`` header value for ``payload``."""
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    return (
        "sha256="
        + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    )
