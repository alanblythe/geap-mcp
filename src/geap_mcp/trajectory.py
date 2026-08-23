"""Render an agent's event stream as one line per action.

The wire carries whole files in a write's arguments and one-line summaries in a
response, so the call is what gets shown and the response is not. Anything that
does not parse is dropped: a stream format change should go quiet, not take the
caller down with it.
"""

import json
import sys

VERBS = {
    "view_file": "read",
    "find_file": "find",
    "run_command": "run",
    "edit_file": "edit",
    "commit_and_push": "push",
    "time_remaining": "clock",
}

WIDTH = 88


def _detail(name: str, args: dict) -> str:
    if name == "run_command":
        return args.get("command_line", "")
    if name in ("view_file", "edit_file"):
        return args.get("file_path", "").split("/repo/")[-1]
    if name == "find_file":
        return args.get("query", "")
    if name == "commit_and_push":
        return args.get("message", "").split("\n")[0]
    if name == "time_remaining":
        return ""
    return json.dumps(args)


def _clip(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= WIDTH else text[: WIDTH - 1] + "…"


def render(lines) -> list[str]:
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            parts = (event.get("content") or {}).get("parts") or []
        except Exception:
            continue
        for part in parts:
            if "text" in part:
                out.append("~ " + _clip(part["text"]))
            call = part.get("function_call")
            if call:
                name = call.get("name", "?")
                verb = VERBS.get(name, name)
                out.append(f"> {verb:<5} {_clip(_detail(name, call.get('args') or {}))}")
            response = part.get("function_response")
            # Only the edits: their summary says what changed, which the call
            # -- a bare path -- does not.
            if response and response.get("name") == "edit_file":
                said = (response.get("response") or {}).get("result", "")
                if said:
                    out.append(f"    {_clip(said)}")
    return out


if __name__ == "__main__":
    for rendered in render(sys.stdin):
        print("  " + rendered)
