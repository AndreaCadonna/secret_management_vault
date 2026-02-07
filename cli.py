# cli.py -- Command-line interface for the Secret Management Vault.
# Implements DESIGN.md Component 3.6: thin CLI wrapper that parses arguments,
# dispatches to Vault methods, and formats output.
# Fulfills: REQ-CLI-001 through REQ-CLI-006

import argparse
import getpass
import sys

from vault import Vault, VaultError


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argparse parser with all subcommands.

    Subcommands: init, unseal, seal, status, put, get, delete, list,
    add-policy, remove-policy, audit-log.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="vault",
        description="Secret Management Vault",
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- init --
    p_init = subparsers.add_parser("init", help="Initialize a new vault")
    p_init.add_argument("--vault-file", default="vault.enc")
    p_init.add_argument("--audit-file", default="audit.log")
    p_init.add_argument("--password", default=None)

    # -- unseal --
    p_unseal = subparsers.add_parser("unseal", help="Unseal the vault")
    p_unseal.add_argument("--vault-file", default="vault.enc")
    p_unseal.add_argument("--audit-file", default="audit.log")
    p_unseal.add_argument("--password", default=None)

    # -- seal --
    p_seal = subparsers.add_parser("seal", help="Seal the vault")
    p_seal.add_argument("--vault-file", default="vault.enc")
    p_seal.add_argument("--audit-file", default="audit.log")

    # -- status --
    p_status = subparsers.add_parser("status", help="Show vault status")
    p_status.add_argument("--vault-file", default="vault.enc")

    # -- put --
    p_put = subparsers.add_parser("put", help="Store or update a secret")
    p_put.add_argument("path", help="Secret path (e.g., production/db/password)")
    p_put.add_argument("value", help="Secret value")
    p_put.add_argument("--identity", required=True)
    p_put.add_argument("--vault-file", default="vault.enc")
    p_put.add_argument("--audit-file", default="audit.log")

    # -- get --
    p_get = subparsers.add_parser("get", help="Retrieve a secret")
    p_get.add_argument("path", help="Secret path")
    p_get.add_argument("--identity", required=True)
    p_get.add_argument("--version", type=int, default=None)
    p_get.add_argument("--vault-file", default="vault.enc")
    p_get.add_argument("--audit-file", default="audit.log")

    # -- delete --
    p_delete = subparsers.add_parser("delete", help="Delete a secret")
    p_delete.add_argument("path", help="Secret path")
    p_delete.add_argument("--identity", required=True)
    p_delete.add_argument("--vault-file", default="vault.enc")
    p_delete.add_argument("--audit-file", default="audit.log")

    # -- list --
    p_list = subparsers.add_parser("list", help="List secrets by prefix")
    p_list.add_argument("prefix", nargs="?", default="", help="Path prefix filter")
    p_list.add_argument("--identity", required=True)
    p_list.add_argument("--vault-file", default="vault.enc")
    p_list.add_argument("--audit-file", default="audit.log")

    # -- add-policy --
    p_add_pol = subparsers.add_parser("add-policy", help="Add an access control policy")
    p_add_pol.add_argument("--identity", required=True)
    p_add_pol.add_argument("--path-pattern", required=True)
    p_add_pol.add_argument("--capabilities", required=True, help="Comma-separated capabilities")
    p_add_pol.add_argument("--vault-file", default="vault.enc")
    p_add_pol.add_argument("--audit-file", default="audit.log")

    # -- remove-policy --
    p_rm_pol = subparsers.add_parser("remove-policy", help="Remove an access control policy")
    p_rm_pol.add_argument("--identity", required=True)
    p_rm_pol.add_argument("--path-pattern", required=True)
    p_rm_pol.add_argument("--vault-file", default="vault.enc")
    p_rm_pol.add_argument("--audit-file", default="audit.log")

    # -- audit-log --
    p_audit = subparsers.add_parser("audit-log", help="View audit log entries")
    p_audit.add_argument("--audit-file", default="audit.log")
    p_audit.add_argument("--last", type=int, default=None)

    return parser


def main() -> None:
    """Entry point. Parse arguments, dispatch to Vault methods, format output."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "init":
            password = args.password
            if password is None:
                password = getpass.getpass("Master password: ")
            v = Vault(args.vault_file, args.audit_file)
            print(v.init_vault(password))

        elif args.command == "unseal":
            password = args.password
            if password is None:
                password = getpass.getpass("Master password: ")
            v = Vault(args.vault_file, args.audit_file)
            print(v.unseal(password))

        elif args.command == "seal":
            v = Vault(args.vault_file, args.audit_file)
            print(v.seal())

        elif args.command == "status":
            v = Vault(args.vault_file)
            result = v.status()
            print(f"Status: {result}")

        elif args.command == "put":
            v = Vault(args.vault_file, args.audit_file)
            print(v.put_secret(args.path, args.value, args.identity))

        elif args.command == "get":
            v = Vault(args.vault_file, args.audit_file)
            r = v.get_secret(args.path, args.identity, args.version)
            print(f"Path: {r['path']}")
            print(f"Version: {r['version']}")
            print(f"Value: {r['value']}")

        elif args.command == "delete":
            v = Vault(args.vault_file, args.audit_file)
            print(v.delete_secret(args.path, args.identity))

        elif args.command == "list":
            v = Vault(args.vault_file, args.audit_file)
            paths = v.list_secrets(args.identity, args.prefix)
            if not paths:
                print("No secrets found.")
            else:
                for p in paths:
                    print(p)

        elif args.command == "add-policy":
            caps = [c.strip() for c in args.capabilities.split(",")]
            v = Vault(args.vault_file, args.audit_file)
            print(v.add_policy(args.identity, args.path_pattern, caps))

        elif args.command == "remove-policy":
            v = Vault(args.vault_file, args.audit_file)
            print(v.remove_policy(args.identity, args.path_pattern))

        elif args.command == "audit-log":
            v = Vault(audit_file=args.audit_file)
            lines = v.get_audit_log(args.last)
            for line in lines:
                print(line)

    except VaultError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
