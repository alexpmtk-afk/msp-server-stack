#!/usr/bin/env bash
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-/home/hermes/.hermes}"
LOCAL_BIN="/home/hermes/.local/bin"
TOOLS_HOME="/home/hermes/.local/share/msp-admin-tools"
PY_ROOT="$HERMES_HOME/tools/python-3.14.7+20260901-linux-x64"
UV_ROOT="$HERMES_HOME/tools/uv-0.12.3-linux-x64"
RG_ROOT="$HERMES_HOME/tools/ripgrep-15.2.0-linux-x64"
TEST_VENV="$TOOLS_HOME/pytest-venv"

mkdir -p "$LOCAL_BIN" "$TOOLS_HOME"

for required in   "$PY_ROOT/bin/python3"   "$PY_ROOT/bin/pip"   "$UV_ROOT/uv"   "$UV_ROOT/uvx"   "$RG_ROOT/rg"
do
  test -x "$required" || { echo "required bundled tool missing: $required" >&2; exit 1; }
done

ln -sfn "$PY_ROOT/bin/pip" "$LOCAL_BIN/pip"
ln -sfn "$PY_ROOT/bin/pip3" "$LOCAL_BIN/pip3"
ln -sfn "$UV_ROOT/uv" "$LOCAL_BIN/uv"
ln -sfn "$UV_ROOT/uvx" "$LOCAL_BIN/uvx"
ln -sfn "$RG_ROOT/rg" "$LOCAL_BIN/rg"

cat > "$LOCAL_BIN/sqlite3" <<EOF
#!/usr/bin/env bash
exec "$PY_ROOT/bin/python3" -m sqlite3 "\$@"
EOF
chmod 0755 "$LOCAL_BIN/sqlite3"

if [ ! -x "$TEST_VENV/bin/python" ]; then
  "$PY_ROOT/bin/python3" -m venv "$TEST_VENV"
fi
"$TEST_VENV/bin/python" -m pip install --disable-pip-version-check --upgrade "pip==26.2.1" "pytest==9.1.1"
ln -sfn "$TEST_VENV/bin/pytest" "$LOCAL_BIN/pytest"

echo "USER_TOOLCHAIN_INSTALL=PASS"
