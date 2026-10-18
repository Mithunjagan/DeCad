#!/bin/sh
set -eu
PROJECT_FILE="$1"
[ -f "$PROJECT_FILE" ] || { echo 'Schematic does not exist' >&2; exit 1; }
WINDOWS=$(xdotool search --onlyvisible --class eeschema 2>/dev/null || true)
for WIN in $WINDOWS; do
    # Ask the window manager to close normally so KiCad can save or prompt.
    xdotool windowactivate --sync "$WIN"
    xdotool key --clearmodifiers alt+F4
done
# Wait for the editor to exit gracefully. An unsaved-changes dialog must not be killed.
i=0
while ps -C eeschema -o stat= | awk '$1 !~ /^Z/ {alive=1} END {exit !alive}'; do
    # KiCad 9 can leave its standalone process on an empty editor after File Close.
    # Terminate only a confirmed empty frame, never a loaded schematic or dialog.
    for WIN in $(xdotool search --onlyvisible --class eeschema 2>/dev/null || true); do
        TITLE=$(xdotool getwindowname "$WIN" 2>/dev/null || true)
        case "$TITLE" in
            "[no schematic loaded]"*)
                ID=$(xdotool getwindowpid "$WIN")
                COUNT=$(xdotool search --onlyvisible --pid "$ID" 2>/dev/null | wc -l)
                [ "$COUNT" -eq 1 ] && kill -TERM "$ID"
                ;;
        esac
    done
    i=$((i+1))
    [ "$i" -lt 30 ] || { echo 'Save or close the open KiCad dialog, then retry activation.' >&2; exit 1; }
    sleep 0.2
done
nohup eeschema "$PROJECT_FILE" > /tmp/eeschema.log 2>&1 &
i=0
while ! xdotool search --onlyvisible --class eeschema >/dev/null 2>&1; do
    i=$((i+1))
    [ "$i" -lt 50 ] || { cat /tmp/eeschema.log >&2; exit 1; }
    sleep 0.2
done

# Initial KiCad window setup can replace its window before the editor is ready.
sleep 0.6
WIN=$(xdotool search --onlyvisible --class eeschema | tail -n 1)
xdotool windowactivate --sync "$WIN"
xdotool key --clearmodifiers ctrl+Home
