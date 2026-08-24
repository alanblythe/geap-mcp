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
# Not exec'd. agy stops a server with SIGTERM when it reloads its MCP config,
# and a shell killed by a signal exits 128+n -- 143. agy reads any non-zero
# exit as "failed to stop", aborts the reload, and drops every other server
# with it. Being asked to stop is not an error, so the signal is forwarded and
# the exit is clean.
# `<&3` because a background job in a non-interactive shell gets /dev/null
# on stdin, and stdin is the MCP transport: the server would see EOF and
# exit before the first message.
exec 3<&0
"$UV" run --quiet --with "mcp>=2,<3" --with google-auth --with requests python -m geap_mcp.server <&3 &
child=$!
# `|| true` on both waits: set -e would otherwise exit the shell with the
# child's 143 before the trap reaches `exit 0`, which is the whole bug.
trap 'kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null || true; exit 0' TERM INT
wait "$child" || true
