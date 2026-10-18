import sqlite3, json, os, datetime
import config
DB = config.DB_PATH
JOB_STATUSES = ["wait", "ready", "run", "done"]
TASK_STATUSES = ["todo", "doing", "done"]
LEVELS = ["low", "normal", "high"]
PRIORITIES = ["low", "normal", "high", "urgent"]

def now(): return datetime.datetime.now().astimezone().isoformat(timespec="seconds")

def conn():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON"); return c

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with conn() as c:
        c.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'wait',
          priority TEXT NOT NULL DEFAULT 'normal', importance TEXT NOT NULL DEFAULT 'normal', tags TEXT NOT NULL DEFAULT '[]',
          group_tag TEXT DEFAULT '', conditions TEXT DEFAULT '', policy TEXT DEFAULT '', note TEXT DEFAULT '',
          sample INTEGER DEFAULT 0, sort REAL DEFAULT 0, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          title TEXT NOT NULL DEFAULT '', body TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
          priority TEXT DEFAULT 'normal', importance TEXT DEFAULT 'normal', assignee TEXT DEFAULT '',
          sort REAL DEFAULT 0, created_at TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS assignees(name TEXT PRIMARY KEY, kind TEXT DEFAULT 'bot', sort INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, job_id INTEGER, at TEXT, text TEXT);
        """)
        if "assignees" not in [r[1] for r in c.execute("PRAGMA table_info(jobs)")]:
            c.execute("ALTER TABLE jobs ADD COLUMN assignees TEXT NOT NULL DEFAULT '[]'")
        c.execute("CREATE TABLE IF NOT EXISTS group_tags(name TEXT PRIMARY KEY, color TEXT DEFAULT '', sort INTEGER DEFAULT 0)")
        c.execute("INSERT OR IGNORE INTO group_tags(name) SELECT DISTINCT group_tag FROM jobs WHERE group_tag!=''")
        if "icon" not in [r[1] for r in c.execute("PRAGMA table_info(assignees)")]:
            c.execute("ALTER TABLE assignees ADD COLUMN icon TEXT DEFAULT ''")
        if not c.execute("SELECT 1 FROM assignees").fetchone():
            c.executemany("INSERT INTO assignees(name,kind,sort) VALUES(?,?,?)", [("Owner","human",0),("Agent Bot","bot",1)])
        if not c.execute("SELECT 1 FROM jobs").fetchone(): seed(c)

def default_assignee():
    with conn() as c:
        r = c.execute("SELECT name FROM assignees ORDER BY (kind='human') DESC, sort, name LIMIT 1").fetchone()
    return r[0] if r else ""

def seed(c):
    S = [("【サンプル】優先度と重要度から取り組む順を判断できるようにする","wait","normal","high",["Crewboard"],
          "優先度と重要度を設定でき、カンバンで確認できる。","既存データを壊さずに列を追加する。","これはサンプルです。",
          [("重要度の保存とAPI","done","Agent Bot"),("ボード表示","done","Agent Bot"),("実ブラウザで確認","doing","Owner"),("画面サイズ追従","todo","Agent Bot")]),
         ("【サンプル】関係者限定のアクセス認証を用意する","ready","high","normal",["インフラ"],
          "関係者のみが管理画面にアクセスできる状態にする。","既存のIDプロバイダを利用する。","",
          [("権限設計","done","Agent Bot"),("ユーザー招待","doing","Owner"),("MFA確認","todo","Owner"),("ドキュメント化","todo","Agent Bot")]),
         ("【サンプル】ニュース要約を毎朝チャットに通知する","run","normal","normal",["News"],
          "毎朝8時にチャットへ要約が届く。","既存の収集スクリプトを流用する。","",
          [("配信スクリプト","done","Agent Bot"),("チャット連携","doing","Agent Bot"),("テスト送信","todo","Owner")]),
         ("【サンプル】完了したジョブの例","done","low","low",["サンプル"],"完了履歴に表示される。","","",
          [("作業","done","Owner")])]
    t = now()
    for i,(title,st,p,imp,tags,cond,pol,note,tasks) in enumerate(S):
        cur = c.execute("INSERT INTO jobs(title,status,priority,importance,tags,group_tag,conditions,policy,note,sample,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,1,?,?,?)",
                        (title,st,p,imp,json.dumps(tags,ensure_ascii=False),"サンプル",cond,pol,note,i,t,t))
        for j,(tt,ts,a) in enumerate(tasks):
            c.execute("INSERT INTO tasks(job_id,title,body,status,assignee,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(cur.lastrowid,tt,"サンプルタスク",ts,a,j,t,t))
        c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(cur.lastrowid,t,"サンプルとして作成"))

def _job(c, r, with_tasks=True):
    d = dict(r); d["tags"] = json.loads(d["tags"] or "[]"); d["assignees"] = json.loads(d.get("assignees") or "[]"); d["sample"] = bool(d["sample"])
    ts = [dict(x) for x in c.execute("SELECT * FROM tasks WHERE job_id=? ORDER BY sort,id",(d["id"],))]
    d["task_counts"] = {s: sum(1 for x in ts if x["status"]==s) for s in TASK_STATUSES}; d["task_counts"]["total"]=len(ts)
    d["current_assignee"] = next((x["assignee"] for x in ts if x["status"] != "done"), None) or None
    if with_tasks: d["tasks"] = ts
    return d

def list_jobs(status=None, q=None, priority=None, group_tag=None, include_tasks=True):
    with conn() as c:
        sql, a = "SELECT * FROM jobs WHERE 1=1", []
        if status: sql += " AND status=?"; a.append(status)
        if priority: sql += " AND priority=?"; a.append(priority)
        if group_tag: sql += " AND group_tag=?"; a.append(group_tag)
        if q: sql += " AND (title LIKE ? OR conditions LIKE ? OR policy LIKE ? OR note LIKE ?)"; a += [f"%{q}%"]*4
        return [_job(c, r, include_tasks) for r in c.execute(sql+" ORDER BY sort,id", a)]

def get_job(job_id):
    with conn() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
        if not r: raise KeyError(f"job {job_id} not found")
        d = _job(c, r); d["history"] = [dict(x) for x in c.execute("SELECT at,text FROM history WHERE job_id=? ORDER BY id DESC",(job_id,))]
        return d

JOB_FIELDS = ["assignees","title","status","priority","importance","tags","group_tag","conditions","policy","note","sort"]
def _check(f, v):
    if f=="status" and v not in JOB_STATUSES: raise ValueError(f"status must be one of {JOB_STATUSES}")
    if f=="priority" and v not in PRIORITIES: raise ValueError(f"priority must be one of {PRIORITIES}")
    if f=="importance" and v not in LEVELS: raise ValueError(f"importance must be one of {LEVELS}")

def create_job(title, status="wait", priority="normal", importance="normal", tags=None, group_tag="", conditions="", policy="", note=""):
    for f,v in (("status",status),("priority",priority),("importance",importance)): _check(f,v)
    if group_tag and group_tag not in [g["name"] for g in list_group_tags()]: raise ValueError("unknown group_tag; register it with add_group_tag")
    t = now()
    with conn() as c:
        mx = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM jobs").fetchone()[0]
        cur = c.execute("INSERT INTO jobs(title,status,priority,importance,tags,group_tag,conditions,policy,note,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (title,status,priority,importance,json.dumps(tags or [],ensure_ascii=False),group_tag,conditions,policy,note,mx,t,t))
        c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(cur.lastrowid,t,"作成"))
        jid = cur.lastrowid
    return get_job(jid)

def update_job(job_id, **kw):
    kw = {k:v for k,v in kw.items() if k in JOB_FIELDS and v is not None}
    for k,v in kw.items(): _check(k,v)
    if "tags" in kw: kw["tags"] = json.dumps(kw["tags"], ensure_ascii=False)
    if "assignees" in kw:
        known = [a["name"] for a in list_assignees()]
        bad = [a for a in kw["assignees"] if a not in known]
        if bad: raise ValueError(f"unknown assignee(s) {bad}; see list_assignees")
        kw["assignees"] = json.dumps(kw["assignees"], ensure_ascii=False)
    if kw.get("group_tag") and kw["group_tag"] not in [g["name"] for g in list_group_tags()]:
        raise ValueError("unknown group_tag; register it with add_group_tag (see list_group_tags)")
    get_job(job_id)
    if kw:
        t = now()
        with conn() as c:
            c.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in kw)},updated_at=? WHERE id=?", [*kw.values(), t, job_id])
            c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(job_id,t,"更新: "+", ".join(kw)))
    return get_job(job_id)

def move_job(job_id, status, sort=None): return update_job(job_id, status=status, sort=sort)

def delete_job(job_id):
    with conn() as c:
        c.execute("DELETE FROM tasks WHERE job_id=?",(job_id,)); c.execute("DELETE FROM history WHERE job_id=?",(job_id,))
        n = c.execute("DELETE FROM jobs WHERE id=?",(job_id,)).rowcount
    if not n: raise KeyError(f"job {job_id} not found")
    return {"deleted": job_id}

def _check_task(kw):
    if "status" in kw and kw["status"] not in TASK_STATUSES: raise ValueError(f"task status must be one of {TASK_STATUSES}")
    if "assignee" in kw and kw["assignee"] not in [a["name"] for a in list_assignees()]: raise ValueError("unknown assignee; see list_assignees")
    for f in ("priority","importance"):
        if f in kw and kw[f] not in LEVELS: raise ValueError(f"{f} must be one of {LEVELS}")

def add_task(job_id, title="", body="", status="todo", assignee="", priority="normal", importance="normal"):
    if not (title or "").strip(): raise ValueError("task title is required")
    if not assignee: assignee = default_assignee()
    if not assignee: raise ValueError("task assignee is required (see list_assignees)")
    _check_task(dict(status=status, assignee=assignee, priority=priority, importance=importance)); get_job(job_id); t = now()
    with conn() as c:
        mx = c.execute("SELECT COALESCE(MAX(sort),0)+1 FROM tasks WHERE job_id=?",(job_id,)).fetchone()[0]
        cur = c.execute("INSERT INTO tasks(job_id,title,body,status,assignee,priority,importance,sort,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (job_id,title,body,status,assignee,priority,importance,mx,t,t))
        c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(job_id,t,f"タスク #{cur.lastrowid} 追加"))
        if status == "done": _auto_done(c, job_id, t)
        else: _auto_reopen(c, job_id, t)
        return dict(c.execute("SELECT * FROM tasks WHERE id=?",(cur.lastrowid,)).fetchone())

def _auto_done(c, job_id, t):
    """全タスク完了時にジョブを自動で done にする（遷移時のみ・タスク0件は対象外）。"""
    j = c.execute("SELECT status FROM jobs WHERE id=?",(job_id,)).fetchone()
    if not j or j["status"] == "done": return
    n, open_ = c.execute("SELECT COUNT(*), SUM(status!='done') FROM tasks WHERE job_id=?",(job_id,)).fetchone()
    if n and not open_:
        c.execute("UPDATE jobs SET status='done',updated_at=? WHERE id=?",(t,job_id))
        c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(job_id,t,"全タスク完了のため自動で完了(done)"))

def _auto_reopen(c, job_id, t):
    """完了(done)ジョブに未完了タスクが生じたら自動で run に戻す。"""
    j = c.execute("SELECT status FROM jobs WHERE id=?",(job_id,)).fetchone()
    if not j or j["status"] != "done": return
    if c.execute("SELECT COUNT(*) FROM tasks WHERE job_id=? AND status!='done'",(job_id,)).fetchone()[0]:
        c.execute("UPDATE jobs SET status='run',updated_at=? WHERE id=?",(t,job_id))
        c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(job_id,t,"未完了タスクがあるため自動で進行中(run)に戻した"))

TASK_FIELDS = ["title","body","status","assignee","priority","importance","sort"]
def update_task(task_id, **kw):
    kw = {k:v for k,v in kw.items() if k in TASK_FIELDS and v is not None}; _check_task(kw); t = now()
    if "title" in kw and not kw["title"].strip(): raise ValueError("task title is required")
    with conn() as c:
        r = c.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone()
        if not r: raise KeyError(f"task {task_id} not found")
        if kw:
            c.execute(f"UPDATE tasks SET {','.join(k+'=?' for k in kw)},updated_at=? WHERE id=?", [*kw.values(), t, task_id])
            c.execute("INSERT INTO history(job_id,at,text) VALUES(?,?,?)",(r["job_id"],t,f"タスク #{task_id} 更新: "+", ".join(kw)))
            if kw.get("status") == "done" and r["status"] != "done": _auto_done(c, r["job_id"], t)
            elif kw.get("status") in ("todo","doing") and r["status"] == "done": _auto_reopen(c, r["job_id"], t)
        return dict(c.execute("SELECT * FROM tasks WHERE id=?",(task_id,)).fetchone())

def delete_task(task_id):
    with conn() as c:
        r = c.execute("SELECT job_id,status FROM tasks WHERE id=?",(task_id,)).fetchone()
        c.execute("DELETE FROM tasks WHERE id=?",(task_id,))
        if r and r["status"] != "done": _auto_done(c, r["job_id"], now())
    return {"deleted": task_id}

def list_assignees(with_counts=False):
    with conn() as c:
        out = [dict(r) for r in c.execute("SELECT name,kind,COALESCE(icon,'') AS icon FROM assignees ORDER BY sort,name")]
        if with_counts:
            jobs = [(r["id"], json.loads(r["assignees"] or "[]")) for r in c.execute("SELECT id,assignees FROM jobs WHERE status!='done'")]
            ids = {j for j,_ in jobs}; tasks = [dict(r) for r in c.execute("SELECT job_id,assignee,status FROM tasks")]
            for a in out:
                n = a["name"]; js = {j for j,al in jobs if n in al} | {t["job_id"] for t in tasks if t["assignee"]==n and t["job_id"] in ids}
                a["job_count"] = len(js); a["open_task_count"] = sum(1 for t in tasks if t["assignee"]==n and t["status"]!="done" and t["job_id"] in ids)
        return out
def assign_job(job_id, assignees): return update_job(job_id, assignees=list(assignees))
def add_assignee(name, kind="bot"):
    if not name.strip(): raise ValueError("name required")
    name = name.strip()
    with conn() as c: c.execute("INSERT OR IGNORE INTO assignees(name,kind,sort) VALUES(?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM assignees))",(name,kind))
    return list_assignees()
def remove_assignee(name):
    with conn() as c: c.execute("DELETE FROM assignees WHERE name=?",(name,))
    return list_assignees()

def get_matrix(include_done=False):
    """Jobs grouped by priority x importance (x axis priority, y axis importance)."""
    cells = {f"{p}:{i}": {"priority": p, "importance": i, "jobs": []} for i in LEVELS for p in PRIORITIES}
    for j in list_jobs(include_tasks=False):
        if j["status"] == "done" and not include_done: continue
        cells[f"{j['priority']}:{j['importance']}"]["jobs"].append({k: j[k] for k in ("id","title","status","task_counts","tags","current_assignee")})
    return {"x_axis": {"field": "priority", "values": PRIORITIES}, "y_axis": {"field": "importance", "values": LEVELS},
            "cells": [c for c in cells.values() if c["jobs"]]}

def _assignee_usage(c, name):
    t = c.execute("SELECT COUNT(*) FROM tasks WHERE assignee=?", (name,)).fetchone()[0]
    j = sum(1 for r in c.execute("SELECT assignees FROM jobs") if name in json.loads(r[0] or "[]"))
    return t, j
def update_assignee(name, new_name=None, kind=None):
    with conn() as c:
        if not c.execute("SELECT 1 FROM assignees WHERE name=?", (name,)).fetchone(): raise KeyError(f"assignee {name} not found")
        if kind: c.execute("UPDATE assignees SET kind=? WHERE name=?", (kind, name))
        if new_name and new_name != name:
            if c.execute("SELECT 1 FROM assignees WHERE name=?", (new_name,)).fetchone(): raise ValueError(f"{new_name} already exists")
            c.execute("UPDATE assignees SET name=? WHERE name=?", (new_name, name))
            c.execute("UPDATE tasks SET assignee=? WHERE assignee=?", (new_name, name))
            for r in c.execute("SELECT id,assignees FROM jobs").fetchall():
                al = json.loads(r[1] or "[]")
                if name in al: c.execute("UPDATE jobs SET assignees=? WHERE id=?", (json.dumps([new_name if a==name else a for a in al], ensure_ascii=False), r[0]))
    return list_assignees(True)
def delete_assignee(name):
    with conn() as c:
        t, j = _assignee_usage(c, name)
        if t or j: raise ValueError(f"「{name}」は使用中のため削除できません（タスク {t} 件・ジョブ担当 {j} 件）。先に担当を付け替えてください。")
        icon = (c.execute("SELECT icon FROM assignees WHERE name=?", (name,)).fetchone() or [""])[0]
        c.execute("DELETE FROM assignees WHERE name=?", (name,))
    if icon and icon.startswith("/avatars/"):
        p = os.path.join(os.path.dirname(DB), "avatars", os.path.basename(icon))
        if os.path.exists(p): os.remove(p)
    return list_assignees(True)
remove_assignee = delete_assignee

def list_group_tags():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT g.name,g.color,(SELECT COUNT(*) FROM jobs WHERE group_tag=g.name) AS job_count FROM group_tags g ORDER BY g.sort,g.name")]
def add_group_tag(name, color=""):
    if not name.strip(): raise ValueError("name required")
    with conn() as c: c.execute("INSERT OR IGNORE INTO group_tags VALUES(?,?,(SELECT COALESCE(MAX(sort),0)+1 FROM group_tags))", (name.strip(), color))
    return list_group_tags()
def update_group_tag(name, new_name=None, color=None):
    with conn() as c:
        if not c.execute("SELECT 1 FROM group_tags WHERE name=?", (name,)).fetchone(): raise KeyError(f"group tag {name} not found")
        if color is not None: c.execute("UPDATE group_tags SET color=? WHERE name=?", (color, name))
        if new_name and new_name != name:
            if c.execute("SELECT 1 FROM group_tags WHERE name=?", (new_name,)).fetchone(): raise ValueError(f"{new_name} already exists")
            c.execute("UPDATE group_tags SET name=? WHERE name=?", (new_name, name))
            c.execute("UPDATE jobs SET group_tag=? WHERE group_tag=?", (new_name, name))
    return list_group_tags()
def delete_group_tag(name):
    """Deletes the tag; jobs using it become 'グループタグなし' (group_tag='')."""
    with conn() as c:
        c.execute("UPDATE jobs SET group_tag='' WHERE group_tag=?", (name,))
        c.execute("DELETE FROM group_tags WHERE name=?", (name,))
    return list_group_tags()


# ---- change events (SSE): every mutating db function is wrapped; emitted once per call ----
import functools, threading
LISTENERS = []          # callables(event_dict)
_tl = threading.local()
def _emit(ev):
    for f in list(LISTENERS):
        try: f(ev)
        except Exception: pass
def _task_job(task_id):
    with conn() as c:
        r = c.execute("SELECT job_id FROM tasks WHERE id=?",(task_id,)).fetchone()
    return r["job_id"] if r else None
def _evented(name, kind):
    fn = globals()[name]
    @functools.wraps(fn)
    def w(*a, **k):
        outer = getattr(_tl, "depth", 0) == 0
        pre = _task_job(a[0] if a else k.get("task_id")) if kind == "task" else None
        _tl.depth = getattr(_tl, "depth", 0) + 1
        if outer: _tl.auto = []
        try: res = fn(*a, **k)
        finally: _tl.depth -= 1
        if outer:
            if kind == "master": ids = []
            elif kind == "task": ids = [pre or (res.get("job_id") if isinstance(res, dict) else None)]
            elif name == "create_job": ids = [res["id"]]
            else: ids = [a[0] if a else k.get("job_id")]
            ids = [i for i in ids if i]
            _emit({"type": name, "scope": "master" if kind == "master" else "job", "job_ids": ids})
            for typ, j in _tl.auto: _emit({"type": typ, "scope": "job", "job_ids": [j]})
        return res
    globals()[name] = w
_orig_auto = _auto_done
def _auto_done(c, job_id, t):
    before = c.total_changes; _orig_auto(c, job_id, t)
    if c.total_changes != before and hasattr(_tl, "auto"): _tl.auto.append(("auto_done", job_id))
_orig_reopen = _auto_reopen
def _auto_reopen(c, job_id, t):
    before = c.total_changes; _orig_reopen(c, job_id, t)
    if c.total_changes != before and hasattr(_tl, "auto"): _tl.auto.append(("auto_reopen", job_id))
for _n in ["create_job","update_job","delete_job","add_task"]: _evented(_n, "job")
for _n in ["update_task","delete_task"]: _evented(_n, "task")
for _n in ["add_assignee","remove_assignee","update_assignee","delete_assignee","add_group_tag","update_group_tag","delete_group_tag"]: _evented(_n, "master")
