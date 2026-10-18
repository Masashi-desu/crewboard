import os, contextlib, secrets
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import db, avatars, asyncio, json, itertools, functools
from fastapi.responses import StreamingResponse
# ---- SSE broadcast ----
_LOOP = None; _SUBS = set(); _SEQ = itertools.count(1)
def _broadcast(ev):
    if _LOOP is None: return
    def push():
        ev2 = {**ev, "id": next(_SEQ)}
        for q in list(_SUBS):
            try: q.put_nowait(ev2)
            except asyncio.QueueFull: pass
    _LOOP.call_soon_threadsafe(push)
db.LISTENERS.append(_broadcast)
_orig_set_icon = avatars.set_icon
@functools.wraps(_orig_set_icon)
def _set_icon(*a, **k):
    r = _orig_set_icon(*a, **k); _broadcast({"type": "set_icon", "scope": "master", "job_ids": []}); return r
avatars.set_icon = _set_icon

import config
HERE = config.HERE
TOKEN = config.MCP_TOKEN
API_TOKEN = config.API_TOKEN
def rules_text():
    with open(config.rules_path(), encoding="utf-8") as source: return source.read()
R_JOB = "ルール: status は wait(着手不可/待ち)/ready(着手可)/run(進行中)/done(完了→完了履歴)。priority low|normal|high|urgent, importance low|normal|high。group_tag はマスタ登録済みのみ。自動完了: 全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。"
R_TASK = "ルール: タスクは上から順に実行（先頭の未完了タスクの担当=現在の担当）。title必須・body任意。assignee はマスタ(list_assignees)の名前が必須。完了は status=done。全タスクが完了するとジョブは自動で done になる（自分でジョブのステータスを変える必要はない）。done のジョブに未完了タスクが生じる（タスクを todo/doing に戻す・未完了タスクを追加）と自動で run に戻る。詳細は get_rules。"
db.init()

mcp = FastMCP("crewboard", stateless_http=True, streamable_http_path="/",
              transport_security=TransportSecuritySettings(
                  enable_dns_rebinding_protection=bool(config.ALLOWED_HOSTS),
                  allowed_hosts=config.ALLOWED_HOSTS,
                  allowed_origins=[f"{scheme}://{host}" for host in config.ALLOWED_HOSTS for scheme in ("http", "https")]),
              instructions="Crewboard: a job board that humans and AI agents both view and operate (Japanese UI). Read the operating rules first via get_rules or resource crewboard://rules.\n\n" + rules_text())
@mcp.resource("crewboard://rules", name="rules", description="Crewboard 運用ルール（日本語）", mime_type="text/markdown")
def rules_resource() -> str:
    return rules_text()
@mcp.resource("jobboard://rules", name="rules_legacy", description="Crewboard 運用ルール（旧URI互換）", mime_type="text/markdown")
def rules_resource_legacy() -> str:
    return rules_text()
@mcp.tool()
def get_rules() -> str:
    """Crewboard の運用ルール（日本語 Markdown）を返す。操作前に一度読むこと。"""
    return rules_text()
@mcp.tool()
def list_jobs(status: Optional[str]=None, query: Optional[str]=None, priority: Optional[str]=None, group_tag: Optional[str]=None, group_tags: Optional[List[str]]=None) -> list:
    """List jobs (with tasks; current_assignee = assignee of the first not-done task). status: wait|ready|run|done. priority: low|normal|high|urgent(最優先)."""
    return db.list_jobs(status, query, priority, group_tag, group_tags=group_tags)
@mcp.tool()
def get_job(job_id: int) -> dict:
    """Get a job with its tasks and history."""
    return db.get_job(job_id)
@mcp.tool()
def create_job(title: str, status: str="wait", priority: str="normal", importance: str="normal", tags: Optional[List[str]]=None,
               group_tag: str="", conditions: str="", policy: str="", note: str="") -> dict:
    """Create a job. priority low|normal|high|urgent, importance low|normal|high. conditions=完了条件, policy=方針, note=その他."""
    return db.create_job(title, status, priority, importance, tags, group_tag, conditions, policy, note)
@mcp.tool()
def update_job(job_id: int, assignees: Optional[List[str]]=None, title: Optional[str]=None, status: Optional[str]=None, priority: Optional[str]=None, importance: Optional[str]=None,
               tags: Optional[List[str]]=None, group_tag: Optional[str]=None, conditions: Optional[str]=None, policy: Optional[str]=None, note: Optional[str]=None) -> dict:
    """Update fields of a job (only provided fields change)."""
    return db.update_job(job_id, assignees=assignees, title=title, status=status, priority=priority, importance=importance, tags=tags, group_tag=group_tag, conditions=conditions, policy=policy, note=note)
@mcp.tool()
def move_job(job_id: int, status: str) -> dict:
    """Move a job to another column: wait|ready|run|done (done = 完了履歴)."""
    return db.move_job(job_id, status)
@mcp.tool()
def delete_job(job_id: int) -> dict:
    """Permanently delete a job with its tasks and history (not moved to 完了履歴)."""
    return db.delete_job(job_id)
@mcp.tool()
def add_task(job_id: int, title: str, body: str="", status: str="todo", assignee: Optional[str]=None, priority: str="normal", importance: str="normal",
             wait_reason: str="", wait_for: str="", wait_note: str="", resume_condition: str="") -> dict:
    """Add a task. wait blocks execution; null/empty assignee remains unassigned."""
    return db.add_task(job_id, title, body, status, assignee, priority, importance, wait_reason, wait_for, wait_note, resume_condition)
@mcp.tool()
def update_task(task_id: int, title: Optional[str]=None, body: Optional[str]=None, status: Optional[str]=None, assignee: Optional[str]=None,
                priority: Optional[str]=None, importance: Optional[str]=None) -> dict:
    """Update a task (e.g. status='done' to complete it)."""
    return db.update_task(task_id, **{k:v for k,v in dict(title=title, body=body, status=status, assignee=assignee, priority=priority, importance=importance).items() if v is not None})
@mcp.tool()
def delete_task(task_id: int) -> dict:
    """Delete a task."""
    return db.delete_task(task_id)
@mcp.tool()
def get_matrix(include_done: bool=False) -> dict:
    """Matrix view: jobs grouped by priority (x: low|normal|high|urgent) x importance (y: low|normal|high). Change position with update_job(priority/importance)."""
    return db.get_matrix(include_done)
@mcp.tool()
def list_assignees() -> list:
    """List assignees (humans and AI agent bots) with job_count and open_task_count."""
    return db.list_assignees(True)
@mcp.tool()
def assign_job(job_id: int, assignees: List[str]) -> dict:
    """Set the job-level assignees (replaces the list). Task assignees are set via add_task/update_task.
    ジョブ担当は任意の概要情報。実際の担当はタスクの assignee（マスタ登録名）。"""
    return db.assign_job(job_id, assignees)
@mcp.tool()
def add_assignee(name: str, kind: str="bot") -> list:
    """Add a new assignee (e.g. a new bot). kind: bot|human."""
    return db.add_assignee(name, kind)
@mcp.tool()
def update_assignee(name: str, new_name: Optional[str]=None, kind: Optional[str]=None,
                    icon_url: Optional[str]=None, icon_base64: Optional[str]=None, remove_icon: bool=False) -> list:
    """Rename an assignee (references updated), change kind, or set the avatar from icon_url (http/https) or
    icon_base64 (png/jpg/webp/svg, data: URL ok; converted to 128px webp). remove_icon=true removes it."""
    res = db.update_assignee(name, new_name, kind); name = new_name or name
    if remove_icon: res = avatars.set_icon(name, None)
    elif icon_base64: res = avatars.set_icon(name, avatars.decode_b64(icon_base64))
    elif icon_url: res = avatars.set_icon(name, avatars.fetch_url(icon_url))
    return res
@mcp.tool()
def delete_assignee(name: str) -> list:
    """Delete an assignee. Fails if still used by any task or job (reassign first)."""
    return db.delete_assignee(name)
@mcp.tool()
def list_group_tags() -> list:
    """List registered group tags (name, color, job_count)."""
    return db.list_group_tags()
@mcp.tool()
def add_group_tag(name: str, color: str="") -> list:
    """Register a group tag. color: CSS color like #3b82f6 (optional)."""
    return db.add_group_tag(name, color)
@mcp.tool()
def update_group_tag(name: str, new_name: Optional[str]=None, color: Optional[str]=None) -> list:
    """Rename a group tag (jobs are updated) and/or change color."""
    return db.update_group_tag(name, new_name, color)
@mcp.tool()
def delete_group_tag(name: str) -> list:
    """Delete a group tag; jobs using it become untagged."""
    return db.delete_group_tag(name)

for _n, _r in [("create_job", R_JOB), ("update_job", R_JOB), ("move_job", R_JOB), ("add_task", R_TASK), ("update_task", R_TASK), ("delete_task", R_TASK)]:
    _t = mcp._tool_manager.get_tool(_n); _t.description = (_t.description or "").strip() + "\n" + _r
mcp_app = mcp.streamable_http_app()
@contextlib.asynccontextmanager
async def lifespan(app):
    global _LOOP; _LOOP = asyncio.get_running_loop()
    async with mcp.session_manager.run(): yield
app = FastAPI(title="Crewboard API", lifespan=lifespan, docs_url=None, redoc_url=None,
              servers=[{"url": config.BASE_PATH}] if config.BASE_PATH else None)
from fastapi.openapi.docs import get_swagger_ui_html
@app.get("/docs", include_in_schema=False)
def docs(): return get_swagger_ui_html(openapi_url="openapi.json", title="Crewboard API")  # relative: works under a sub-path

@app.middleware("http")
async def mcp_auth(request: Request, call_next):
    def authorized(token):
        return bool(token) and secrets.compare_digest(
            request.headers.get("authorization", "").encode(), f"Bearer {token}".encode())
    if request.url.path.startswith("/mcp"):
        allowed = authorized(TOKEN)
    elif API_TOKEN and (request.url.path == "/api" or request.url.path.startswith("/api/")):
        allowed = authorized(API_TOKEN)
        if request.method == "GET" and request.url.path == "/api/events":
            allowed = allowed or secrets.compare_digest(request.query_params.get("token", "").encode(), API_TOKEN.encode())
    else:
        allowed = True
    if not allowed:
        return JSONResponse({"error": "unauthorized"}, status_code=401,
                            headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})
    resp = await call_next(request)
    if request.url.path.startswith(("/static", "/api")): resp.headers["Cache-Control"] = "no-cache"
    return resp

def wrap(fn, *a, **k):
    try: return fn(*a, **k)
    except KeyError as e: raise HTTPException(404, str(e))
    except ValueError as e: raise HTTPException(400, str(e))

class JobIn(BaseModel):
    title: Optional[str]=None; status: Optional[str]=None; priority: Optional[str]=None; importance: Optional[str]=None
    assignees: Optional[List[str]]=None; tags: Optional[List[str]]=None; group_tag: Optional[str]=None; conditions: Optional[str]=None; policy: Optional[str]=None
    note: Optional[str]=None; sort: Optional[float]=None
    group_tags: Optional[List[str]]=None
    source: Optional[dict]=None
    source_history: Optional[List[dict]]=None
class TaskIn(BaseModel):
    title: Optional[str]=None; body: Optional[str]=None; status: Optional[str]=None; assignee: Optional[str]=None
    priority: Optional[str]=None; importance: Optional[str]=None; sort: Optional[float]=None
    wait_reason: Optional[str]=None; wait_for: Optional[str]=None
    wait_note: Optional[str]=None; resume_condition: Optional[str]=None
    source: Optional[dict]=None
    source_history: Optional[List[dict]]=None
class AssigneeIn(BaseModel):
    name: str; kind: str="bot"

@app.get("/api/jobs")
def api_list(status: Optional[str]=None, q: Optional[str]=None, priority: Optional[str]=None, group_tag: Optional[str]=None, group_tags: Optional[List[str]]=Query(None)):
    return db.list_jobs(status, q, priority, group_tag, group_tags=group_tags)
@app.post("/api/jobs", status_code=201)
def api_create(j: JobIn):
    if not j.title: raise HTTPException(400, "title required")
    return wrap(db.create_job, **j.model_dump(exclude_none=True, exclude={"sort"}))
@app.get("/api/jobs/{job_id}")
def api_get(job_id: int): return wrap(db.get_job, job_id)
@app.patch("/api/jobs/{job_id}")
def api_update(job_id: int, j: JobIn): return wrap(db.update_job, job_id, **j.model_dump(exclude_unset=True))
@app.delete("/api/jobs/{job_id}")
def api_delete(job_id: int): return wrap(db.delete_job, job_id)
@app.post("/api/jobs/{job_id}/tasks", status_code=201)
def api_add_task(job_id: int, t: TaskIn): return wrap(db.add_task, job_id, **t.model_dump(exclude_unset=True, exclude={"sort"}))
@app.patch("/api/tasks/{task_id}")
def api_update_task(task_id: int, t: TaskIn): return wrap(db.update_task, task_id, **t.model_dump(exclude_unset=True))
@app.delete("/api/tasks/{task_id}")
def api_delete_task(task_id: int): return db.delete_task(task_id)
@app.get("/api/assignees")
def api_assignees(): return db.list_assignees(True)
@app.get("/api/source_refs")
def api_source_refs(system: str, uuid: Optional[str]=None, number: Optional[str]=None):
    return wrap(db.source_refs, system, uuid, number)
class AssignIn(BaseModel):
    assignees: List[str]
@app.put("/api/jobs/{job_id}/assignees")
def api_assign(job_id: int, a: AssignIn): return wrap(db.assign_job, job_id, a.assignees)
@app.post("/api/assignees", status_code=201)
def api_add_assignee(a: AssigneeIn): return wrap(db.add_assignee, a.name, a.kind)
class MasterUpd(BaseModel):
    new_name: Optional[str]=None; kind: Optional[str]=None; color: Optional[str]=None
class IconIn(BaseModel):
    data_base64: Optional[str]=None; url: Optional[str]=None
class TagIn(BaseModel):
    name: str; color: str=""
@app.patch("/api/assignees/{name}")
def api_upd_assignee(name: str, u: MasterUpd): return wrap(db.update_assignee, name, u.new_name, u.kind)
@app.put("/api/assignees/{name}/icon")
async def api_set_icon(name: str, request: Request):
    """Body: raw image bytes or JSON {"data_base64": "..."} / {"url": "https://example.com/avatar.png"}."""
    ct = request.headers.get("content-type", "")
    limit = 4 * ((avatars.MAX_BYTES + 2) // 3) + 4096 if ct.startswith("application/json") else avatars.MAX_BYTES
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit: raise HTTPException(413, "image request too large (max 5MB image)")
        body.extend(chunk)
    if ct.startswith("application/json"):
        b = wrap(IconIn.model_validate_json, bytes(body))
        if b.data_base64: raw = wrap(avatars.decode_b64, b.data_base64)
        elif b.url: raw = await asyncio.to_thread(wrap, avatars.fetch_url, b.url)
        else: raise HTTPException(400, "data_base64 or url required")
    else:
        raw = bytes(body)
    return await asyncio.to_thread(wrap, avatars.set_icon, name, raw)
@app.delete("/api/assignees/{name}/icon")
def api_rm_icon(name: str): return wrap(avatars.set_icon, name, None)
@app.delete("/api/assignees/{name}")
def api_rm_assignee(name: str): return wrap(db.delete_assignee, name)
@app.get("/api/group_tags")
def api_tags(): return db.list_group_tags()
@app.post("/api/group_tags", status_code=201)
def api_add_tag(t: TagIn): return wrap(db.add_group_tag, t.name, t.color)
@app.patch("/api/group_tags/{name}")
def api_upd_tag(name: str, u: MasterUpd): return wrap(db.update_group_tag, name, u.new_name, u.color)
@app.delete("/api/group_tags/{name}")
def api_rm_tag(name: str): return db.delete_group_tag(name)
@app.get("/api/matrix")
def api_matrix(include_done: bool=False): return db.get_matrix(include_done)
from fastapi.responses import PlainTextResponse
@app.get("/favicon.ico", include_in_schema=False)
def favicon(): return FileResponse(os.path.join(HERE, "static", "favicon.svg"), media_type="image/svg+xml")
@app.get("/api/events")
async def api_events(request: Request):
    q = asyncio.Queue(maxsize=1000); _SUBS.add(q)
    async def gen():
        try:
            yield "retry: 3000\n: connected\n\n"
            while True:
                if await request.is_disconnected(): break
                try: ev = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError: yield ": ping\n\n"; continue
                yield f"id: {ev['id']}\nevent: change\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally: _SUBS.discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"})
@app.get("/api/rules")
def api_rules(format: str = "json"):
    if format == "md": return PlainTextResponse(rules_text(), media_type="text/markdown; charset=utf-8")
    return {"rules_markdown": rules_text()}
@app.get("/healthz")
def health(): return {"ok": True}

app.mount("/mcp", mcp_app)
os.makedirs(avatars.DIR, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=avatars.DIR), name="avatars")
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
from fastapi.responses import HTMLResponse
def _ver():
    return str(int(max(os.path.getmtime(os.path.join(HERE, "static", f)) for f in ("app.js", "style.css"))))
@app.get("/")
def index():
    with open(os.path.join(HERE, "static", "index.html"), encoding="utf-8") as source: html = source.read()
    v = _ver(); html = html.replace("static/style.css", f"static/style.css?v={v}").replace("static/app.js", f"static/app.js?v={v}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
