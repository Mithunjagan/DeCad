#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p backend/.state
touch backend/.state/bridge-stop
docker compose --profile vision stop
