"""Cifrado simétrico para secretos (API keys de agentes).

Usa Fernet (AES-128-CBC + HMAC) con una clave derivada de SECRET_KEY.
La API nunca devuelve el valor en claro: solo `has_api_key` y un enmascarado.
"""

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings

_SECRET_CACHE: dict = {}


def _fernet() -> Fernet:
    secret = settings.SECRET_KEY
    if secret not in _SECRET_CACHE:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        _SECRET_CACHE[secret] = Fernet(base64.urlsafe_b64encode(digest))
    return _SECRET_CACHE[secret]


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
