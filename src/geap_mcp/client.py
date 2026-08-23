"""Resolving and calling agents on Gemini Enterprise Agent Platform.

Two engines answer on two different routes. A pickled or ADK engine answers on
`:streamQuery`. A container engine -- one with a `sourceCodeSpec` -- answers on
a route of its own, and `:streamQuery` returns 404 for it: a 404 built from the
right project and region reads like a missing agent rather than a wrong
endpoint.

Both publish `classMethods`, so those cannot be used to tell them apart.
"""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
FULL_NAME = re.compile(r"^projects/[^/]+/locations/[^/]+/reasoningEngines/[^/]+$")


def access_token() -> str:
    """ADC first, because it is the same story on a laptop, Cloud Shell and CI.

    Only a missing credential falls back to gcloud. Catching everything here
    reports an import error or an expired refresh token as "no credentials",
    which sends the reader to fix the one thing that was not wrong.
    """
    import google.auth
    import google.auth.transport.requests
    from google.auth.exceptions import DefaultCredentialsError

    try:
        credentials, _ = google.auth.default(scopes=[SCOPE])
    except DefaultCredentialsError:
        out = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=False,
        )
        token = out.stdout.strip()
        if token:
            return token
        raise RuntimeError(
            "no credentials: run `gcloud auth application-default login`, or set "
            "CLOUDSDK_CONFIG if your ADC lives outside ~/.config/gcloud"
        ) from None
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def default_project() -> str:
    for key in ("GOOGLE_CLOUD_PROJECT", "CLOUDSDK_CORE_PROJECT"):
        if os.environ.get(key):
            return os.environ[key]
    out = subprocess.run(
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True, check=False,
    )
    project = out.stdout.strip()
    if project and project != "(unset)":
        return project
    raise RuntimeError("no project: pass project=, or set GOOGLE_CLOUD_PROJECT")


def call(url: str, token: str, body: dict | None = None, stream: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    response = urllib.request.urlopen(request)
    return response if stream else json.load(response)


def host(location: str) -> str:
    # MODEL_LOCATION is "global"; interpolated here it gives a host that does
    # not resolve, and the failure looks like DNS rather than like config.
    if location == "global":
        raise ValueError("'global' is a model endpoint, not a region")
    return f"https://{location}-aiplatform.googleapis.com"


def _describe(detail: dict, project: str, location: str) -> dict:
    spec = detail.get("spec", {}) or {}
    return {
        "id": detail.get("name", "").split("/")[-1],
        "project": project,
        "location": location,
        "name": detail.get("name", ""),
        "display_name": detail.get("displayName", ""),
        "created": detail.get("createTime", ""),
        "class_methods": [m.get("name") for m in (spec.get("classMethods") or [])],
        # A container engine publishes classMethods too, so those cannot pick
        # the route. sourceCodeSpec is what :streamQuery 404s on.
        "container": bool(spec.get("sourceCodeSpec")),
        # An engine with no deploymentSpec runs no code: it holds sessions and
        # cannot be queried, and listing it as available is how a dispatch ends
        # up aimed at nothing.
        "deployed": bool(spec.get("deploymentSpec")),
    }


def where(project: str | None, location: str | None) -> tuple[str, str]:
    project = project or default_project()
    location = location or os.environ.get("AGENT_ENGINE_LOCATION")
    if not location:
        raise ValueError(
            "no location: pass location=, or set AGENT_ENGINE_LOCATION. Agent "
            "Platform is regional, so there is nowhere to look without one."
        )
    return project, location


def list_engines(project: str | None, location: str | None, token: str) -> list[dict]:
    project, location = where(project, location)
    base = f"{host(location)}/v1/projects/{project}/locations/{location}/reasoningEngines"
    listed = call(base, token).get("reasoningEngines", []) or []
    return [_describe(e, project, location) for e in listed]


def resolve(engine: str, project: str | None, location: str | None, token: str) -> dict:
    """Take a full resource name, a numeric id, or a display name."""
    if FULL_NAME.match(engine):
        _, project, _, location, _, engine_id = engine.split("/")
    elif engine.isdigit():
        engine_id = engine
        project, location = where(project, location)
    else:
        # A display name, which is what a person calls it and what the console
        # shows. Not unique by construction, so an ambiguous one is refused
        # rather than guessed.
        project, location = where(project, location)
        matches = [e for e in list_engines(project, location, token)
                   if e["display_name"] == engine]
        if not matches:
            known = [e["display_name"] for e in list_engines(project, location, token)]
            raise ValueError(
                f"no agent named {engine!r} in {project}/{location}. Found: {known or 'none'}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"{len(matches)} agents are named {engine!r} in {project}/{location}: "
                f"{[m['id'] for m in matches]}. Pass an id."
            )
        return matches[0]

    base = f"{host(location)}/v1/projects/{project}/locations/{location}/reasoningEngines"
    detail = call(f"{base}/{engine_id}", token)
    spec = detail.get("spec", {}) or {}
    return _describe(detail, project, location)


def query_url(engine: dict, transport: str) -> tuple[str, str]:
    """The URL to POST to, and which transport was chosen."""
    if transport == "auto":
        transport = "container" if engine["container"] else "stream_query"
    base = host(engine["location"])
    if transport == "stream_query":
        return (
            f"{base}/v1/projects/{engine['project']}/locations/{engine['location']}"
            f"/reasoningEngines/{engine['id']}:streamQuery?alt=sse",
            transport,
        )
    return (
        f"{base}/reasoningEngines/v1/projects/{engine['project']}"
        f"/locations/{engine['location']}/reasoningEngines/{engine['id']}"
        f"/api/api/stream_reasoning_engine",
        transport,
    )


def body(message: str, user_id: str, session_id: str | None, class_method: str) -> dict:
    payload = {"user_id": user_id, "message": message}
    if session_id:
        payload["session_id"] = session_id
    return {"class_method": class_method, "input": payload}
