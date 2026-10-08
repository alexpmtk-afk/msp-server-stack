#!/usr/bin/env python3
"""Read-only audit of MPSTATS Codex and Hermes integration (redacted output)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tomllib
from urllib.parse import parse_qs, urlsplit

DEPLOYED_COMMIT = "503262060d7d818a6e2ed6fd5dead5dd41aab157"
ROOT = Path("/home/hermes")
SKILL = ROOT / ".hermes/skills/productivity/mpstats"
CONFIGS = [ROOT / ".codex/config.toml", ROOT / ".codex-dashboard/config.toml"]
SECRET = Path("/opt/mcp/secrets/mpstats.env")
SOURCES = {
 "SKILL.md": "apps/hermes/mpstats_skill/SKILL.md",
 "references/catalog.json": "config/mpstats/semantics/catalog.json",
 "references/routing.json": "config/mpstats/semantics/routing.json",
 "references/tool_policy.json": "config/mpstats/semantics/tool_policy.json",
 "references/response_shapes.json": "config/mpstats/semantics/response_shapes.json",
 "references/metric_semantics.json": "config/mpstats/semantics/metric_semantics.json",
 "references/live-tools.md": "docs/MPSTATS_TOOLS_2026-10-07.md",
 "references/semantic-layer.md": "docs/MPSTATS_SEMANTIC_LAYER.md",
 "references/official-knowledge.md": "docs/MPSTATS_OFFICIAL_KNOWLEDGE.md",
}

def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(argv):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=25, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployed-source", required=True)
    canonical = Path(parser.parse_args().deployed_source)
    issues = []
    warnings = []
    out = {"audit": "REMOTE_MPSTATS_RUNTIME_AUDIT",
           "mode": "read_only_no_mpstats_api",
           "expected_deployed_commit": DEPLOYED_COMMIT}

    def check(name, value):
        out[name] = "PASS" if value else "FAIL"
        if not value:
            issues.append(name)

    try:
        uid = pwd.getpwnam("hermes").pw_uid
    except KeyError:
        uid = -1
    check("runner_identity", os.getuid() == uid)
    try:
        st = SECRET.lstat()
        check("secret_file_mode_owner",
              stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode)==0o600 and st.st_uid==uid)
    except OSError:
        check("secret_file_mode_owner", False)
    # Never read or emit protected secret content, even for diagnostic purposes.

    endpoints = []
    for idx, path in enumerate(CONFIGS, 1):
        key = "config"+str(idx)
        try:
            st = path.lstat()
            check(key+"_mode_owner",
                  stat.S_ISREG(st.st_mode) and st.st_uid==uid and stat.S_IMODE(st.st_mode)==0o600)
            parsed = tomllib.loads(path.read_text(encoding="utf-8"))
            servers = parsed.get("mcp_servers", {})
            m = servers.get("mpstats", {})
            endpoint = m.get("url", "")
            parts = urlsplit(endpoint) if isinstance(endpoint,str) else urlsplit("")
            params = parse_qs(parts.query, keep_blank_values=True)
            valid = (parts.scheme=="https" and parts.netloc=="mcp.mpstats.io"
                     and parts.path=="/mcp" and not parts.fragment
                     and set(params)=={"token"} and len(params["token"])==1
                     and bool(params["token"][0]))
            endpoints.append(endpoint if valid else "")
            check(key+"_mpstats", valid and m.get("enabled") is True)
            check(key+"_hermes_tools", "hermes-tools" in servers)
            out[key+"_mcp_server_count"] = len(servers)
            out[key+"_backup_count"] = len(list(path.parent.glob(path.name+".pre-mpstats.*.bak")))
        except (OSError, UnicodeError, ValueError, TypeError):
            check(key+"_read_and_parse", False)
    check("mcp_url_equal_across_configs",
          len(endpoints)==2 and bool(endpoints[0]) and endpoints[0]==endpoints[1])
    # endpoints may contain a credential: never print them or subprocess stderr.

    try:
        if not SKILL.is_dir() or SKILL.is_symlink():
            check("skill_directory", False)
        else:
            found = {str(p.relative_to(SKILL)) for p in SKILL.rglob("*") if p.is_file()}
            check("skill_file_set", found == set(SOURCES)|{"references/deployment.json"})
            matched = True
            modes = True
            for target, src in SOURCES.items():
                deployed = SKILL / target
                upstream = canonical / src
                if not deployed.is_file() or deployed.is_symlink() or not upstream.is_file():
                    matched = False
                    modes = False
                    continue
                matched &= checksum(deployed) == checksum(upstream)
                fs = deployed.lstat()
                modes &= fs.st_uid==uid and stat.S_IMODE(fs.st_mode)==0o644
            check("skill_sha256_matches_pinned_git", matched)
            check("skill_file_modes_owners", modes)
            meta = json.loads((SKILL/"references/deployment.json").read_text(encoding="utf-8"))
            check("skill_pinned_deployment_marker",
                  meta.get("canonical_commit")==DEPLOYED_COMMIT
                  and meta.get("contains_secrets") is False)
            out["skill_expected_reference_count"] = len(SOURCES)
    except (OSError, UnicodeError, ValueError, TypeError):
        check("skill_audit_exception", False)

    parent = SKILL.parent
    try:
        remnants = [p for p in parent.iterdir()
                    if p.name.startswith(".mpstats.install.") or p.name=="mpstats.prev"]
        out["mpstats_temporary_entry_count"] = len(remnants)
        if remnants:
            warnings.append("mpstats_temp_or_previous_tree_exists")
    except OSError:
        warnings.append("cannot_inspect_skill_parent")

    for key,service in [("gateway","hermes-gateway.service"),
                        ("dashboard","hermes-dashboard.service")]:
        code, stdout = run(["systemctl","is-active",service])
        check(key+"_active", code==0 and stdout.strip()=="active")

    code, stdout = run(["codex","mcp","list","--json"])
    if code==0:
        try:
            listed = json.loads(stdout)
            if isinstance(listed,dict):
                listed=listed.get("servers", [])
            if isinstance(listed,dict):
                names=set(listed)
            elif isinstance(listed,list):
                names={entry.get("name") for entry in listed if isinstance(entry,dict)}
            else:
                names=set()
            check("codex_cli_mpstats", "mpstats" in names)
            check("codex_cli_hermes_tools", "hermes-tools" in names)
        except (ValueError,TypeError,AttributeError):
            check("codex_cli_json",False)
    else:
        check("codex_cli_list",False)

    binary = ROOT / ".hermes/hermes-agent/.hermes/bin/hermes"
    code, stdout = run([str(binary),"skills","list"])
    check("hermes_skills_cli", code==0 and any(
        "mpstats" in line.lower() and "enabled" in line.lower()
        for line in stdout.splitlines()))
    out["issue_count"] = len(issues)
    out["warning_count"] = len(warnings)
    out["result"] = "FAIL" if issues else "WARN" if warnings else "PASS"
    for key,value in out.items():
        print(f"{key}={value}")
    for issue in issues:
        print("issue="+issue)
    for warning in warnings:
        print("warning="+warning)
    return 1 if issues else 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("audit=REMOTE_MPSTATS_RUNTIME_AUDIT")
        print("result=FAIL")
        print("issue=unhandled_exception_suppressed")
        raise SystemExit(2)
