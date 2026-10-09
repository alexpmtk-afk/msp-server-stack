#!/usr/bin/env bash
set -euo pipefail

# Install a new, self-contained Hermes skill without touching other skills,
# the Telegram Gateway, notifier, timers, archive, credentials or sessions.
mode=install
if [[ "${1:-}" == '--check' ]]; then mode=check; shift; fi
if [[ "$#" -ne 1 ]]; then
  echo 'usage: install-msp-signals-skill.sh [--check] /opt/mcp/projects/msp-server-stack' >&2
  exit 2
fi
if [[ "$(id -un)" != hermes ]]; then echo 'STOP: installer requires hermes user' >&2; exit 1; fi
ROOT="$(readlink -f "$1")"
[[ "$ROOT" == '/opt/mcp/projects/msp-server-stack' ]] || { echo 'STOP: noncanonical source path'; exit 1; }
BASE=/home/hermes/.hermes/skills/productivity
TARGET="$BASE/msp-signals"
[[ -d "$BASE" && -w "$BASE" ]] || { echo 'STOP: skill base inaccessible'; exit 1; }
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || { echo 'STOP: existing msp-signals skill requires separate review'; exit 1; }
SKILL="$ROOT/apps/hermes/msp_signals_skill/SKILL.md"
RULES="$ROOT/docs/signals/REVIEWED_RULES_2026-10-05.md"
SIM="$ROOT/docs/signals/SIMULATED_NOTIFICATIONS.md"
STOCK="$ROOT/docs/signals/stock-shortage.md"
for f in "$SKILL" "$RULES" "$SIM" "$STOCK"; do
  [[ -f "$f" && -r "$f" ]] || { echo 'STOP: missing skill/reference source'; exit 1; }
done
python3 - "$SKILL" "$RULES" "$SIM" <<'PY'
import pathlib,sys
skill,rules,sim=(pathlib.Path(x).read_text(encoding='utf-8') for x in sys.argv[1:])
assert skill.startswith('---\nname: msp-signals\n')
assert 'references/reviewed-rules.md' in skill
assert 'не заказан на производство' in skill
assert 'if _N is present' in rules and 'recommend raising the price' in rules
assert 'no production/inbound date' in sim
print('SKILL_SEMANTICS=PASS')
PY
if [[ "$mode" == check ]]; then echo 'MSP_SIGNALS_SKILL_PREFLIGHT=PASS'; exit 0; fi
TEMP="$(mktemp -d "$BASE/.msp-signals.install.XXXXXX")"
trap 'rm -rf "$TEMP"' EXIT
mkdir -m 0755 "$TEMP/references"
install -m 0644 "$SKILL" "$TEMP/SKILL.md"
install -m 0644 "$RULES" "$TEMP/references/reviewed-rules.md"
install -m 0644 "$SIM" "$TEMP/references/simulated-notifications.md"
install -m 0644 "$STOCK" "$TEMP/references/stock-shortage.md"
COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
python3 - "$TEMP/references/deployment.json" "$COMMIT" <<'PY'
import datetime,json,pathlib,sys
meta={
  'canonical_repository':'alexpmtk-afk/msp-server-stack',
  'canonical_commit':sys.argv[2],
  'deployed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
  'contains_secrets':False,
  'skill':'msp-signals',
}
p=pathlib.Path(sys.argv[1]);p.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
p.chmod(0o644)
PY
[[ ! -e "$TARGET" && ! -L "$TARGET" ]] || { echo 'STOP: skill added concurrently'; exit 1; }
mv "$TEMP" "$TARGET"
trap - EXIT
echo 'MSP_SIGNALS_SKILL_INSTALLED=PASS'
echo "installed_path=$TARGET"
echo "canonical_commit=$COMMIT"
