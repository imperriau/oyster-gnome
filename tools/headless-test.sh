#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run the extension in an isolated headless GNOME Shell, drive it with the fake daemon, check what
# it does and save screenshots. Exits non-zero if any check fails. Touches nothing in your real
# session: private session bus, temporary XDG dirs, and a throwaway helper extension that enables
# unsafe mode (for Eval/Screenshot).
#
#   tools/headless-test.sh [OUTDIR]
#
# Needs dbus-run-session (zypper in dbus-1-daemon). Set DBUS_DAEMON=/path/to/dbus-daemon and
# DBUS_RUN_SESSION=/path/to/dbus-run-session to use an unpacked copy instead.
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$(mktemp -d -t oyster-headless.XXXX)}"
RUNSESSION="${DBUS_RUN_SESSION:-$(command -v dbus-run-session || true)}"
[ -n "$RUNSESSION" ] || { echo "dbus-run-session not found (zypper in dbus-1-daemon)"; exit 1; }
DAEMON_ARG=()
[ -n "${DBUS_DAEMON:-}" ] && DAEMON_ARG=(--dbus-daemon="$DBUS_DAEMON")
SHELL_MAJOR="$(gnome-shell --version | sed -E 's/^GNOME Shell ([0-9]+).*/\1/')"
# Containers have no user session to provide one.
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    export XDG_RUNTIME_DIR="$OUT/run"
    mkdir -p "$XDG_RUNTIME_DIR"
    chmod 700 "$XDG_RUNTIME_DIR"
fi

mkdir -p "$OUT"/{data/gnome-shell/extensions,config,cache}
: > "$OUT/results"
H="$OUT/data/gnome-shell/extensions/test-helper@local"
mkdir -p "$H"
echo '{"uuid":"test-helper@local","name":"test helper","description":"unsafe mode","shell-version":["'"$SHELL_MAJOR"'"]}' > "$H/metadata.json"
cat > "$H/extension.js" <<'JS'
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
export default class H extends Extension {
    enable() { global.context.unsafe_mode = true; }
    disable() {}
}
JS
ln -sfn "$REPO/extension" "$OUT/data/gnome-shell/extensions/oyster@imperriau.github.io"

cat > "$OUT/inner.sh" <<'SH'
#!/bin/bash
OUT="$1"; REPO="$2"
gsettings set org.gnome.shell enabled-extensions "['test-helper@local', 'oyster@imperriau.github.io']"
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
gnome-shell --headless --wayland --no-x11 --virtual-monitor 1280x800 \
    --wayland-display wayland-airpods-test > "$OUT/shell.log" 2>&1 &
SHELL_PID=$!
ev() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell -m org.gnome.Shell.Eval "$1"; }
shot() { gdbus call --session -d org.gnome.Shell -o /org/gnome/Shell/Screenshot \
    -m org.gnome.Shell.Screenshot.Screenshot false false "$OUT/$1.png" >/dev/null; }
EXT='Main.extensionManager.lookup("oyster@imperriau.github.io")'
CARD="$EXT.stateObj._card"
# check NAME JS: record whether the expression is true in the Shell
check() {
    if ev "!!($2)" 2>&1 | grep -q "(true, 'true')"; then
        echo "ok   $1" >> "$OUT/results"
    else
        echo "FAIL $1" >> "$OUT/results"
    fi
}
# Screenshots too: a broken paint path shows up as a failed call or a missing file.
shot_check() {
    if shot "$1" && [ -s "$OUT/$1.png" ]; then
        echo "ok   screenshot $1" >> "$OUT/results"
    else
        echo "FAIL screenshot $1" >> "$OUT/results"
    fi
}
for i in $(seq 1 60); do ev 1 >/dev/null 2>&1 && break; sleep 0.5; done
sleep 2; ev 'Main.overview.hide(); 1' >/dev/null
check 'extension active' "$EXT.state === 1 && !$EXT.error"
python3 "$REPO/daemon/tests/fake_daemon.py" > "$OUT/fake.log" 2>&1 &
FAKE_PID=$!
# fake script: t=2 open, t=4 update, t=6 close, t=8 single-battery open, t=10 close
sleep 3
check 'card shown when the lid opens' "$CARD._box.visible && $CARD._title.text === 'AirPods Pro 2 (USB-C)'"
shot_check 1-open
sleep 2
check 'live update reaches the card' "$CARD._rows.left.pct.text === '100 %' && $CARD._rows.case.pct.text === '–'"
check '3D spin loaded' "$CARD._hero !== null"
shot_check 2-update
sleep 2.2
check 'card hidden when the lid closes' "!$CARD._box.visible"
shot_check 3-closed
sleep 1.8
check 'single-battery layout' "$CARD._box.visible && !$CARD._rows.right.row.visible && !$CARD._rows.case.row.visible"
shot_check 4-single
kill $FAKE_PID; sleep 1
check 'card hidden when the daemon goes' "!$CARD._box.visible"
shot_check 5-daemon-gone
for i in 1 2 3 4 5; do
    gnome-extensions disable oyster@imperriau.github.io; sleep 0.2
    gnome-extensions enable oyster@imperriau.github.io; sleep 0.2
done
check 'active after 5 disable/enable cycles' "$EXT.state === 1 && !$EXT.error"
echo done >> "$OUT/results"
kill $SHELL_PID; wait $SHELL_PID 2>/dev/null
SH
chmod +x "$OUT/inner.sh"

env XDG_DATA_HOME="$OUT/data" XDG_CONFIG_HOME="$OUT/config" XDG_CACHE_HOME="$OUT/cache" \
    GSETTINGS_BACKEND=keyfile \
    timeout 90 "$RUNSESSION" "${DAEMON_ARG[@]}" --config-file=/usr/share/dbus-1/session.conf \
    -- "$OUT/inner.sh" "$OUT" "$REPO" >/dev/null 2>&1 || true

echo "GNOME Shell $SHELL_MAJOR:"
grep -v '^done$' "$OUT/results" || true
echo "extension log lines:"
grep -E "\[Oyster\]|oyster@|JS ERROR|Gjs-CRITICAL" "$OUT/shell.log" || true
echo "screenshots in $OUT"
if ! grep -qx done "$OUT/results"; then
    echo "FAIL: the run did not finish"
    exit 1
fi
if grep -q '^FAIL' "$OUT/results" || grep -qE "JS ERROR|Gjs-CRITICAL" "$OUT/shell.log"; then
    exit 1
fi
