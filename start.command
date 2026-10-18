#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo 'Install and start Docker Desktop first.'; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Start Docker Desktop, then run this launcher again.'; exit 1; }
DOCKER_MEMORY=$(docker info --format '{{.MemTotal}}')
if [ "${ENABLE_VISION:-false}" = true ] && [ "$DOCKER_MEMORY" -ge 7500000000 ]; then
    export IMAGE_MODE=vision MODEL_MEMORY_LIMIT="${MODEL_MEMORY_LIMIT:-4g}"
fi
export S2SDN_HOST_UID="$(id -u)" S2SDN_HOST_GID="$(id -g)"
umask 077
mkdir -p backend/workspaces backend/.state backend/datasets
# Build/start the circuit workbench first; its core operations work independently of vision.
docker compose build kicad
docker compose build frontend
docker compose up -d kicad frontend
printf '\nWorkbench: http://localhost:3100\nKiCad desktop: http://localhost:6180/embedded.html\n'
if command -v python3 >/dev/null; then
    nohup python3 bridge/desktop_bridge.py --state backend/.state > backend/.state/bridge.log 2>&1 &
else
    echo 'Desktop application opening requires Python 3.11+. Portable bundles are available without it.'
fi
DOCKER_MEMORY=$(docker info --format '{{.MemTotal}}')
if { [ "${ENABLE_AI:-false}" = true ] || [ "${ENABLE_VISION:-false}" = true ]; } && [ "$DOCKER_MEMORY" -ge 3700000000 ]; then
    docker compose --profile vision up -d vision
    i=0
    until docker compose exec -T vision ollama list >/dev/null 2>&1; do
        i=$((i+1)); [ "$i" -lt 30 ] || { echo 'Model service did not start; core remains available.'; break; }; sleep 1
    done
    docker compose exec -T vision ollama pull "${CHAT_MODEL:-qwen3:0.6b}" || echo 'Model download failed; core remains available.'
else
    echo 'Local AI stays off within this memory budget. Core and OCR operations remain available.'
fi
# Large image models are opt-in and are not loaded into a low-memory desktop.
if [ "${ENABLE_VISION:-false}" = true ] && [ "$DOCKER_MEMORY" -ge 7500000000 ]; then
    docker compose exec -T vision ollama pull "${VISION_MODEL:-qwen3-vl:2b-instruct}"
fi
if command -v open >/dev/null; then open http://localhost:3100; elif command -v xdg-open >/dev/null; then xdg-open http://localhost:3100; fi
