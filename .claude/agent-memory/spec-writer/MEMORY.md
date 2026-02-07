# Spec Writer Agent Memory

## Project: Secret Management Vault
- Core principle: Envelope encryption with key hierarchy (DEK per secret, Root Key from PBKDF2)
- 7 features: SEAL, ENC, CRUD, ACL, AUD, VER, CLI
- 38 total requirements across 7 feature groups
- 28 behavior scenarios (6.1 through 6.28)
- Resolved open questions: Python class API + CLI wrapper, single encrypted JSON file

## Lessons Learned

### Self-Review Catches
1. **Banned word "may"** appeared in Data Model constraint descriptions (e.g., "Required (may be empty)"). Replace with "can" or rephrase.
2. **REQ format consistency**: One requirement started with "Each audit log entry shall" instead of "The system shall" -- easy to miss in logging/audit requirements.
3. **Self-contained scenarios**: Avoid "Same setup as Scenario X.Y" -- always repeat the full Given clause.
4. **Audit file parameter consistency**: When audit logging is a feature, ensure every operation that generates audit entries has the `--audit-file` parameter in its interface contract. Easy to miss on seal/unseal commands.
5. **Verification token deviation**: When specifying password rejection (wrong password on unseal), the mechanism to verify correctness (verification token) is an implementation-visible deviation that must be documented.

### Feature Prefix Conventions
- SEAL (Seal/Unseal lifecycle) -- from "Seal"
- ENC (Envelope Encryption) -- from "Encryption"
- CRUD (CRUD operations) -- from the acronym itself
- ACL (Access Control) -- from "Access Control List" acronym
- AUD (Audit log) -- from "Audit"
- VER (Versioning) -- from "Versioning"
- CLI (Command-line interface) -- from "CLI" acronym

### Cryptography Spec Patterns
- When core principle IS the algorithm, internal structure requirements (key hierarchy, DEK generation, nonce sizes) are valid behavioral requirements per Rule 10.
- Key derivation parameters (iterations, salt size) are behavioral because they affect security properties observable via the storage format.
- Nonce uniqueness is a behavioral requirement (two encryptions produce different ciphertexts).

### Edge Case Patterns for CRUD Features
- Empty collection (list with no items)
- Not-found errors (retrieve/delete nonexistent)
- Invalid input format (bad path characters, consecutive slashes)
- Persistence across lifecycle (store, seal, unseal, retrieve)
- Delete-then-retrieve (confirms deletion)

### Edge Case Patterns for ACL Features
- Default deny (no policies exist)
- Cross-identity isolation (service-a cannot access service-b paths)
- Capability granularity (read-only user cannot write/delete/list)
- Wildcard specificity (* vs **)
- Policy persistence across seal/unseal
