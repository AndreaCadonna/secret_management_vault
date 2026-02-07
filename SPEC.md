# SPEC.md -- Secret Management Vault

## 1. Overview

The Secret Management Vault is a local, single-process Python tool that stores sensitive credentials (API keys, passwords, tokens) in an encrypted file using a two-layer envelope encryption scheme. A master password derives a Root Key via PBKDF2, which protects per-secret Data Encryption Keys (DEKs). Secrets are addressed by hierarchical paths, access is governed by path-based policies evaluated against caller-declared identities, every operation is recorded in an append-only audit log, and secret updates retain previous versions to support rotation workflows.

## 2. Core Principle

Demonstrating a layered encryption key hierarchy with envelope encryption to protect secrets at rest, mediated by path-based access control policies and recorded in an append-only audit log.

The central mechanism is envelope encryption: each secret is encrypted with a unique Data Encryption Key (DEK) using AES-256-GCM, and all DEKs are encrypted with a single Root Key. The Root Key is derived from a user-provided master password using PBKDF2 with HMAC-SHA256. This hierarchy means that compromising the storage file yields only ciphertext; compromising a single DEK exposes only one secret; and the Root Key never touches disk in plaintext -- it exists only in memory after the vault is unsealed. Access control policies determine which identities can perform which operations at specific paths, and every access attempt is written to an append-only audit log.

Because the core principle IS the encryption architecture, requirements describing the internal key hierarchy structure (DEK per secret, Root Key encrypting DEKs, PBKDF2 derivation) are valid behavioral requirements rather than implementation details.

## 3. Functional Requirements

### 3.1 Seal/Unseal Lifecycle

**REQ-SEAL-001:** The system shall accept a master password and create a new, empty vault that is immediately in the sealed state after creation.

**REQ-SEAL-002:** The system shall derive a 256-bit Root Key from the master password using PBKDF2 with HMAC-SHA256, a randomly generated 16-byte salt, and a minimum of 600,000 iterations during vault initialization.

**REQ-SEAL-003:** The system shall store the PBKDF2 salt and iteration count alongside the vault data so that the Root Key can be re-derived on subsequent unseals.

**REQ-SEAL-004:** The system shall transition from sealed to unsealed state when provided the correct master password, making the derived Root Key available in memory for cryptographic operations.

**REQ-SEAL-005:** The system shall reject an unseal attempt with an incorrect master password and remain in the sealed state.

**REQ-SEAL-006:** The system shall transition from unsealed to sealed state on a seal command, discarding the Root Key from memory.

**REQ-SEAL-007:** The system shall reject all secret operations (store, retrieve, update, delete, list) when the vault is in the sealed state, returning a "vault is sealed" error.

**REQ-SEAL-008:** The system shall report its current state (sealed or unsealed) when queried.

### 3.2 Envelope Encryption for Secrets

**REQ-ENC-001:** The system shall generate a unique, random AES-256-GCM Data Encryption Key (DEK) for each secret stored in the vault.

**REQ-ENC-002:** The system shall encrypt the secret value using its DEK with AES-256-GCM, producing ciphertext and generating a unique 12-byte nonce (initialization vector) for each encryption operation.

**REQ-ENC-003:** The system shall encrypt each DEK using the Root Key with AES-256-GCM, producing an encrypted DEK and generating a unique 12-byte nonce for each DEK encryption operation.

**REQ-ENC-004:** The system shall store the encrypted DEK, the DEK encryption nonce, the encrypted secret value, and the value encryption nonce together as a single record for each secret version.

**REQ-ENC-005:** The system shall decrypt a secret by first decrypting the DEK using the Root Key, then decrypting the secret value using the decrypted DEK, returning the original plaintext secret value.

**REQ-ENC-006:** The system shall use a distinct DEK for each secret path, such that two different secrets stored at different paths are encrypted with different DEKs.

### 3.3 CRUD Operations on Secrets by Path

**REQ-CRUD-001:** The system shall store a secret value at a specified hierarchical path (using forward-slash separators, e.g., "production/db/password"), associating the encrypted value with that path.

**REQ-CRUD-002:** The system shall retrieve and return the plaintext value of the current version of a secret at a specified path.

**REQ-CRUD-003:** The system shall update a secret at an existing path by storing a new encrypted value at that path, incrementing the version number.

**REQ-CRUD-004:** The system shall delete a secret at a specified path, removing all versions of that secret from the vault.

**REQ-CRUD-005:** The system shall list all secret paths that exist under a given path prefix (including the prefix itself if it matches an exact path), without revealing secret values.

**REQ-CRUD-006:** The system shall return a "secret not found" error when attempting to retrieve or delete a secret at a path that does not exist in the vault.

**REQ-CRUD-007:** The system shall accept paths consisting of alphanumeric characters, hyphens, underscores, and forward slashes, with each path segment being non-empty.

**REQ-CRUD-008:** The system shall persist all stored secrets to the encrypted storage file so that secrets survive vault seal/unseal cycles.

### 3.4 Path-Based Access Control Policies

**REQ-ACL-001:** The system shall accept policy definitions that associate a named identity (a string) with a set of capabilities (one or more of: read, write, list, delete) on a specified path pattern.

**REQ-ACL-002:** The system shall support glob wildcard patterns in policy path specifications, where `*` matches any sequence of characters within a single path segment and `**` matches any sequence of characters across multiple path segments (including the separator).

**REQ-ACL-003:** The system shall evaluate the applicable access control policy before executing any secret operation (store, retrieve, update, delete, list), and deny the operation if the identity lacks the required capability for the target path.

**REQ-ACL-004:** The system shall require the "write" capability for store and update operations, the "read" capability for retrieve operations, the "list" capability for list operations, and the "delete" capability for delete operations.

**REQ-ACL-005:** The system shall deny access by default when no policy grants the requested capability on the target path for the given identity.

**REQ-ACL-006:** The system shall grant access when at least one policy grants the required capability for the given identity on a path pattern that matches the target path.

**REQ-ACL-007:** The system shall accept an identity string as a parameter with each secret operation to identify the caller for policy evaluation.

**REQ-ACL-008:** The system shall persist policy definitions so that policies survive vault seal/unseal cycles.

**REQ-ACL-009:** The system shall support removing a previously defined policy.

### 3.5 Append-Only Audit Log

**REQ-AUD-001:** The system shall record an audit log entry for every secret operation attempted, including operations that are denied by access control.

**REQ-AUD-002:** The system shall include the following fields in each audit log entry: timestamp (ISO 8601 format), identity of the caller, operation type (store, retrieve, update, delete, list), target path, and outcome (success or denied).

**REQ-AUD-003:** The system shall append audit log entries to a log file in a manner that does not modify or remove previously written entries.

**REQ-AUD-004:** The system shall record audit log entries for seal and unseal operations, including the outcome (success or failure).

**REQ-AUD-005:** The system shall write audit log entries before the operation result is returned, ensuring that every completed operation has a corresponding log entry.

### 3.6 Secret Versioning for Rotation

**REQ-VER-001:** The system shall assign version number 1 to the first value stored at a given secret path.

**REQ-VER-002:** The system shall increment the version number by 1 each time a secret at an existing path is updated, retaining all previous versions.

**REQ-VER-003:** The system shall return the value of the highest-numbered version (the current version) when a secret is retrieved without specifying a version number.

**REQ-VER-004:** The system shall return the value of a specific version when a secret is retrieved with a version number parameter.

**REQ-VER-005:** The system shall return a "version not found" error when a specific version number is requested that does not exist for the given path.

**REQ-VER-006:** The system shall report the current (latest) version number along with the secret value when a secret is retrieved.

### 3.7 Command-Line Interface

**REQ-CLI-001:** The system shall provide a command-line interface that exposes all vault operations: init, seal, unseal, status, put (store), get (retrieve), delete, list, add-policy, remove-policy, and audit-log.

**REQ-CLI-002:** The system shall accept the vault file path as a command-line argument or use a default path when not specified.

**REQ-CLI-003:** The system shall accept the audit log file path as a command-line argument or use a default path when not specified.

**REQ-CLI-004:** The system shall display operation results as human-readable text on standard output.

**REQ-CLI-005:** The system shall display error messages on standard error and exit with a non-zero exit code when an operation fails.

**REQ-CLI-006:** The system shall prompt for the master password on standard input (without echoing) for the init and unseal commands when the password is not provided via a command-line argument.

## 4. Data Model

### 4.1 Vault

| Attribute | Type | Constraints |
|-----------|------|-------------|
| salt | bytes | Required. Exactly 16 bytes. Randomly generated during vault initialization. |
| iterations | integer | Required. Minimum value 600,000. Set during vault initialization. |
| secrets | map of string -> Secret | Required (can be empty). Keys are secret paths. Each key is a non-empty string containing only alphanumeric characters, hyphens, underscores, and forward slashes. |
| policies | list of Policy | Required (can be empty). |

*Referenced by: REQ-SEAL-001, REQ-SEAL-002, REQ-SEAL-003, REQ-SEAL-004, REQ-SEAL-008, REQ-CRUD-008, REQ-ACL-008*

### 4.2 Secret

| Attribute | Type | Constraints |
|-----------|------|-------------|
| path | string | Required, non-empty. Contains only alphanumeric characters, hyphens, underscores, and forward slashes. No leading or trailing slashes. No consecutive slashes. |
| versions | list of SecretVersion | Required, non-empty (at least one version). Ordered by version number ascending. |

*Referenced by: REQ-CRUD-001, REQ-CRUD-002, REQ-CRUD-003, REQ-CRUD-004, REQ-CRUD-005, REQ-CRUD-006, REQ-VER-001, REQ-VER-002, REQ-VER-003*

### 4.3 SecretVersion

| Attribute | Type | Constraints |
|-----------|------|-------------|
| version_number | integer | Required. Starts at 1, increments by 1. |
| encrypted_dek | bytes | Required. The DEK encrypted with the Root Key via AES-256-GCM. |
| dek_nonce | bytes | Required. Exactly 12 bytes. The nonce used to encrypt the DEK. |
| encrypted_value | bytes | Required. The secret value encrypted with the DEK via AES-256-GCM. |
| value_nonce | bytes | Required. Exactly 12 bytes. The nonce used to encrypt the secret value. |
| created_at | datetime | Required. ISO 8601 timestamp of when this version was created. |

*Referenced by: REQ-ENC-001, REQ-ENC-002, REQ-ENC-003, REQ-ENC-004, REQ-ENC-005, REQ-VER-001, REQ-VER-002, REQ-VER-004, REQ-VER-005, REQ-VER-006*

### 4.4 Policy

| Attribute | Type | Constraints |
|-----------|------|-------------|
| identity | string | Required, non-empty, max 255 characters. |
| path_pattern | string | Required, non-empty. A path that can include `*` (single-segment wildcard) and `**` (multi-segment wildcard). |
| capabilities | list of enum(read, write, list, delete) | Required, non-empty. At least one capability. |

*Referenced by: REQ-ACL-001, REQ-ACL-002, REQ-ACL-003, REQ-ACL-004, REQ-ACL-005, REQ-ACL-006, REQ-ACL-008, REQ-ACL-009*

### 4.5 AuditEntry

| Attribute | Type | Constraints |
|-----------|------|-------------|
| timestamp | datetime | Required. ISO 8601 format with timezone. |
| identity | string | Required. Use "system" for seal/unseal/init operations. |
| operation | enum(init, seal, unseal, store, retrieve, update, delete, list, add-policy, remove-policy) | Required. |
| path | optional string | Required for secret operations. Absent for seal/unseal/policy operations. |
| outcome | enum(success, denied, error) | Required. |
| detail | optional string | Additional context (e.g., error reason). Max 1024 characters. |

*Referenced by: REQ-AUD-001, REQ-AUD-002, REQ-AUD-003, REQ-AUD-004, REQ-AUD-005*

## 5. Interface Contracts

The system exposes a command-line interface (CLI). Each subcommand is described below.

### 5.1 init

**Signature:**
```
vault init [--vault-file PATH] [--audit-file PATH] [--password PASSWORD]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --vault-file | string | No | `vault.enc` | Valid file path. File must not already exist. |
| --audit-file | string | No | `audit.log` | Valid file path. |
| --password | string | No | Prompted on stdin | Non-empty string. |

**Behavior:**
1. Generate a random 16-byte salt.
2. Derive a 256-bit Root Key from the master password using PBKDF2 with HMAC-SHA256 and 600,000 iterations.
3. Create an empty vault structure with the salt and iteration count.
4. Persist the vault to the vault file in encrypted form.
5. Record an audit log entry for the init operation.
6. The vault is left in the sealed state after initialization.

**Output:**
```
Vault initialized at vault.enc
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault file already exists | `Error: Vault file already exists at vault.enc` | 1 |
| Password is empty | `Error: Master password must not be empty` | 1 |

### 5.2 unseal

**Signature:**
```
vault unseal [--vault-file PATH] [--audit-file PATH] [--password PASSWORD]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --vault-file | string | No | `vault.enc` | Valid file path. File must exist. |
| --audit-file | string | No | `audit.log` | Valid file path. |
| --password | string | No | Prompted on stdin | Non-empty string. |

**Behavior:**
1. Read the vault file.
2. Extract the salt and iteration count.
3. Derive the Root Key from the provided password using PBKDF2 with the stored salt and iteration count.
4. Verify the derived Root Key is correct by attempting to decrypt a verification token stored in the vault.
5. Transition the vault to the unsealed state, holding the Root Key in memory.
6. Record an audit log entry for the unseal operation.

**Output:**
```
Vault unsealed successfully.
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault file not found | `Error: Vault file not found at vault.enc` | 1 |
| Incorrect password | `Error: Incorrect master password` | 1 |

### 5.3 seal

**Signature:**
```
vault seal [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Discard the Root Key from memory.
2. Transition the vault to the sealed state.
3. Record an audit log entry for the seal operation.

**Output:**
```
Vault sealed.
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is already sealed | `Error: Vault is already sealed` | 1 |

### 5.4 status

**Signature:**
```
vault status [--vault-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --vault-file | string | No | `vault.enc` | Valid file path. |

**Behavior:**
1. Report whether the vault is sealed or unsealed.

**Output (unsealed):**
```
Status: unsealed
```

**Output (sealed):**
```
Status: sealed
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault file not found | `Error: Vault file not found at vault.enc` | 1 |

### 5.5 put (store/update)

**Signature:**
```
vault put PATH VALUE --identity IDENTITY [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| PATH | string | Yes | -- | Non-empty. Alphanumeric, hyphens, underscores, forward slashes only. No leading/trailing/consecutive slashes. |
| VALUE | string | Yes | -- | Non-empty string. |
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Evaluate access control: the identity must have the "write" capability on the target path.
3. If the path does not exist: generate a new DEK, encrypt the value, encrypt the DEK, store as version 1.
4. If the path exists: generate a new DEK, encrypt the new value, encrypt the DEK, store as the next version number.
5. Persist the updated vault.
6. Record an audit log entry.

**Output (new secret):**
```
Secret stored at production/db/password (version 1)
```

**Output (updated secret):**
```
Secret updated at production/db/password (version 2)
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Access denied | `Error: Access denied for identity 'service-a' on path 'production/db/password' (requires write)` | 1 |
| Invalid path format | `Error: Invalid path format: 'invalid//path'` | 1 |
| Empty value | `Error: Secret value must not be empty` | 1 |

### 5.6 get (retrieve)

**Signature:**
```
vault get PATH --identity IDENTITY [--version VERSION] [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| PATH | string | Yes | -- | Non-empty. Valid path format. |
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --version | integer | No | Latest version | Positive integer. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Evaluate access control: the identity must have the "read" capability on the target path.
3. Look up the secret at the given path.
4. If --version is specified, retrieve that version; otherwise retrieve the latest version.
5. Decrypt the DEK using the Root Key, then decrypt the secret value using the DEK.
6. Record an audit log entry.

**Output:**
```
Path: production/db/password
Version: 2
Value: s3cret_v2
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Access denied | `Error: Access denied for identity 'service-a' on path 'production/db/password' (requires read)` | 1 |
| Secret not found | `Error: Secret not found at path 'nonexistent/path'` | 1 |
| Version not found | `Error: Version 99 not found for path 'production/db/password'` | 1 |

### 5.7 delete

**Signature:**
```
vault delete PATH --identity IDENTITY [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| PATH | string | Yes | -- | Non-empty. Valid path format. |
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Evaluate access control: the identity must have the "delete" capability on the target path.
3. Remove the secret and all its versions from the vault.
4. Persist the updated vault.
5. Record an audit log entry.

**Output:**
```
Secret deleted at production/db/password
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Access denied | `Error: Access denied for identity 'service-a' on path 'production/db/password' (requires delete)` | 1 |
| Secret not found | `Error: Secret not found at path 'nonexistent/path'` | 1 |

### 5.8 list

**Signature:**
```
vault list [PREFIX] --identity IDENTITY [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| PREFIX | string | No | "" (all paths) | Valid path characters. |
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Evaluate access control: the identity must have the "list" capability on the target prefix.
3. Return all secret paths that start with the given prefix.
4. Record an audit log entry.

**Output:**
```
production/db/password
production/db/username
production/api/key
```

**Output (no secrets found):**
```
No secrets found.
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Access denied | `Error: Access denied for identity 'service-a' on path 'production' (requires list)` | 1 |

### 5.9 add-policy

**Signature:**
```
vault add-policy --identity IDENTITY --path-pattern PATTERN --capabilities CAP[,CAP,...] [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --path-pattern | string | Yes | -- | Non-empty. Valid path characters plus `*` and `**` wildcards. |
| --capabilities | string | Yes | -- | Comma-separated list of one or more of: read, write, list, delete. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Parse the capabilities list.
3. Create a policy associating the identity with the capabilities on the path pattern.
4. Persist the updated vault.
5. Record an audit log entry.

**Output:**
```
Policy added: identity='service-a', path='production/db/*', capabilities=[read, write]
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Invalid capability | `Error: Invalid capability 'execute'. Valid capabilities: read, write, list, delete` | 1 |
| Empty capabilities list | `Error: At least one capability must be specified` | 1 |

### 5.10 remove-policy

**Signature:**
```
vault remove-policy --identity IDENTITY --path-pattern PATTERN [--vault-file PATH] [--audit-file PATH]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --identity | string | Yes | -- | Non-empty, max 255 characters. |
| --path-pattern | string | Yes | -- | Non-empty. Must match an existing policy's path pattern. |
| --vault-file | string | No | `vault.enc` | Valid file path. |
| --audit-file | string | No | `audit.log` | Valid file path. |

**Behavior:**
1. Verify the vault is unsealed.
2. Find and remove the policy matching the given identity and path pattern.
3. Persist the updated vault.
4. Record an audit log entry.

**Output:**
```
Policy removed: identity='service-a', path='production/db/*'
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Vault is sealed | `Error: Vault is sealed` | 1 |
| Policy not found | `Error: No policy found for identity 'service-a' on path 'nonexistent/*'` | 1 |

### 5.11 audit-log

**Signature:**
```
vault audit-log [--audit-file PATH] [--last N]
```

**Input:**

| Parameter | Type | Required | Default | Constraints |
|-----------|------|----------|---------|-------------|
| --audit-file | string | No | `audit.log` | Valid file path. |
| --last | integer | No | All entries | Positive integer. |

**Behavior:**
1. Read the audit log file.
2. If --last is specified, return only the N most recent entries.
3. Display each entry with its fields.

**Output:**
```
2025-01-15T10:30:00Z | admin | init | - | success
2025-01-15T10:30:05Z | admin | unseal | - | success
2025-01-15T10:30:10Z | service-a | store | production/db/password | success
2025-01-15T10:30:15Z | service-b | retrieve | production/db/password | denied
```

**Errors:**

| Condition | Error Message | Exit Code |
|-----------|---------------|-----------|
| Audit file not found | `Error: Audit log file not found at audit.log` | 1 |

## 6. Behavior Scenarios

### 6.1 Initialize and Unseal a New Vault

**Given:** No vault file exists at `test_vault.enc`.

**When:** The following operations are performed in sequence:
1. `vault init --vault-file test_vault.enc --audit-file test_audit.log --password "MyMasterPass123"`
2. `vault status --vault-file test_vault.enc`
3. `vault unseal --vault-file test_vault.enc --password "MyMasterPass123"`
4. `vault status --vault-file test_vault.enc`

**Then:**
1. Output contains: `Vault initialized at test_vault.enc`
2. Output contains: `Status: sealed`
3. Output contains: `Vault unsealed successfully.`
4. Output contains: `Status: unsealed`

The file `test_vault.enc` exists on disk after step 1.

**Validates:** REQ-SEAL-001, REQ-SEAL-002, REQ-SEAL-003, REQ-SEAL-004, REQ-SEAL-008

---

### 6.2 Reject Unseal with Wrong Password

**Given:** A vault file `test_vault.enc` initialized with password "CorrectPassword".

**When:** `vault unseal --vault-file test_vault.enc --password "WrongPassword"`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Incorrect master password`
- `vault status --vault-file test_vault.enc` outputs `Status: sealed`

**Validates:** REQ-SEAL-005

---

### 6.3 Reject Operations When Sealed

**Given:** A vault file `test_vault.enc` initialized with password "MyPass" and currently sealed. A policy exists granting identity "admin" write capability on `**`.

**When:** `vault put secrets/key "myvalue" --identity admin --vault-file test_vault.enc --audit-file test_audit.log`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Vault is sealed`

**Validates:** REQ-SEAL-007

---

### 6.4 Store and Retrieve a Secret with Envelope Encryption

**Given:** A vault `test_vault.enc` initialized with password "MyPass", unsealed, with a policy granting identity "admin" capabilities [read, write] on path pattern `**`.

**When:**
1. `vault put production/db/password "s3cretValue!" --identity admin --vault-file test_vault.enc --audit-file test_audit.log`
2. `vault get production/db/password --identity admin --vault-file test_vault.enc --audit-file test_audit.log`

**Then:**
1. Output contains: `Secret stored at production/db/password (version 1)`
2. Output contains:
   ```
   Path: production/db/password
   Version: 1
   Value: s3cretValue!
   ```

**Validates:** REQ-ENC-001, REQ-ENC-002, REQ-ENC-003, REQ-ENC-004, REQ-ENC-005, REQ-CRUD-001, REQ-CRUD-002, REQ-VER-001

---

### 6.5 Verify Different DEKs for Different Secrets

**Given:** A vault `test_vault.enc` initialized, unsealed, with a policy granting "admin" capabilities [read, write] on `**`.

**When:**
1. `vault put path/secret-a "value-a" --identity admin --vault-file test_vault.enc`
2. `vault put path/secret-b "value-b" --identity admin --vault-file test_vault.enc`
3. Retrieve both secrets.

**Then:**
- `vault get path/secret-a --identity admin` returns Value: `value-a`
- `vault get path/secret-b --identity admin` returns Value: `value-b`
- Both secrets are independently decryptable (demonstrating distinct DEKs).

**Validates:** REQ-ENC-006

---

### 6.6 Retrieve Secret Not Found

**Given:** A vault `test_vault.enc` initialized, unsealed, with a policy granting "admin" capabilities [read] on `**`. No secrets stored.

**When:** `vault get nonexistent/path --identity admin --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Secret not found at path 'nonexistent/path'`

**Validates:** REQ-CRUD-006

---

### 6.7 Delete a Secret

**Given:** A vault `test_vault.enc` initialized, unsealed, with a policy granting "admin" capabilities [read, write, delete, list] on `**`. A secret at path `temp/api-key` with value "abc123".

**When:**
1. `vault delete temp/api-key --identity admin --vault-file test_vault.enc`
2. `vault get temp/api-key --identity admin --vault-file test_vault.enc`

**Then:**
1. Output contains: `Secret deleted at temp/api-key`
2. Exit code is non-zero. Stderr contains: `Error: Secret not found at path 'temp/api-key'`

**Validates:** REQ-CRUD-004, REQ-CRUD-006

---

### 6.8 List Secrets by Prefix

**Given:** A vault with secrets at paths: `prod/db/user`, `prod/db/pass`, `prod/api/key`, `staging/db/user`. A policy granting "admin" capabilities [list] on `**`.

**When:** `vault list prod/db --identity admin --vault-file test_vault.enc`

**Then:** Output contains:
```
prod/db/user
prod/db/pass
```
Output does not contain `prod/api/key` or `staging/db/user`.

**Validates:** REQ-CRUD-005

---

### 6.9 List Returns Empty When No Secrets Match

**Given:** A vault with no secrets stored. A policy granting "admin" capabilities [list] on `**`.

**When:** `vault list --identity admin --vault-file test_vault.enc`

**Then:** Output contains: `No secrets found.`

**Validates:** REQ-CRUD-005

---

### 6.10 Invalid Path Format Rejected

**Given:** A vault `test_vault.enc` initialized, unsealed, with a policy granting "admin" capabilities [write] on `**`.

**When:** `vault put "invalid//path" "value" --identity admin --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Invalid path format`

**Validates:** REQ-CRUD-007

---

### 6.11 Access Control Denies Unauthorized Read

**Given:** A vault `test_vault.enc` initialized, unsealed. Policies:
- Identity "service-a" has [read, write] on `app-a/**`
- Identity "service-b" has [read] on `app-b/**`
A secret at `app-a/db/password` with value "secret123" stored by "service-a".

**When:** `vault get app-a/db/password --identity service-b --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Access denied for identity 'service-b' on path 'app-a/db/password' (requires read)`

**Validates:** REQ-ACL-003, REQ-ACL-005

---

### 6.12 Access Control Grants Authorized Read

**Given:** A vault `test_vault.enc` initialized, unsealed. Policies:
- Identity "service-a" has [read, write] on `app-a/**`
- Identity "service-b" has [read] on `app-b/**`
A secret at `app-a/db/password` with value "secret123" stored by "service-a".

**When:** `vault get app-a/db/password --identity service-a --vault-file test_vault.enc`

**Then:** Output contains:
```
Path: app-a/db/password
Version: 1
Value: secret123
```

**Validates:** REQ-ACL-003, REQ-ACL-006, REQ-ACL-004

---

### 6.13 Glob Wildcard Policy Matching

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting identity "deployer" capabilities [read, write] on `production/*/credentials`.

**When:**
1. `vault put production/web/credentials "web-cred" --identity deployer --vault-file test_vault.enc`
2. `vault put production/cache/credentials "cache-cred" --identity deployer --vault-file test_vault.enc`
3. `vault put production/web/config "web-config" --identity deployer --vault-file test_vault.enc`

**Then:**
1. Output contains: `Secret stored at production/web/credentials (version 1)` -- access granted by `*` matching "web".
2. Output contains: `Secret stored at production/cache/credentials (version 1)` -- access granted by `*` matching "cache".
3. Exit code is non-zero. Stderr contains: `Error: Access denied` -- "config" does not match the pattern `production/*/credentials`.

**Validates:** REQ-ACL-002, REQ-ACL-004, REQ-ACL-006

---

### 6.14 Double-Star Wildcard Policy Matching

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting identity "admin" capabilities [read, write, list, delete] on `**`.

**When:**
1. `vault put any/deep/nested/path "value" --identity admin --vault-file test_vault.enc`
2. `vault get any/deep/nested/path --identity admin --vault-file test_vault.enc`

**Then:**
1. Output contains: `Secret stored at any/deep/nested/path (version 1)`
2. Output contains value: `value`

**Validates:** REQ-ACL-002, REQ-ACL-006

---

### 6.15 Default Deny When No Policy Exists

**Given:** A vault `test_vault.enc` initialized, unsealed. No policies defined.

**When:** `vault put secrets/key "value" --identity unknown-user --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Access denied`

**Validates:** REQ-ACL-005, REQ-ACL-007

---

### 6.16 Add and Remove a Policy

**Given:** A vault `test_vault.enc` initialized, unsealed.

**When:**
1. `vault add-policy --identity reader --path-pattern "reports/*" --capabilities read,list --vault-file test_vault.enc`
2. `vault remove-policy --identity reader --path-pattern "reports/*" --vault-file test_vault.enc`

**Then:**
1. Output contains: `Policy added: identity='reader', path='reports/*', capabilities=[read, list]`
2. Output contains: `Policy removed: identity='reader', path='reports/*'`

**Validates:** REQ-ACL-001, REQ-ACL-009

---

### 6.17 Policies Persist Across Seal/Unseal

**Given:** A vault `test_vault.enc` initialized with password "TestPass", unsealed. A policy granting "service-x" capabilities [read, write] on `data/**`.

**When:**
1. `vault put data/item "val1" --identity service-x --vault-file test_vault.enc` (succeeds)
2. `vault seal --vault-file test_vault.enc`
3. `vault unseal --vault-file test_vault.enc --password "TestPass"`
4. `vault get data/item --identity service-x --vault-file test_vault.enc`

**Then:**
1. Output contains: `Secret stored at data/item (version 1)`
4. Output contains value: `val1`

**Validates:** REQ-ACL-008, REQ-CRUD-008

---

### 6.18 Audit Log Records All Operations

**Given:** A vault `test_vault.enc` initialized with password "AuditPass", with a policy granting "admin" capabilities [read, write] on `**`.

**When:**
1. `vault unseal --vault-file test_vault.enc --password "AuditPass"`
2. `vault put audit/test "val" --identity admin --vault-file test_vault.enc --audit-file test_audit.log`
3. `vault get audit/test --identity admin --vault-file test_vault.enc --audit-file test_audit.log`
4. `vault get audit/test --identity unauthorized --vault-file test_vault.enc --audit-file test_audit.log` (denied)
5. `vault audit-log --audit-file test_audit.log`

**Then:** The audit log output contains entries for:
- init operation with outcome "success"
- unseal operation with outcome "success"
- store operation by "admin" on path "audit/test" with outcome "success"
- retrieve operation by "admin" on path "audit/test" with outcome "success"
- retrieve operation by "unauthorized" on path "audit/test" with outcome "denied"

Each entry contains a timestamp in ISO 8601 format.

**Validates:** REQ-AUD-001, REQ-AUD-002, REQ-AUD-003, REQ-AUD-004

---

### 6.19 Audit Log Entry Written Before Result Returned

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting "admin" capabilities [write] on `**`.

**When:** `vault put timing/secret "value" --identity admin --vault-file test_vault.enc --audit-file test_audit.log`

**Then:**
- The audit log file contains an entry for the store operation on "timing/secret" with outcome "success".
- The operation output contains: `Secret stored at timing/secret (version 1)`

(The log entry exists when the output is returned, verifying REQ-AUD-005.)

**Validates:** REQ-AUD-005

---

### 6.20 Secret Versioning on Update

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting "admin" capabilities [read, write] on `**`.

**When:**
1. `vault put config/api-key "key-v1" --identity admin --vault-file test_vault.enc`
2. `vault put config/api-key "key-v2" --identity admin --vault-file test_vault.enc`
3. `vault put config/api-key "key-v3" --identity admin --vault-file test_vault.enc`
4. `vault get config/api-key --identity admin --vault-file test_vault.enc`
5. `vault get config/api-key --identity admin --version 1 --vault-file test_vault.enc`
6. `vault get config/api-key --identity admin --version 2 --vault-file test_vault.enc`

**Then:**
1. Output contains: `Secret stored at config/api-key (version 1)`
2. Output contains: `Secret updated at config/api-key (version 2)`
3. Output contains: `Secret updated at config/api-key (version 3)`
4. Output contains: `Version: 3` and `Value: key-v3`
5. Output contains: `Version: 1` and `Value: key-v1`
6. Output contains: `Version: 2` and `Value: key-v2`

**Validates:** REQ-VER-001, REQ-VER-002, REQ-VER-003, REQ-VER-004, REQ-VER-006

---

### 6.21 Version Not Found Error

**Given:** A vault with a secret at `config/api-key` with versions 1 and 2. Policy granting "admin" capabilities [read] on `**`.

**When:** `vault get config/api-key --identity admin --version 99 --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Version 99 not found for path 'config/api-key'`

**Validates:** REQ-VER-005

---

### 6.22 Seal Discards Root Key

**Given:** A vault `test_vault.enc` initialized with password "SealTest", unsealed. A policy granting "admin" capabilities [read, write] on `**`. A secret at `test/key` with value "before-seal".

**When:**
1. `vault seal --vault-file test_vault.enc`
2. `vault get test/key --identity admin --vault-file test_vault.enc`

**Then:**
1. Output contains: `Vault sealed.`
2. Exit code is non-zero. Stderr contains: `Error: Vault is sealed`

**Validates:** REQ-SEAL-006, REQ-SEAL-007

---

### 6.23 Secrets Persist Across Seal/Unseal Cycles

**Given:** A vault `test_vault.enc` initialized with password "PersistTest", unsealed. A policy granting "admin" capabilities [read, write] on `**`.

**When:**
1. `vault put persist/secret "persistent-value" --identity admin --vault-file test_vault.enc`
2. `vault seal --vault-file test_vault.enc`
3. `vault unseal --vault-file test_vault.enc --password "PersistTest"`
4. `vault get persist/secret --identity admin --vault-file test_vault.enc`

**Then:**
4. Output contains: `Value: persistent-value`

**Validates:** REQ-CRUD-008, REQ-SEAL-004

---

### 6.24 CLI Error Output and Exit Codes

**Given:** A vault `test_vault.enc` initialized, unsealed.

**When:** `vault add-policy --identity test --path-pattern "path/*" --capabilities "read,execute" --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Invalid capability 'execute'`

**Validates:** REQ-CLI-005

---

### 6.25 Delete Nonexistent Secret Returns Error

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting "admin" capabilities [delete] on `**`. No secret at path `ghost/secret`.

**When:** `vault delete ghost/secret --identity admin --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Secret not found at path 'ghost/secret'`

**Validates:** REQ-CRUD-006

---

### 6.26 Capability Mapping Enforced for Each Operation Type

**Given:** A vault `test_vault.enc` initialized, unsealed. A policy granting "limited" only [read] on `data/**`. A secret at `data/item` with value "readable".

**When:**
1. `vault get data/item --identity limited --vault-file test_vault.enc` (requires read)
2. `vault put data/item "new-val" --identity limited --vault-file test_vault.enc` (requires write)
3. `vault list data --identity limited --vault-file test_vault.enc` (requires list)
4. `vault delete data/item --identity limited --vault-file test_vault.enc` (requires delete)

**Then:**
1. Output contains value: `readable` (read capability is granted).
2. Exit code non-zero. Stderr contains: `Error: Access denied` (write not granted).
3. Exit code non-zero. Stderr contains: `Error: Access denied` (list not granted).
4. Exit code non-zero. Stderr contains: `Error: Access denied` (delete not granted).

**Validates:** REQ-ACL-003, REQ-ACL-004, REQ-ACL-005

---

### 6.27 Vault Init Rejects Existing File

**Given:** A vault file `test_vault.enc` already exists.

**When:** `vault init --vault-file test_vault.enc --password "NewPass"`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: Vault file already exists`

**Validates:** REQ-CLI-005

---

### 6.28 Remove Nonexistent Policy Returns Error

**Given:** A vault `test_vault.enc` initialized, unsealed. No policies defined for identity "phantom".

**When:** `vault remove-policy --identity phantom --path-pattern "any/*" --vault-file test_vault.enc`

**Then:**
- Exit code is non-zero.
- Stderr contains: `Error: No policy found`

**Validates:** REQ-ACL-009

## 7. Technical Constraints

| Constraint | Source | Detail |
|------------|--------|--------|
| Language | RESEARCH.md Section 6 | Python 3.10+ |
| Cryptographic library | RESEARCH.md Section 6 | The `cryptography` library (provides AES-GCM and PBKDF2). This is the only external cryptographic dependency. |
| Cipher | RESEARCH.md Section 3 | AES-256-GCM for all encryption operations (both DEK encryption and value encryption). |
| Key derivation | RESEARCH.md Section 3, 6 | PBKDF2 with HMAC-SHA256, minimum 600,000 iterations, 16-byte random salt. |
| Nonce size | RESEARCH.md Section 3 | 12-byte (96-bit) nonce per AES-GCM encryption operation. |
| Root Key size | RESEARCH.md Section 3 | 256 bits (32 bytes). |
| Storage format | RESEARCH.md Section 7 (resolved) | Single encrypted JSON file. |
| Interface type | RESEARCH.md Section 7 (resolved) | Python class-based API with thin CLI wrapper. |
| CLI framework | RESEARCH.md Section 6 | Python `argparse` or `click` library. Agent's choice. |
| Concurrency | RESEARCH.md Section 6 | Single-user, single-process. No concurrency control required. |
| Identity model | RESEARCH.md Section 5.3 | Simple identity string passed as parameter. No authentication. |
| Secret values | RESEARCH.md Section 6 | String type only (not binary). |
| Audit log format | RESEARCH.md Section 5.3 | Append-only local file. No cryptographic hash chains. |

## 8. Deviations from Research

1. **Added REQ-SEAL-008 (status query):** RESEARCH.md does not explicitly list a status query as an in-scope item, but the seal/unseal lifecycle implies the ability to check the current state. This is necessary for testing the seal/unseal behavior and is a minimal addition that supports the core lifecycle feature.

2. **Added REQ-ACL-009 (remove policy):** RESEARCH.md Section 5.1 mentions "define policies" but does not explicitly mention removing them. Policy removal is necessary for a complete policy management interface and for testing that policy changes take effect.

3. **Added REQ-CLI-006 (password prompting):** RESEARCH.md Section 6 states "The master password is provided interactively or as a parameter" -- the CLI spec formalizes both modes. The interactive prompt without echo is standard security practice for CLI password entry.

4. **Explicit path format constraints (REQ-CRUD-007):** RESEARCH.md describes hierarchical paths with forward-slash separators but does not specify character constraints. The spec defines a concrete character set (alphanumeric, hyphens, underscores, slashes) and disallows empty segments, leading/trailing slashes, and consecutive slashes to ensure path validity is testable.

5. **Audit log "detail" field (AuditEntry entity):** RESEARCH.md specifies timestamp, identity, operation, path, and outcome. The "detail" field is added to carry error reasons (e.g., "incorrect password") for richer audit context. This is optional and does not change the required fields.

6. **Vault verification token:** The unseal interface contract references decrypting a "verification token" to confirm the password is correct. RESEARCH.md does not explicitly mention this mechanism, but it is necessary to implement REQ-SEAL-005 (rejecting incorrect passwords). The verification token is a well-known pattern in encrypted storage systems.

## 9. Traceability Matrix

| Research Scope Item (Section 5.1) | Requirements | Interface Contracts | Behavior Scenarios |
|---|---|---|---|
| Seal/Unseal lifecycle: Derive Root Key from master password using PBKDF2 on unseal; hold Root Key in memory; discard on seal. Initialize a new vault with a master password. | REQ-SEAL-001, REQ-SEAL-002, REQ-SEAL-003, REQ-SEAL-004, REQ-SEAL-005, REQ-SEAL-006, REQ-SEAL-007, REQ-SEAL-008 | 5.1 init, 5.2 unseal, 5.3 seal, 5.4 status | 6.1, 6.2, 6.3, 6.22, 6.23 |
| Envelope encryption for secrets: Generate a unique AES-256-GCM DEK per secret; encrypt the secret value with the DEK; encrypt the DEK with the Root Key; store encrypted DEK + encrypted value + nonces + metadata together. | REQ-ENC-001, REQ-ENC-002, REQ-ENC-003, REQ-ENC-004, REQ-ENC-005, REQ-ENC-006 | 5.5 put, 5.6 get | 6.4, 6.5 |
| CRUD operations on secrets by path: Store, retrieve, update, and delete secrets addressed by hierarchical paths. | REQ-CRUD-001, REQ-CRUD-002, REQ-CRUD-003, REQ-CRUD-004, REQ-CRUD-005, REQ-CRUD-006, REQ-CRUD-007, REQ-CRUD-008 | 5.5 put, 5.6 get, 5.7 delete, 5.8 list | 6.4, 6.6, 6.7, 6.8, 6.9, 6.10, 6.23, 6.25 |
| Path-based access control policies: Define policies that grant read/write/list/delete capabilities on path patterns (with glob wildcard support) to named identities. Evaluate policies on every operation. | REQ-ACL-001, REQ-ACL-002, REQ-ACL-003, REQ-ACL-004, REQ-ACL-005, REQ-ACL-006, REQ-ACL-007, REQ-ACL-008, REQ-ACL-009 | 5.5 put, 5.6 get, 5.7 delete, 5.8 list, 5.9 add-policy, 5.10 remove-policy | 6.11, 6.12, 6.13, 6.14, 6.15, 6.16, 6.17, 6.26, 6.28 |
| Append-only audit log: Log every operation (including denied attempts) with timestamp, identity, operation, path, and outcome to an append-only file. | REQ-AUD-001, REQ-AUD-002, REQ-AUD-003, REQ-AUD-004, REQ-AUD-005 | 5.11 audit-log | 6.18, 6.19 |
| Basic secret versioning for rotation: When a secret is updated, retain the previous version. Support reading the current version or a specific version number. | REQ-VER-001, REQ-VER-002, REQ-VER-003, REQ-VER-004, REQ-VER-005, REQ-VER-006 | 5.5 put, 5.6 get | 6.4, 6.20, 6.21 |
| CLI or programmatic interface: A command-line interface or Python API that exercises all the above capabilities end-to-end. | REQ-CLI-001, REQ-CLI-002, REQ-CLI-003, REQ-CLI-004, REQ-CLI-005, REQ-CLI-006 | 5.1 through 5.11 (all) | 6.1, 6.24, 6.27 |
