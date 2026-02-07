# Domain Research Phase 0 - Agent Memory

## Project: Secret Management Vault
- Core principle: Envelope encryption with key hierarchy + path-based access control + audit logging
- Recommended approach: Password-derived master key (PBKDF2) with per-secret DEKs (AES-256-GCM)
- Scoped down from: Shamir's Secret Sharing, network server, dynamic secrets, auto-rotation

## Scoping Lessons Learned
- Security/crypto projects tempt over-scoping. The user listed 4 features (encryption, ACL, audit, rotation). Each could be its own project. Kept rotation to "versioning" only.
- Shamir's Secret Sharing is a common trap: interesting but adds polynomial math complexity without demonstrating a fundamentally different principle than password-derived keys for an experiment.
- "Rotation" in production means contacting external systems. For experiments, redefine as "versioning" (store new value, keep old).
- Network API (HTTP server) doubles scope. CLI/library is sufficient to demonstrate the principle.

## Effective Patterns
- Envelope encryption is the cleanest "core principle" for a vault -- it's the single mechanism that separates a vault from a password manager.
- Stubbing authentication as a simple identity string while keeping authorization (policy evaluation) real is a good split. Auth is integration; authz is logic.
- Append-only file for audit log is sufficient. Hash-chaining is interesting but not essential for demonstrating accountability.

## Reliable Sources for Crypto/Security Domain
- HashiCorp Vault docs (architecture, security model, seal/unseal): authoritative reference implementation
- Google Cloud envelope encryption docs: clearest explanation of envelope encryption pattern
- AWS CloudHSM blog series: good for key hierarchy concepts
- cryptobook.nakov.com: practical AES-GCM examples with code
- asecuritysite.com: AES-GCM + PBKDF2 Python examples

## Research Process Notes
- Search for reference implementations early. Finding anthonynsimon/secrets-vault confirmed that a single-file Python vault is achievable.
- Always search for the "how it works" of the dominant open-source tool (HashiCorp Vault) to understand what the production architecture looks like before scoping down.
