# IMPLEMENTATION.md — Secret Management Vault

## 1. Setup Instructions

### 1.1 Prerequisites
- **Python**: 3.10 or higher
- **pip**: For installing the `cryptography` library

### 1.2 Installation

```bash
# Navigate to project directory
cd 24_Secret_Management_Vault

# Install dependencies
pip install cryptography>=42.0
```

### 1.3 Running the Application

```bash
# Initialize a new vault
python cli.py init --vault-file vault.enc --audit-file audit.log --password "MyMasterPass123"

# Unseal the vault
python cli.py unseal --vault-file vault.enc --audit-file audit.log --password "MyMasterPass123"

# Add a policy granting admin full access
python cli.py add-policy --identity admin --path-pattern "**" --capabilities read,write,list,delete --vault-file vault.enc --audit-file audit.log

# Store a secret
python cli.py put production/db/password "s3cretValue!" --identity admin --vault-file vault.enc --audit-file audit.log
# Output: Secret stored at production/db/password (version 1)

# Retrieve a secret
python cli.py get production/db/password --identity admin --vault-file vault.enc --audit-file audit.log
# Output:
# Path: production/db/password
# Version: 1
# Value: s3cretValue!

# List secrets
python cli.py list production --identity admin --vault-file vault.enc --audit-file audit.log

# Seal the vault
python cli.py seal --vault-file vault.enc --audit-file audit.log
```

### 1.4 Quick Verification

```bash
# Run this to verify the installation works (creates temp files, cleans up after)
python -c "
from vault import Vault
import os
v = Vault('verify_test.enc', 'verify_test.log')
print(v.init_vault('TestPass'))
print(v.unseal('TestPass'))
v.add_policy('admin', '**', ['read', 'write'])
print(v.put_secret('test/key', 'hello-world', 'admin'))
r = v.get_secret('test/key', 'admin')
print(f'Retrieved: {r[\"value\"]}')
v.seal()
for f in ['verify_test.enc', 'verify_test.log', 'verify_test.enc.session']:
    if os.path.exists(f): os.remove(f)
print('Verification complete')
"
# Expected output:
# Vault initialized at verify_test.enc
# Vault unsealed successfully.
# Secret stored at test/key (version 1)
# Retrieved: hello-world
# Verification complete
```

## 2. Deviations from Design

The implementation follows DESIGN.md exactly. No deviations.

## 3. Known Limitations

- **Session file security**: The `.vault_session` file stores the root key in hex on disk while the vault is unsealed. This is a deliberate simplicity trade-off for a pet project, as noted in DESIGN.md Section 7.1.
- **No authentication**: Identity strings are trusted without cryptographic verification. The system demonstrates authorization (policy evaluation), not authentication.
- **Single-process only**: No concurrency control. Running multiple CLI commands simultaneously against the same vault file could cause data corruption.
- **String-only secrets**: Secret values must be strings, not binary data.

## 4. Code Map

### 4.1 Reading Order

1. `cli.py` — Entry point. Parses command-line arguments and dispatches to Vault methods.
2. `vault.py` — Central orchestrator. Coordinates all vault operations across the other modules.
3. `crypto.py` — Cryptographic primitives. AES-256-GCM encryption/decryption, PBKDF2 key derivation.
4. `storage.py` — Persistence layer. JSON file serialization with base64 encoding, session file management.
5. `policy.py` — Access control engine. Path validation, glob pattern matching, policy evaluation.
6. `audit.py` — Audit logger. Append-only log file with pipe-separated fields.

### 4.2 File Descriptions

| File | Component | Lines | Description |
|------|-----------|-------|-------------|
| `cli.py` | CLI (3.6) | 180 | Argparse CLI wrapper with all 11 subcommands, translates args to Vault method calls |
| `vault.py` | Vault API (3.5) | 482 | Central Vault class orchestrating init, seal/unseal, CRUD, policies, and audit |
| `crypto.py` | Crypto (3.1) | 94 | AES-256-GCM encryption/decryption, PBKDF2-HMAC-SHA256 key derivation, random generation |
| `storage.py` | Storage (3.2) | 130 | JSON vault file persistence with base64 binary encoding, session file read/write/delete |
| `policy.py` | Policy (3.3) | 103 | Path validation, glob wildcard matching (* and **), access control evaluation |
| `audit.py` | Audit (3.4) | 74 | Append-only audit log with ISO 8601 timestamps, pipe-separated fields |

## 5. Behavior Scenario Results

| Scenario (SPEC Section 6) | Status | Notes |
|---------------------------|--------|-------|
| 6.1 Initialize and Unseal a New Vault | ✅ Pass | |
| 6.2 Reject Unseal with Wrong Password | ✅ Pass | |
| 6.3 Reject Operations When Sealed | ✅ Pass | |
| 6.4 Store and Retrieve a Secret with Envelope Encryption | ✅ Pass | |
| 6.5 Verify Different DEKs for Different Secrets | ✅ Pass | |
| 6.6 Retrieve Secret Not Found | ✅ Pass | |
| 6.7 Delete a Secret | ✅ Pass | |
| 6.8 List Secrets by Prefix | ✅ Pass | |
| 6.9 List Returns Empty When No Secrets Match | ✅ Pass | |
| 6.10 Invalid Path Format Rejected | ✅ Pass | |
| 6.11 Access Control Denies Unauthorized Read | ✅ Pass | |
| 6.12 Access Control Grants Authorized Read | ✅ Pass | |
| 6.13 Glob Wildcard Policy Matching | ✅ Pass | |
| 6.14 Double-Star Wildcard Policy Matching | ✅ Pass | |
| 6.15 Default Deny When No Policy Exists | ✅ Pass | |
| 6.16 Add and Remove a Policy | ✅ Pass | |
| 6.17 Policies Persist Across Seal/Unseal | ✅ Pass | |
| 6.18 Audit Log Records All Operations | ✅ Pass | |
| 6.19 Audit Log Entry Written Before Result Returned | ✅ Pass | |
| 6.20 Secret Versioning on Update | ✅ Pass | |
| 6.21 Version Not Found Error | ✅ Pass | |
| 6.22 Seal Discards Root Key | ✅ Pass | |
| 6.23 Secrets Persist Across Seal/Unseal Cycles | ✅ Pass | |
| 6.24 CLI Error Output and Exit Codes | ✅ Pass | |
| 6.25 Delete Nonexistent Secret Returns Error | ✅ Pass | |
| 6.26 Capability Mapping Enforced for Each Operation Type | ✅ Pass | |
| 6.27 Vault Init Rejects Existing File | ✅ Pass | |
| 6.28 Remove Nonexistent Policy Returns Error | ✅ Pass | |
