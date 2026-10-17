from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def generate_keypair() -> tuple[bytes, bytes]:
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, public


def sign_bytes(private_pem: bytes, payload: bytes) -> str:
    key = serialization.load_pem_private_key(private_pem, password=None)
    return base64.b64encode(key.sign(payload)).decode()


def verify_bytes(public_pem: bytes, payload: bytes, signature_b64: str) -> bool:
    try:
        key = serialization.load_pem_public_key(public_pem)
        key.verify(base64.b64decode(signature_b64), payload)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def load_public_key(public_pem: bytes) -> bool:
    try:
        key = serialization.load_pem_public_key(public_pem)
    except ValueError:
        return False
    return key.__class__.__name__ == "Ed25519PublicKey"
