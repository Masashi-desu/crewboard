# Crewboard

A job board that **humans and AI agents both view and operate**. FastAPI + SQLite, a single-page static UI (Japanese), a REST API, an MCP (Streamable HTTP) endpoint, WebMCP tools in the browser, and live updates via Server-Sent Events.

人と AI エージェントが同じボードを見て操作するジョブボードです（日本語は下部）。

## Features
- Kanban (wait / ready / run, drag to move), draft jobs (no tasks yet), done history, light/dark theme
- Jobs contain ordered tasks; the *current assignee* is the assignee of the first unfinished task
- Auto-done: a job becomes `done` when all its tasks are done, and returns to `run` when an unfinished task appears
- Master data: assignees (human / bot, with avatars) and colored group tags
- In-place editing design rule: switching view → edit never moves elements
- Live updates: `GET api/events` (SSE) — every client re-renders when anyone (human or agent) changes something
- Operating rules for agents in `rules.md` (served via MCP instructions, `crewboard://rules`, `get_rules`, `GET api/rules`)

## Quick start
```bash
cp .env.example .env          # set CREWBOARD_MCP_TOKEN
python -m venv .venv
.venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip ...
.venv/bin/python run.py                       # http://127.0.0.1:8090/
```
On Windows, install with `.venv\Scripts\pip.exe install -r requirements.txt`, then run `start.cmd` or `.venv\Scripts\python.exe run.py`. A local `crewboard.vbs` wrapper can launch the same `run.py` without a console; it is not distributed with this repository.
On first start an empty data dir is created and seeded with generic sample jobs and two assignees (`Owner`, `Agent Bot`). Rename them and add avatars in マスタ管理.

## Configuration (environment / `.env`)
| Variable | Default | |
|---|---|---|
| `CREWBOARD_MCP_TOKEN` | – | Bearer token for `/mcp/` (required for MCP) |
| `CREWBOARD_API_TOKEN` | empty | Optional bearer token for every `/api/*` endpoint, including SSE |
| `CREWBOARD_ALLOWED_HOSTS` | empty | Comma-separated MCP Host allowlist; setting it enables MCP Host/Origin validation |
| `CREWBOARD_DATA_DIR` | `data` | SQLite DB (`jobs.db`), `avatars/`, optional `rules.md` override |
| `CREWBOARD_HOST` / `CREWBOARD_PORT` | `127.0.0.1` / `8090` | used by `run.py` |
| `CREWBOARD_BASE_PATH` | empty | public sub-path when behind a prefix-stripping proxy (e.g. `/crewboard`) |
| `CREWBOARD_RULES_FILE` | `<data>/rules.md` if present, else `rules.md` | operating rules |
| `CREWBOARD_MIGRATION_ENABLED` | empty | Set `1` only on an isolated copy to enable migration writes; dry-run is always available |

The UI uses only relative URLs, so it works at the root or under any sub-path. Example Caddy config:
```
redir /crewboard /crewboard/ 308
handle_path /crewboard/* {
	reverse_proxy 127.0.0.1:8090 {
		flush_interval -1   # needed for SSE
	}
}
```

## API
- REST: `GET/POST api/jobs`, `GET/PATCH/DELETE api/jobs/{id}`, `POST api/jobs/{id}/tasks`, `PATCH/DELETE api/tasks/{id}`, `GET/POST api/assignees`, `PATCH/DELETE api/assignees/{name}`, `PUT/DELETE api/assignees/{name}/icon`, `GET/POST api/group_tags`, `PATCH/DELETE api/group_tags/{name}`, `PUT api/jobs/{id}/assignees`, `GET api/matrix`, `GET api/rules`, `GET api/events` (SSE). OpenAPI docs at `docs`.
- MCP (Streamable HTTP, stateless): `<base>/mcp/` with header `Authorization: Bearer <CREWBOARD_MCP_TOKEN>`. Tools: get_rules, list_jobs, get_job, create_job, update_job, move_job, delete_job, add_task, update_task, delete_task, get_matrix, assign_job, list_assignees, add_assignee, update_assignee, delete_assignee, list_group_tags, add_group_tag, update_group_tag, delete_group_tag.
- Migration tools: source_refs, dry_run_migration, import_migration, get_migration_batch (REST: `api/source_refs`, `api/migrations/dry_run`, `api/migrations`, `api/migrations/{batch_id}`).
- WebMCP: if `navigator.modelContext` exists, the page registers 21 tools sharing names with the 24 MCP tools, omitting `delete_task`, `delete_assignee`, and `delete_group_tag`. Job/task writes and filters share typed REST/MCP/WebMCP schemas, including sort, priority, importance, wait, tags and source fields. `delete_job` requires `confirm:true`.

## Security
- By default, Crewboard is intended for a trusted network (such as a private tailnet) or an authenticating reverse proxy. REST reads and writes are unauthenticated while `CREWBOARD_API_TOKEN` is empty. Bind to loopback by default; do not expose this configuration directly to an untrusted network.
- Set a strong, independent `CREWBOARD_API_TOKEN` to require `Authorization: Bearer <token>` for **all `/api/*` endpoints**. `/healthz`, the static UI, avatars, and API documentation remain accessible; this token is not a login system or per-user authorization.
- The bundled UI prompts once per page load after a 401, stores the API token in `localStorage`, and attaches it to API fetches, including WebMCP. Use HTTPS and a trusted browser profile. To replace a saved token, clear the `crewboard-api-token` localStorage entry and reload.
- Native `EventSource` cannot set an Authorization header, so the UI sends the API token as `api/events?token=<token>`. Only `GET /api/events` accepts a query token; other API endpoints require the header. Configure proxy/access logs to omit or redact SSE query strings.
- `/mcp/` always requires `CREWBOARD_MCP_TOKEN`; an empty token disables MCP access. The API token and MCP token are separate.
- MCP Host/Origin validation is enabled **only** when `CREWBOARD_ALLOWED_HOSTS` is set. List exact Host header values, including ports where applicable, for example `board.example.com,127.0.0.1:8090`; the MCP SDK also supports `host:*` port patterns. HTTP and HTTPS origins for those hosts are accepted. List the public host forwarded by your reverse proxy. Empty preserves compatibility with arbitrary private-network hostnames, with no MCP DNS rebinding protection.
- Avatar URLs must be HTTP(S) and resolve exclusively to public IP addresses. Private, loopback, link-local, reserved, multicast, unspecified and non-global addresses are rejected, including IPv4-mapped addresses. Connections use the validated IPs without a second DNS lookup, verify HTTPS certificates, ignore proxy environment variables, reject redirects, and limit downloads to 5 MiB with 15-second network timeouts.
- Uploaded avatars are decoded and converted to 128px WebP; inputs are limited to 5 MiB and 16 megapixels. SVG requires optional CairoSVG plus native Cairo; without them it returns a descriptive 400. External SVG resources are disabled.

## Tests
Migration contract, additive schema, backup/restore and copy-environment procedure: [docs/migration.md](docs/migration.md).
For pytest, install `requirements-dev.txt` and run `python -m pytest tests/ -q`.
With dependencies installed, run `python -m unittest discover -s tests -v`. The suite uses temporary data directories, a disposable local server, and test-only tokens; it never writes the normal `data/` or `.env`.

UI authentication tests require Node.js: `node --test tests/test_ui_auth.cjs`.

The individual `tests/test_*_mcp.py` and `tests/test_mcp_client.py` scripts can also target a running server via `CREWBOARD_MCP_URL`. They create/delete test data, so run them only against a disposable server.

## Data & privacy
Everything operational lives in the data dir and `.env`, both git-ignored. The repository only contains code, the UI, docs, the default `rules.md` and generic seed data.

## License
[MIT](LICENSE) © 2026 Crewboard contributors

---

## 日本語（概要）
Crewboard は、人と AI エージェントが同じボードを見て操作するためのジョブボードです。

- 起動: `.env.example` を `.env` にコピーしてトークンを設定 → `python -m venv .venv` → `pip install -r requirements.txt` → `python run.py`
- データ（SQLite・アバター・ローカルの運用ルール `data/rules.md`）は `CREWBOARD_DATA_DIR`（既定 `data/`）に保存され、Git 管理外です。
- 初回起動時は汎用サンプルジョブと担当者 2 名（Owner / Agent Bot）が作成されます。
- サブパス配信（例 `/crewboard/`）は相対パスで対応。リバースプロキシで SSE のためバッファリングを無効化してください（Caddy: `flush_interval -1`）。
- AI 向け運用ルールは `rules.md`（MCP の instructions・`get_rules`・`GET api/rules` で配信）。
- REST は既定で信頼ネットワーク前提です。`CREWBOARD_API_TOKEN` 設定時だけ全 `/api/*` に認証を要求します。MCP は常に `CREWBOARD_MCP_TOKEN` が必要です。`CREWBOARD_ALLOWED_HOSTS` 設定時だけ MCP の Host/Origin 検証が有効になります。詳細は Security 節を参照してください。
- ライセンス: MIT（LICENSE）
- デザインルール: 表示→編集で要素の位置を動かさない（`.v` / `.e` を同じ場所に置き `setEd()` で切替）。
