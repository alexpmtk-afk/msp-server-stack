#!/usr/bin/env bash
# Recover the canonical Hermes USER timer; never touch system-level units.
set -euo pipefail

mode=apply
if [[ "$#" -gt 0 && "$1" == "--check" ]]; then mode=check; shift; fi
if [[ "$#" -ne 1 ]]; then
  echo "usage: install-msp-data-sync.sh [--check] /opt/mcp/projects/msp-server-stack" >&2
  exit 2
fi
if [[ "$(id -un)" != "hermes" ]]; then
  echo "STOP: run as hermes, not sudo/root; this is a user-systemd installer" >&2
  exit 1
fi

target=/opt/mcp/projects/msp-server-stack
if [[ ! -d "$1" || "$(readlink -f "$1")" != "$target" ]]; then
  echo "STOP: deploy the reviewed canonical repository at $target first" >&2
  exit 1
fi
for path in \
  "$target/apps/msp_data_sync/sync.py" \
  "$target/apps/msp_data_sync/run_with_alerts.py" \
  "$target/config/msp-data/sync.json" \
  "$target/systemd/user/msp-data-sync.service" \
  "$target/systemd/user/msp-data-sync.timer"; do
  [[ -r "$path" ]] || { echo "STOP: missing readable deployment file: $path" >&2; exit 1; }
done

for dir in /opt/mcp/data/msp /opt/mcp/backups/msp; do
  [[ -d "$dir" && -w "$dir" ]] || {
    echo "STOP: $dir must exist and be writable by hermes; owner bootstrap required" >&2
    exit 1
  }
done

env_file=/home/hermes/.hermes/.env
[[ -f "$env_file" ]] || { echo "STOP: existing protected Hermes env file absent" >&2; exit 1; }
[[ "$(stat -c '%u:%a' "$env_file")" == "$(id -u):600" ]] || {
  echo "STOP: existing Hermes env file must be hermes-owned with mode 0600" >&2
  exit 1
}
[[ "$(loginctl show-user hermes -p Linger --value 2>/dev/null)" == "yes" ]] || {
  echo "STOP: hermes linger disabled; owner must provision separately" >&2
  exit 1
}
if systemctl is-active --quiet msp-data-sync.timer; then
  echo "STOP: system-level msp-data-sync.timer active; duplicate schedule forbidden" >&2
  exit 1
fi

unit_dir=/home/hermes/.config/systemd/user
for name in msp-data-sync.service msp-data-sync.timer; do
  source="$target/systemd/user/$name"
  destination="$unit_dir/$name"
  if [[ -e "$destination" && ! -f "$destination" ]]; then
    echo "STOP: unexpected unit type: $destination" >&2
    exit 1
  fi
  if [[ -f "$destination" ]] && ! cmp -s "$source" "$destination"; then
    echo "STOP: installed $name differs; review required, no overwrite" >&2
    exit 1
  fi
done
if [[ "$mode" == "check" ]]; then
  echo "CHECK=PASS (read-only; no unit changes or sync runs)"
  exit 0
fi

if [[ -z "$(printenv XDG_RUNTIME_DIR || true)" ]]; then
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [[ -z "$(printenv DBUS_SESSION_BUS_ADDRESS || true)" ]]; then
  export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi
[[ -S "$XDG_RUNTIME_DIR/bus" ]] || {
  echo "STOP: hermes user bus unavailable; nothing installed" >&2
  exit 1
}
install -d -m 0700 "$unit_dir"
for name in msp-data-sync.service msp-data-sync.timer; do
  if [[ ! -e "$unit_dir/$name" ]]; then
    install -m 0644 "$target/systemd/user/$name" "$unit_dir/$name"
  fi
done
systemctl --user daemon-reload
systemctl --user enable --now msp-data-sync.timer
systemctl --user is-enabled --quiet msp-data-sync.timer
systemctl --user is-active --quiet msp-data-sync.timer
echo "INSTALL=PASS (Hermes user timer enabled and active)"
echo "NOTE: Persistent=true may start a missed sync; inspect journalctl --user"
