"""Regression tests using disposable data only: python -m unittest discover -s tests -v."""
import importlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import httpx
from PIL import Image
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
API_TOKEN = "test-api-token"
MCP_TOKEN = "test-mcp-token"


def stop_test_process(process):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    process.wait(timeout=10)


def setUpModule():
    global sandbox, environment, app, avatars, db, client
    sandbox = tempfile.TemporaryDirectory(prefix="crewboard-tests-")
    environment = patch.dict(os.environ, {
        "CREWBOARD_DATA_DIR": sandbox.name,
        "CREWBOARD_RULES_FILE": str(ROOT / "rules.md"),
        "CREWBOARD_API_TOKEN": API_TOKEN,
        "CREWBOARD_MCP_TOKEN": MCP_TOKEN,
        "CREWBOARD_ALLOWED_HOSTS": "testserver,board.example.com:8090",
        "CREWBOARD_BASE_PATH": "",
        "CREWBOARD_HOST": "127.0.0.1",
        "CREWBOARD_PORT": "8090",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    environment.start()
    # Other smoke-test modules may already have imported configuration during discovery.
    import config
    importlib.reload(config)
    import app, avatars, db
    assert Path(db.DB).parent == Path(sandbox.name)
    client = TestClient(app.app, raise_server_exceptions=False)
    client.__enter__()


def tearDownModule():
    client.__exit__(None, None, None)
    environment.stop()
    sandbox.cleanup()


def png():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(output, "PNG")
    return output.getvalue()


def addresses(*ips, port=80):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "",
             (ip, port, 0, 0) if ":" in ip else (ip, port)) for ip in ips]


class AvatarSecurityTests(unittest.TestCase):
    def test_rejects_nonpublic_ipv4_ipv6_and_mapped_addresses(self):
        blocked = ["10.0.0.1", "172.16.0.1", "192.168.0.1", "127.0.0.1", "169.254.169.254",
                   "0.0.0.0", "224.0.0.1", "240.0.0.1", "192.0.2.1", "100.64.0.1",
                   "::", "::1", "fc00::1", "fe80::1", "ff02::1", "2001:db8::1",
                   "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254"]
        for ip in blocked:
            with self.subTest(ip=ip), patch.object(avatars.socket, "getaddrinfo", return_value=addresses(ip)), \
                    patch.object(avatars, "_AvatarConnection") as connection:
                with self.assertRaisesRegex(ValueError, "public IP"):
                    avatars.fetch_url("https://images.example.com/avatar.png")
                connection.assert_not_called()

    def test_rejects_mixed_public_private_dns_answers(self):
        with patch.object(avatars.socket, "getaddrinfo", return_value=addresses("8.8.8.8", "::1")), \
                patch.object(avatars, "_AvatarConnection") as connection:
            with self.assertRaisesRegex(ValueError, "public IP"):
                avatars.fetch_url("https://images.example.com/avatar.png")
            connection.assert_not_called()

    def test_rejects_bad_schemes_credentials_and_scoped_addresses(self):
        for url in ["file:///etc/passwd", "ftp://images.example.com/a", "https:///a",
                    "https://user:pass@images.example.com/a", "http://[fe80::1%25eth0]/a",
                    "http://images.example.com:0/a", "http://images.example.com/\r\nX-Test: a"]:
            with self.subTest(url=url), patch.object(avatars.socket, "getaddrinfo") as resolve:
                with self.assertRaises(ValueError): avatars.fetch_url(url)
                resolve.assert_not_called()

    def test_public_addresses_and_https_request_keep_hostname(self):
        for ip in ("8.8.8.8", "2001:4860:4860::8888"):
            resolved = addresses(ip, port=443)
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.getheader.return_value = "5"
            response.read1.side_effect = [b"image", b""]
            with self.subTest(ip=ip), patch.object(avatars.socket, "getaddrinfo", return_value=resolved) as resolve, \
                    patch.object(avatars, "_AvatarConnection") as connection:
                connection.return_value.getresponse.return_value = response
                connection.return_value.deadline = time.monotonic() + 15
                self.assertEqual(avatars.fetch_url("https://images.example.com/avatar.png?q=1"), b"image")
                resolve.assert_called_once_with("images.example.com", 443, type=socket.SOCK_STREAM)
                connection.assert_called_once_with("images.example.com", 443, resolved, True)
                self.assertEqual(connection.return_value.request.call_args.args[:2], ("GET", "/avatar.png?q=1"))

    def test_connection_pins_address_without_resolving_again_and_uses_tls_sni(self):
        resolved = addresses("8.8.8.8", port=443)
        sock = MagicMock()
        tls = MagicMock()
        with patch.object(avatars.socket, "socket", return_value=sock), \
                patch.object(avatars.socket, "getaddrinfo") as resolve, \
                patch.object(avatars.ssl, "create_default_context", return_value=tls):
            connection = avatars._AvatarConnection("images.example.com", 443, resolved, True)
            connection.connect()
            sock.connect.assert_called_once_with(("8.8.8.8", 443))
            tls.wrap_socket.assert_called_once_with(sock, server_hostname="images.example.com")
            resolve.assert_not_called()
            connection.close()

    def test_network_resolution_failure_is_a_validation_error(self):
        with patch.object(avatars.socket, "getaddrinfo", side_effect=socket.gaierror("test failure")):
            with self.assertRaisesRegex(ValueError, "network, TLS or timeout"):
                avatars.fetch_url("https://images.example.com/avatar.png")

    def test_svg_missing_dependency_is_descriptive_400(self):
        with patch.dict(sys.modules, {"cairosvg": None, "cairosvg.surface": None}):
            response = client.put("/api/assignees/Owner/icon", content=b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                                  headers={"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "image/svg+xml"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("CairoSVG", response.json()["detail"])

    def test_svg_renderer_cannot_fetch_external_resources(self):
        def convert(**kwargs):
            self.assertFalse(kwargs["unsafe"])
            with self.assertRaisesRegex(ValueError, "external resources"):
                kwargs["url_fetcher"]("http://127.0.0.1/private", "image/png")
            return png()
        fake = types.ModuleType("cairosvg.surface")
        fake.PNGSurface = types.SimpleNamespace(convert=convert)
        with patch.dict(sys.modules, {"cairosvg": types.ModuleType("cairosvg"), "cairosvg.surface": fake}):
            self.assertTrue(avatars._to_webp(b'<svg xmlns="http://www.w3.org/2000/svg"/>').startswith(b"RIFF"))

    def test_invalid_and_oversized_uploads_are_4xx(self):
        for content, content_type, status in [(b"<script>alert(1)</script>", "image/png", 400),
                                               (b'{"data_base64":"%%%"}', "application/json", 400),
                                               (b"[]", "application/json", 400),
                                               (b"x" * (avatars.MAX_BYTES + 1), "image/png", 413)]:
            with self.subTest(content_type=content_type, length=len(content)):
                response = client.put("/api/assignees/Owner/icon", content=content,
                                      headers={"Authorization": f"Bearer {API_TOKEN}", "Content-Type": content_type})
                self.assertEqual(response.status_code, status)

    def test_private_url_is_400_through_rest(self):
        response = client.put("/api/assignees/Owner/icon", json={"url": "http://127.0.0.1/private"},
                              headers={"Authorization": f"Bearer {API_TOKEN}"})
        self.assertEqual(response.status_code, 400)

    def test_avatar_names_cannot_escape_or_share_files(self):
        for name in ("../avatar-a", "..\\avatar-a"):
            db.add_assignee(name)
            avatars.set_icon(name, png())
        icons = {a["name"]: a["icon"] for a in db.list_assignees()}
        first, second = (icons[name] for name in ("../avatar-a", "..\\avatar-a"))
        self.assertNotEqual(first, second)
        for icon in (first, second):
            path = Path(avatars.DIR) / Path(icon).name
            self.assertEqual(path.resolve().parent, Path(avatars.DIR).resolve())
            self.assertTrue(path.is_file())
            with Image.open(path) as image:
                self.assertEqual(image.size, (128, 128))
                self.assertEqual(image.format, "WEBP")
        avatars.set_icon("../avatar-a", None)
        self.assertTrue((Path(avatars.DIR) / Path(second).name).is_file())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="crewboard-migration-tests-")
        self.db_patch = patch.object(db, "DB", str(Path(self.directory.name) / "jobs.db"))
        self.db_patch.start()
        db.init()
        self.headers = {"Authorization": f"Bearer {API_TOKEN}"}

    def tearDown(self):
        self.db_patch.stop()
        self.directory.cleanup()

    def test_wait_unassigned_roundtrip_and_ordered_blocking(self):
        job = db.create_job("wait test")
        fields = dict(wait_reason="承認待ち\n詳細", wait_for="Owner", wait_note="原文", resume_condition="承認後")
        response = client.post(f"/api/jobs/{job['id']}/tasks", headers=self.headers,
                               json=dict(title="blocked", status="wait", assignee=None, **fields))
        self.assertEqual(response.status_code, 201)
        first = response.json()
        self.assertIsNone(first["assignee"])
        db.add_task(job["id"], "later", assignee="Owner")
        saved = db.get_job(job["id"])
        self.assertTrue(saved["blocked"])
        self.assertFalse(saved["can_start"])
        self.assertIsNone(saved["current_assignee"])
        self.assertEqual(saved["task_counts"]["wait"], 1)
        for key, value in fields.items(): self.assertEqual(saved["tasks"][0][key], value)
        db.update_task(first["id"], status="done")
        self.assertEqual(db.get_job(job["id"])["current_assignee"], "Owner")

    def test_null_patch_does_not_change_omitted_assignee(self):
        job = db.create_job("patch test")
        task = db.add_task(job["id"], "assigned", assignee="Owner")
        url = f"/api/tasks/{task['id']}"
        self.assertEqual(client.patch(url, json={"body":"edited"}, headers=self.headers).json()["assignee"], "Owner")
        self.assertIsNone(client.patch(url, json={"assignee":None}, headers=self.headers).json()["assignee"])
        self.assertEqual(db.add_task(job["id"], "empty", assignee="")["assignee"], "")
        self.assertIsNone(db.add_task(job["id"], "omitted")["assignee"])

    def test_wait_prevents_completion_and_reopens_done_job(self):
        job = db.create_job("transitions")
        task = db.add_task(job["id"], "task", status="done", assignee=None)
        self.assertEqual(db.get_job(job["id"])["status"], "done")
        db.update_task(task["id"], status="wait", resume_condition="review")
        self.assertEqual(db.get_job(job["id"])["status"], "run")
        self.assertTrue(db.get_job(job["id"])["blocked"])
        db.update_task(task["id"], status="todo")
        self.assertFalse(db.get_job(job["id"])["can_start"])
        db.update_task(task["id"], assignee="Owner")
        self.assertTrue(db.get_job(job["id"])["can_start"])

    def test_additive_wait_schema_preserves_existing_data(self):
        before = db.get_job(1)
        with db.conn() as connection:
            connection.execute("CREATE TABLE preserved_marker(value TEXT)")
            connection.execute("INSERT INTO preserved_marker VALUES('keep')")
        db.init(); db.init()
        self.assertEqual(db.get_job(1), before)
        with db.conn() as connection:
            self.assertEqual(connection.execute("SELECT value FROM preserved_marker").fetchone()[0], "keep")

    def test_multiple_groups_and_filter_and_legacy_compatibility(self):
        db.add_group_tag("TagA"); db.add_group_tag("TagB")
        both = db.create_job("both", group_tags=["TagA", "TagB", "TagA"])
        single = db.create_job("single", group_tag="TagA")
        self.assertEqual(both["group_tags"], ["TagA", "TagB"])
        self.assertEqual(both["group_tag"], "TagA")
        self.assertEqual([j["id"] for j in db.list_jobs(group_tags=["TagA", "TagB"])], [both["id"]])
        response = client.get("/api/jobs?group_tags=TagA&group_tags=TagB", headers=self.headers)
        self.assertEqual([j["id"] for j in response.json()], [both["id"]])
        self.assertEqual(db.list_jobs(group_tags=["TagA", "absent"]), [])
        db.update_job(single["id"], group_tags=["TagB", "TagA"])
        self.assertEqual(db.update_job(single["id"], group_tag="TagA")["group_tags"], ["TagA"])
        before = db.get_job(1); db.init()
        self.assertEqual(db.get_job(1), before)

    def test_group_rename_delete_and_strict_master_validation(self):
        db.add_group_tag("TagA"); db.add_group_tag("TagB")
        job = db.create_job("groups", group_tags=["TagA", "TagB"])
        db.update_group_tag("TagA", new_name="Cloud")
        self.assertEqual(db.get_job(job["id"])["group_tags"], ["Cloud", "TagB"])
        db.delete_group_tag("Cloud")
        self.assertEqual(db.get_job(job["id"])["group_tag"], "TagB")
        self.assertEqual(db.get_job(job["id"])["group_tags"], ["TagB"])
        with self.assertRaises(ValueError): db.update_job(job["id"], group_tags=["locius"])
        with self.assertRaises(ValueError): db.create_job("conflict", group_tag="TagB", group_tags=[])
        self.assertEqual(db.update_job(job["id"], group_tags=[])["group_tag"], "")

    def test_source_numbers_are_namespaced_and_never_merge_existing_jobs(self):
        before = [db.get_job(j["id"]) for j in db.list_jobs()]
        source = dict(system="Job Board", uuid="job-uuid-1", number="#0001")
        imported = db.create_job(before[0]["title"], source=source)
        self.assertNotEqual(imported["id"], 1)
        other = db.create_job("other", source=dict(system="Another", uuid="job-uuid-1", number="#0001"))
        refs = client.get("/api/source_refs", params={"system":"Job Board", "number":"#0001"}, headers=self.headers).json()
        self.assertEqual([r["new_id"] for r in refs], [imported["id"]])
        self.assertNotEqual(refs[0]["new_id"], other["id"])
        self.assertEqual(db.source_refs("Job Board", uuid=source["uuid"]), refs)
        for original in before: self.assertEqual(db.get_job(original["id"]), original)
        self.assertEqual(db.list_jobs(q="Job Board:#0001")[0]["id"], imported["id"])

    def test_source_duplicate_atomicity_immutability_and_task_mapping(self):
        source = dict(system="old", uuid="job-uuid", number="#0001")
        job = db.create_job("native", source=source)
        count = len(db.list_jobs())
        with self.assertRaises(ValueError): db.create_job("duplicate", source=source)
        self.assertEqual(len(db.list_jobs()), count)
        with self.assertRaises(ValueError): db.add_task(job["id"], "duplicate UUID", source=source)
        self.assertEqual(db.get_job(job["id"])["tasks"], [])
        task = db.add_task(job["id"], "source task", source=dict(system="old", uuid="task-uuid", number="#0001-01"))
        self.assertEqual(db.source_refs("old", uuid="task-uuid")[0]["job_id"], job["id"])
        self.assertEqual(task["source"]["number"], "#0001-01")
        self.assertEqual(db.update_job(job["id"], source=source)["source"], source)
        with self.assertRaises(ValueError): db.update_job(job["id"], title="bad", source=dict(source, number="#0002"))
        self.assertEqual(db.get_job(job["id"])["title"], "native")
        with self.assertRaises(ValueError): db.update_task(task["id"], source=None)

    def test_source_dates_version_and_history_are_preserved_separately(self):
        source = dict(system="old", uuid="dated", number="#0002", created_at="2020-01-02T03:04:05.123+09:00",
                      updated_at="2021-02-03T04:05:06Z", completed_at=None, version=17)
        events = [dict(id=2, occurred_at="2021-02-03T04:05:06+00:00", operation="edit", details={"text":"原文"},
                       job_uuid="dated", task_uuid=None, recorder=None, source="mcp"),
                  dict(id=1, occurred_at="2020-01-02T03:04:05+09:00", operation="create", recorder="旧担当A", source="ui")]
        job = db.create_job("dated", source=source, source_history=events)
        saved = db.update_job(job["id"], note="local edit")
        self.assertEqual(saved["source"], source)
        self.assertEqual(saved["source_history"], events)
        self.assertEqual(saved["version"], job["version"] + 1)
        self.assertNotEqual(saved["created_at"], source["created_at"])
        audits = [h for h in saved["history"] if h["category"] == "migration"]
        self.assertEqual(len(audits), 1)
        self.assertTrue(audits[0]["batch_id"].startswith("manual:"))
        self.assertIsNone(saved["source_history"][0]["recorder"])

    def test_source_history_atomic_validation_and_immutability(self):
        count = len(db.list_jobs())
        source = dict(system="old", uuid="invalid", number="#0003", created_at="2020-01-01T00:00:00")
        with self.assertRaises(ValueError): db.create_job("bad timezone", source=source)
        self.assertEqual(len(db.list_jobs()), count)
        del source["created_at"]
        events = [dict(id="same", occurred_at="2020-01-01T00:00:00+09:00")]*2
        with self.assertRaises(ValueError): db.create_job("duplicate events", source=source, source_history=events)
        self.assertEqual(len(db.list_jobs()), count)
        job = db.create_job("immutable", source=source)
        with self.assertRaises(ValueError): db.update_job(job["id"], source_history=[])

    def test_markdown_and_session_urls_roundtrip_without_splitting(self):
        raw = '# 見出し\r\n\r\n```python\r\nprint("<原文>")\r\n```\r\n[リンク](https://example.com/?x=1&y=2)\n末尾\n'
        urls = ["https://example.com/session/1?q=%E5%8E%9F%E6%96%87#x", "http://127.0.0.1:1234/saved-only"]
        job = db.create_job("markdown", description=raw, session_urls=urls, conditions="existing")
        task = db.add_task(job["id"], "task", description=raw, body="既存本文", session_urls=urls)
        saved = db.get_job(job["id"])
        self.assertEqual(saved["description"], raw)
        self.assertEqual(saved["session_urls"], urls)
        self.assertEqual(saved["conditions"], "existing")
        self.assertEqual(saved["tasks"][0]["description"], raw)
        self.assertEqual(saved["tasks"][0]["body"], "既存本文")
        self.assertEqual(db.update_task(task["id"], description=raw)["description"], raw)

    def test_safe_markdown_rendering_and_no_external_image_requests(self):
        from markdown_view import render
        html = render('# heading\n\n```js\n<script>\n```\n<script>alert(1)</script>\n[x](javascript:alert(1))\n![alt](https://example.com/img)\n[ok](https://example.com)')
        self.assertIn("<h1>heading</h1>", html)
        self.assertIn("<pre><code", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn("<img", html)
        self.assertIn('href="https://example.com"', html)
        response = client.post("/api/markdown", json={"text":"**bold**\nnext"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("<strong>bold</strong>", response.json()["html"])
        with self.assertRaises(ValueError): db.create_job("unsafe", session_urls=["javascript:alert(1)"])

    def test_only_explicit_source_references_resolve(self):
        target = db.create_job("target", source=dict(system="old", uuid="target", number="#0001"))
        source = dict(system="old", uuid="referrer", number="#0002", references=[dict(uuid="target"), dict(number="#9999")])
        job = db.create_job("referrer", source=source, description="Issue #0001 and example #9999")
        self.assertTrue(job["resolved_references"][0]["resolved"])
        self.assertEqual(job["resolved_references"][0]["matches"][0]["new_id"], target["id"])
        self.assertFalse(job["resolved_references"][1]["resolved"])
        self.assertEqual(db.create_job("plain", description="#0001")["resolved_references"], [])


class DownloadTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                cls.seen.append(self.path)
                self.send_response(302 if self.path == "/redirect" else 200)
                if self.path == "/redirect": self.send_header("Location", "/private")
                if self.path == "/large-header": self.send_header("Content-Length", str(avatars.MAX_BYTES + 1))
                self.end_headers()
                try:
                    if self.path == "/slow": time.sleep(0.3)
                    self.wfile.write(b"x" * (avatars.MAX_BYTES + 1) if self.path == "/large-body" else b"image")
                except OSError: pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def test_direct_download_and_redirect_refusal(self):
        # Only transport is under test here; nonpublic address rejection is tested separately.
        with patch.object(avatars, "_public_ip", return_value=True):
            self.assertEqual(avatars.fetch_url(self.base + "/image"), b"image")
            with self.assertRaisesRegex(ValueError, "redirects"):
                avatars.fetch_url(self.base + "/redirect")
        self.assertNotIn("/private", self.seen)

    def test_size_limits_with_and_without_content_length(self):
        with patch.object(avatars, "_public_ip", return_value=True):
            for path in ("/large-header", "/large-body"):
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "too large"):
                    avatars.fetch_url(self.base + path)

    def test_download_timeout(self):
        with patch.object(avatars, "_public_ip", return_value=True), patch.object(avatars, "URL_TIMEOUT", 0.05):
            started = time.monotonic()
            with self.assertRaises(ValueError): avatars.fetch_url(self.base + "/slow")
            self.assertLess(time.monotonic() - started, 1)


def initialize():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}


class ApiTests(unittest.TestCase):
    def test_every_api_endpoint_requires_token(self):
        for method, path in [("GET", "/api/jobs"), ("POST", "/api/jobs"), ("GET", "/api/rules"),
                             ("GET", "/api/events"), ("GET", "/api/matrix"), ("GET", "/api/assignees"),
                             ("GET", "/api/group_tags"), ("DELETE", "/api/jobs/1"),
                             ("PATCH", "/api/tasks/1"), ("PUT", "/api/assignees/Owner/icon"), ("GET", "/api/unknown")]:
            with self.subTest(method=method, path=path):
                response = client.request(method, path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")

    def test_query_tokens_are_not_accepted_outside_sse(self):
        for path in ("/api/jobs", "/api/rules", "/api/group_tags", "/mcp/"):
            self.assertEqual(client.get(path, params={"token": API_TOKEN}).status_code, 401)
        self.assertEqual(client.get("/api/events?token=wrong").status_code, 401)

    def test_public_health_and_ui_and_optional_auth(self):
        for path in ("/healthz", "/", "/static/app.js"):
            self.assertEqual(client.get(path).status_code, 200)
        self.assertEqual(client.get("/api/jobs", headers={"Authorization": f"Bearer {API_TOKEN}"}).status_code, 200)
        self.assertEqual(client.get("/api/jobs", headers={"Authorization": f"Bearer {MCP_TOKEN}"}).status_code, 401)
        with patch.object(app, "API_TOKEN", ""):
            self.assertEqual(client.get("/api/jobs").status_code, 200)
            response = client.post("/api/jobs", json={"title": "trusted network test"})
            self.assertEqual(response.status_code, 201)

    def test_create_job_with_assignees_and_atomic_validation(self):
        headers = {"Authorization": f"Bearer {API_TOKEN}"}
        response = client.post("/api/jobs", json={"title": "assigned job", "assignees": ["Owner", "Agent Bot"]}, headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["assignees"], ["Owner", "Agent Bot"])
        count = len(db.list_jobs())
        response = client.post("/api/jobs", json={"title": "bad assignee", "assignees": ["unknown"]}, headers=headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(db.list_jobs()), count)

    def test_seed_tags_are_registered_and_editable_on_first_start(self):
        tags = {tag["name"] for tag in db.list_group_tags()}
        for job in db.list_jobs():
            if job["sample"]:
                self.assertIn(job["group_tag"], tags)
                self.assertEqual(db.update_job(job["id"], group_tag=job["group_tag"])["group_tag"], job["group_tag"])

    def test_auto_completion_and_reopening(self):
        job = db.create_job("task transition")
        task = db.add_task(job["id"], "task", assignee="Owner")
        db.update_task(task["id"], status="done")
        self.assertEqual(db.get_job(job["id"])["status"], "done")
        db.update_task(task["id"], status="todo")
        self.assertEqual(db.get_job(job["id"])["status"], "run")

    def test_mcp_auth_and_optional_host_origin_validation(self):
        headers = {"Accept": "application/json, text/event-stream", "Authorization": f"Bearer {MCP_TOKEN}"}
        self.assertEqual(client.post("/mcp/", json=initialize()).status_code, 401)
        self.assertEqual(client.post("/mcp/", json=initialize(), headers={**headers, "Authorization": f"Bearer {API_TOKEN}"}).status_code, 401)
        self.assertEqual(client.post("/mcp/", json=initialize(), headers=headers).status_code, 200)
        self.assertEqual(client.post("/mcp/", json=initialize(), headers={**headers, "Host": "attacker.example.com"}).status_code, 421)
        self.assertEqual(client.post("/mcp/", json=initialize(), headers={**headers, "Origin": "https://attacker.example.com"}).status_code, 403)
        self.assertEqual(client.post("/mcp/", json=initialize(), headers={**headers, "Host": "board.example.com:8090", "Origin": "https://board.example.com:8090"}).status_code, 200)
        with patch.object(app, "TOKEN", ""):
            self.assertEqual(client.post("/mcp/", json=initialize(), headers=headers).status_code, 401)


class RunningServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="crewboard-server-tests-")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.env = {**os.environ, "CREWBOARD_DATA_DIR": cls.directory.name, "CREWBOARD_PORT": str(port),
                   "CREWBOARD_MCP_URL": cls.base + "/mcp/", "CREWBOARD_ALLOWED_HOSTS": ""}
        cls.process = subprocess.Popen([sys.executable, "-B", "run.py"], cwd=ROOT, env=cls.env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if httpx.get(cls.base + "/healthz", timeout=0.2).status_code == 200: return
            except httpx.HTTPError: pass
            if cls.process.poll() is not None: break
            time.sleep(0.05)
        stop_test_process(cls.process)
        cls.directory.cleanup()
        raise RuntimeError("disposable server failed to start")

    @classmethod
    def tearDownClass(cls):
        stop_test_process(cls.process)
        cls.directory.cleanup()

    def test_sse_header_and_query_tokens_and_change_delivery(self):
        for headers, query in [({"Authorization": f"Bearer {API_TOKEN}"}, ""), ({}, f"?token={API_TOKEN}")]:
            with self.subTest(query_token=bool(query)), httpx.Client(timeout=5) as connection:
                with connection.stream("GET", self.base + "/api/events" + query, headers=headers) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("text/event-stream", response.headers["content-type"])
                    lines = response.iter_lines()
                    self.assertEqual(next(lines), "retry: 3000")
                    created = httpx.post(self.base + "/api/jobs", json={"title": "SSE test"},
                                         headers={"Authorization": f"Bearer {API_TOKEN}"})
                    self.assertEqual(created.status_code, 201)
                    for line in lines:
                        if line.startswith("data: "):
                            event = json.loads(line[6:])
                            self.assertEqual(event["type"], "create_job")
                            self.assertIn(created.json()["id"], event["job_ids"])
                            break
                    else: self.fail("no SSE change event")

    def test_mcp_default_hosts_remain_unrestricted(self):
        response = httpx.post(self.base + "/mcp/", json=initialize(), headers={
            "Authorization": f"Bearer {MCP_TOKEN}", "Accept": "application/json, text/event-stream",
            "Host": "board.example.com", "Origin": "https://board.example.com"})
        self.assertEqual(response.status_code, 200)

    def test_existing_mcp_smoke_scripts(self):
        for name in ("test_rules_mcp.py", "test_master_mcp.py", "test_mcp_client.py"):
            with self.subTest(script=name):
                result = subprocess.run([sys.executable, "-B", str(ROOT / "tests" / name)], cwd=ROOT,
                                        env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
