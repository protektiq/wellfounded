"""Envelope encryption: AES-256-GCM with per-organization data keys."""

from __future__ import annotations

import os
import struct
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import get_settings

_FORMAT_VERSION = 1
_NONCE_LEN = 12
_DEK_LEN = 32
_MAX_BLOB = 220 * 1024 * 1024


class DataKeyRevokedError(Exception):
    """Raised when decrypt is attempted after org data key revocation."""


@dataclass(frozen=True)
class EncryptedBlob:
    """On-wire format stored in S3."""

    encryption_key_id: str
    payload: bytes


class EnvelopeCrypto(ABC):
    @abstractmethod
    def generate_data_key(
        self,
        organization_id: uuid.UUID,
    ) -> tuple[bytes, bytes, str]:
        """Return (plaintext_dek, wrapped_dek, encryption_key_id)."""

    @abstractmethod
    def encrypt_blob(self, plaintext_dek: bytes, plaintext: bytes) -> bytes:
        """Return versioned envelope ciphertext for S3."""

    @abstractmethod
    def decrypt_blob(
        self,
        organization_id: uuid.UUID,
        payload: bytes,
        *,
        is_revoked: bool,
    ) -> bytes:
        """Decrypt S3 payload; raises DataKeyRevokedError when revoked."""


class LocalEnvelopeCrypto(EnvelopeCrypto):
    """Dev/local: master key wraps per-org DEKs in the object header."""

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("master key must be 32 bytes")
        self._master = master_key

    def generate_data_key(
        self,
        organization_id: uuid.UUID,
    ) -> tuple[bytes, bytes, str]:
        dek = os.urandom(_DEK_LEN)
        wrapped = AESGCM(self._master).encrypt(
            _nonce_for_wrap(organization_id),
            dek,
            None,
        )
        key_id = f"local:{organization_id}"
        return dek, wrapped, key_id

    def encrypt_blob(self, plaintext_dek: bytes, plaintext: bytes) -> bytes:
        if len(plaintext_dek) != _DEK_LEN:
            raise ValueError("invalid DEK length")
        if len(plaintext) > _MAX_BLOB:
            raise ValueError("plaintext exceeds maximum size")
        nonce = os.urandom(_NONCE_LEN)
        ciphertext = AESGCM(plaintext_dek).encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt_blob(
        self,
        organization_id: uuid.UUID,
        payload: bytes,
        *,
        is_revoked: bool,
    ) -> bytes:
        if is_revoked:
            raise DataKeyRevokedError("Organization data encryption key was revoked")
        if len(payload) < 1 + 2 + _NONCE_LEN + 16:
            raise ValueError("payload too short")
        version = payload[0]
        if version != _FORMAT_VERSION:
            raise ValueError(f"unsupported envelope version: {version}")
        wrapped_len = struct.unpack(">H", payload[1:3])[0]
        offset = 3
        wrapped_dek = payload[offset : offset + wrapped_len]
        offset += wrapped_len
        blob_nonce_cipher = payload[offset:]
        if len(blob_nonce_cipher) < _NONCE_LEN + 16:
            raise ValueError("invalid encrypted blob")
        dek = AESGCM(self._master).decrypt(
            _nonce_for_wrap(organization_id),
            wrapped_dek,
            None,
        )
        nonce = blob_nonce_cipher[:_NONCE_LEN]
        cipher = blob_nonce_cipher[_NONCE_LEN:]
        return AESGCM(dek).decrypt(nonce, cipher, None)

    def pack_for_storage(
        self,
        organization_id: uuid.UUID,
        plaintext_dek: bytes,
        wrapped_dek: bytes,
        inner_ciphertext: bytes,
    ) -> bytes:
        if len(wrapped_dek) > 65535:
            raise ValueError("wrapped DEK too large")
        header = (
            bytes([_FORMAT_VERSION])
            + struct.pack(">H", len(wrapped_dek))
            + wrapped_dek
            + inner_ciphertext
        )
        return header

    def unpack_and_decrypt(
        self,
        organization_id: uuid.UUID,
        payload: bytes,
        *,
        is_revoked: bool,
    ) -> bytes:
        if is_revoked:
            raise DataKeyRevokedError("Organization data encryption key was revoked")
        if len(payload) < 3:
            raise ValueError("payload too short")
        version = payload[0]
        if version != _FORMAT_VERSION:
            raise ValueError(f"unsupported envelope version: {version}")
        wrapped_len = struct.unpack(">H", payload[1:3])[0]
        offset = 3
        wrapped_dek = payload[offset : offset + wrapped_len]
        offset += wrapped_len
        inner = payload[offset:]
        dek = AESGCM(self._master).decrypt(
            _nonce_for_wrap(organization_id),
            wrapped_dek,
            None,
        )
        if len(inner) < _NONCE_LEN + 16:
            raise ValueError("invalid inner ciphertext")
        nonce = inner[:_NONCE_LEN]
        cipher = inner[_NONCE_LEN:]
        return AESGCM(dek).decrypt(nonce, cipher, None)


def _nonce_for_wrap(organization_id: uuid.UUID) -> bytes:
    return organization_id.bytes[:12]


def encrypt_audio_for_storage(
    crypto: LocalEnvelopeCrypto,
    organization_id: uuid.UUID,
    plaintext: bytes,
) -> tuple[bytes, str]:
    dek, wrapped, key_id = crypto.generate_data_key(organization_id)
    inner = crypto.encrypt_blob(dek, plaintext)
    packed = crypto.pack_for_storage(organization_id, dek, wrapped, inner)
    return packed, key_id


def decrypt_audio_from_storage(
    crypto: LocalEnvelopeCrypto,
    organization_id: uuid.UUID,
    payload: bytes,
    *,
    is_revoked: bool,
) -> bytes:
    return crypto.unpack_and_decrypt(
        organization_id,
        payload,
        is_revoked=is_revoked,
    )


@lru_cache
def get_envelope_crypto() -> LocalEnvelopeCrypto:
    settings = get_settings()
    raw = settings.envelope_master_key_b64.strip()
    if not raw:
        raise RuntimeError("ENVELOPE_MASTER_KEY is required for envelope encryption")
    import base64

    key = base64.b64decode(raw, validate=True)
    if len(key) != 32:
        raise RuntimeError("ENVELOPE_MASTER_KEY must decode to 32 bytes")
    return LocalEnvelopeCrypto(key)
