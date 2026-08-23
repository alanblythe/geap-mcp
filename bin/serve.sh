#!/usr/bin/env bash
#
# Launch the server. A plugin's MCP command is exec'd directly with no shell and
# no variable expansion, so mcp_config.json calls /bin/sh, which calls this.
#
# stdout is the MCP transport. Anything printed to it that is not a protocol
# message breaks the handshake, which is why uv is run quiet.
#
# PYTHONPATH, and -m rather than a path, because the package uses relative
# imports and the runner is respawned as a module by the server.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
UV=$(command -v uv || true)
[ -n "$UV" ] || UV="$HOME/.local/bin/uv"
export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$UV" run --quiet --with "mcp>=2,<3" --with google-auth --with requests python -m geap_mcp.server
