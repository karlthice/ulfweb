"""Encryption key management and file-level encryption for vault data."""

import base64
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

from backend.config import settings

logger = logging.getLogger("ulfweb")

_encryption_key: bytes | None = None
_fernet: Fernet | None = None


def init_encryption_key() -> None:
    """Load or generate the encryption key on first run."""
    global _encryption_key, _fernet

    if not settings.encryption.enabled:
        _encryption_key = None
        _fernet = None
        return

    key_path = Path(settings.encryption.key_file)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        _encryption_key = key_path.read_bytes()
        if len(_encryption_key) != 32:
            raise RuntimeError(
                f"Encryption key file {key_path} is corrupt "
                f"(expected 32 bytes, got {len(_encryption_key)}). "
                "Restore from backup or delete to generate a new key (data will be lost)."
            )
        logger.info("Loaded encryption key from %s", key_path)
    else:
        _encryption_key = os.urandom(32)
        # Write with restrictive permissions
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, _encryption_key)
        finally:
            os.close(fd)
        logger.warning(
            "Generated new encryption key at %s — "
            "BACK UP THIS FILE. If lost, all encrypted data is unrecoverable.",
            key_path,
        )

    # Fernet requires a 32-byte key encoded as url-safe base64
    fernet_key = base64.urlsafe_b64encode(_encryption_key)
    _fernet = Fernet(fernet_key)


def get_db_key() -> str:
    """Return the encryption key as a hex string for SQLCipher PRAGMA key."""
    if _encryption_key is None:
        raise RuntimeError("Encryption not initialized — call init_encryption_key() first")
    return _encryption_key.hex()


def get_fernet() -> Fernet:
    """Return the Fernet instance for file encryption."""
    if _fernet is None:
        raise RuntimeError("Encryption not initialized — call init_encryption_key() first")
    return _fernet


def encrypt_file(data: bytes) -> bytes:
    """Encrypt bytes with Fernet."""
    return get_fernet().encrypt(data)


def decrypt_file(data: bytes) -> bytes:
    """Decrypt bytes with Fernet."""
    return get_fernet().decrypt(data)


def is_encrypted() -> bool:
    """Return True if encryption is enabled and initialized."""
    return settings.encryption.enabled and _encryption_key is not None
