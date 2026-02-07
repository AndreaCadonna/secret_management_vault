# DESIGN.md -- Secret Management Vault

## 1. Technology Stack

### 1.1 Language & Runtime

**Python 3.10+** -- Mandated by RESEARCH.md Section 6 and SPEC.md Section 7. Python's standard library provides JSON serialization, base64 encoding, file I/O, datetime handling, argument parsing, and `fnmatch` glob matching, minimizing external dependencies.

### 1.2 Dependencies

| Name | Version | Purpose | Justification |
|------|---------|---------|---------------|
| `cryptography` | >= 42.0 | AES-256-GCM encryption/decryption and PBKDF2-HMAC-SHA256 key derivation | Mandated by SPEC.md Section 7. Python's stdlib has no AES-GCM implementation. `hashlib.pbkdf2_hmac` exists but `cryptography` provides a unified API for both KDF and cipher operations with safe nonce generation. |

One external dependency total. All other functionality uses the Python standard library: `argparse` (CLI), `json` (serialization), `base64` (binary-to-text encoding), `datetime` (timestamps), `os` (random bytes, file operations), `getpass` (password prompting), `sys` (stderr/exit codes), `fnmatch` (glob pattern matching), `re` (path validation), `pathlib` (file path handling).

### 1.3 Setup & Run Commands

**Install:**
```
pip install cryptography>=42.0
```

**Run (examples):**
```
python cli.py init --vault-file vault.enc --password "MyMasterPass123"
python cli.py unseal --vault-file vault.enc --password "MyMasterPass123"
python cli.py put production/db/password "s3cret" --identity admin --vault-file vault.enc
python cli.py get production/db/password --identity admin --vault-file vault.enc
python cli.py seal --vault-file vault.enc
```

---

## 2. Architecture Overview

```
                           DESIGN ARCHITECTURE
 ============================================================================

  User
    |
    | (command-line args)
    v
 +--------+     parsed args      +-------+    encrypt/decrypt   +--------+
 | cli.py | ------------------> | vault  | -----------------> | crypto |
 | (entry |     function calls   | .py    |    calls            | .py    |
 |  point)|                      | (API)  |                     | (AES/  |
 +--------+                      +-------+                     |  KDF)  |
    |                             |  |  |                       +--------+
    | stdout/                     |  |  |
    | stderr                      |  |  | check policy
    v                             |  |  +---------------+
  Terminal                        |  |                  v
                                  |  |             +---------+
                  load/save vault |  | log event   | policy  |
                                  |  +-----------> | .py     |
                                  v              | | (match) |
                            +---------+          | +---------+
                            | storage |          |
                            | .py     |          v
                            | (JSON   |    +-----------+
                            |  file)  |    | audit.py  |
                            +---------+    | (append-  |
                                           |  only log)|
                                           +-----------+
```

**Design philosophy:** Five focused modules with a single orchestrator. The `Vault` class is the central API that coordinates all operations. It calls `crypto` for all encryption/decryption/key derivation, `storage` for vault persistence, `policy` for access control evaluation, and `audit` for logging. The `cli` module is a thin translation layer that parses command-line arguments, calls `Vault` methods, and formats output. Each module has a single responsibility and communicates through direct function calls with typed inputs and outputs. There is no shared mutable state between modules -- all state flows through function parameters and return values, with the `Vault` class holding the runtime state (root key, loaded vault data) as instance attributes.

**CLI state management:** The vault's sealed/unsealed state must persist between separate CLI invocations (each is a new process). A session file (`.vault_session`) stores the hex-encoded root key after `unseal` and is deleted on `seal`. The `Vault` class checks for this file to determine sealed/unsealed state. This is acceptable for a local pet project -- the root key is stored on disk only while the vault is unsealed, and `seal` removes it.

---

## 3. Component Specifications

### 3.1 Component: `crypto` (Cryptographic Operations)

- **File:** `crypto.py`
- **Responsibility:** Provides all cryptographic primitives -- key derivation, encryption, decryption, and random byte generation -- used by the Vault.
- **Dependencies:** `cryptography` library (external).

**Public Interface:**

```python
def derive_root_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derive a 256-bit root key from a master password using PBKDF2-HMAC-SHA256.
    Returns 32 bytes."""
    ...

def encrypt_aes_gcm(key: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypt plaintext with AES-256-GCM using the given 32-byte key.
    Generates a random 12-byte nonce internally.
    Returns (nonce, ciphertext). Ciphertext includes the GCM auth tag."""
    ...

def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Decrypt ciphertext with AES-256-GCM using the given key and nonce.
    Raises DecryptionError if authentication fails (wrong key or tampered data).
    Returns plaintext bytes."""
    ...

def generate_salt() -> bytes:
    """Generate a random 16-byte salt for PBKDF2."""
    ...

def generate_dek() -> bytes:
    """Generate a random 32-byte AES-256 Data Encryption Key."""
    ...

class DecryptionError(Exception):
    """Raised when AES-GCM decryption fails (bad key or tampered data)."""
    pass
```

**Internal Data Structures:** None -- this module is stateless and purely functional.

### 3.2 Component: `storage` (Vault Persistence)

- **File:** `storage.py`
- **Responsibility:** Serializes and deserializes the vault data structure to/from a JSON file on disk, handling base64 encoding of binary fields.
- **Dependencies:** None (standard library only: `json`, `base64`, `pathlib`).

**Public Interface:**

```python
def save_vault(vault_data: dict, vault_file: str) -> None:
    """Serialize vault_data to JSON and write it to vault_file.
    Binary fields (bytes) are base64-encoded before serialization.
    Overwrites the file atomically (write to temp, then rename)."""
    ...

def load_vault(vault_file: str) -> dict:
    """Read vault_file and deserialize JSON into a vault_data dict.
    Base64-encoded fields are decoded back to bytes.
    Raises FileNotFoundError if vault_file does not exist."""
    ...

def vault_file_exists(vault_file: str) -> bool:
    """Return True if vault_file exists on disk."""
    ...

def save_session(session_file: str, root_key: bytes) -> None:
    """Write the hex-encoded root key to the session file."""
    ...

def load_session(session_file: str) -> bytes | None:
    """Read the root key from the session file. Returns None if file does not exist."""
    ...

def delete_session(session_file: str) -> None:
    """Delete the session file if it exists."""
    ...
```

**Internal Data Structures:**

The vault JSON file has this structure (all `bytes` fields are stored as base64 strings):

```python
# VaultFileFormat (serialized as JSON)
{
    "salt": str,             # base64-encoded 16 bytes
    "iterations": int,       # minimum 600000
    "verification_nonce": str,  # base64-encoded 12 bytes
    "verification_token": str,  # base64-encoded ciphertext of known plaintext
    "secrets": {
        "<path>": {
            "path": str,
            "versions": [
                {
                    "version_number": int,
                    "encrypted_dek": str,      # base64
                    "dek_nonce": str,           # base64
                    "encrypted_value": str,     # base64
                    "value_nonce": str,         # base64
                    "created_at": str           # ISO 8601
                }
            ]
        }
    },
    "policies": [
        {
            "identity": str,
            "path_pattern": str,
            "capabilities": [str]   # subset of ["read", "write", "list", "delete"]
        }
    ]
}
```

### 3.3 Component: `policy` (Access Control Engine)

- **File:** `policy.py`
- **Responsibility:** Evaluates whether a given identity has a required capability on a target path, based on the set of defined policies using glob pattern matching.
- **Dependencies:** None (standard library only: `fnmatch`, `re`).

**Public Interface:**

```python
VALID_CAPABILITIES: list[str] = ["read", "write", "list", "delete"]

def check_access(
    policies: list[dict],
    identity: str,
    path: str,
    capability: str
) -> bool:
    """Return True if at least one policy grants the given capability to the
    given identity on a path pattern that matches the target path.
    Return False if no policy grants access (default deny).

    Policy path patterns support:
    - '*' matches any characters within a single path segment (no slashes)
    - '**' matches any characters across multiple segments (including slashes)
    """
    ...

def validate_path(path: str) -> bool:
    """Return True if path consists only of alphanumeric chars, hyphens,
    underscores, and forward slashes, with no leading/trailing slashes,
    no consecutive slashes, and no empty segments."""
    ...

def validate_capabilities(capabilities: list[str]) -> str | None:
    """Return the first invalid capability name, or None if all are valid."""
    ...

def match_path_pattern(pattern: str, path: str) -> bool:
    """Return True if the path matches the glob pattern.
    '*' matches within a single segment. '**' matches across segments."""
    ...
```

**Internal Data Structures:** None -- stateless functions operating on the policy list from vault data.

### 3.4 Component: `audit` (Audit Logger)

- **File:** `audit.py`
- **Responsibility:** Appends structured audit log entries to an append-only log file and reads log entries for display.
- **Dependencies:** None (standard library only: `datetime`, `json`).

**Public Interface:**

```python
def log_event(
    audit_file: str,
    identity: str,
    operation: str,
    path: str | None,
    outcome: str,
    detail: str | None = None
) -> None:
    """Append a single audit log entry to the audit file.
    Each entry is one line of pipe-separated fields:
    timestamp | identity | operation | path_or_dash | outcome [| detail]
    Timestamp is ISO 8601 with UTC timezone."""
    ...

def read_log(audit_file: str, last_n: int | None = None) -> list[str]:
    """Read all log entries from the audit file. If last_n is specified,
    return only the last N entries. Each entry is a raw line string.
    Raises FileNotFoundError if the audit file does not exist."""
    ...

def format_entry(entry_line: str) -> str:
    """Format a raw log line for display (pass through -- lines are already
    formatted as pipe-separated fields)."""
    ...
```

**Internal Data Structures:** None -- each log entry is a single line in the file with pipe-separated fields.

### 3.5 Component: `vault` (Vault API / Orchestrator)

- **File:** `vault.py`
- **Responsibility:** Central API that coordinates all vault operations -- initialization, seal/unseal lifecycle, CRUD on secrets, policy management -- by delegating to `crypto`, `storage`, `policy`, and `audit` components.
- **Dependencies:** `crypto`, `storage`, `policy`, `audit` (internal modules).

**Public Interface:**

```python
class VaultError(Exception):
    """Base exception for vault operation errors."""
    pass

class Vault:
    def __init__(self, vault_file: str = "vault.enc", audit_file: str = "audit.log") -> None:
        """Initialize the Vault instance with file paths.
        Does not load or create any files -- just stores configuration."""
        ...

    def init_vault(self, password: str) -> str:
        """Create a new vault file with the given master password.
        Generates salt, derives root key, creates verification token,
        saves empty vault structure, logs init event, returns success message.
        Raises VaultError if vault file already exists or password is empty."""
        ...

    def unseal(self, password: str) -> str:
        """Unseal the vault with the given master password.
        Loads vault data, derives root key, verifies against verification token,
        stores root key in session file, logs unseal event.
        Raises VaultError if vault file not found, already unsealed, or wrong password."""
        ...

    def seal(self) -> str:
        """Seal the vault by discarding the root key from the session file.
        Logs seal event.
        Raises VaultError if vault is already sealed."""
        ...

    def status(self) -> str:
        """Return 'sealed' or 'unsealed' based on session file existence."""
        ...

    def put_secret(self, path: str, value: str, identity: str) -> str:
        """Store or update a secret at the given path.
        Validates path, checks access (write capability), performs envelope encryption,
        persists vault, logs event. Returns success message with version number.
        Raises VaultError on sealed vault, access denied, invalid path, or empty value."""
        ...

    def get_secret(self, path: str, identity: str, version: int | None = None) -> dict:
        """Retrieve a secret at the given path, optionally a specific version.
        Checks access (read capability), decrypts via envelope decryption,
        logs event. Returns dict with keys: 'path', 'version', 'value'.
        Raises VaultError on sealed vault, access denied, not found, version not found."""
        ...

    def delete_secret(self, path: str, identity: str) -> str:
        """Delete a secret and all its versions at the given path.
        Checks access (delete capability), removes from vault, persists, logs event.
        Raises VaultError on sealed vault, access denied, or not found."""
        ...

    def list_secrets(self, identity: str, prefix: str = "") -> list[str]:
        """List all secret paths matching the given prefix.
        Checks access (list capability on the prefix), logs event.
        Returns list of path strings (may be empty).
        Raises VaultError on sealed vault or access denied."""
        ...

    def add_policy(self, identity: str, path_pattern: str, capabilities: list[str]) -> str:
        """Add an access control policy. Validates capabilities.
        Persists vault, logs event. Returns success message.
        Raises VaultError on sealed vault or invalid capabilities."""
        ...

    def remove_policy(self, identity: str, path_pattern: str) -> str:
        """Remove a policy matching the identity and path pattern.
        Persists vault, logs event. Returns success message.
        Raises VaultError on sealed vault or policy not found."""
        ...

    def get_audit_log(self, last_n: int | None = None) -> list[str]:
        """Read and return audit log entries. Returns list of formatted lines.
        Raises VaultError if audit file not found."""
        ...

    # Private helpers (not part of public interface, listed for clarity):
    # _ensure_unsealed() -> bytes:  Load root key from session, raise if sealed.
    # _load_vault_data() -> dict:   Load vault data from file.
    # _save_vault_data(data: dict): Save vault data to file.
    # _session_file() -> str:       Derive session file path from vault file path.
```

**Internal Data Structures:** The `Vault` class stores these instance attributes:
- `vault_file: str` -- path to the encrypted vault JSON file
- `audit_file: str` -- path to the audit log file

The root key is NOT stored as an instance attribute. It is loaded from the session file on each operation and discarded after the method completes. This ensures the root key's lifetime is minimal within each CLI invocation.

### 3.6 Component: `cli` (Command-Line Interface)

- **File:** `cli.py`
- **Responsibility:** Parses command-line arguments using `argparse`, translates them into `Vault` method calls, formats output to stdout/stderr, and sets exit codes.
- **Dependencies:** `vault` (internal module), standard library (`argparse`, `sys`, `getpass`).

**Public Interface:**

```python
def main() -> None:
    """Entry point. Parse sys.argv, dispatch to the appropriate Vault method,
    print results to stdout, print errors to stderr, and call sys.exit with
    the appropriate exit code (0 for success, 1 for errors)."""
    ...

def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse parser with all subcommands:
    init, unseal, seal, status, put, get, delete, list, add-policy,
    remove-policy, audit-log."""
    ...
```

**Internal Data Structures:** None -- purely a translation layer.

---

## 4. Data Models

All entity field names match SPEC.md Section 4 exactly.

### 4.1 Vault (in-memory representation)

```python
vault_data: dict = {
    "salt": bytes,           # 16 bytes, from SPEC 4.1
    "iterations": int,       # >= 600000, from SPEC 4.1
    "verification_nonce": bytes,  # 12 bytes (design addition for REQ-SEAL-005)
    "verification_token": bytes,  # encrypted known plaintext (design addition)
    "secrets": dict[str, dict],   # map of path -> Secret, from SPEC 4.1
    "policies": list[dict],       # list of Policy dicts, from SPEC 4.1
}
```

### 4.2 Secret

```python
secret: dict = {
    "path": str,                   # from SPEC 4.2
    "versions": list[dict],        # list of SecretVersion, from SPEC 4.2
}
```

### 4.3 SecretVersion

```python
secret_version: dict = {
    "version_number": int,         # from SPEC 4.3, starts at 1
    "encrypted_dek": bytes,        # from SPEC 4.3
    "dek_nonce": bytes,            # from SPEC 4.3, 12 bytes
    "encrypted_value": bytes,      # from SPEC 4.3
    "value_nonce": bytes,          # from SPEC 4.3, 12 bytes
    "created_at": str,             # from SPEC 4.3, ISO 8601 string
}
```

### 4.4 Policy

```python
policy: dict = {
    "identity": str,               # from SPEC 4.4
    "path_pattern": str,           # from SPEC 4.4
    "capabilities": list[str],     # from SPEC 4.4, subset of [read, write, list, delete]
}
```

### 4.5 AuditEntry (log line format)

```python
# Stored as a pipe-separated text line in the audit log file:
# "{timestamp} | {identity} | {operation} | {path_or_dash} | {outcome}"
# or with detail:
# "{timestamp} | {identity} | {operation} | {path_or_dash} | {outcome} | {detail}"
#
# Fields from SPEC 4.5:
#   timestamp: str    -- ISO 8601 with UTC timezone
#   identity: str     -- caller identity or "system"
#   operation: str    -- one of: init, seal, unseal, store, retrieve, update, delete, list, add-policy, remove-policy
#   path: str | None  -- secret path or "-" for non-path operations
#   outcome: str      -- one of: success, denied, error
#   detail: str | None -- optional additional context
```

### 4.6 Storage Strategy

**Single JSON file** (`vault.enc` by default). All binary fields (`salt`, nonces, encrypted DEKs, encrypted values, verification token) are base64-encoded for JSON compatibility. The JSON structure is NOT encrypted as a whole -- the envelope encryption happens at the individual secret level. The file is human-readable in structure but secret values are encrypted. This is the correct approach because:

1. Policies and metadata (paths, version numbers, timestamps) need to be readable without the root key for operations like `status` and policy management during unsealed state.
2. The security guarantee comes from per-secret envelope encryption, not from encrypting the whole file.
3. JSON is simpler than SQLite and has zero dependencies.

**Session file** (`.vault_session` by default, derived from vault file path). Contains only the hex-encoded root key. Created on `unseal`, deleted on `seal`. This file is what makes the sealed/unsealed state persist across CLI invocations.

### 4.7 Mock/Sample Data

Aligned with SPEC Behavior Scenario 6.4:

```python
# After: vault init --password "MyMasterPass123"
# Then:  vault unseal --password "MyMasterPass123"
# Then:  vault add-policy --identity admin --path-pattern "**" --capabilities read,write,list,delete
# Then:  vault put production/db/password "s3cretValue!" --identity admin

sample_vault_data = {
    "salt": b'\x8a\x12...',            # 16 random bytes
    "iterations": 600000,
    "verification_nonce": b'\x01\x02...', # 12 random bytes
    "verification_token": b'\xab\xcd...',  # encrypted "vault-verification-token"
    "secrets": {
        "production/db/password": {
            "path": "production/db/password",
            "versions": [
                {
                    "version_number": 1,
                    "encrypted_dek": b'...',      # DEK encrypted with root key
                    "dek_nonce": b'...',           # 12 bytes
                    "encrypted_value": b'...',     # "s3cretValue!" encrypted with DEK
                    "value_nonce": b'...',         # 12 bytes
                    "created_at": "2025-01-15T10:30:10+00:00"
                }
            ]
        }
    },
    "policies": [
        {
            "identity": "admin",
            "path_pattern": "**",
            "capabilities": ["read", "write", "list", "delete"]
        }
    ]
}
```

---

## 5. Project Structure

```
24_Secret_Management_Vault/
    RESEARCH.md          # Phase 0 output (exists)
    SPEC.md              # Phase 1 output (exists)
    DESIGN.md            # Phase 2 output (this file)
    cli.py               # Entry point: argparse CLI wrapper
    vault.py             # Vault class: central API orchestrator
    crypto.py            # Cryptographic operations (AES-GCM, PBKDF2)
    storage.py           # JSON file persistence and session management
    policy.py            # Access control policy evaluation
    audit.py             # Append-only audit log
```

**6 source files total.** All at root level. No nesting. Entry point is `cli.py`.

---

## 6. Implementation Plan

### Step 1: Project Scaffolding and Smoke Test

**Title:** Create project skeleton with entry point and dependency verification.

**Files:** `cli.py`, `vault.py`, `crypto.py`, `storage.py`, `policy.py`, `audit.py`

**Details:**

Create all 6 Python source files as stubs.

`crypto.py`: Import `cryptography` library at the top to verify it is installed. Define the `DecryptionError` exception class with `pass` body. Add placeholder functions `derive_root_key`, `encrypt_aes_gcm`, `decrypt_aes_gcm`, `generate_salt`, `generate_dek` -- each with correct signatures and type hints, but bodies that just `raise NotImplementedError`.

`storage.py`: Add placeholder functions `save_vault`, `load_vault`, `vault_file_exists`, `save_session`, `load_session`, `delete_session` -- each with correct signatures and `raise NotImplementedError`.

`policy.py`: Define `VALID_CAPABILITIES = ["read", "write", "list", "delete"]`. Add placeholder functions `check_access`, `validate_path`, `validate_capabilities`, `match_path_pattern` -- each with correct signatures and `raise NotImplementedError`.

`audit.py`: Add placeholder functions `log_event`, `read_log`, `format_entry` -- each with correct signatures and `raise NotImplementedError`.

`vault.py`: Define `VaultError(Exception)` class. Define `Vault` class with `__init__(self, vault_file="vault.enc", audit_file="audit.log")` that stores the two file paths as instance attributes. Add placeholder methods `init_vault`, `unseal`, `seal`, `status`, `put_secret`, `get_secret`, `delete_secret`, `list_secrets`, `add_policy`, `remove_policy`, `get_audit_log` -- each with correct signatures and `raise NotImplementedError`.

`cli.py`: Import `argparse` and `sys`. Define `build_parser()` that creates an `ArgumentParser` with `prog="vault"` and `description="Secret Management Vault"`. Add a single subcommand `status` that accepts `--vault-file` with default `"vault.enc"`. Define `main()` that calls `build_parser().parse_args()` and prints `"Vault CLI ready"`. Add the `if __name__ == "__main__": main()` guard.

**Definition of Done:**

```
pip install cryptography>=42.0 && python cli.py status --vault-file test.enc
```
Expected output: `Vault CLI ready` (exit code 0).

---

### Step 2: Implement Cryptographic Operations

**Title:** Implement all functions in `crypto.py`.

**Files:** `crypto.py`

**Details:**

Implement `generate_salt()`: Use `os.urandom(16)` to generate 16 random bytes. Return the bytes.

Implement `generate_dek()`: Use `os.urandom(32)` to generate 32 random bytes (256-bit AES key). Return the bytes.

Implement `derive_root_key(password, salt, iterations)`: Use `cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC` with algorithm `hashes.SHA256()`, length 32, salt, and iterations. Call `kdf.derive(password.encode("utf-8"))` and return the 32-byte result.

Implement `encrypt_aes_gcm(key, plaintext)`: Generate a 12-byte nonce with `os.urandom(12)`. Create an `AESGCM(key)` instance from `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Call `aesgcm.encrypt(nonce, plaintext, None)` -- the `None` means no associated data. Return `(nonce, ciphertext)`. The ciphertext includes the 16-byte GCM authentication tag appended by the library.

Implement `decrypt_aes_gcm(key, nonce, ciphertext)`: Create an `AESGCM(key)` instance. Call `aesgcm.decrypt(nonce, ciphertext, None)` inside a try/except. If `cryptography.exceptions.InvalidTag` is raised, raise `DecryptionError("Decryption failed: invalid key or tampered data")`. Return the plaintext bytes.

**Definition of Done:**

```
python -c "from crypto import *; s=generate_salt(); k=derive_root_key('test',s,600000); n,c=encrypt_aes_gcm(k,b'hello'); p=decrypt_aes_gcm(k,n,c); print(p.decode()); assert p==b'hello'; print('crypto OK')"
```
Expected output:
```
hello
crypto OK
```

---

### Step 3: Implement Storage Persistence

**Title:** Implement vault file serialization and session management in `storage.py`.

**Files:** `storage.py`

**Details:**

Import `json`, `base64`, `pathlib.Path`, `os`, `tempfile`.

Define a module-level constant `BINARY_FIELDS` as a set: `{"salt", "verification_nonce", "verification_token", "encrypted_dek", "dek_nonce", "encrypted_value", "value_nonce"}`. These are the field names that hold binary data and need base64 encoding/decoding.

Implement `vault_file_exists(vault_file)`: Return `Path(vault_file).exists()`.

Implement `save_vault(vault_data, vault_file)`: Deep-copy `vault_data`. Walk the dictionary recursively and convert any `bytes` values to base64-encoded strings using `base64.b64encode(val).decode("ascii")`. Store a marker in the key name convention: do NOT rename keys, just convert the values. Specifically:
- Encode `vault_data["salt"]`, `vault_data["verification_nonce"]`, `vault_data["verification_token"]` as base64 strings.
- For each secret in `vault_data["secrets"]`, for each version in `secret["versions"]`, encode `encrypted_dek`, `dek_nonce`, `encrypted_value`, `value_nonce` as base64 strings.
- Write the resulting dict to a temp file with `json.dump(data, f, indent=2)`, then rename the temp file to `vault_file` using `os.replace()` for atomicity.

Implement `load_vault(vault_file)`: Read the file with `json.load()`. Walk the structure and decode base64 strings back to bytes for the same fields listed above. Specifically:
- Decode `["salt"]`, `["verification_nonce"]`, `["verification_token"]` from base64 strings to bytes using `base64.b64decode(val)`.
- For each secret in `["secrets"]`, for each version in `["versions"]`, decode `encrypted_dek`, `dek_nonce`, `encrypted_value`, `value_nonce` from base64 to bytes.
- Raise `FileNotFoundError` if the file does not exist (let `open()` raise naturally).
- Return the decoded dict.

Implement `save_session(session_file, root_key)`: Write `root_key.hex()` to the session file (plain text, single line).

Implement `load_session(session_file)`: If `Path(session_file).exists()`, read the hex string, convert to bytes with `bytes.fromhex()`, and return it. Otherwise return `None`.

Implement `delete_session(session_file)`: If `Path(session_file).exists()`, delete it with `Path(session_file).unlink()`.

**Definition of Done:**

```
python -c "from storage import *; d={'salt':b'\\x00'*16,'iterations':600000,'verification_nonce':b'\\x00'*12,'verification_token':b'\\xab\\xcd','secrets':{},'policies':[]}; save_vault(d,'test_store.json'); d2=load_vault('test_store.json'); assert d2['salt']==b'\\x00'*16; assert d2['iterations']==600000; assert isinstance(d2['salt'],bytes); save_session('test.session',b'\\xde\\xad'*16); k=load_session('test.session'); assert k==b'\\xde\\xad'*16; delete_session('test.session'); assert load_session('test.session') is None; import os; os.remove('test_store.json'); print('storage OK')"
```
Expected output: `storage OK`

---

### Step 4: Implement Access Control Policy Engine

**Title:** Implement path validation, glob matching, and policy evaluation in `policy.py`.

**Files:** `policy.py`

**Details:**

Import `re`, `fnmatch`.

`VALID_CAPABILITIES` is already defined as `["read", "write", "list", "delete"]`.

Implement `validate_path(path)`: Use a regex to validate the path. The path must:
- Be non-empty
- Contain only `[a-zA-Z0-9_/-]` (alphanumeric, hyphens, underscores, forward slashes)
- Not start or end with `/`
- Not contain `//` (consecutive slashes)
- Every segment between slashes must be non-empty

Use regex: `r'^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*$'`. Return `True` if it matches, `False` otherwise.

Implement `validate_capabilities(capabilities)`: Iterate through `capabilities`. For each one, check if it is in `VALID_CAPABILITIES`. Return the first invalid capability string found, or `None` if all are valid.

Implement `match_path_pattern(pattern, path)`: This function handles two wildcard types:
- `**` matches any characters across path segments (including `/`).
- `*` matches any characters within a single path segment (no `/`).

Implementation approach: Convert the pattern to a regex.
1. Split the pattern by `**` to get segments.
2. For each segment, replace `*` with `[^/]*` (match anything except slash).
3. Escape other regex-special characters in each segment (using `re.escape` on non-wildcard parts).
4. Join the `**`-separated segments with `.*` (match anything including slash).
5. Anchor with `^` and `$`.
6. Return `bool(re.fullmatch(regex, path))`.

More precisely, the conversion algorithm:
1. Split the pattern on the literal string `"**"`. This gives a list of parts.
2. For each part, process single `*` wildcards: split the part on `"*"`, `re.escape()` each piece, then join with `[^/]*`.
3. Join all parts with `".*"` (the replacement for `**`).
4. Wrap with `^...$` and use `re.fullmatch()`.

Special case: if the pattern is exactly `"**"`, it matches everything.

Implement `check_access(policies, identity, path, capability)`: Iterate through `policies`. For each policy where `policy["identity"] == identity` and `capability in policy["capabilities"]`, call `match_path_pattern(policy["path_pattern"], path)`. If any match returns `True`, return `True`. After checking all policies, return `False` (default deny).

**Definition of Done:**

```
python -c "from policy import *; assert validate_path('prod/db/pass')==True; assert validate_path('invalid//path')==False; assert validate_path('')==False; assert validate_path('/leading')==False; assert match_path_pattern('**','any/deep/path')==True; assert match_path_pattern('prod/*/pass','prod/db/pass')==True; assert match_path_pattern('prod/*/pass','prod/db/user')==False; assert match_path_pattern('app-a/**','app-a/db/password')==True; p=[{'identity':'admin','path_pattern':'**','capabilities':['read','write']}]; assert check_access(p,'admin','any/path','read')==True; assert check_access(p,'admin','any/path','delete')==False; assert check_access(p,'nobody','any/path','read')==False; print('policy OK')"
```
Expected output: `policy OK`

---

### Step 5: Implement Audit Logger

**Title:** Implement append-only audit logging and log reading in `audit.py`.

**Files:** `audit.py`

**Details:**

Import `datetime`, `pathlib.Path`.

Implement `log_event(audit_file, identity, operation, path, outcome, detail=None)`: Create a timestamp string using `datetime.datetime.now(datetime.timezone.utc).isoformat()`. Construct the log line as pipe-separated fields: `f"{timestamp} | {identity} | {operation} | {path or '-'} | {outcome}"`. If `detail` is not None and not empty, append `f" | {detail}"`. Open the file in append mode (`"a"`) and write the line followed by a newline. This ensures existing entries are never modified.

Implement `read_log(audit_file, last_n=None)`: Check if `Path(audit_file).exists()`. If not, raise `FileNotFoundError(f"Audit log file not found at {audit_file}")`. Read all lines from the file, stripping trailing whitespace. Filter out empty lines. If `last_n` is specified and is a positive integer, return only the last `last_n` entries. Return the list of line strings.

Implement `format_entry(entry_line)`: Simply return the `entry_line` as-is (the pipe-separated format is already human-readable per SPEC Section 5.11 output format).

**Definition of Done:**

```
python -c "from audit import *; import os; f='test_audit.log'; log_event(f,'system','init',None,'success'); log_event(f,'admin','store','prod/db/pass','success'); log_event(f,'baduser','retrieve','prod/db/pass','denied','no policy'); lines=read_log(f); assert len(lines)==3; assert 'init' in lines[0]; assert 'denied' in lines[2]; last=read_log(f,last_n=1); assert len(last)==1; assert 'denied' in last[0]; os.remove(f); print('audit OK')"
```
Expected output: `audit OK`

---

### Step 6: Implement Vault Initialization, Seal, Unseal, and Status

**Title:** Implement the seal/unseal lifecycle methods in the Vault class.

**Files:** `vault.py`

**Details:**

Import `crypto`, `storage`, `policy`, `audit` at the top of the file. Also import `os` and `getpass`.

Implement private helper `_session_file(self) -> str`: Derive the session file path from the vault file path. Use the vault file path with a `.session` suffix appended. For example, if `vault_file` is `vault.enc`, the session file is `vault.enc.session`. Return the string path.

Implement `init_vault(self, password)`:
1. If `password` is empty or None, raise `VaultError("Master password must not be empty")`.
2. If `storage.vault_file_exists(self.vault_file)`, raise `VaultError(f"Vault file already exists at {self.vault_file}")`.
3. Call `salt = crypto.generate_salt()`.
4. Set `iterations = 600000`.
5. Call `root_key = crypto.derive_root_key(password, salt, iterations)`.
6. Create a verification token: `verification_plaintext = b"vault-verification-token"`. Call `v_nonce, v_ciphertext = crypto.encrypt_aes_gcm(root_key, verification_plaintext)`.
7. Build the vault data dict: `{"salt": salt, "iterations": iterations, "verification_nonce": v_nonce, "verification_token": v_ciphertext, "secrets": {}, "policies": []}`.
8. Call `storage.save_vault(vault_data, self.vault_file)`.
9. Call `audit.log_event(self.audit_file, "system", "init", None, "success")`.
10. Make sure the vault is sealed after init: call `storage.delete_session(self._session_file())` to ensure no session file exists.
11. Return `f"Vault initialized at {self.vault_file}"`.

Implement `unseal(self, password)`:
1. If not `storage.vault_file_exists(self.vault_file)`, raise `VaultError(f"Vault file not found at {self.vault_file}")`.
2. Call `vault_data = storage.load_vault(self.vault_file)`.
3. Extract `salt = vault_data["salt"]`, `iterations = vault_data["iterations"]`.
4. Call `root_key = crypto.derive_root_key(password, salt, iterations)`.
5. Try to decrypt the verification token: `crypto.decrypt_aes_gcm(root_key, vault_data["verification_nonce"], vault_data["verification_token"])`. If `crypto.DecryptionError` is raised, call `audit.log_event(self.audit_file, "system", "unseal", None, "error", "Incorrect master password")` and raise `VaultError("Incorrect master password")`.
6. Call `storage.save_session(self._session_file(), root_key)`.
7. Call `audit.log_event(self.audit_file, "system", "unseal", None, "success")`.
8. Return `"Vault unsealed successfully."`.

Implement `seal(self)`:
1. Load session: `root_key = storage.load_session(self._session_file())`.
2. If `root_key is None`, raise `VaultError("Vault is already sealed")`.
3. Call `storage.delete_session(self._session_file())`.
4. Call `audit.log_event(self.audit_file, "system", "seal", None, "success")`.
5. Return `"Vault sealed."`.

Implement `status(self)`:
1. If not `storage.vault_file_exists(self.vault_file)`, raise `VaultError(f"Vault file not found at {self.vault_file}")`.
2. Load session: `root_key = storage.load_session(self._session_file())`.
3. If `root_key is not None`, return `"unsealed"`. Else return `"sealed"`.

Implement private helper `_ensure_unsealed(self) -> bytes`:
1. `root_key = storage.load_session(self._session_file())`.
2. If `root_key is None`, raise `VaultError("Vault is sealed")`.
3. Return `root_key`.

**Definition of Done:**

```
python -c "from vault import Vault; import os; v=Vault('test_v.enc','test_a.log'); print(v.init_vault('MyPass')); print(v.status()); print(v.unseal('MyPass')); print(v.status()); print(v.seal()); print(v.status()); os.remove('test_v.enc'); os.remove('test_a.log')"
```
Expected output:
```
Vault initialized at test_v.enc
sealed
Vault unsealed successfully.
unsealed
Vault sealed.
sealed
```

---

### Step 7: Implement Policy Management (add-policy, remove-policy)

**Title:** Implement add_policy and remove_policy methods in the Vault class.

**Files:** `vault.py`

**Details:**

Implement `add_policy(self, identity, path_pattern, capabilities)`:
1. Call `self._ensure_unsealed()` (root key not needed for policy ops but vault must be unsealed).
2. Call `invalid = policy.validate_capabilities(capabilities)`. If `invalid is not None`, raise `VaultError(f"Invalid capability '{invalid}'. Valid capabilities: read, write, list, delete")`.
3. If `capabilities` is empty, raise `VaultError("At least one capability must be specified")`.
4. Load vault data: `vault_data = storage.load_vault(self.vault_file)`.
5. Create the policy dict: `{"identity": identity, "path_pattern": path_pattern, "capabilities": capabilities}`.
6. Append it to `vault_data["policies"]`.
7. Call `storage.save_vault(vault_data, self.vault_file)`.
8. Format capabilities for display: `caps_str = ", ".join(capabilities)`.
9. Call `audit.log_event(self.audit_file, "system", "add-policy", None, "success", f"identity='{identity}', path='{path_pattern}'")`.
10. Return `f"Policy added: identity='{identity}', path='{path_pattern}', capabilities=[{caps_str}]"`.

Implement `remove_policy(self, identity, path_pattern)`:
1. Call `self._ensure_unsealed()`.
2. Load vault data.
3. Search `vault_data["policies"]` for a policy where `p["identity"] == identity` and `p["path_pattern"] == path_pattern`.
4. If not found, raise `VaultError(f"No policy found for identity '{identity}' on path '{path_pattern}'")`.
5. Remove that policy from the list.
6. Save vault data.
7. Call `audit.log_event(self.audit_file, "system", "remove-policy", None, "success", f"identity='{identity}', path='{path_pattern}'")`.
8. Return `f"Policy removed: identity='{identity}', path='{path_pattern}'"`.

**Definition of Done:**

```
python -c "from vault import Vault; import os; v=Vault('test_v.enc','test_a.log'); v.init_vault('pass'); v.unseal('pass'); print(v.add_policy('admin','**',['read','write'])); print(v.remove_policy('admin','**')); v.seal(); os.remove('test_v.enc'); os.remove('test_a.log')"
```
Expected output:
```
Policy added: identity='admin', path='**', capabilities=[read, write]
Policy removed: identity='admin', path='**'
```

---

### Step 8: Implement Secret CRUD Operations (put, get, delete, list)

**Title:** Implement put_secret, get_secret, delete_secret, and list_secrets methods in the Vault class.

**Files:** `vault.py`

**Details:**

Import `datetime` at the top of `vault.py`.

Implement `put_secret(self, path, value, identity)`:
1. `root_key = self._ensure_unsealed()`.
2. If not `policy.validate_path(path)`, raise `VaultError(f"Invalid path format: '{path}'")`.
3. If `value` is empty or None, raise `VaultError("Secret value must not be empty")`.
4. Load vault data.
5. Call `policy.check_access(vault_data["policies"], identity, path, "write")`. If `False`, call `audit.log_event(self.audit_file, identity, "store", path, "denied", "requires write")` and raise `VaultError(f"Access denied for identity '{identity}' on path '{path}' (requires write)")`.
6. Generate a new DEK: `dek = crypto.generate_dek()`.
7. Encrypt the value: `value_nonce, encrypted_value = crypto.encrypt_aes_gcm(dek, value.encode("utf-8"))`.
8. Encrypt the DEK: `dek_nonce, encrypted_dek = crypto.encrypt_aes_gcm(root_key, dek)`.
9. Create the version dict: `{"version_number": <next_version>, "encrypted_dek": encrypted_dek, "dek_nonce": dek_nonce, "encrypted_value": encrypted_value, "value_nonce": value_nonce, "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}`.
10. If `path` exists in `vault_data["secrets"]`: get the current versions list, determine `next_version = len(versions) + 1`, append the new version. Set `operation = "update"`.
11. If `path` does not exist: create a new secret dict `{"path": path, "versions": [version_dict]}` with `version_number = 1`. Add to `vault_data["secrets"][path]`. Set `operation = "store"`.
12. Save vault data.
13. Call `audit.log_event(self.audit_file, identity, operation, path, "success")`.
14. If `operation == "store"`, return `f"Secret stored at {path} (version 1)"`. If `operation == "update"`, return `f"Secret updated at {path} (version {next_version})"`.

Implement `get_secret(self, path, identity, version=None)`:
1. `root_key = self._ensure_unsealed()`.
2. Load vault data.
3. Check access for "read" capability. If denied, log with outcome "denied" and raise `VaultError(f"Access denied for identity '{identity}' on path '{path}' (requires read)")`.
4. If `path` not in `vault_data["secrets"]`, raise `VaultError(f"Secret not found at path '{path}'")`.
5. Get the secret's versions list.
6. If `version is None`: pick the last version in the list (highest version_number).
7. If `version` is specified: find the version where `version_number == version`. If not found, raise `VaultError(f"Version {version} not found for path '{path}'")`.
8. Decrypt: `dek = crypto.decrypt_aes_gcm(root_key, selected_version["dek_nonce"], selected_version["encrypted_dek"])`.
9. Then: `plaintext = crypto.decrypt_aes_gcm(dek, selected_version["value_nonce"], selected_version["encrypted_value"])`.
10. Call `audit.log_event(self.audit_file, identity, "retrieve", path, "success")`.
11. Return `{"path": path, "version": selected_version["version_number"], "value": plaintext.decode("utf-8")}`.

Implement `delete_secret(self, path, identity)`:
1. `root_key = self._ensure_unsealed()` (root_key not used but vault must be unsealed).
2. Load vault data.
3. Check access for "delete" capability. If denied, log and raise.
4. If `path` not in `vault_data["secrets"]`, raise `VaultError(f"Secret not found at path '{path}'")`.
5. Delete `vault_data["secrets"][path]`.
6. Save vault data.
7. Log event with operation "delete", outcome "success".
8. Return `f"Secret deleted at {path}"`.

Implement `list_secrets(self, identity, prefix="")`:
1. `self._ensure_unsealed()`.
2. Load vault data.
3. Check access for "list" capability on `prefix`. If denied, log and raise `VaultError(f"Access denied for identity '{identity}' on path '{prefix}' (requires list)")`. Note: for list, the prefix may be empty string; use `prefix or ""` as the path in the access denied message.
4. Collect all paths in `vault_data["secrets"]` that start with `prefix`. If prefix is empty, return all paths.
5. Sort the paths alphabetically.
6. Log event with operation "list", path = prefix or "-", outcome "success".
7. Return the list of matching path strings.

Implement `get_audit_log(self, last_n=None)`:
1. Try: `lines = audit.read_log(self.audit_file, last_n)`.
2. Except `FileNotFoundError`: raise `VaultError(f"Audit log file not found at {self.audit_file}")`.
3. Return `lines`.

**Definition of Done:**

```
python -c "from vault import Vault; import os; v=Vault('test_v.enc','test_a.log'); v.init_vault('pass'); v.unseal('pass'); v.add_policy('admin','**',['read','write','list','delete']); print(v.put_secret('prod/db/pass','secret123','admin')); r=v.get_secret('prod/db/pass','admin'); print(f\"Path: {r['path']}\"); print(f\"Version: {r['version']}\"); print(f\"Value: {r['value']}\"); print(v.put_secret('prod/db/pass','secret456','admin')); r2=v.get_secret('prod/db/pass','admin'); print(f\"Latest version: {r2['version']}, value: {r2['value']}\"); r1=v.get_secret('prod/db/pass','admin',version=1); print(f\"Version 1: {r1['value']}\"); paths=v.list_secrets('admin','prod'); print('Listed:',paths); print(v.delete_secret('prod/db/pass','admin')); v.seal(); os.remove('test_v.enc'); os.remove('test_a.log')"
```
Expected output:
```
Secret stored at prod/db/pass (version 1)
Path: prod/db/pass
Version: 1
Value: secret123
Secret updated at prod/db/pass (version 2)
Latest version: 2, value: secret456
Version 1: secret123
Listed: ['prod/db/pass']
Secret deleted at prod/db/pass
```

---

### Step 9: Implement Full CLI with All Subcommands

**Title:** Implement the complete argparse CLI in `cli.py` with all 11 subcommands.

**Files:** `cli.py`

**Details:**

Import `argparse`, `sys`, `getpass`, and `from vault import Vault, VaultError`.

Implement `build_parser()`:

Create the main parser with `prog="vault"`. Create subparsers with `dest="command"`.

For each subcommand, add a subparser with the appropriate arguments:

1. **`init`**: `--vault-file` (default `"vault.enc"`), `--audit-file` (default `"audit.log"`), `--password` (default `None`).
2. **`unseal`**: `--vault-file`, `--audit-file`, `--password`.
3. **`seal`**: `--vault-file`, `--audit-file`.
4. **`status`**: `--vault-file`.
5. **`put`**: positional `path`, positional `value`, `--identity` (required), `--vault-file`, `--audit-file`.
6. **`get`**: positional `path`, `--identity` (required), `--version` (type=int, default=None), `--vault-file`, `--audit-file`.
7. **`delete`**: positional `path`, `--identity` (required), `--vault-file`, `--audit-file`.
8. **`list`**: positional `prefix` (nargs="?", default=""), `--identity` (required), `--vault-file`, `--audit-file`.
9. **`add-policy`**: `--identity` (required), `--path-pattern` (required), `--capabilities` (required), `--vault-file`, `--audit-file`.
10. **`remove-policy`**: `--identity` (required), `--path-pattern` (required), `--vault-file`, `--audit-file`.
11. **`audit-log`**: `--audit-file`, `--last` (type=int, default=None).

Implement `main()`:

1. Parse args with `build_parser().parse_args()`.
2. If no command is given, print help and exit with code 1.
3. Wrap all operations in a try/except block catching `VaultError` -- on error, print `f"Error: {e}"` to `sys.stderr` and `sys.exit(1)`.
4. Dispatch based on `args.command`:

   - **`init`**: If `args.password` is None, prompt with `getpass.getpass("Master password: ")`. Create `Vault(args.vault_file, args.audit_file)`. Call `v.init_vault(password)`. Print result.
   - **`unseal`**: If `args.password` is None, prompt. Create `Vault`. Call `v.unseal(password)`. Print result.
   - **`seal`**: Create `Vault`. Call `v.seal()`. Print result.
   - **`status`**: Create `Vault`. Call `v.status()`. Print `f"Status: {result}"`.
   - **`put`**: Create `Vault`. Call `v.put_secret(args.path, args.value, args.identity)`. Print result.
   - **`get`**: Create `Vault`. Call `v.get_secret(args.path, args.identity, args.version)`. Print `f"Path: {r['path']}\nVersion: {r['version']}\nValue: {r['value']}"`.
   - **`delete`**: Create `Vault`. Call `v.delete_secret(args.path, args.identity)`. Print result.
   - **`list`**: Create `Vault`. Call `v.list_secrets(args.identity, args.prefix)`. If empty list, print `"No secrets found."`. Else print each path on its own line.
   - **`add-policy`**: Parse `args.capabilities` by splitting on comma: `caps = [c.strip() for c in args.capabilities.split(",")]`. Create `Vault`. Call `v.add_policy(args.identity, args.path_pattern, caps)`. Print result.
   - **`remove-policy`**: Create `Vault`. Call `v.remove_policy(args.identity, args.path_pattern)`. Print result.
   - **`audit-log`**: Create `Vault(audit_file=args.audit_file)`. Call `v.get_audit_log(args.last)`. Print each line.

**Definition of Done:**

```
python cli.py init --vault-file test_cli.enc --audit-file test_cli.log --password "TestPass"
```
Expected output: `Vault initialized at test_cli.enc`

Then:
```
python cli.py unseal --vault-file test_cli.enc --audit-file test_cli.log --password "TestPass"
```
Expected output: `Vault unsealed successfully.`

Then:
```
python cli.py status --vault-file test_cli.enc
```
Expected output: `Status: unsealed`

Then clean up session file and temp files.

---

### Step 10: Integration Verification Against SPEC Behavior Scenarios

**Title:** Wire everything together and verify against SPEC behavior scenarios 6.1 through 6.28.

**Files:** No new files created. Uses `cli.py` to run all scenarios.

**Details:**

This step verifies the complete system by running through the behavior scenarios from SPEC.md Section 6. The implementation agent should execute these scenario sequences to confirm correctness. Below are the key verification sequences that cover all 28 scenarios:

**Verification Sequence A (Scenarios 6.1, 6.2, 6.3, 6.22, 6.23):** Seal/Unseal lifecycle.

Run in sequence, with a clean directory (no existing vault files):
1. `python cli.py init --vault-file scenario_test.enc --audit-file scenario_test.log --password "MyMasterPass123"` -- expect output containing `Vault initialized at scenario_test.enc`.
2. `python cli.py status --vault-file scenario_test.enc` -- expect `Status: sealed`.
3. `python cli.py unseal --vault-file scenario_test.enc --audit-file scenario_test.log --password "MyMasterPass123"` -- expect `Vault unsealed successfully.`
4. `python cli.py status --vault-file scenario_test.enc` -- expect `Status: unsealed`.
5. `python cli.py add-policy --identity admin --path-pattern "**" --capabilities read,write,list,delete --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Policy added`.
6. `python cli.py put persist/secret "persistent-value" --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Secret stored`.
7. `python cli.py seal --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Vault sealed.`
8. `python cli.py put secrets/key "myvalue" --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect error containing `Vault is sealed` (exit code 1). This validates Scenario 6.3.
9. `python cli.py unseal --vault-file scenario_test.enc --audit-file scenario_test.log --password "MyMasterPass123"` -- expect `Vault unsealed successfully.`
10. `python cli.py get persist/secret --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Value: persistent-value`. This validates Scenario 6.23.

**Verification Sequence B (Scenarios 6.4, 6.5, 6.20, 6.21):** Envelope encryption and versioning.

Continuing from Sequence A (vault is unsealed with admin policy):
1. `python cli.py put production/db/password "s3cretValue!" --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Secret stored at production/db/password (version 1)`.
2. `python cli.py get production/db/password --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect `Value: s3cretValue!` and `Version: 1`.
3. `python cli.py put path/secret-a "value-a" --identity admin --vault-file scenario_test.enc` -- expect `Secret stored`.
4. `python cli.py put path/secret-b "value-b" --identity admin --vault-file scenario_test.enc` -- expect `Secret stored`.
5. `python cli.py get path/secret-a --identity admin --vault-file scenario_test.enc` -- expect `Value: value-a`.
6. `python cli.py get path/secret-b --identity admin --vault-file scenario_test.enc` -- expect `Value: value-b`.
7. `python cli.py put config/api-key "key-v1" --identity admin --vault-file scenario_test.enc --audit-file scenario_test.log` -- expect version 1.
8. `python cli.py put config/api-key "key-v2" --identity admin --vault-file scenario_test.enc` -- expect version 2.
9. `python cli.py put config/api-key "key-v3" --identity admin --vault-file scenario_test.enc` -- expect version 3.
10. `python cli.py get config/api-key --identity admin --vault-file scenario_test.enc` -- expect `Version: 3`, `Value: key-v3`.
11. `python cli.py get config/api-key --identity admin --version 1 --vault-file scenario_test.enc` -- expect `Value: key-v1`.
12. `python cli.py get config/api-key --identity admin --version 99 --vault-file scenario_test.enc` -- expect error `Version 99 not found`.

**Verification Sequence C (Scenarios 6.6, 6.7, 6.8, 6.9, 6.10, 6.25):** CRUD edge cases.

Continuing from previous state:
1. `python cli.py get nonexistent/path --identity admin --vault-file scenario_test.enc` -- expect error `Secret not found`.
2. `python cli.py put temp/api-key "abc123" --identity admin --vault-file scenario_test.enc` -- expect stored.
3. `python cli.py delete temp/api-key --identity admin --vault-file scenario_test.enc` -- expect `Secret deleted`.
4. `python cli.py get temp/api-key --identity admin --vault-file scenario_test.enc` -- expect error `Secret not found`.
5. `python cli.py list prod --identity admin --vault-file scenario_test.enc` -- expect `production/db/password` in output.
6. `python cli.py put "invalid//path" "value" --identity admin --vault-file scenario_test.enc` -- expect error `Invalid path format`.
7. `python cli.py delete ghost/secret --identity admin --vault-file scenario_test.enc` -- expect error `Secret not found`.

**Verification Sequence D (Scenarios 6.11, 6.12, 6.13, 6.14, 6.15, 6.16, 6.17, 6.26, 6.28):** Access control.

Start a fresh vault for access control tests:
1. Init and unseal a new vault `acl_test.enc` with password `"ACLTest"`.
2. Add policy: identity `"service-a"`, path `"app-a/**"`, capabilities `read,write`.
3. Add policy: identity `"service-b"`, path `"app-b/**"`, capabilities `read`.
4. Put secret `app-a/db/password` with value `"secret123"` as `service-a` -- expect success.
5. Get `app-a/db/password` as `service-b` -- expect `Access denied` (Scenario 6.11).
6. Get `app-a/db/password` as `service-a` -- expect `Value: secret123` (Scenario 6.12).
7. Add policy: identity `"deployer"`, path `"production/*/credentials"`, capabilities `read,write`.
8. Put `production/web/credentials` `"web-cred"` as `deployer` -- expect success (Scenario 6.13).
9. Put `production/web/config` `"web-config"` as `deployer` -- expect `Access denied` (Scenario 6.13).
10. Add policy: identity `"limited"`, path `"data/**"`, capabilities `read`.
11. Put `data/item` `"readable"` as `service-a` -- will fail because service-a has no write on `data/**`. Instead add a temporary admin policy, put the secret, then remove the admin policy. Or more simply: add another policy for "limited" is not needed -- we need an identity that has write access to `data/**`. Add policy: identity `"writer"`, path `"data/**"`, capabilities `write`. Put `data/item` `"readable"` as `writer`. Then test:
    - Get `data/item` as `limited` -- expect success (read is granted).
    - Put `data/item` `"new-val"` as `limited` -- expect denied (write not granted, Scenario 6.26).
    - List `data` as `limited` -- expect denied (list not granted).
    - Delete `data/item` as `limited` -- expect denied (delete not granted).
12. Put `secrets/key` `"value"` as `unknown-user` with no policies for that user -- expect denied (Scenario 6.15).
13. Add policy: identity `"reader"`, path `"reports/*"`, capabilities `read,list`. Then remove it. Verify output messages (Scenario 6.16).
14. Remove-policy for identity `"phantom"` on path `"any/*"` -- expect `No policy found` (Scenario 6.28).

**Verification Sequence E (Scenarios 6.18, 6.19, 6.24, 6.27):** Audit and CLI error handling.

1. View the audit log from the main scenario vault: `python cli.py audit-log --audit-file scenario_test.log` -- verify entries for init, unseal, store, retrieve operations are present.
2. `python cli.py init --vault-file scenario_test.enc --password "NewPass"` -- expect error `Vault file already exists` (Scenario 6.27).
3. `python cli.py add-policy --identity test --path-pattern "path/*" --capabilities "read,execute" --vault-file scenario_test.enc` -- expect error `Invalid capability 'execute'` (Scenario 6.24).

**Definition of Done:**

Run the following minimal end-to-end integration command that covers the critical path (Scenarios 6.1, 6.4, 6.20, 6.11):

```
python -c "
import subprocess, sys, os

# Clean up any previous test files
for f in ['e2e_test.enc', 'e2e_test.log', 'e2e_test.enc.session']:
    if os.path.exists(f): os.remove(f)

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

# Scenario 6.1: Init and unseal
out, err, code = run('python cli.py init --vault-file e2e_test.enc --audit-file e2e_test.log --password MyPass')
assert 'Vault initialized' in out, f'init failed: {out} {err}'

out, err, code = run('python cli.py status --vault-file e2e_test.enc')
assert 'sealed' in out, f'status failed: {out}'

out, err, code = run('python cli.py unseal --vault-file e2e_test.enc --audit-file e2e_test.log --password MyPass')
assert 'unsealed successfully' in out, f'unseal failed: {out} {err}'

# Add admin policy
out, err, code = run('python cli.py add-policy --identity admin --path-pattern \"**\" --capabilities read,write,list,delete --vault-file e2e_test.enc --audit-file e2e_test.log')
assert 'Policy added' in out, f'add-policy failed: {out} {err}'

# Scenario 6.4: Store and retrieve
out, err, code = run('python cli.py put production/db/password s3cretValue! --identity admin --vault-file e2e_test.enc --audit-file e2e_test.log')
assert 'version 1' in out, f'put failed: {out} {err}'

out, err, code = run('python cli.py get production/db/password --identity admin --vault-file e2e_test.enc --audit-file e2e_test.log')
assert 's3cretValue!' in out, f'get failed: {out} {err}'

# Scenario 6.20: Versioning
out, err, code = run('python cli.py put production/db/password newvalue --identity admin --vault-file e2e_test.enc --audit-file e2e_test.log')
assert 'version 2' in out, f'put v2 failed: {out} {err}'

out, err, code = run('python cli.py get production/db/password --identity admin --version 1 --vault-file e2e_test.enc --audit-file e2e_test.log')
assert 's3cretValue!' in out, f'get v1 failed: {out} {err}'

# Scenario 6.15: Default deny
out, err, code = run('python cli.py put secrets/key val --identity unknown --vault-file e2e_test.enc --audit-file e2e_test.log')
assert code != 0, 'should have failed'
assert 'Access denied' in err, f'deny failed: {err}'

# Scenario 6.2: Wrong password
out, err, code = run('python cli.py seal --vault-file e2e_test.enc --audit-file e2e_test.log')
out, err, code = run('python cli.py unseal --vault-file e2e_test.enc --audit-file e2e_test.log --password WrongPass')
assert code != 0 and 'Incorrect master password' in err, f'wrong pass: {err}'

# Audit log check
out, err, code = run('python cli.py unseal --vault-file e2e_test.enc --audit-file e2e_test.log --password MyPass')
out, err, code = run('python cli.py audit-log --audit-file e2e_test.log')
assert 'init' in out and 'unseal' in out and 'store' in out, f'audit: {out}'

# Clean up
for f in ['e2e_test.enc', 'e2e_test.log', 'e2e_test.enc.session']:
    if os.path.exists(f): os.remove(f)

print('ALL E2E TESTS PASSED')
"
```
Expected output: `ALL E2E TESTS PASSED`

---

## 7. Risks & Non-Obvious Implementation Notes

### 7.1 Session File Security

The `.vault_session` file stores the root key in hex on disk. This is a deliberate simplicity trade-off for a pet project -- the alternative (OS keyring, memory-mapped files, or requiring password on every operation) adds significant complexity. The implementation agent should NOT try to add encryption to the session file -- it would require another key, creating a chicken-and-egg problem. Just store the hex string in plaintext.

### 7.2 Glob Pattern Matching: `*` vs `**`

This is the most error-prone part of the implementation. The `fnmatch` module's `*` matches everything including `/`, which is NOT what we want for single-segment matching. The implementation agent MUST NOT use `fnmatch.fnmatch()` directly. Instead, implement custom regex conversion as described in Step 4:

- `*` should become `[^/]*` (match anything except slash -- single segment only)
- `**` should become `.*` (match anything including slashes -- cross-segment)

The conversion must handle `**` BEFORE `*` to avoid partial replacement. Split on `**` first, then handle `*` within each part.

### 7.3 Base64 Encoding in Storage

When saving the vault, binary fields must be converted to base64 strings BEFORE `json.dump()`. When loading, they must be converted back. The implementation agent should be careful to convert exactly the right fields and not miss any. The fields to convert are enumerated explicitly in Step 3:
- Top-level: `salt`, `verification_nonce`, `verification_token`
- Per-version: `encrypted_dek`, `dek_nonce`, `encrypted_value`, `value_nonce`

Missing a field will cause a `TypeError` on serialization or a type mismatch on decryption.

### 7.4 AES-GCM Ciphertext Includes Auth Tag

The `cryptography` library's `AESGCM.encrypt()` returns ciphertext with the 16-byte GCM authentication tag appended. `AESGCM.decrypt()` expects the same format. The implementation agent should NOT try to separate or handle the auth tag manually -- just pass the full output of `encrypt()` to `decrypt()`.

### 7.5 PBKDF2 Performance

With 600,000 iterations, `derive_root_key` takes approximately 0.3-1.0 seconds depending on hardware. This is intentional and correct. The implementation agent should NOT reduce the iteration count for "faster testing" -- the SPEC mandates a minimum of 600,000.

### 7.6 Atomic File Writes

`storage.save_vault()` should write to a temporary file first, then rename to the target path. This prevents corruption if the process is interrupted mid-write. On Windows, `os.replace()` is atomic. The implementation agent should use `os.replace(tmp_path, vault_file)` rather than writing directly to the vault file.

### 7.7 Audit Log Before Result (REQ-AUD-005)

The SPEC requires that audit log entries are written BEFORE the operation result is returned. In the `Vault` class methods, the `audit.log_event()` call must happen BEFORE the `return` statement. For denied operations, the audit log should be written BEFORE raising the `VaultError`. The implementation agent must order these calls carefully.

### 7.8 Policy Operations Require Unsealed Vault

Per the SPEC CLI contracts (Sections 5.9 and 5.10), `add-policy` and `remove-policy` require the vault to be unsealed. This is because they modify the vault data which is stored in the vault file. The implementation agent should call `_ensure_unsealed()` at the start of these methods.

### 7.9 List Command Access Control

The `list` command checks the "list" capability on the PREFIX, not on each individual secret path. If the caller has "list" on `**`, they can list everything. If they have "list" on `prod/**`, they can list with prefix `prod`. The access check uses the prefix as the path for policy evaluation.

### 7.10 Empty Prefix for List

When no prefix is given to the `list` command, the prefix defaults to empty string `""`. The `check_access` call should still work -- an empty path with a `**` policy should match. The implementation agent should ensure that `match_path_pattern("**", "")` returns `True`. This may require a special case in the pattern matching: if the pattern is `**`, always return `True` regardless of path (including empty).

### 7.11 Windows File Path Compatibility

The project runs on Windows. `os.replace()` works on Windows. `pathlib.Path` handles Windows paths correctly. The vault file uses the path as-is from the CLI argument. The session file path is derived by appending `.session` to the vault file path string.

### 7.12 CLI Argument for `add-policy` Capabilities

The `--capabilities` argument is a single comma-separated string (e.g., `"read,write"`). The CLI must split this string on commas and strip whitespace from each capability. The Vault's `add_policy` method receives a list of strings. The validation of individual capabilities happens in the Vault, not in the CLI.

---

## 8. Requirement Coverage Table

| Requirement ID | Description | Component | Implementation Step |
|---|---|---|---|
| REQ-SEAL-001 | Create new empty vault in sealed state | `vault.py` (init_vault) | Step 6 |
| REQ-SEAL-002 | Derive 256-bit Root Key via PBKDF2-HMAC-SHA256, 16-byte salt, 600K iterations | `crypto.py` (derive_root_key), `vault.py` (init_vault) | Step 2, Step 6 |
| REQ-SEAL-003 | Store PBKDF2 salt and iteration count with vault data | `storage.py` (save_vault), `vault.py` (init_vault) | Step 3, Step 6 |
| REQ-SEAL-004 | Transition sealed to unsealed on correct password | `vault.py` (unseal) | Step 6 |
| REQ-SEAL-005 | Reject unseal with incorrect password | `vault.py` (unseal), `crypto.py` (decrypt verification token) | Step 6 |
| REQ-SEAL-006 | Transition unsealed to sealed, discard Root Key | `vault.py` (seal), `storage.py` (delete_session) | Step 6 |
| REQ-SEAL-007 | Reject all secret operations when sealed | `vault.py` (_ensure_unsealed) | Step 6, Step 8 |
| REQ-SEAL-008 | Report sealed/unsealed status | `vault.py` (status) | Step 6 |
| REQ-ENC-001 | Generate unique random AES-256-GCM DEK per secret | `crypto.py` (generate_dek), `vault.py` (put_secret) | Step 2, Step 8 |
| REQ-ENC-002 | Encrypt secret value with DEK using AES-256-GCM, unique 12-byte nonce | `crypto.py` (encrypt_aes_gcm), `vault.py` (put_secret) | Step 2, Step 8 |
| REQ-ENC-003 | Encrypt DEK with Root Key using AES-256-GCM, unique 12-byte nonce | `crypto.py` (encrypt_aes_gcm), `vault.py` (put_secret) | Step 2, Step 8 |
| REQ-ENC-004 | Store encrypted DEK, DEK nonce, encrypted value, value nonce together | `storage.py` (save_vault), `vault.py` (put_secret) | Step 3, Step 8 |
| REQ-ENC-005 | Decrypt secret by decrypting DEK then decrypting value | `crypto.py` (decrypt_aes_gcm), `vault.py` (get_secret) | Step 2, Step 8 |
| REQ-ENC-006 | Distinct DEK for each secret path | `vault.py` (put_secret generates new DEK per call) | Step 8 |
| REQ-CRUD-001 | Store secret value at hierarchical path | `vault.py` (put_secret) | Step 8 |
| REQ-CRUD-002 | Retrieve plaintext of current version | `vault.py` (get_secret) | Step 8 |
| REQ-CRUD-003 | Update secret with new value, increment version | `vault.py` (put_secret) | Step 8 |
| REQ-CRUD-004 | Delete secret and all versions | `vault.py` (delete_secret) | Step 8 |
| REQ-CRUD-005 | List paths under prefix | `vault.py` (list_secrets) | Step 8 |
| REQ-CRUD-006 | Return "secret not found" for nonexistent path | `vault.py` (get_secret, delete_secret) | Step 8 |
| REQ-CRUD-007 | Accept valid path characters, reject invalid | `policy.py` (validate_path), `vault.py` (put_secret) | Step 4, Step 8 |
| REQ-CRUD-008 | Persist secrets across seal/unseal cycles | `storage.py` (save_vault, load_vault) | Step 3, Step 8 |
| REQ-ACL-001 | Accept policy: identity + capabilities + path pattern | `vault.py` (add_policy) | Step 7 |
| REQ-ACL-002 | Support `*` and `**` glob wildcards in path patterns | `policy.py` (match_path_pattern) | Step 4 |
| REQ-ACL-003 | Evaluate policy before every secret operation, deny if lacking capability | `vault.py` (put_secret, get_secret, delete_secret, list_secrets) | Step 8 |
| REQ-ACL-004 | Map capabilities: write for store/update, read for retrieve, list for list, delete for delete | `vault.py` (put_secret, get_secret, delete_secret, list_secrets) | Step 8 |
| REQ-ACL-005 | Default deny when no policy grants access | `policy.py` (check_access returns False by default) | Step 4 |
| REQ-ACL-006 | Grant access when at least one policy matches | `policy.py` (check_access) | Step 4 |
| REQ-ACL-007 | Accept identity string with each operation | `vault.py` (all secret methods take identity param) | Step 8 |
| REQ-ACL-008 | Persist policies across seal/unseal cycles | `storage.py` (policies in vault file) | Step 3 |
| REQ-ACL-009 | Support removing a policy | `vault.py` (remove_policy) | Step 7 |
| REQ-AUD-001 | Record audit entry for every operation including denied | `audit.py` (log_event), `vault.py` (all methods) | Step 5, Step 6, Step 7, Step 8 |
| REQ-AUD-002 | Audit fields: timestamp (ISO 8601), identity, operation, path, outcome | `audit.py` (log_event) | Step 5 |
| REQ-AUD-003 | Append-only: never modify/remove previous entries | `audit.py` (log_event uses append mode) | Step 5 |
| REQ-AUD-004 | Record seal/unseal operations with outcome | `vault.py` (seal, unseal, init_vault) | Step 6 |
| REQ-AUD-005 | Write audit entry before returning operation result | `vault.py` (log_event called before return) | Step 6, Step 7, Step 8 |
| REQ-VER-001 | Assign version 1 to first value at a path | `vault.py` (put_secret) | Step 8 |
| REQ-VER-002 | Increment version on update, retain previous | `vault.py` (put_secret) | Step 8 |
| REQ-VER-003 | Return highest version when no version specified | `vault.py` (get_secret) | Step 8 |
| REQ-VER-004 | Return specific version when requested | `vault.py` (get_secret) | Step 8 |
| REQ-VER-005 | Return "version not found" error | `vault.py` (get_secret) | Step 8 |
| REQ-VER-006 | Report current version number with retrieved value | `vault.py` (get_secret), `cli.py` (format output) | Step 8, Step 9 |
| REQ-CLI-001 | CLI exposes all operations: init, seal, unseal, status, put, get, delete, list, add-policy, remove-policy, audit-log | `cli.py` (build_parser, main) | Step 9 |
| REQ-CLI-002 | Accept vault file path as CLI arg or default | `cli.py` (--vault-file with default) | Step 9 |
| REQ-CLI-003 | Accept audit file path as CLI arg or default | `cli.py` (--audit-file with default) | Step 9 |
| REQ-CLI-004 | Display results as human-readable text on stdout | `cli.py` (print to stdout) | Step 9 |
| REQ-CLI-005 | Display errors on stderr with non-zero exit code | `cli.py` (print to stderr, sys.exit(1)) | Step 9 |
| REQ-CLI-006 | Prompt for password on stdin without echo | `cli.py` (getpass.getpass) | Step 9 |
