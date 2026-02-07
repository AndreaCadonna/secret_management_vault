# crypto.py -- Cryptographic operations for the Secret Management Vault.
# Implements DESIGN.md Component 3.1: key derivation, AES-256-GCM encryption/decryption,
# and random byte generation.
# Fulfills: REQ-SEAL-002, REQ-ENC-001, REQ-ENC-002, REQ-ENC-003, REQ-ENC-005

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class DecryptionError(Exception):
    """Raised when AES-GCM decryption fails (bad key or tampered data)."""
    pass


def derive_root_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derive a 256-bit root key from a master password using PBKDF2-HMAC-SHA256.

    Args:
        password: The master password string.
        salt: A 16-byte random salt.
        iterations: Number of PBKDF2 iterations (minimum 600,000).

    Returns:
        32 bytes (256-bit key).
    """
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_aes_gcm(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypt plaintext with AES-256-GCM using the given 32-byte key.

    Generates a random 12-byte nonce internally. The returned ciphertext
    includes the 16-byte GCM authentication tag appended by the library.

    Args:
        key: A 32-byte AES-256 key.
        plaintext: The data to encrypt.

    Returns:
        A tuple of (nonce, ciphertext) where nonce is 12 bytes.
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return (nonce, ciphertext)


def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Decrypt ciphertext with AES-256-GCM using the given key and nonce.

    Args:
        key: A 32-byte AES-256 key.
        nonce: The 12-byte nonce used during encryption.
        ciphertext: The ciphertext including the GCM auth tag.

    Returns:
        The decrypted plaintext bytes.

    Raises:
        DecryptionError: If authentication fails (wrong key or tampered data).
    """
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise DecryptionError("Decryption failed: invalid key or tampered data")


def generate_salt() -> bytes:
    """Generate a random 16-byte salt for PBKDF2.

    Returns:
        16 random bytes.
    """
    return os.urandom(16)


def generate_dek() -> bytes:
    """Generate a random 32-byte AES-256 Data Encryption Key.

    Returns:
        32 random bytes.
    """
    return os.urandom(32)
