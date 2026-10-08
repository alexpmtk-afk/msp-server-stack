#!/usr/bin/env bash
set -euo pipefail

STACK_ROOT="${1:-}"
if [ -z "$STACK_ROOT" ]; then
  echo "usage: $0 /path/to/msp-server-stack" >&2
  exit 2
fi

STACK_ROOT="$(cd "$STACK_ROOT" && pwd)"
SOURCE_SKILL="$STACK_ROOT/apps/hermes/mpstats_skill/SKILL.md"
SEM="$STACK_ROOT/config/mpstats/semantics"
LIVE_TOOLS="$STACK_ROOT/docs/MPSTATS_TOOLS_2026-10-07.md"
SEM_DOC="$STACK_ROOT/docs/MPSTATS_SEMANTIC_LAYER.md"
OFFICIAL_DOC="$STACK_ROOT/docs/MPSTATS_OFFICIAL_KNOWLEDGE.md"

for f in "$SOURCE_SKILL" "$SEM/catalog.json" "$SEM/routing.json" "$SEM/tool_policy.json" "$SEM/response_shapes.json" "$SEM/metric_semantics.json" "$LIVE_TOOLS" "$SEM_DOC" "$OFFICIAL_DOC"; do
  if [ ! -r "$f" ]; then
    echo "missing required source: $f" >&2
    exit 3
  fi
done

python3 - "$SEM" <<'PY'
import json, pathlib, sys
root=pathlib.Path(sys.argv[1])
for name in ("catalog.json","routing.json","tool_policy.json","response_shapes.json","metric_semantics.json"):
    json.loads((root/name).read_text(encoding="utf-8"))
print("semantic_json=PASS")
PY

HERMES_HOME="${HERMES_HOME:-/home/hermes/.hermes}"
BASE="$HERMES_HOME/skills/productivity"
TARGET="$BASE/mpstats"
TMP="$(mktemp -d "$BASE/.mpstats.install.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/references"

install -m 0644 "$SOURCE_SKILL" "$TMP/SKILL.md"
install -m 0644 "$SEM/catalog.json" "$TMP/references/catalog.json"
install -m 0644 "$SEM/routing.json" "$TMP/references/routing.json"
install -m 0644 "$SEM/tool_policy.json" "$TMP/references/tool_policy.json"
install -m 0644 "$SEM/response_shapes.json" "$TMP/references/response_shapes.json"
install -m 0644 "$SEM/metric_semantics.json" "$TMP/references/metric_semantics.json"
install -m 0644 "$LIVE_TOOLS" "$TMP/references/live-tools.md"
install -m 0644 "$SEM_DOC" "$TMP/references/semantic-layer.md"
install -m 0644 "$OFFICIAL_DOC" "$TMP/references/official-knowledge.md"

COMMIT="$(git -C "$STACK_ROOT" rev-parse HEAD 2>/dev/null || printf unknown)"
python3 - "$TMP/references/deployment.json" "$COMMIT" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1])
obj={
  "canonical_repository":"alexpmtk-afk/msp-server-stack",
  "canonical_commit":sys.argv[2],
  "deployed_at_utc":datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
  "contains_secrets":False
}
p.write_text(json.dumps(obj,indent=2)+"\n",encoding="utf-8")
PY
chmod 0644 "$TMP/references/deployment.json"

if [ -e "$TARGET" ]; then
  rm -rf "$TARGET.prev"
  mv "$TARGET" "$TARGET.prev"
fi
mv "$TMP" "$TARGET"
trap - EXIT
rm -rf "$TARGET.prev"
find "$TARGET" -type d -exec chmod 0755 {} +
find "$TARGET" -type f -exec chmod 0644 {} +

echo "installed=$TARGET"
echo "canonical_commit=$COMMIT"
echo "result=PASS"
