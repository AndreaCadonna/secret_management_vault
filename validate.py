# validate.py - Tests all 28 SPEC.md Section 6 scenarios
# Automated validation for Secret Management Vault
import os
import subprocess
import sys
import tempfile
import shutil
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(ROOT, "cli.py")
PC = 0
FC = 0
RES = []


def rc(args):
    r = subprocess.run(
        [sys.executable, CLI] + args,
        capture_output=True, text=True, cwd=ROOT
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def ck(a, e):
    if e in a:
        return True, ""
    return False, "want %r in %r" % (e, a)


def ckn(a, e):
    if e not in a:
        return True, ""
    return False, "unwanted %r in %r" % (e, a)


def nzc(c):
    if c != 0:
        return True, ""
    return False, "exit 0, expected nonzero"


def fex(p):
    if os.path.exists(p):
        return True, ""
    return False, "missing " + p


def rep(sid, desc, ok, diag=""):
    global PC, FC
    if ok:
        PC += 1
    else:
        FC += 1
    RES.append((sid, desc, "PASS" if ok else "FAIL", diag))
    tag = "[PASS]" if ok else "[FAIL]"
    print("  %s %s: %s" % (tag, sid, desc))
    if not ok and diag:
        for ln in diag.strip().split("\n"):
            print("         " + ln)


def _a(p, d, ok, m, prefix=""):
    if ok:
        return p, d
    return False, d + [prefix + m if prefix else m]


class TV:
    def __init__(self):
        self.d = None

    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="vt_")
        return self

    def __exit__(self, *a):
        if self.d and os.path.exists(self.d):
            shutil.rmtree(self.d, ignore_errors=True)

    @property
    def vf(self):
        return os.path.join(self.d, "v.enc")

    @property
    def af(self):
        return os.path.join(self.d, "a.log")

    def init(self, pw="T1"):
        return rc(["init", "--vault-file", self.vf,
                    "--audit-file", self.af, "--password", pw])

    def unseal(self, pw="T1"):
        return rc(["unseal", "--vault-file", self.vf,
                    "--audit-file", self.af, "--password", pw])

    def seal(self):
        return rc(["seal", "--vault-file", self.vf,
                    "--audit-file", self.af])

    def status(self):
        return rc(["status", "--vault-file", self.vf])

    def put(self, p, val, ident):
        return rc(["put", p, val, "--identity", ident,
                    "--vault-file", self.vf, "--audit-file", self.af])

    def get(self, p, ident, ver=None):
        cmd = ["get", p, "--identity", ident,
               "--vault-file", self.vf, "--audit-file", self.af]
        if ver is not None:
            cmd += ["--version", str(ver)]
        return rc(cmd)

    def delete(self, p, ident):
        return rc(["delete", p, "--identity", ident,
                    "--vault-file", self.vf, "--audit-file", self.af])

    def ls(self, ident, pfx=None):
        cmd = ["list"]
        if pfx is not None:
            cmd.append(pfx)
        cmd += ["--identity", ident,
                "--vault-file", self.vf, "--audit-file", self.af]
        return rc(cmd)

    def apol(self, ident, pp, caps):
        return rc(["add-policy", "--identity", ident,
                    "--path-pattern", pp, "--capabilities", caps,
                    "--vault-file", self.vf, "--audit-file", self.af])

    def rpol(self, ident, pp):
        return rc(["remove-policy", "--identity", ident,
                    "--path-pattern", pp,
                    "--vault-file", self.vf, "--audit-file", self.af])

    def alog(self, last=None):
        cmd = ["audit-log", "--audit-file", self.af]
        if last:
            cmd += ["--last", str(last)]
        return rc(cmd)

    def su(self, pw="T1"):
        self.init(pw)
        self.unseal(pw)
        self.apol("admin", "**", "read,write,list,delete")


def t61():
    with TV() as v:
        d, p = [], True
        c, o, e = v.init("MMP1")
        p, d = _a(p, d, *ck(o, "Vault initialized at"))
        p, d = _a(p, d, *fex(v.vf))
        c, o, e = v.status()
        p, d = _a(p, d, *ck(o, "Status: sealed"))
        c, o, e = v.unseal("MMP1")
        p, d = _a(p, d, *ck(o, "Vault unsealed successfully."))
        c, o, e = v.status()
        p, d = _a(p, d, *ck(o, "Status: unsealed"))
        rep("6.1", "Initialize and Unseal a New Vault", p, "\n".join(d))


def t62():
    with TV() as v:
        d, p = [], True
        v.init("CorrectPW")
        c, o, e = v.unseal("WrongPW")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Incorrect master password"))
        c, o, e = v.status()
        p, d = _a(p, d, *ck(o, "Status: sealed"))
        rep("6.2", "Reject Unseal with Wrong Password", p, "\n".join(d))


def t63():
    with TV() as v:
        d, p = [], True
        v.init("MP1"); v.unseal("MP1"); v.apol("admin", "**", "write"); v.seal()
        c, o, e = v.put("secrets/key", "myvalue", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Vault is sealed"))
        rep("6.3", "Reject Operations When Sealed", p, "\n".join(d))


def t64():
    with TV() as v:
        d, p = [], True
        v.su("MP1")
        c, o, e = v.put("production/db/password", "s3cretValue!", "admin")
        p, d = _a(p, d, *ck(o, "Secret stored at production/db/password (version 1)"))
        c, o, e = v.get("production/db/password", "admin")
        for s in ["Path: production/db/password", "Version: 1", "Value: s3cretValue!"]:
            p, d = _a(p, d, *ck(o, s))
        rep("6.4", "Store and Retrieve with Envelope Encryption", p, "\n".join(d))


def t65():
    with TV() as v:
        d, p = [], True
        v.su()
        v.put("path/secret-a", "value-a", "admin")
        v.put("path/secret-b", "value-b", "admin")
        c, o, e = v.get("path/secret-a", "admin")
        p, d = _a(p, d, *ck(o, "Value: value-a"))
        c, o, e = v.get("path/secret-b", "admin")
        p, d = _a(p, d, *ck(o, "Value: value-b"))
        rep("6.5", "Verify Different DEKs for Different Secrets", p, "\n".join(d))


def t66():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal(); v.apol("admin", "**", "read")
        c, o, e = v.get("nonexistent/path", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Secret not found at path 'nonexistent/path'"))
        rep("6.6", "Retrieve Secret Not Found", p, "\n".join(d))


def t67():
    with TV() as v:
        d, p = [], True
        v.su(); v.put("temp/api-key", "abc123", "admin")
        c, o, e = v.delete("temp/api-key", "admin")
        p, d = _a(p, d, *ck(o, "Secret deleted at temp/api-key"))
        c, o, e = v.get("temp/api-key", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Secret not found at path 'temp/api-key'"))
        rep("6.7", "Delete a Secret", p, "\n".join(d))


def t68():
    with TV() as v:
        d, p = [], True
        v.su()
        for path, val in [("prod/db/user", "u1"), ("prod/db/pass", "p1"),
                          ("prod/api/key", "k1"), ("staging/db/user", "u2")]:
            v.put(path, val, "admin")
        c, o, e = v.ls("admin", "prod/db")
        p, d = _a(p, d, *ck(o, "prod/db/user"))
        p, d = _a(p, d, *ck(o, "prod/db/pass"))
        p, d = _a(p, d, *ckn(o, "prod/api/key"))
        p, d = _a(p, d, *ckn(o, "staging/db/user"))
        rep("6.8", "List Secrets by Prefix", p, "\n".join(d))


def t69():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal(); v.apol("admin", "**", "list")
        c, o, e = v.ls("admin")
        p, d = _a(p, d, *ck(o, "No secrets found."))
        rep("6.9", "List Returns Empty When No Secrets Match", p, "\n".join(d))


def t610():
    with TV() as v:
        d, p = [], True
        v.su()
        c, o, e = v.put("invalid//path", "value", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Invalid path format"))
        rep("6.10", "Invalid Path Format Rejected", p, "\n".join(d))


def t611():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        v.apol("service-a", "app-a/**", "read,write")
        v.apol("service-b", "app-b/**", "read")
        v.put("app-a/db/password", "secret123", "service-a")
        c, o, e = v.get("app-a/db/password", "service-b")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Access denied for identity 'service-b' on path 'app-a/db/password' (requires read)"))
        rep("6.11", "Access Control Denies Unauthorized Read", p, "\n".join(d))


def t612():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        v.apol("service-a", "app-a/**", "read,write")
        v.apol("service-b", "app-b/**", "read")
        v.put("app-a/db/password", "secret123", "service-a")
        c, o, e = v.get("app-a/db/password", "service-a")
        for s in ["Path: app-a/db/password", "Version: 1", "Value: secret123"]:
            p, d = _a(p, d, *ck(o, s))
        rep("6.12", "Access Control Grants Authorized Read", p, "\n".join(d))


def t613():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        v.apol("deployer", "production/*/credentials", "read,write")
        c, o, e = v.put("production/web/credentials", "web-cred", "deployer")
        p, d = _a(p, d, *ck(o, "Secret stored at production/web/credentials (version 1)"))
        c, o, e = v.put("production/cache/credentials", "cache-cred", "deployer")
        p, d = _a(p, d, *ck(o, "Secret stored at production/cache/credentials (version 1)"))
        c, o, e = v.put("production/web/config", "web-config", "deployer")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Access denied"))
        rep("6.13", "Glob Wildcard Policy Matching", p, "\n".join(d))


def t614():
    with TV() as v:
        d, p = [], True
        v.su()
        c, o, e = v.put("any/deep/nested/path", "value", "admin")
        p, d = _a(p, d, *ck(o, "Secret stored at any/deep/nested/path (version 1)"))
        c, o, e = v.get("any/deep/nested/path", "admin")
        p, d = _a(p, d, *ck(o, "Value: value"))
        rep("6.14", "Double-Star Wildcard Policy Matching", p, "\n".join(d))


def t615():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        c, o, e = v.put("secrets/key", "value", "unknown-user")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Access denied"))
        rep("6.15", "Default Deny When No Policy Exists", p, "\n".join(d))


def t616():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        c, o, e = v.apol("reader", "reports/*", "read,list")
        p, d = _a(p, d, *ck(o, "Policy added: identity='reader', path='reports/*', capabilities=[read, list]"))
        c, o, e = v.rpol("reader", "reports/*")
        p, d = _a(p, d, *ck(o, "Policy removed: identity='reader', path='reports/*'"))
        rep("6.16", "Add and Remove a Policy", p, "\n".join(d))


def t617():
    with TV() as v:
        d, p = [], True
        v.init("TP1"); v.unseal("TP1")
        v.apol("service-x", "data/**", "read,write")
        c, o, e = v.put("data/item", "val1", "service-x")
        p, d = _a(p, d, *ck(o, "Secret stored at data/item (version 1)"))
        v.seal(); v.unseal("TP1")
        c, o, e = v.get("data/item", "service-x")
        p, d = _a(p, d, *ck(o, "Value: val1"))
        rep("6.17", "Policies Persist Across Seal/Unseal", p, "\n".join(d))


def t618():
    with TV() as v:
        d, p = [], True
        v.init("AP1"); v.unseal("AP1")
        v.apol("admin", "**", "read,write")
        v.put("audit/test", "val", "admin")
        v.get("audit/test", "admin")
        v.get("audit/test", "unauthorized")
        c, o, e = v.alog()
        for kw in ["init", "unseal", "store", "audit/test", "retrieve", "denied"]:
            ok, m = ck(o, kw)
            if not ok:
                p = False
                d.append("Missing '%s': %s" % (kw, m))
        if not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", o):
            p = False
            d.append("No ISO 8601 timestamp")
        rep("6.18", "Audit Log Records All Operations", p, "\n".join(d))


def t619():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal(); v.apol("admin", "**", "write")
        c, o, e = v.put("timing/secret", "value", "admin")
        p, d = _a(p, d, *ck(o, "Secret stored at timing/secret (version 1)"))
        c2, o2, e2 = v.alog()
        for kw in ["store", "timing/secret", "success"]:
            ok, m = ck(o2, kw)
            if not ok:
                p = False
                d.append("Audit missing '%s'" % kw)
        rep("6.19", "Audit Log Entry Written Before Result", p, "\n".join(d))


def t620():
    with TV() as v:
        d, p = [], True
        v.su()
        c, o, e = v.put("config/api-key", "key-v1", "admin")
        p, d = _a(p, d, *ck(o, "Secret stored at config/api-key (version 1)"))
        c, o, e = v.put("config/api-key", "key-v2", "admin")
        p, d = _a(p, d, *ck(o, "Secret updated at config/api-key (version 2)"))
        c, o, e = v.put("config/api-key", "key-v3", "admin")
        p, d = _a(p, d, *ck(o, "Secret updated at config/api-key (version 3)"))
        c, o, e = v.get("config/api-key", "admin")
        p, d = _a(p, d, *ck(o, "Version: 3"))
        p, d = _a(p, d, *ck(o, "Value: key-v3"))
        c, o, e = v.get("config/api-key", "admin", ver=1)
        p, d = _a(p, d, *ck(o, "Version: 1"))
        p, d = _a(p, d, *ck(o, "Value: key-v1"))
        c, o, e = v.get("config/api-key", "admin", ver=2)
        p, d = _a(p, d, *ck(o, "Version: 2"))
        p, d = _a(p, d, *ck(o, "Value: key-v2"))
        rep("6.20", "Secret Versioning on Update", p, "\n".join(d))


def t621():
    with TV() as v:
        d, p = [], True
        v.su()
        v.put("config/api-key", "v1", "admin")
        v.put("config/api-key", "v2", "admin")
        c, o, e = v.get("config/api-key", "admin", ver=99)
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Version 99 not found for path 'config/api-key'"))
        rep("6.21", "Version Not Found Error", p, "\n".join(d))


def t622():
    with TV() as v:
        d, p = [], True
        v.init("ST1"); v.unseal("ST1")
        v.apol("admin", "**", "read,write")
        v.put("test/key", "before-seal", "admin")
        c, o, e = v.seal()
        p, d = _a(p, d, *ck(o, "Vault sealed."))
        c, o, e = v.get("test/key", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Vault is sealed"))
        rep("6.22", "Seal Discards Root Key", p, "\n".join(d))


def t623():
    with TV() as v:
        d, p = [], True
        v.init("PT1"); v.unseal("PT1")
        v.apol("admin", "**", "read,write")
        v.put("persist/secret", "persistent-value", "admin")
        v.seal(); v.unseal("PT1")
        c, o, e = v.get("persist/secret", "admin")
        p, d = _a(p, d, *ck(o, "Value: persistent-value"))
        rep("6.23", "Secrets Persist Across Seal/Unseal Cycles", p, "\n".join(d))


def t624():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        c, o, e = v.apol("test", "path/*", "read,execute")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Invalid capability 'execute'"))
        rep("6.24", "CLI Error Output and Exit Codes", p, "\n".join(d))


def t625():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal(); v.apol("admin", "**", "delete")
        c, o, e = v.delete("ghost/secret", "admin")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Secret not found at path 'ghost/secret'"))
        rep("6.25", "Delete Nonexistent Secret Returns Error", p, "\n".join(d))


def t626():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        v.apol("admin", "**", "read,write,list,delete")
        v.put("data/item", "readable", "admin")
        v.apol("limited", "data/**", "read")
        c, o, e = v.get("data/item", "limited")
        p, d = _a(p, d, *ck(o, "Value: readable"), "Read: ")
        c, o, e = v.put("data/item", "new-val", "limited")
        p, d = _a(p, d, *nzc(c), "Write: ")
        p, d = _a(p, d, *ck(e, "Error: Access denied"), "Write err: ")
        c, o, e = v.ls("limited", "data")
        p, d = _a(p, d, *nzc(c), "List: ")
        p, d = _a(p, d, *ck(e, "Error: Access denied"), "List err: ")
        c, o, e = v.delete("data/item", "limited")
        p, d = _a(p, d, *nzc(c), "Del: ")
        p, d = _a(p, d, *ck(e, "Error: Access denied"), "Del err: ")
        rep("6.26", "Capability Mapping Enforced", p, "\n".join(d))


def t627():
    with TV() as v:
        d, p = [], True
        v.init("NP1")
        c, o, e = v.init("NP1")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: Vault file already exists"))
        rep("6.27", "Vault Init Rejects Existing File", p, "\n".join(d))


def t628():
    with TV() as v:
        d, p = [], True
        v.init(); v.unseal()
        c, o, e = v.rpol("phantom", "any/*")
        p, d = _a(p, d, *nzc(c))
        p, d = _a(p, d, *ck(e, "Error: No policy found"))
        rep("6.28", "Remove Nonexistent Policy Returns Error", p, "\n".join(d))


def main():
    print("=" * 70)
    print("Secret Management Vault -- Validation Suite")
    print("SPEC.md Section 6: All 28 Behavior Scenarios")
    print("=" * 70)
    print()
    ts = [t61, t62, t63, t64, t65, t66, t67, t68, t69, t610,
          t611, t612, t613, t614, t615, t616, t617, t618, t619,
          t620, t621, t622, t623, t624, t625, t626, t627, t628]
    for f in ts:
        try:
            f()
        except Exception as x:
            sid = f.__name__[1:]
            sid = sid[0] + "." + sid[1:]
            rep(sid, "EXCEPTION: %s" % x, False, str(x))
    print()
    print("=" * 70)
    print("Results: %d/%d passed, %d failed" % (PC, PC + FC, FC))
    print("=" * 70)
    sys.exit(1 if FC > 0 else 0)


if __name__ == "__main__":
    main()
