# Software Architect Agent Memory

## Project: Secret Management Vault

### Key Design Decisions
- **CLI state persistence**: For CLI tools where state (like "unsealed") must persist between process invocations, a session file storing runtime state (e.g., hex-encoded key) is the simplest approach. No OS keyring, no daemon.
- **Envelope encryption storage**: Individual secret values are envelope-encrypted; the vault JSON file itself is NOT encrypted as a whole. Policies and metadata remain readable without the root key.
- **Password verification**: Use a "verification token" -- encrypt a known plaintext during init, decrypt during unseal. AES-GCM auth tag failure indicates wrong password.
- **Glob matching**: Do NOT use fnmatch directly -- its `*` matches `/` which breaks single-segment matching. Convert to regex: `*` -> `[^/]*`, `**` -> `.*`. Split on `**` before processing `*`.
- **Binary in JSON**: Base64-encode specific named fields (salt, nonces, encrypted values). Enumerate the exact field names to avoid missing any.

### Architecture Pattern
- 5 modules + 1 CLI entry point works well for medium-complexity projects
- Data flow order for implementation steps: primitives -> persistence -> business rules -> orchestrator -> UI layer -> integration
- Stub-first approach: create all files with NotImplementedError stubs in Step 1, implement bottom-up

### Requirement Count
- SPEC had 48 total requirements across 7 categories (SEAL:8, ENC:6, CRUD:8, ACL:9, AUD:5, VER:6, CLI:6), not 38 as initially stated by user
- Always count requirements directly from SPEC rather than trusting stated counts

### Risks Identified
- Audit log ordering (write before return) is easy to get wrong
- Empty string prefix in list command needs special-case handling in pattern matching
- Windows `os.replace()` is atomic and works for safe file writes
- PBKDF2 with 600K iterations takes ~0.3-1.0s -- do not reduce for testing
