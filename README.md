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
uv run es-steward tui --help
uv run es-steward tui show --prefix logs-
```

Missing flags are prompted (forms). TUI subcommands: `show`, `promote`, `redact`, `journal`. Other mutations are CLI / HTTP only.

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

Requires **`mcp>=2.1`** (`MCPServer`; FastMCP is 1.x and is gone). Tools: `steward_show`,
`steward_journal`, `steward_promote_dry_run` (always dry-run), `steward_redact` (`execute`
defaults false). Empty selection and bad arguments raise MCP `ToolError` with the message.
