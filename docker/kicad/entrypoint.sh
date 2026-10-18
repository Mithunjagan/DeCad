#!/bin/sh
set -eu
APP_UID=${S2SDN_HOST_UID:-1000}
APP_GID=${S2SDN_HOST_GID:-1000}
case "$APP_UID:$APP_GID" in *[!0-9:]*|:*) echo 'Invalid host UID/GID' >&2; exit 1;; esac
mkdir -p /state /workspaces /datasets
if [ "$APP_UID" -eq 0 ]; then exec /start.sh; fi
APP_GROUP=$(getent group "$APP_GID" | cut -d: -f1 || true)
if [ -z "$APP_GROUP" ]; then groupadd -g "$APP_GID" schematic2sdn-host; APP_GROUP=schematic2sdn-host; fi
APP_USER=$(getent passwd "$APP_UID" | cut -d: -f1 || true)
if [ -z "$APP_USER" ]; then
 useradd -m -u "$APP_UID" -g "$APP_GROUP" -d /home/schematic2sdn schematic2sdn
 APP_USER=schematic2sdn
fi
# These are this application's dedicated volumes, never the original checkout.
chown -R "$APP_UID:$APP_GID" /state /workspaces /datasets
# runuser sets the service user's normal login environment and drops root privileges.
exec runuser -u "$APP_USER" -- /start.sh
