#!/bin/sh
# Start the workspace with both local synthesis and detailed vision services.
set -eu
cd "$(dirname "$0")"
export ENABLE_AI=true ENABLE_VISION=true
exec sh ./start.command
