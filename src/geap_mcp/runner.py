"""Stream one query to its log, detached from whoever asked for it.

Run state is the log file, not memory: an MCP server is started per client
session and restarted freely, so a run held in a dict would vanish between the
call that started it and the call that reads it.
"""

import json
import pathlib
import sys

from . import client


def run(run_dir: str, engine: str, message: str, user_id: str,
        session_id: str | None, project: str | None, location: str | None,
        transport: str, class_method: str) -> int:
    directory = pathlib.Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "events.ndjson"
    status = directory / "status"

    def finish(state: str, detail: str = "") -> int:
        # Merged, not overwritten: which transport and engine answered is most
        # wanted once a run has failed, and that is written before it can fail.
        try:
            known = json.loads(status.read_text())
        except (OSError, json.JSONDecodeError):
            known = {}
        known.update({"state": state, "detail": detail})
        status.write_text(json.dumps(known))
        return 0 if state == "done" else 1

    try:
        token = client.access_token()
        resolved = client.resolve(engine, project, location, token)
        url, chosen = client.query_url(resolved, transport)
        status.write_text(json.dumps({
            "state": "running", "transport": chosen,
            "engine": resolved["id"], "display_name": resolved["display_name"],
        }))
        payload = client.body(message, user_id, session_id, class_method)
        response = client.call(url, token, payload, stream=True)
        with open(log, "ab", buffering=0) as out:
            for line in response:
                out.write(line)
    except Exception as error:  # the detail is the whole value of a failed run
        return finish("error", f"{type(error).__name__}: {error}")
    return finish("done")


if __name__ == "__main__":
    # One JSON argument, so an absent session_id stays absent rather than
    # arriving as the string "None".
    sys.exit(run(**json.loads(sys.argv[1])))
