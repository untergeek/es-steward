# Steward

Elasticsearch index hygiene CLI (`es-steward --help`).

PyPI / console script: **`es-steward`**. Import package: **`es_steward`**. Tracking index: **`es-steward-journal`**.

Depends on unpublished **`es-tools`** (path `../es-tools`) including the `[cli]` extra.

## Install (dev)

```bash
cd /Users/buh/WORK/es-steward
uv sync --extra dev
uv run es-steward --help
```

Selectors live in `es_tools.select`. Predicates and `promote --dry-run` are S1. `redact` is hot-path `update_by_query` via `es_tools.redact.RedactFields`. Default is dry-run (`persist=False`); pass `--execute` to mutate and journal.

## TUI

```bash
uv sync --extra tui --extra dev
```

`es-steward tui` takes no arguments.
The screen shows the text hello. Binding q quits.
Screens named workshop, show, and journal are registered and are not opened.
There is no promote screen and no redact screen.

## API

```bash
uv sync --extra api --extra dev
export STEWARD_API_TOKEN=secret
uv run uvicorn es_steward.api.app:app --port 8137
curl http://127.0.0.1:8137/
curl -H 'X-Steward-Token: secret' http://127.0.0.1:8137/journal/workbooks
```

Mutations: `POST /actions/{promote,redact,alias,delete,close,open,delete-snapshots,snapshot,restore,forcemerge,allocation,replicas,shrink,rollover,reindex,index-settings,cluster-routing,cold2frozen,create-index}` (see OpenAPI / `--help`). Invalid bodies return **422**
(Pydantic models, `extra=forbid`). Redact defaults `execute=false` (dry-run). Client YAML is
process-level only (`create_app(config=...)` / env); request bodies have no `config` field.
Cluster-down / transport errors return **503**. Token compare uses `hmac.compare_digest`.

## MCP

```bash
uv sync --extra mcp --extra dev
uv run es-steward-mcp
```

Requires **`mcp>=2.1`** (`MCPServer`; FastMCP is 1.x and is gone). Empty selection and bad arguments raise MCP `ToolError` with the message.
The MCP server registers 24 tools. Each tool calls the HTTP API. The API must already be running.
If either STEWARD_API_URL or STEWARD_API_TOKEN is unset, the tool call fails with an error that names both variables.
