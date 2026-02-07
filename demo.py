# demo.py - Narrated demonstration of the Secret Management Vault
# Uses fresh data different from the validation suite
import os
import subprocess
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(ROOT, "cli.py")


def run(args, expect_fail=False):
    cmd_str = "python cli.py " + " ".join(args)
    print("  $ %s" % cmd_str)
    r = subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True, text=True, cwd=ROOT
    )
    if r.stdout.strip():
        print("  %s" % r.stdout.strip())
    if r.stderr.strip():
        print("  %s" % r.stderr.strip())
    print()
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def banner(text):
    print()
    print("-" * 60)
    print("  %s" % text)
    print("-" * 60)
    print()


def main():
    tmpdir = tempfile.mkdtemp(prefix="demo_")
    vf = os.path.join(tmpdir, "demo_vault.enc")
    af = os.path.join(tmpdir, "demo_audit.log")

    def vargs():
        return ["--vault-file", vf, "--audit-file", af]

    try:
        print("=" * 60)
        print("  SECRET MANAGEMENT VAULT -- DEMONSTRATION")
        print("=" * 60)
        print()
        print("  This demo shows how a local secret management vault")
        print("  protects sensitive data using two layers of encryption,")
        print("  controls access with path-based policies, and records")
        print("  every operation in an audit log.")
        print()
        print("  The core idea: each piece of data gets its own unique")
        print("  key (DEK). All those keys are locked under a single")
        print("  master key derived from your chosen phrase. If someone")
        print("  steals the file, they see only scrambled data.")

        # --- Act 1: Initialize ---
        banner("ACT 1: Creating a new vault")
        print("  First, we create a new vault with a master phrase.")
        print("  This generates a salt, derives the master key using")
        print("  PBKDF2 (600,000 rounds), and saves an empty vault.")
        print()
        run(["init"] + vargs() + ["--password", "DemoMasterPhrase2026"])

        # --- Act 2: Unseal ---
        banner("ACT 2: Unsealing the vault")
        print("  The vault starts locked (sealed). We must unseal it")
        print("  by providing the correct phrase. The master key is")
        print("  re-derived and held in memory for operations.")
        print()
        run(["unseal"] + vargs() + ["--password", "DemoMasterPhrase2026"])
        run(["status"] + ["--vault-file", vf])

        # --- Act 3: Policies ---
        banner("ACT 3: Setting up access control policies")
        print("  Before storing data, we define who can do what.")
        print("  We create an 'ops-team' identity with full access,")
        print("  and a 'web-app' identity that can only read from")
        print("  'services/web/**'.")
        print()
        run(["add-policy", "--identity", "ops-team",
             "--path-pattern", "**",
             "--capabilities", "read,write,list,delete"] + vargs())
        run(["add-policy", "--identity", "web-app",
             "--path-pattern", "services/web/**",
             "--capabilities", "read"] + vargs())

        # --- Act 4: Storing secrets ---
        banner("ACT 4: Storing secrets with envelope encryption")
        print("  Each item gets its own random key (DEK), the data is")
        print("  encrypted with that key, then the DEK itself is")
        print("  encrypted with the master key. Two layers of protection.")
        print()
        run(["put", "services/web/db-conn",
             "host=db.example.com;user=webapp;port=5432",
             "--identity", "ops-team"] + vargs())
        run(["put", "services/web/api-token",
             "tok_demo_abc123xyz789",
             "--identity", "ops-team"] + vargs())
        run(["put", "services/backend/queue-creds",
             "amqp://user:pass@mq.internal:5672",
             "--identity", "ops-team"] + vargs())

        # --- Act 5: Retrieving secrets ---
        banner("ACT 5: Retrieving secrets")
        print("  The vault decrypts the DEK with the master key,")
        print("  then decrypts the data with the DEK. The original")
        print("  plaintext is returned.")
        print()
        run(["get", "services/web/db-conn",
             "--identity", "ops-team"] + vargs())

        # --- Act 6: Access control in action ---
        banner("ACT 6: Access control enforcement")
        print("  The 'web-app' identity can read from services/web/**")
        print("  but NOT from services/backend/**. Let us see both.")
        print()
        print("  Allowed read:")
        run(["get", "services/web/api-token",
             "--identity", "web-app"] + vargs())
        print("  Denied read (different path scope):")
        run(["get", "services/backend/queue-creds",
             "--identity", "web-app"] + vargs(), expect_fail=True)

        # --- Act 7: Versioning ---
        banner("ACT 7: Secret rotation with versioning")
        print("  When we update a value, the old version is kept.")
        print("  This supports rotation: deploy the new credential,")
        print("  then retire the old one.")
        print()
        run(["put", "services/web/api-token",
             "tok_demo_ROTATED_2026",
             "--identity", "ops-team"] + vargs())
        print("  Latest version:")
        run(["get", "services/web/api-token",
             "--identity", "ops-team"] + vargs())
        print("  Previous version (v1):")
        run(["get", "services/web/api-token",
             "--identity", "ops-team", "--version", "1"] + vargs())

        # --- Act 8: Listing ---
        banner("ACT 8: Listing secrets by path prefix")
        run(["list", "services/web",
             "--identity", "ops-team"] + vargs())

        # --- Act 9: Audit log ---
        banner("ACT 9: Reviewing the audit trail")
        print("  Every operation -- successful or denied -- is logged")
        print("  with timestamp, identity, operation, path, and outcome.")
        print()
        run(["audit-log"] + ["--audit-file", af])

        # --- Act 10: Seal ---
        banner("ACT 10: Sealing the vault")
        print("  Sealing discards the master key from memory.")
        print("  No operations are possible until the next unseal.")
        print()
        run(["seal"] + vargs())
        run(["status"] + ["--vault-file", vf])
        print("  Attempting to read while sealed:")
        run(["get", "services/web/db-conn",
             "--identity", "ops-team"] + vargs(), expect_fail=True)

        print("=" * 60)
        print("  DEMONSTRATION COMPLETE")
        print()
        print("  This demo showed the core principle: envelope encryption")
        print("  with a two-layer key hierarchy, mediated by path-based")
        print("  access control and recorded in an append-only audit log.")
        print("=" * 60)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
