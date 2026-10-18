#!/bin/sh
set -eu
umask 077
CONFIG_ROOT=${XDG_CONFIG_HOME:-/state/gui-config}
export XDG_CONFIG_HOME="$CONFIG_ROOT"
mkdir -p "$CONFIG_ROOT/openbox" "$CONFIG_ROOT/kicad/9.0" /workspaces /state /datasets
# This dedicated container has no surviving editors at startup. Remove their stale locks.
find /workspaces -type f -name '~*.lck' -delete
cat > "$CONFIG_ROOT/openbox/rc.xml" <<'XML'
<openbox_config xmlns="http://openbox.org/3.4/rc"><keyboard><keybind key="A-F4"><action name="Close"/></keybind></keyboard><applications><application class="*"><maximized>yes</maximized><decorations>no</decorations></application></applications></openbox_config>
XML
cat > "$CONFIG_ROOT/kicad/9.0/kicad_common.json" <<'JSON'
{"system":{"first_run_shown":true}}
JSON
# Assign an explicit hotkey to grid visibility (KiCad has none by default).
printf 'common.Control.toggleGrid\tF6\t\n' > "$CONFIG_ROOT/kicad/9.0/user.hotkeys"
# Install real library tables rather than replacing them with empty tables.
[ -f /usr/share/kicad/template/sym-lib-table ] && cp /usr/share/kicad/template/sym-lib-table "$CONFIG_ROOT/kicad/9.0/sym-lib-table"
[ -f /usr/share/kicad/template/fp-lib-table ] && cp /usr/share/kicad/template/fp-lib-table "$CONFIG_ROOT/kicad/9.0/fp-lib-table"

# A stopped container retains /tmp; an interrupted X server leaves its lock/socket.
# This container owns its display and starts exactly one X server.
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
Xvfb :1 -screen 0 "${RESOLUTION:-1600x1000x24}" &
XVFB_PID=$!
sleep 1
openbox --config-file "$CONFIG_ROOT/openbox/rc.xml" &
WM_PID=$!
x11vnc -display :1 -forever -shared -nopw -quiet -rfbport 5900 -localhost &
VNC_PID=$!
websockify --web /usr/share/novnc 6080 localhost:5900 &
WEB_PID=$!
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
trap 'kill "$API_PID" "$WEB_PID" "$VNC_PID" "$WM_PID" "$XVFB_PID" 2>/dev/null || true; exit 0' TERM INT
# Exit on failure of any required service; Docker restarts the complete stack.
while kill -0 "$API_PID" && kill -0 "$WEB_PID" && kill -0 "$VNC_PID" && kill -0 "$XVFB_PID"; do sleep 2; done
exit 1
