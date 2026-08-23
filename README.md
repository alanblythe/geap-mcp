# geap-mcp

An MCP server for talking to agents deployed on Gemini Enterprise Agent
Platform. Send a message to a deployed agent and follow what it does, from any
MCP client — Antigravity CLI, Claude Code, or anything else that speaks the
protocol.

Google's managed Agent Platform MCP server covers generation, prediction,
notebooks, endpoints, models, tuning, evaluation and prompts. It does not cover
reasoning engines, so there is no way to reach a deployed agent from an MCP
client. That is the gap this fills.

## Tools

| Tool | What it does |
| :--- | :--- |
| `list_agents` | List the agents deployed in a project and region |
| `start_query` | Send a message to a deployed agent; returns a run id immediately |
| `read_query` | Read what the run has done since a cursor, one line per action |
| `cancel_query` | Stop following a run; the agent keeps working |

`engine` takes a display name, a numeric id, or a full resource name, so
`list_agents` output goes straight back in. `message` is passed through untouched — prose for a conversational agent, a
JSON string for one expecting a job. Knowing which the agent wants is the
caller's business.

Queries do not block. An agent's run can outlast any client timeout, so
`start_query` returns a run id and `read_query` is polled against it. Run state
is a directory under the system temp directory rather than memory, because an
MCP server is started per client session and restarted freely: a run held in
memory would not survive the gap between the call that started it and the call
that reads it.

## Install

As an Antigravity CLI plugin:

```shell
git clone https://github.com/alanblythe/geap-mcp
agy plugin install ./geap-mcp
```

Servers supplied by a plugin appear in the TUI's MCP view under
`Plugins (~/.gemini/config/plugins)`, not in `agy mcp list`, which reports only
what `agy mcp add` registered.

For any other MCP client, run `bin/serve.sh` over stdio.

Credentials come from Application Default Credentials
(`gcloud auth application-default login`), falling back to
`gcloud auth print-access-token`. `uv` provides the dependencies at launch;
nothing needs installing first.

## Two things about Agent Platform that this encodes

**A container engine and a pickled one answer on different routes.** An engine
with a `sourceCodeSpec` answers on a route of its own, and `:streamQuery`
returns 404 for it — a 404 built from the right project and region, which reads
like a missing agent rather than a wrong endpoint. `transport` defaults to
`auto` and picks by that field; pass `stream_query` or `container` to override.

**`classMethods` cannot tell the two apart.** A container engine publishes them
too, `async_stream_query` included.

## Status

Early. All four tools work against a live container engine. Sessions and
memory are not built yet.
