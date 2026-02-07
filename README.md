# Secret Management Vault

A local, single-process Python tool that stores sensitive credentials using two-layer envelope encryption. Each secret is encrypted with its own unique Data Encryption Key (AES-256-GCM), and all DEKs are encrypted under a Root Key derived from a master password via PBKDF2. Access is governed by path-based policies with glob wildcards, and every operation is recorded in an append-only audit log.

## Features

- **Envelope encryption** -- unique DEK per secret, Root Key protects all DEKs
- **AES-256-GCM** with 12-byte random nonces for all encryption
- **PBKDF2-HMAC-SHA256** key derivation (600,000 iterations)
- **Seal/unseal lifecycle** -- Root Key exists in memory only while unsealed
- **Path-based access control** with `*` (single-segment) and `**` (multi-segment) glob wildcards
- **Append-only audit log** with ISO 8601 timestamps
- **Secret versioning** -- updates retain previous versions for rotation workflows
- **CLI interface** with 11 subcommands

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Install

```bash
pip install "cryptography>=42.0"
```

### Basic Usage

```bash
# Initialize a new vault
python cli.py init --vault-file vault.enc --audit-file audit.log --password "MyMasterPass123"

# Unseal
python cli.py unseal --vault-file vault.enc --audit-file audit.log --password "MyMasterPass123"

# Set up a policy
python cli.py add-policy --identity admin --path-pattern "**" --capabilities read,write,list,delete \
    --vault-file vault.enc --audit-file audit.log

# Store a secret
python cli.py put production/db/password "s3cretValue!" --identity admin \
    --vault-file vault.enc --audit-file audit.log

# Retrieve a secret
python cli.py get production/db/password --identity admin \
    --vault-file vault.enc --audit-file audit.log

# List secrets
python cli.py list production --identity admin --vault-file vault.enc --audit-file audit.log

# Seal the vault
python cli.py seal --vault-file vault.enc --audit-file audit.log
```

## Testing

Run the automated validation suite that tests all 28 specification behavior scenarios:

```bash
python validate.py
```

Run the narrated demo to see all features in action:

```bash
python demo.py
```

## Project Structure

| File | Description |
|------|-------------|
| `cli.py` | CLI entry point with 11 subcommands (argparse) |
| `vault.py` | Central orchestrator coordinating all vault operations |
| `crypto.py` | AES-256-GCM encryption/decryption, PBKDF2 key derivation |
| `storage.py` | JSON vault file persistence with base64-encoded binary fields |
| `policy.py` | Path validation, glob pattern matching, access control evaluation |
| `audit.py` | Append-only audit logger with pipe-separated fields |
| `validate.py` | Automated test suite (28 scenarios) |
| `demo.py` | Narrated end-to-end demonstration |

## Documentation

| Document | Purpose |
|----------|---------|
| [RESEARCH.md](docs/RESEARCH.md) | Domain research -- envelope encryption concepts, key hierarchies, prior art |
| [SPEC.md](docs/SPEC.md) | Behavioral specification -- 48 requirements, 28 scenarios, interface contracts |
| [DESIGN.md](docs/DESIGN.md) | Technical blueprint -- architecture, data model, implementation plan |
| [IMPLEMENTATION.md](docs/IMPLEMENTATION.md) | Build log -- setup instructions, code map, scenario results |
| [VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) | Independent QA -- runtime validation results, requirement coverage, verdict |
