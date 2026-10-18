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
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.directory.cleanup()
        raise RuntimeError("disposable server failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
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
