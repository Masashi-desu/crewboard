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
On first start an empty data dir is created and seeded with generic sample jobs and two assignees (`Owner`, `Agent Bot`). Rename them and add avatars in マスタ管理.

## Configuration (environment / `.env`)
| Variable | Default | |
|---|---|---|
| `CREWBOARD_MCP_TOKEN` | – | Bearer token for `/mcp/` (required for MCP) |
| `CREWBOARD_DATA_DIR` | `data` | SQLite DB (`jobs.db`), `avatars/`, optional `rules.md` override |
| `CREWBOARD_HOST` / `CREWBOARD_PORT` | `127.0.0.1` / `8090` | used by `run.py` |
| `CREWBOARD_BASE_PATH` | empty | public sub-path when behind a prefix-stripping proxy (e.g. `/crewboard`) |
| `CREWBOARD_RULES_FILE` | `<data>/rules.md` if present, else `rules.md` | operating rules |

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
- WebMCP: if `navigator.modelContext` exists, the page registers the same tools (except destructive ones without `confirm:true`).
- Smoke tests against a running server: `python tests/test_rules_mcp.py` etc. (they create/delete test data).

## Data & privacy
Everything operational lives in the data dir and `.env`, both git-ignored. The repository only contains code, the UI, docs, the default `rules.md` and generic seed data.

## License
TBD.

---

## 日本語（概要）
Crewboard は、人と AI エージェントが同じボードを見て操作するためのジョブボードです。

- 起動: `.env.example` を `.env` にコピーしてトークンを設定 → `python -m venv .venv` → `pip install -r requirements.txt` → `python run.py`
- データ（SQLite・アバター・ローカルの運用ルール `data/rules.md`）は `CREWBOARD_DATA_DIR`（既定 `data/`）に保存され、Git 管理外です。
- 初回起動時は汎用サンプルジョブと担当者 2 名（Owner / Agent Bot）が作成されます。
- サブパス配信（例 `/crewboard/`）は相対パスで対応。リバースプロキシで SSE のためバッファリングを無効化してください（Caddy: `flush_interval -1`）。
- AI 向け運用ルールは `rules.md`（MCP の instructions・`get_rules`・`GET api/rules` で配信）。
- デザインルール: 表示→編集で要素の位置を動かさない（`.v` / `.e` を同じ場所に置き `setEd()` で切替）。
