# storage.py -- Vault persistence for the Secret Management Vault.
# Implements DESIGN.md Component 3.2: JSON file serialization/deserialization
# with base64 encoding of binary fields, and session file management.
# Fulfills: REQ-SEAL-003, REQ-CRUD-008, REQ-ACL-008, REQ-ENC-004

import base64
import copy
import json
import os
import tempfile
from pathlib import Path


def vault_file_exists(vault_file: str) -> bool:
    """Return True if the vault file exists on disk.

    Args:
        vault_file: Path to the vault file.

    Returns:
        True if file exists, False otherwise.
    """
    return Path(vault_file).exists()


def save_vault(vault_data: dict, vault_file: str) -> None:
    """Serialize vault_data to JSON and write it to vault_file.

    Binary fields (bytes) are base64-encoded before serialization.
    Writes to a temp file first, then renames for atomicity.

    Args:
        vault_data: The vault data dictionary with bytes fields.
        vault_file: Path to write the vault file.
    """
    data = copy.deepcopy(vault_data)

    # Encode top-level binary fields
    for field in ("salt", "verification_nonce", "verification_token"):
        if field in data and isinstance(data[field], bytes):
            data[field] = base64.b64encode(data[field]).decode("ascii")

    # Encode binary fields in secret versions
    for secret in data.get("secrets", {}).values():
        for version in secret.get("versions", []):
            for field in ("encrypted_dek", "dek_nonce", "encrypted_value", "value_nonce"):
                if field in version and isinstance(version[field], bytes):
                    version[field] = base64.b64encode(version[field]).decode("ascii")

    # Write to temp file then rename for atomicity
    dir_name = os.path.dirname(os.path.abspath(vault_file))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, vault_file)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_vault(vault_file: str) -> dict:
    """Read vault_file and deserialize JSON into a vault_data dict.

    Base64-encoded fields are decoded back to bytes.

    Args:
        vault_file: Path to the vault file.

    Returns:
        The vault data dictionary with bytes fields restored.

    Raises:
        FileNotFoundError: If vault_file does not exist.
    """
    with open(vault_file, "r") as f:
        data = json.load(f)

    # Decode top-level binary fields
    for field in ("salt", "verification_nonce", "verification_token"):
        if field in data and isinstance(data[field], str):
            data[field] = base64.b64decode(data[field])

    # Decode binary fields in secret versions
    for secret in data.get("secrets", {}).values():
        for version in secret.get("versions", []):
            for field in ("encrypted_dek", "dek_nonce", "encrypted_value", "value_nonce"):
                if field in version and isinstance(version[field], str):
                    version[field] = base64.b64decode(version[field])

    return data


def save_session(session_file: str, root_key: bytes) -> None:
    """Write the hex-encoded root key to the session file.

    Args:
        session_file: Path to the session file.
        root_key: The root key bytes to persist.
    """
    with open(session_file, "w") as f:
        f.write(root_key.hex())


def load_session(session_file: str) -> bytes | None:
    """Read the root key from the session file.

    Args:
        session_file: Path to the session file.

    Returns:
        The root key bytes, or None if the session file does not exist.
    """
    if not Path(session_file).exists():
        return None
    with open(session_file, "r") as f:
        return bytes.fromhex(f.read().strip())


def delete_session(session_file: str) -> None:
    """Delete the session file if it exists.

    Args:
        session_file: Path to the session file.
    """
    path = Path(session_file)
    if path.exists():
        path.unlink()
