# vault.py -- Central API orchestrator for the Secret Management Vault.
# Implements DESIGN.md Component 3.5: coordinates all vault operations by
# delegating to crypto, storage, policy, and audit components.
# Fulfills: REQ-SEAL-001 through REQ-SEAL-008, REQ-ENC-001 through REQ-ENC-006,
#           REQ-CRUD-001 through REQ-CRUD-008, REQ-ACL-001 through REQ-ACL-009,
#           REQ-AUD-001 through REQ-AUD-005, REQ-VER-001 through REQ-VER-006

import datetime

import audit
import crypto
import policy
import storage


class VaultError(Exception):
    """Base exception for vault operation errors."""
    pass


class Vault:
    """Central API for the Secret Management Vault.

    Coordinates initialization, seal/unseal lifecycle, CRUD on secrets,
    policy management, and audit logging. The root key is loaded from
    the session file on each operation and not stored as an instance attribute.

    Args:
        vault_file: Path to the encrypted vault JSON file.
        audit_file: Path to the audit log file.
    """

    def __init__(self, vault_file: str = "vault.enc", audit_file: str = "audit.log") -> None:
        self.vault_file = vault_file
        self.audit_file = audit_file

    def _session_file(self) -> str:
        """Derive the session file path from the vault file path."""
        return self.vault_file + ".session"

    def _ensure_unsealed(self) -> bytes:
        """Load the root key from the session file.

        Returns:
            The root key bytes.

        Raises:
            VaultError: If the vault is sealed (no session file).
        """
        root_key = storage.load_session(self._session_file())
        if root_key is None:
            raise VaultError("Vault is sealed")
        return root_key

    # -- Seal/Unseal Lifecycle --

    def init_vault(self, password: str) -> str:
        """Create a new vault file with the given master password.

        Generates a PBKDF2 salt, derives the root key, creates a verification
        token, saves an empty vault structure, and logs the init event.
        The vault is left in the sealed state after initialization.

        Args:
            password: The master password for the vault.

        Returns:
            Success message string.

        Raises:
            VaultError: If vault file already exists or password is empty.
        """
        # Fulfills: REQ-SEAL-001, REQ-SEAL-002, REQ-SEAL-003
        if not password:
            raise VaultError("Master password must not be empty")
        if storage.vault_file_exists(self.vault_file):
            raise VaultError(f"Vault file already exists at {self.vault_file}")

        salt = crypto.generate_salt()
        iterations = 600000
        root_key = crypto.derive_root_key(password, salt, iterations)

        # Create verification token for password validation on unseal
        verification_plaintext = b"vault-verification-token"
        v_nonce, v_ciphertext = crypto.encrypt_aes_gcm(root_key, verification_plaintext)

        vault_data = {
            "salt": salt,
            "iterations": iterations,
            "verification_nonce": v_nonce,
            "verification_token": v_ciphertext,
            "secrets": {},
            "policies": [],
        }

        storage.save_vault(vault_data, self.vault_file)
        # Ensure sealed state after init
        storage.delete_session(self._session_file())
        audit.log_event(self.audit_file, "system", "init", None, "success")
        return f"Vault initialized at {self.vault_file}"

    def unseal(self, password: str) -> str:
        """Unseal the vault with the given master password.

        Loads vault data, derives the root key, verifies it against the
        stored verification token, and saves the root key to the session file.

        Args:
            password: The master password.

        Returns:
            Success message string.

        Raises:
            VaultError: If vault not found, already unsealed, or wrong password.
        """
        # Fulfills: REQ-SEAL-004, REQ-SEAL-005
        if not storage.vault_file_exists(self.vault_file):
            raise VaultError(f"Vault file not found at {self.vault_file}")

        vault_data = storage.load_vault(self.vault_file)
        salt = vault_data["salt"]
        iterations = vault_data["iterations"]
        root_key = crypto.derive_root_key(password, salt, iterations)

        # Verify the derived root key by decrypting the verification token
        try:
            crypto.decrypt_aes_gcm(
                root_key,
                vault_data["verification_nonce"],
                vault_data["verification_token"],
            )
        except crypto.DecryptionError:
            audit.log_event(
                self.audit_file, "system", "unseal", None, "error",
                "Incorrect master password",
            )
            raise VaultError("Incorrect master password")

        storage.save_session(self._session_file(), root_key)
        audit.log_event(self.audit_file, "system", "unseal", None, "success")
        return "Vault unsealed successfully."

    def seal(self) -> str:
        """Seal the vault by discarding the root key from the session file.

        Returns:
            Success message string.

        Raises:
            VaultError: If the vault is already sealed.
        """
        # Fulfills: REQ-SEAL-006
        root_key = storage.load_session(self._session_file())
        if root_key is None:
            raise VaultError("Vault is already sealed")

        storage.delete_session(self._session_file())
        audit.log_event(self.audit_file, "system", "seal", None, "success")
        return "Vault sealed."

    def status(self) -> str:
        """Return 'sealed' or 'unsealed' based on session file existence.

        Returns:
            The string 'sealed' or 'unsealed'.

        Raises:
            VaultError: If the vault file does not exist.
        """
        # Fulfills: REQ-SEAL-008
        if not storage.vault_file_exists(self.vault_file):
            raise VaultError(f"Vault file not found at {self.vault_file}")

        root_key = storage.load_session(self._session_file())
        if root_key is not None:
            return "unsealed"
        return "sealed"

    # -- Policy Management --

    def add_policy(self, identity: str, path_pattern: str, capabilities: list[str]) -> str:
        """Add an access control policy.

        Args:
            identity: The identity string the policy applies to.
            path_pattern: The path pattern with optional glob wildcards.
            capabilities: List of capabilities (read, write, list, delete).

        Returns:
            Success message string.

        Raises:
            VaultError: If sealed, capabilities empty, or invalid capability.
        """
        # Fulfills: REQ-ACL-001, REQ-ACL-008
        self._ensure_unsealed()

        if not capabilities:
            raise VaultError("At least one capability must be specified")

        invalid = policy.validate_capabilities(capabilities)
        if invalid is not None:
            raise VaultError(
                f"Invalid capability '{invalid}'. Valid capabilities: read, write, list, delete"
            )

        vault_data = storage.load_vault(self.vault_file)
        new_policy = {
            "identity": identity,
            "path_pattern": path_pattern,
            "capabilities": capabilities,
        }
        vault_data["policies"].append(new_policy)
        storage.save_vault(vault_data, self.vault_file)

        caps_str = ", ".join(capabilities)
        audit.log_event(
            self.audit_file, "system", "add-policy", None, "success",
            f"identity='{identity}', path='{path_pattern}'",
        )
        return f"Policy added: identity='{identity}', path='{path_pattern}', capabilities=[{caps_str}]"

    def remove_policy(self, identity: str, path_pattern: str) -> str:
        """Remove a policy matching the identity and path pattern.

        Args:
            identity: The identity string of the policy to remove.
            path_pattern: The path pattern of the policy to remove.

        Returns:
            Success message string.

        Raises:
            VaultError: If sealed or policy not found.
        """
        # Fulfills: REQ-ACL-009
        self._ensure_unsealed()

        vault_data = storage.load_vault(self.vault_file)
        found = False
        for i, pol in enumerate(vault_data["policies"]):
            if pol["identity"] == identity and pol["path_pattern"] == path_pattern:
                vault_data["policies"].pop(i)
                found = True
                break

        if not found:
            raise VaultError(
                f"No policy found for identity '{identity}' on path '{path_pattern}'"
            )

        storage.save_vault(vault_data, self.vault_file)
        audit.log_event(
            self.audit_file, "system", "remove-policy", None, "success",
            f"identity='{identity}', path='{path_pattern}'",
        )
        return f"Policy removed: identity='{identity}', path='{path_pattern}'"

    # -- Secret CRUD Operations --

    def put_secret(self, path: str, value: str, identity: str) -> str:
        """Store or update a secret at the given path.

        Performs envelope encryption: generates a DEK, encrypts the value
        with the DEK, encrypts the DEK with the root key.

        Args:
            path: The hierarchical secret path.
            value: The secret value string.
            identity: The caller's identity for access control.

        Returns:
            Success message with version number.

        Raises:
            VaultError: If sealed, access denied, invalid path, or empty value.
        """
        # Fulfills: REQ-ENC-001, REQ-ENC-002, REQ-ENC-003, REQ-ENC-006,
        #           REQ-CRUD-001, REQ-CRUD-003, REQ-VER-001, REQ-VER-002
        root_key = self._ensure_unsealed()

        if not policy.validate_path(path):
            raise VaultError(f"Invalid path format: '{path}'")

        if not value:
            raise VaultError("Secret value must not be empty")

        vault_data = storage.load_vault(self.vault_file)

        # Check access control (write capability required)
        if not policy.check_access(vault_data["policies"], identity, path, "write"):
            audit.log_event(self.audit_file, identity, "store", path, "denied", "requires write")
            raise VaultError(
                f"Access denied for identity '{identity}' on path '{path}' (requires write)"
            )

        # Envelope encryption: generate DEK, encrypt value, encrypt DEK
        dek = crypto.generate_dek()
        value_nonce, encrypted_value = crypto.encrypt_aes_gcm(dek, value.encode("utf-8"))
        dek_nonce, encrypted_dek = crypto.encrypt_aes_gcm(root_key, dek)

        version_dict = {
            "version_number": 1,
            "encrypted_dek": encrypted_dek,
            "dek_nonce": dek_nonce,
            "encrypted_value": encrypted_value,
            "value_nonce": value_nonce,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if path in vault_data["secrets"]:
            # Update existing secret with new version
            versions = vault_data["secrets"][path]["versions"]
            next_version = len(versions) + 1
            version_dict["version_number"] = next_version
            versions.append(version_dict)
            operation = "update"
        else:
            # Store new secret
            vault_data["secrets"][path] = {
                "path": path,
                "versions": [version_dict],
            }
            next_version = 1
            operation = "store"

        storage.save_vault(vault_data, self.vault_file)
        audit.log_event(self.audit_file, identity, operation, path, "success")

        if operation == "store":
            return f"Secret stored at {path} (version 1)"
        return f"Secret updated at {path} (version {next_version})"

    def get_secret(self, path: str, identity: str, version: int | None = None) -> dict:
        """Retrieve a secret at the given path, optionally a specific version.

        Performs envelope decryption: decrypts the DEK with the root key,
        then decrypts the secret value with the DEK.

        Args:
            path: The secret path.
            identity: The caller's identity for access control.
            version: Optional specific version number to retrieve.

        Returns:
            Dict with keys: 'path', 'version', 'value'.

        Raises:
            VaultError: If sealed, access denied, not found, or version not found.
        """
        # Fulfills: REQ-ENC-005, REQ-CRUD-002, REQ-CRUD-006,
        #           REQ-VER-003, REQ-VER-004, REQ-VER-005, REQ-VER-006
        root_key = self._ensure_unsealed()

        vault_data = storage.load_vault(self.vault_file)

        # Check access control (read capability required)
        if not policy.check_access(vault_data["policies"], identity, path, "read"):
            audit.log_event(self.audit_file, identity, "retrieve", path, "denied", "requires read")
            raise VaultError(
                f"Access denied for identity '{identity}' on path '{path}' (requires read)"
            )

        if path not in vault_data["secrets"]:
            raise VaultError(f"Secret not found at path '{path}'")

        versions = vault_data["secrets"][path]["versions"]

        if version is None:
            # Return the latest version (highest version_number)
            selected = versions[-1]
        else:
            # Find the specified version
            selected = None
            for v in versions:
                if v["version_number"] == version:
                    selected = v
                    break
            if selected is None:
                raise VaultError(f"Version {version} not found for path '{path}'")

        # Envelope decryption: decrypt DEK, then decrypt value
        dek = crypto.decrypt_aes_gcm(root_key, selected["dek_nonce"], selected["encrypted_dek"])
        plaintext = crypto.decrypt_aes_gcm(dek, selected["value_nonce"], selected["encrypted_value"])

        audit.log_event(self.audit_file, identity, "retrieve", path, "success")
        return {
            "path": path,
            "version": selected["version_number"],
            "value": plaintext.decode("utf-8"),
        }

    def delete_secret(self, path: str, identity: str) -> str:
        """Delete a secret and all its versions at the given path.

        Args:
            path: The secret path.
            identity: The caller's identity for access control.

        Returns:
            Success message string.

        Raises:
            VaultError: If sealed, access denied, or not found.
        """
        # Fulfills: REQ-CRUD-004, REQ-CRUD-006
        self._ensure_unsealed()

        vault_data = storage.load_vault(self.vault_file)

        # Check access control (delete capability required)
        if not policy.check_access(vault_data["policies"], identity, path, "delete"):
            audit.log_event(self.audit_file, identity, "delete", path, "denied", "requires delete")
            raise VaultError(
                f"Access denied for identity '{identity}' on path '{path}' (requires delete)"
            )

        if path not in vault_data["secrets"]:
            raise VaultError(f"Secret not found at path '{path}'")

        del vault_data["secrets"][path]
        storage.save_vault(vault_data, self.vault_file)
        audit.log_event(self.audit_file, identity, "delete", path, "success")
        return f"Secret deleted at {path}"

    def list_secrets(self, identity: str, prefix: str = "") -> list[str]:
        """List all secret paths matching the given prefix.

        Args:
            identity: The caller's identity for access control.
            prefix: Path prefix to filter by. Empty string returns all paths.

        Returns:
            Sorted list of matching path strings (may be empty).

        Raises:
            VaultError: If sealed or access denied.
        """
        # Fulfills: REQ-CRUD-005
        self._ensure_unsealed()

        vault_data = storage.load_vault(self.vault_file)

        # Check access control (list capability on the prefix)
        check_path = prefix if prefix else ""
        if not policy.check_access(vault_data["policies"], identity, check_path, "list"):
            audit.log_event(
                self.audit_file, identity, "list", prefix or "-", "denied", "requires list",
            )
            raise VaultError(
                f"Access denied for identity '{identity}' on path '{prefix}' (requires list)"
            )

        # Collect paths matching the prefix
        matching = []
        for secret_path in vault_data["secrets"]:
            if prefix == "" or secret_path.startswith(prefix):
                matching.append(secret_path)

        matching.sort()
        audit.log_event(self.audit_file, identity, "list", prefix or "-", "success")
        return matching

    # -- Audit Log --

    def get_audit_log(self, last_n: int | None = None) -> list[str]:
        """Read and return audit log entries.

        Args:
            last_n: If specified, return only the last N entries.

        Returns:
            List of formatted audit log lines.

        Raises:
            VaultError: If the audit file is not found.
        """
        try:
            return audit.read_log(self.audit_file, last_n)
        except FileNotFoundError:
            raise VaultError(f"Audit log file not found at {self.audit_file}")
