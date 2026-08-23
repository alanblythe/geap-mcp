"""MCP tools for agents deployed on Gemini Enterprise Agent Platform."""

import json
import pathlib
import subprocess
import sys
import tempfile
import uuid

from mcp.server.mcpserver import MCPServer

from . import trajectory

mcp = MCPServer("geap-mcp")
RUNS = pathlib.Path(tempfile.gettempdir()) / "geap-mcp"


def _status(run_dir: pathlib.Path) -> dict:
    path = run_dir / "status"
    if not path.exists():
        return {"state": "starting"}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"state": "starting"}


@mcp.tool()
def list_agents(project: str | None = None, location: str | None = None) -> list[dict]:
    """List the agents deployed on Agent Platform in a project and region.

    Call this first when you do not already know which agent to talk to: its
    `id` or `display_name` is what start_query takes. `deployed` false means the
    engine runs no code and cannot answer a query -- it only holds sessions.

    `project` falls back to GOOGLE_CLOUD_PROJECT or the active gcloud project,
    `location` to AGENT_ENGINE_LOCATION. Agent Platform is regional, so an
    agent in another region will not appear here.
    """
    from . import client

    return client.list_engines(project, location, client.access_token())


@mcp.tool()
def start_query(
    engine: str,
    message: str,
    user_id: str = "mcp",
    session_id: str | None = None,
    project: str | None = None,
    location: str | None = None,
    transport: str = "auto",
    class_method: str = "async_stream_query",
) -> dict:
    """Send a message to a deployed agent and return immediately.

    `message` is passed through untouched: prose for a conversational agent, a
    JSON string for one that expects a job. Knowing which is the caller's job.

    `engine` is a display name, a numeric id, or a full
    projects/*/locations/*/reasoningEngines/* name. Use list_agents to find one.
    `transport` of "auto" picks :streamQuery for an engine publishing
    classMethods and the container route for one that does not.

    Follow the run with read_query.
    """
    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    arguments = json.dumps({
        "run_dir": str(run_dir), "engine": engine, "message": message,
        "user_id": user_id, "session_id": session_id, "project": project,
        "location": location, "transport": transport, "class_method": class_method,
    })
    subprocess.Popen(
        [sys.executable, "-m", "geap_mcp.runner", arguments],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # outlives this server, which restarts per session
    )
    return {"run_id": run_id, "log": str(run_dir / "events.ndjson")}


@mcp.tool()
def read_query(run_id: str, cursor: int = 0) -> dict:
    """Read what a run has done since `cursor`, one line per action.

    Returns `next_cursor` to pass to the following call. A `state` of "running"
    with no new lines means the agent is working, not that it has stopped.
    """
    run_dir = RUNS / run_id
    if not run_dir.exists():
        return {"state": "unknown", "lines": [], "next_cursor": cursor,
                "detail": f"no run {run_id}"}
    log = run_dir / "events.ndjson"
    # Whole lines only. The writer is still appending, and half an event is not
    # an event -- so read to the last newline and no further.
    data = log.read_bytes() if log.exists() else b""
    if not data.endswith(b"\n"):
        data = data[: data.rfind(b"\n") + 1]
    complete = data.decode(errors="replace").splitlines()[cursor:]
    status = _status(run_dir)
    return {
        "state": status.get("state", "starting"),
        "detail": status.get("detail", ""),
        "transport": status.get("transport", ""),
        "lines": trajectory.render(complete),
        "next_cursor": cursor + len(complete),
    }


@mcp.tool()
def cancel_query(run_id: str) -> str:
    """Stop following a run. The agent keeps working; only the stream ends."""
    run_dir = RUNS / run_id
    if not run_dir.exists():
        return f"no run {run_id}"
    (run_dir / "status").write_text(json.dumps({"state": "cancelled"}))
    return f"{run_id} marked cancelled"


if __name__ == "__main__":
    mcp.run()
