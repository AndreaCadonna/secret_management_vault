# policy.py -- Access control policy engine for the Secret Management Vault.
# Implements DESIGN.md Component 3.3: path validation, glob pattern matching,
# and policy evaluation with default-deny semantics.
# Fulfills: REQ-ACL-001, REQ-ACL-002, REQ-ACL-003, REQ-ACL-004, REQ-ACL-005,
#           REQ-ACL-006, REQ-CRUD-007

import re

VALID_CAPABILITIES: list[str] = ["read", "write", "list", "delete"]


def validate_path(path: str) -> bool:
    """Return True if path is valid per SPEC.md Section 4.2.

    A valid path consists of alphanumeric characters, hyphens, underscores,
    and forward slashes, with no leading/trailing slashes, no consecutive
    slashes, and no empty segments.

    Args:
        path: The secret path to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not path:
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*", path))


def validate_capabilities(capabilities: list[str]) -> str | None:
    """Return the first invalid capability name, or None if all are valid.

    Args:
        capabilities: List of capability strings to validate.

    Returns:
        The first invalid capability string, or None if all are valid.
    """
    for cap in capabilities:
        if cap not in VALID_CAPABILITIES:
            return cap
    return None


def match_path_pattern(pattern: str, path: str) -> bool:
    """Return True if the path matches the glob pattern.

    Wildcard semantics:
    - '*' matches any characters within a single path segment (no slashes).
    - '**' matches any characters across multiple segments (including slashes).

    Args:
        pattern: The glob pattern (e.g., "prod/*/pass", "**", "app-a/**").
        path: The actual secret path to match against.

    Returns:
        True if the path matches the pattern.
    """
    # Special case: "**" matches everything including empty string
    if pattern == "**":
        return True

    # Split pattern on "**" to handle multi-segment wildcards first
    parts = pattern.split("**")

    # For each part, handle single "*" wildcards within segments
    regex_parts = []
    for part in parts:
        # Split on single "*", escape literal parts, join with [^/]* (single-segment match)
        segments = part.split("*")
        escaped_segments = [re.escape(seg) for seg in segments]
        regex_parts.append("[^/]*".join(escaped_segments))

    # Join the "**"-separated parts with ".*" (match anything including slashes)
    full_regex = ".*".join(regex_parts)

    return bool(re.fullmatch(full_regex, path))


def check_access(
    policies: list[dict],
    identity: str,
    path: str,
    capability: str,
) -> bool:
    """Return True if at least one policy grants the capability to the identity on the path.

    Default deny: returns False if no policy grants access.

    Args:
        policies: List of policy dicts with keys: identity, path_pattern, capabilities.
        identity: The caller's identity string.
        path: The target secret path.
        capability: The required capability (read, write, list, or delete).

    Returns:
        True if access is granted, False otherwise.
    """
    for pol in policies:
        if pol["identity"] == identity and capability in pol["capabilities"]:
            if match_path_pattern(pol["path_pattern"], path):
                return True
    return False
