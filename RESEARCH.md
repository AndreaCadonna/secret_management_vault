# Domain Research: Secret Management Vault

## 1. Problem Domain Overview

Software systems rely on sensitive credentials -- API keys, database passwords, encryption keys, tokens, and certificates -- to communicate with each other and with external services. These credentials are collectively called "secrets." The problem of secret management is: how do you store, distribute, and control access to these secrets so that they remain confidential, available only to authorized entities, and auditable?

Without a dedicated secret management system, secrets end up in plaintext configuration files, environment variables, source code repositories, or shared spreadsheets. This leads to credential leakage (secrets committed to Git, visible in CI logs, or accessible on developer laptops), inability to audit who accessed what secret and when, difficulty rotating compromised credentials quickly, and no centralized control over which applications or users can read which secrets. A secret management vault solves these problems by providing a single, encrypted, access-controlled store for secrets with a complete audit trail of every operation.

The domain sits at the intersection of applied cryptography (encryption at rest, key derivation, key hierarchies), access control (authentication and authorization policies), and operational security (audit logging, secret rotation, least-privilege enforcement). Major implementations include HashiCorp Vault (open-source, Go), AWS Secrets Manager, Azure Key Vault, and CyberArk. All share the same fundamental architecture: secrets are encrypted before storage, access is mediated through policies, and every operation is logged.

## 2. Core Principle

Demonstrating a layered encryption key hierarchy with envelope encryption to protect secrets at rest, mediated by path-based access control policies and recorded in an append-only audit log.

The central mechanism is envelope encryption: each secret is encrypted with a unique Data Encryption Key (DEK), and all DEKs are encrypted with a single Root Key (also called a Master Key). The Root Key itself is derived from a user-provided master password using a key derivation function (PBKDF2). This hierarchy means that compromising the storage backend yields only ciphertext; compromising a single DEK exposes only one secret; and the Root Key never touches disk in plaintext -- it exists only in memory after the vault is "unsealed." Access control policies determine which identities can read, write, or list secrets at specific paths, and every access attempt is written to an immutable, append-only audit log.

## 3. Key Concepts

| Concept | Definition | Relevance to Our Build |
|---------|------------|------------------------|
| Envelope Encryption | A two-layer encryption scheme where data is encrypted with a Data Encryption Key (DEK), and the DEK is encrypted with a Key Encryption Key (KEK) or Root Key. | This is the core encryption architecture we will implement. Every secret gets its own DEK; all DEKs are encrypted under the Root Key. |
| Root Key (Master Key) | The top-level encryption key that protects all other keys. In HashiCorp Vault, this is called the "root key" and is itself protected by the unseal key. | We will derive this from a master password using PBKDF2. It exists only in memory when the vault is unsealed. |
| Key Derivation Function (KDF) | An algorithm that derives a cryptographic key from a password or passphrase. PBKDF2 applies a pseudorandom function (HMAC-SHA256) repeatedly to make brute-force attacks expensive. | We use PBKDF2 to convert the user's master password into a 256-bit Root Key. The salt and iteration count are stored alongside the encrypted vault. |
| AES-256-GCM | Advanced Encryption Standard with 256-bit keys in Galois/Counter Mode. Provides both confidentiality (encryption) and integrity (authentication tag). Requires a unique 96-bit nonce per encryption operation. | The symmetric cipher used for all encryption operations -- both encrypting secrets with DEKs and encrypting DEKs with the Root Key. |
| Seal / Unseal | The vault starts in a "sealed" state where it cannot decrypt any data. Unsealing provides the Root Key (derived from the master password), loading it into memory so operations can proceed. Sealing discards the Root Key from memory. | The vault lifecycle: start sealed, unseal with password, perform operations, seal when done. Controls when the Root Key exists in memory. |
| Access Control Policy | A declarative rule that grants or denies specific operations (read, write, list, delete) on specific secret paths to specific identities. | We implement path-based policies (e.g., "service-account-A can read secrets/database/*") to control who can access what. |
| Audit Log | An append-only record of every operation attempted against the vault, including the identity, operation type, path, timestamp, and whether it succeeded or was denied. | We write every vault operation to an append-only log file. This log is the accountability mechanism. |
| Secret Rotation | The process of replacing a secret's value with a new one on a schedule or on demand, while maintaining a brief overlap period where both old and new values are valid. | We implement a simplified version: manual rotation that creates a new version of a secret and marks the old version as superseded. |
| Secret Path | A hierarchical identifier for a secret, using forward-slash separators (e.g., "production/database/password"). Paths organize secrets and serve as the basis for access control policy matching. | Secrets are addressed by path. Policies grant permissions on path patterns (including glob wildcards). |

## 4. Existing Approaches

### Approach 1: Full Key Hierarchy with Shamir's Secret Sharing (HashiCorp Vault Model)

**How it works:** The vault uses a three-tier key hierarchy: an unseal key (split into shares using Shamir's Secret Sharing), a root key (encrypted by the unseal key), and per-secret data encryption keys (encrypted by the root key). Unsealing requires a threshold number of key shares from separate operators. Access control uses token-based authentication with ACL policies. All data passes through an encryption barrier before reaching the storage backend.

**Pros:** Maximum security through key splitting across multiple operators; no single person can unseal the vault; well-proven architecture used in production worldwide.

**Cons:** Shamir's Secret Sharing adds significant implementation complexity; requires multiple operators for unsealing; the token-based auth system requires its own lifecycle management.

**Complexity:** High -- Shamir's polynomial interpolation, token management, multiple auth backends, lease management, and secret engines are all substantial subsystems.

### Approach 2: Password-Derived Master Key with Envelope Encryption

**How it works:** A single master password is run through a KDF (PBKDF2 or Argon2) to produce a Root Key. The Root Key encrypts per-secret DEKs. Each secret is encrypted with its own DEK using AES-256-GCM. The encrypted DEKs and encrypted secrets are stored together (e.g., in a JSON file or SQLite database). Access control is enforced through in-memory policy evaluation. Audit events are appended to a log file.

**Pros:** Conceptually clear and straightforward to implement; demonstrates the full envelope encryption pattern; no external dependencies; single master password is easy to manage in an experiment.

**Cons:** Single point of failure (one password); no key splitting; not suitable for multi-operator production use; password strength directly determines security.

**Complexity:** Low to Medium -- the cryptographic primitives (AES-GCM, PBKDF2) are provided by standard libraries; the key hierarchy is two layers deep; policy evaluation is string matching on paths.

### Approach 3: Encrypted File with Direct Encryption (Password Manager Model)

**How it works:** All secrets are serialized into a single data structure (JSON or similar), and the entire structure is encrypted as one blob using a key derived from a master password. No per-secret keys. Access control is binary: you either have the master password and can see everything, or you cannot. Used by tools like Ansible Vault and simple password managers.

**Pros:** Extremely simple to implement; single encrypt/decrypt operation; minimal code.

**Cons:** No per-secret encryption granularity; no access control (all-or-nothing); must decrypt everything to read one secret; cannot demonstrate key hierarchy or access policies -- which are the core mechanisms of a secret management vault.

**Complexity:** Low -- but too simple to demonstrate the core principle.

### Recommended Approach for This Experiment

**Approach 2: Password-Derived Master Key with Envelope Encryption.** This approach hits the precise balance between demonstrating the real mechanisms of a secret vault (key hierarchy, envelope encryption, per-secret DEKs, path-based access control, audit logging) and remaining implementable in a single session. It strips away the operational complexity of Shamir's Secret Sharing and token-based authentication without losing the architectural essence. The implementation agent can focus on the cryptographic core and access control logic rather than on multi-operator coordination protocols.

## 5. Scope Decision

### In Scope

- **Seal/Unseal lifecycle:** Derive Root Key from master password using PBKDF2 on unseal; hold Root Key in memory; discard on seal. Initialize a new vault with a master password.
- **Envelope encryption for secrets:** Generate a unique AES-256-GCM DEK per secret; encrypt the secret value with the DEK; encrypt the DEK with the Root Key; store encrypted DEK + encrypted value + nonces + metadata together.
- **CRUD operations on secrets by path:** Store, retrieve, update, and delete secrets addressed by hierarchical paths (e.g., "production/db/password").
- **Path-based access control policies:** Define policies that grant read/write/list/delete capabilities on path patterns (with glob wildcard support) to named identities. Evaluate policies on every operation.
- **Append-only audit log:** Log every operation (including denied attempts) with timestamp, identity, operation, path, and outcome to an append-only file.
- **Basic secret versioning for rotation:** When a secret is updated, retain the previous version. Support reading the current version or a specific version number. This demonstrates the rotation concept without automatic scheduling.
- **CLI or programmatic interface:** A command-line interface or Python API that exercises all the above capabilities end-to-end.

### Out of Scope

- **Shamir's Secret Sharing:** Adds complexity without demonstrating a different core principle than password-derived key hierarchy. Cut to keep scope tight.
- **Network server / HTTP API:** The vault runs as a local library or CLI tool, not as a networked service. Networking adds TLS, session management, and concurrency concerns that do not demonstrate the core principle.
- **Multiple authentication backends:** No LDAP, OAuth, Kubernetes auth, or certificate-based auth. We use a simple identity string passed at operation time.
- **Dynamic secrets:** Generating on-demand credentials for external systems (databases, cloud providers) requires integration with those systems. Cut entirely.
- **Automatic timed rotation:** Scheduled background rotation requires a scheduler, timer management, and integration with target systems. We demonstrate the concept through manual versioning instead.
- **High availability / replication:** No clustering, leader election, or storage replication. Single-instance only.
- **Transit encryption (encryption-as-a-service):** Vault's ability to encrypt/decrypt arbitrary data on behalf of applications is a separate concern from secret storage. Cut.
- **Lease management and TTLs:** Automatic secret expiration and renewal adds lifecycle complexity beyond the core principle. Cut.
- **Web UI or dashboard:** No graphical interface. CLI or programmatic API only.

### Mocks/Stubs

- **Storage backend:** Production vaults use Consul, etcd, or cloud storage. We use a local JSON file or SQLite database as the storage backend. No mock needed -- file-based storage is a legitimate (if minimal) backend.
- **Identity/Authentication:** Production vaults authenticate users against identity providers (LDAP, OAuth, cloud IAM). We stub this with a simple identity string (e.g., "admin", "service-a") passed as a parameter to each operation. No actual authentication occurs -- we trust the caller's stated identity and focus on authorization (policy evaluation).
- **External systems for rotation:** Production rotation connects to databases or cloud APIs to change credentials. We mock this entirely -- "rotation" means generating a new random value and storing it as a new version. No external system is contacted.
- **Hash-chained audit log integrity:** Production audit logs use cryptographic hash chains for tamper detection. We stub this with a simpler append-only file. The log demonstrates accountability (who did what) without the cryptographic tamper-proofing.

## 6. Assumptions

- The implementation language is Python 3.10+, using the `cryptography` library (which provides AES-GCM and PBKDF2) as the only external cryptographic dependency.
- The vault operates as a single-user, single-process, local tool. Concurrency control is not required.
- The master password is provided interactively or as a parameter at unseal time. No secure hardware (HSM, TPM) is involved.
- File-based storage (JSON) is acceptable for this experiment. Durability and performance are not concerns.
- The identity of the caller is a simple string, not cryptographically verified. The experiment focuses on authorization policy evaluation, not authentication.
- Secret values are strings (not binary blobs). This simplifies serialization.
- PBKDF2 with HMAC-SHA256 and a minimum of 600,000 iterations is acceptable for key derivation. Argon2 would be stronger but adds a compiled dependency.
- The audit log is a local file. Log shipping, aggregation, and analysis are out of scope.
- "Rotation" means creating a new version of a secret value. The vault does not contact external systems to propagate the new value.
- The CLI interface (if built) uses Python's `argparse` or `click` library. No custom shell or REPL.

## 7. Open Questions

- **Should the experiment include a simple CLI, a Python API (library), or both?** This affects whether the implementation agent builds a `__main__.py` with argparse or a clean class-based API with a thin CLI wrapper. Both are achievable in one session, but knowing the preference upfront avoids rework. If no preference, the default will be a Python class-based API with a thin CLI wrapper.
- **Is there a preferred storage format?** A single JSON file is simplest. SQLite adds query capability but also a dependency. If no preference, the default will be a single encrypted JSON file.

## 8. References

- HashiCorp Vault Architecture Documentation: https://developer.hashicorp.com/vault/docs/internals/architecture
- HashiCorp Vault Security Model: https://developer.hashicorp.com/vault/docs/internals/security
- HashiCorp Vault Seal/Unseal Concepts: https://developer.hashicorp.com/vault/docs/concepts/seal
- HashiCorp Vault Policies (Access Control): https://developer.hashicorp.com/vault/docs/concepts/policies
- Google Cloud Envelope Encryption Documentation: https://cloud.google.com/kms/docs/envelope-encryption
- AWS Key Hierarchy with Master Keys (CloudHSM Series): https://aws.amazon.com/blogs/security/benefits-of-a-key-hierarchy-with-a-master-key-part-two-of-the-aws-cloudhsm-series/
- AWS Secrets Manager Encryption and Decryption: https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html
- Shamir's Secret Sharing (Wikipedia): https://en.wikipedia.org/wiki/Shamir%27s_secret_sharing
- Practical Cryptography for Developers -- AES Encrypt/Decrypt Examples: https://cryptobook.nakov.com/symmetric-key-ciphers/aes-encrypt-decrypt-examples
- AES-GCM with PBKDF2 Key Derivation (A Security Site): https://asecuritysite.com/encryption/aes_gcm2
- anthonynsimon/secrets-vault (Simple Python encrypted secrets): https://github.com/anthonynsimon/secrets-vault
- Infisical Secret Rotation Documentation: https://infisical.com/docs/documentation/platform/secret-rotation/overview
