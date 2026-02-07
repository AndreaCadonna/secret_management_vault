# audit.py -- Append-only audit logger for the Secret Management Vault.
# Implements DESIGN.md Component 3.4: structured audit log entries with
# pipe-separated fields and append-only file semantics.
# Fulfills: REQ-AUD-001, REQ-AUD-002, REQ-AUD-003, REQ-AUD-004, REQ-AUD-005

import datetime
from pathlib import Path


def log_event(
    audit_file: str,
    identity: str,
    operation: str,
    path: str | None,
    outcome: str,
    detail: str | None = None,
) -> None:
    """Append a single audit log entry to the audit file.

    Each entry is one line of pipe-separated fields:
    timestamp | identity | operation | path_or_dash | outcome [| detail]

    Args:
        audit_file: Path to the audit log file.
        identity: The caller identity (or "system" for lifecycle operations).
        operation: The operation type (init, seal, unseal, store, retrieve, etc.).
        path: The target secret path, or None for non-path operations.
        outcome: The outcome (success, denied, or error).
        detail: Optional additional context string.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    path_str = path if path else "-"
    line = f"{timestamp} | {identity} | {operation} | {path_str} | {outcome}"
    if detail:
        line += f" | {detail}"
    with open(audit_file, "a") as f:
        f.write(line + "\n")


def read_log(audit_file: str, last_n: int | None = None) -> list[str]:
    """Read all log entries from the audit file.

    Args:
        audit_file: Path to the audit log file.
        last_n: If specified, return only the last N entries.

    Returns:
        List of raw line strings (one per entry).

    Raises:
        FileNotFoundError: If the audit file does not exist.
    """
    if not Path(audit_file).exists():
        raise FileNotFoundError(f"Audit log file not found at {audit_file}")
    with open(audit_file, "r") as f:
        lines = [line.rstrip() for line in f if line.strip()]
    if last_n is not None and last_n > 0:
        lines = lines[-last_n:]
    return lines


def format_entry(entry_line: str) -> str:
    """Format a raw log line for display.

    The pipe-separated format is already human-readable, so this passes
    through unchanged.

    Args:
        entry_line: A raw audit log line.

    Returns:
        The formatted line (unchanged).
    """
    return entry_line
