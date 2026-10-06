#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run_as_root=REQUIRED" >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo "usage: install-msp-data-sync.sh SOURCE_ROOT" >&2
  exit 2
fi

SRC_ROOT="$1"
TARGET_ROOT=/opt/mcp/projects/msp-server-stack
DATA_DIR=/opt/mcp/data/msp
BACKUP_DIR=/opt/mcp/backups/msp

install -d -o hermes -g hermes -m 0755 "$TARGET_ROOT/apps/msp_data_sync"
install -d -o hermes -g hermes -m 0755 "$TARGET_ROOT/config/msp-data/semantics"
install -d -o hermes -g hermes -m 0750 "$DATA_DIR"
install -d -o hermes -g hermes -m 0750 "$BACKUP_DIR"

install -o hermes -g hermes -m 0755 "$SRC_ROOT/apps/msp_data_sync/sync.py" "$TARGET_ROOT/apps/msp_data_sync/sync.py"
install -o hermes -g hermes -m 0644 "$SRC_ROOT/config/msp-data/sync.json" "$TARGET_ROOT/config/msp-data/sync.json"
for f in "$SRC_ROOT"/config/msp-data/semantics/*.yaml; do
  install -o hermes -g hermes -m 0644 "$f" "$TARGET_ROOT/config/msp-data/semantics/$(basename "$f")"
done

install -o root -g root -m 0644 "$SRC_ROOT/systemd/msp-data-sync.service" /etc/systemd/system/msp-data-sync.service
install -o root -g root -m 0644 "$SRC_ROOT/systemd/msp-data-sync.timer" /etc/systemd/system/msp-data-sync.timer
systemctl daemon-reload
systemctl enable --now msp-data-sync.timer

echo "install=PASS"
echo "target_root=$TARGET_ROOT"
echo "data_dir=$DATA_DIR"
systemctl is-enabled msp-data-sync.timer
systemctl is-active msp-data-sync.timer
