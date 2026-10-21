#!/usr/bin/env bash
set -euo pipefail

# Reviewed manual Hermes Skill install for MSP self-purchases. No Gateway/timer restart.
# Usage: install-msp-self-purchases-skill.sh [--check] PUBLIC_REPO_ROOT PRIVATE_BRIDGE_CHECKOUT
mode=install
if [[ "${1:-}" == "--check" ]]; then mode=check; shift; fi
if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 [--check] /opt/mcp/projects/msp-server-stack /path/to/authorized/private/msp-server-bridge" >&2
  exit 2
fi
[[ "$(id -un)" == "hermes" ]] || { echo "STOP: requires hermes user" >&2; exit 1; }
public_root="$(readlink -f "$1")"
private_root="$(readlink -f "$2")"
[[ "$public_root" == "/opt/mcp/projects/msp-server-stack" ]] || { echo "STOP: noncanonical public root" >&2; exit 1; }
[[ "$private_root" != "$public_root" && -d "$private_root/.git" ]] || { echo "STOP: authorized private checkout required" >&2; exit 1; }
base="/home/hermes/.hermes/skills/productivity"
target="$base/msp-self-purchases"
[[ -d "$base" && -w "$base" ]] || { echo "STOP: skill base inaccessible" >&2; exit 1; }
[[ ! -e "$target" && ! -L "$target" ]] || { echo "STOP: existing skill; use reviewed upgrade path" >&2; exit 1; }

skill="$public_root/apps/hermes/msp_self_purchases_skill/SKILL.md"
compass="$public_root/docs/self-purchases/PROJECT_COMPASS.md"
vision="$private_root/docs/self-purchases/original/INITIAL_VISION_V1_2026-10-21.md"
transcript="$private_root/docs/self-purchases/original/MEETING_TRANSCRIPT_2026-10-21.md"
for f in "$skill" "$compass" "$vision" "$transcript"; do
  [[ -f "$f" && -r "$f" && ! -L "$f" ]] || { echo "STOP: missing/unreadable/symlink source file" >&2; exit 1; }
done

grep -q '^name: msp-self-purchases$' "$skill" || { echo "STOP: skill identity mismatch" >&2; exit 1; }
grep -q 'неизменяемая редакция' "$transcript" || { echo "STOP: transcript marker mismatch" >&2; exit 1; }
grep -q 'замороженная редакция v1.0' "$vision" || { echo "STOP: original vision marker mismatch" >&2; exit 1; }
if [[ "$mode" == check ]]; then
  echo "MSP_SELF_PURCHASES_SKILL_PREFLIGHT=PASS"
  echo "ORIGINALS_PRESENT=YES"
  exit 0
fi

umask 077
tmp="$(mktemp -d "$base/.msp-self-purchases.install.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
mkdir -m 0700 "$tmp/references"
install -m 0600 "$skill" "$tmp/SKILL.md"
install -m 0600 "$compass" "$tmp/references/PROJECT_COMPASS.md"
install -m 0600 "$vision" "$tmp/references/INITIAL_VISION_V1_2026-10-21.md"
install -m 0600 "$transcript" "$tmp/references/MEETING_TRANSCRIPT_2026-10-21.md"
# Independent copy integrity verification. Never print original contents in logs.
for spec in \
  "$skill|$tmp/SKILL.md" \
  "$compass|$tmp/references/PROJECT_COMPASS.md" \
  "$vision|$tmp/references/INITIAL_VISION_V1_2026-10-21.md" \
  "$transcript|$tmp/references/MEETING_TRANSCRIPT_2026-10-21.md"; do
  src="${spec%%|*}"; dst="${spec#*|}"
  [[ "$(sha256sum "$src" | cut -d' ' -f1)" == "$(sha256sum "$dst" | cut -d' ' -f1)" ]] || { echo "STOP: copied file digest mismatch" >&2; exit 1; }
done
git -C "$public_root" rev-parse HEAD >"$tmp/public_commit"
git -C "$private_root" rev-parse HEAD >"$tmp/private_commit"
chmod 0600 "$tmp/public_commit" "$tmp/private_commit"
[[ ! -e "$target" && ! -L "$target" ]] || { echo "STOP: destination changed concurrently" >&2; exit 1; }
mv "$tmp" "$target"
trap - EXIT
echo "MSP_SELF_PURCHASES_SKILL_INSTALLED=PASS"
echo "Skill deployed with source copies and recorded commits. Verify independent Hermes discovery."
