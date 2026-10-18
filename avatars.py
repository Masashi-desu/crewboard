"""Assignee avatar processing: any png/jpg/webp/svg -> 128px square webp under <data dir>/avatars/."""
import io, os, hashlib, base64, binascii, re, http.client, ipaddress, socket, ssl, time
from urllib.parse import urlsplit, quote
from PIL import Image, ImageOps
import db
import config
DIR = config.AVATAR_DIR
MAX_BYTES = 5 * 1024 * 1024
URL_TIMEOUT = 15

def _no_svg_resources(url, resource_type):
    raise ValueError("SVG external resources are not supported")

def _to_webp(raw: bytes) -> bytes:
    if len(raw) > MAX_BYTES: raise ValueError("image too large (max 5MB)")
    head = raw[:512].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in raw[:1024].lower():
        try:
            from cairosvg.surface import PNGSurface
        except (ImportError, OSError) as e:
            raise ValueError("SVG upload requires CairoSVG and the native Cairo library; use PNG, JPEG or WebP") from e
        try:
            raw = PNGSurface.convert(bytestring=raw, output_width=256, output_height=256,
                                     unsafe=False, url_fetcher=_no_svg_resources)
        except Exception as e:
            raise ValueError("invalid SVG or unsupported external resource; use a self-contained SVG") from e
    try: im = Image.open(io.BytesIO(raw))
    except Exception: raise ValueError("unsupported image (png/jpg/webp/svg)")
    if im.format not in (None, "PNG", "JPEG", "WEBP", "MPO"): raise ValueError(f"unsupported format {im.format}")
    if im.width * im.height > 16 * 1024 * 1024: raise ValueError("image dimensions too large (max 16 megapixels)")
    try: im.load()
    except Exception as e: raise ValueError("invalid image") from e
    im = ImageOps.exif_transpose(im).convert("RGBA")
    im = ImageOps.fit(im, (128, 128), Image.LANCZOS)
    out = io.BytesIO(); im.save(out, "WEBP", quality=88); return out.getvalue()

def decode_b64(s: str) -> bytes:
    s = re.sub(r"^data:[^,]*,", "", s.strip())
    if len(s) > 4 * ((MAX_BYTES + 2) // 3): raise ValueError("image too large (max 5MB)")
    try: return base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as e: raise ValueError("invalid base64 image") from e

def _public_ip(address):
    ip = ipaddress.ip_address(address)
    # IPv4-mapped IPv6 must be checked as IPv4, too.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and not _public_ip(str(mapped)): return False
    return ip.is_global and not any((ip.is_private, ip.is_loopback, ip.is_link_local,
                                    ip.is_reserved, ip.is_multicast, ip.is_unspecified))

class _AvatarConnection(http.client.HTTPConnection):
    """Connect only to the already validated addresses; retain Host and TLS SNI."""
    def __init__(self, host, port, addresses, tls):
        super().__init__(host, port, timeout=URL_TIMEOUT)
        self.addresses = addresses
        self.tls = tls
        self.deadline = time.monotonic() + URL_TIMEOUT

    def connect(self):
        last_error = OSError("no address available")
        for family, kind, protocol, _, address in self.addresses:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError("avatar connection timed out")
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(remaining)
                sock.connect(address)
                if self.tls:
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                self.sock = sock
                return
            except OSError as e:
                sock.close()
                last_error = e
        raise last_error

def fetch_url(url: str) -> bytes:
    connection = None
    try:
        if any(ord(ch) <= 32 or ord(ch) == 127 for ch in url): raise ValueError("invalid icon URL")
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise ValueError("icon_url must be http(s)")
        if parts.username is not None or parts.password is not None or "%" in parts.hostname:
            raise ValueError("URL credentials and scoped addresses are not allowed")
        host = parts.hostname.encode("idna").decode("ascii")
        port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
        if not 1 <= port <= 65535: raise ValueError("invalid icon URL port")
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not addresses or any(not _public_ip(item[4][0]) for item in addresses):
            raise ValueError("icon URL must resolve only to public IP addresses")
        connection = _AvatarConnection(host, port, addresses, parts.scheme == "https")
        target = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parts.query: target += "?" + quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
        connection.request("GET", target, headers={"User-Agent": "crewboard", "Accept": "image/*"})
        with connection.getresponse() as response:
            # http.client never follows redirects, including redirects to internal hosts.
            if 300 <= response.status < 400: raise ValueError("avatar URL redirects are not allowed")
            if response.status != 200: raise ValueError("avatar URL did not return HTTP 200")
            length = response.getheader("Content-Length")
            if length is not None and int(length) > MAX_BYTES: raise ValueError("image too large (max 5MB)")
            raw = bytearray()
            while len(raw) <= MAX_BYTES:
                remaining = connection.deadline - time.monotonic()
                if remaining <= 0: raise ValueError("avatar download timed out")
                if connection.sock is not None: connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_BYTES + 1 - len(raw)))
                if not chunk: break
                raw.extend(chunk)
            if len(raw) > MAX_BYTES: raise ValueError("image too large (max 5MB)")
            return bytes(raw)
    except (OSError, http.client.HTTPException, UnicodeError) as e:
        raise ValueError("could not fetch avatar URL (network, TLS or timeout error)") from e
    finally:
        if connection is not None: connection.close()

def _remove_file(icon):
    if icon and icon.startswith("/avatars/"):
        p = os.path.join(DIR, os.path.basename(icon))
        if os.path.exists(p): os.remove(p)

def set_icon(name: str, raw: bytes | None):
    """raw=None removes the icon. Returns updated assignee list."""
    cur = {a["name"]: a for a in db.list_assignees()}
    if name not in cur: raise KeyError(f"assignee {name} not found")
    old = cur[name].get("icon") or ""
    new = ""
    if raw is not None:
        data = _to_webp(raw); os.makedirs(DIR, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40] or "a"
        owner = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
        fn = f"{slug}-{owner}-{hashlib.sha256(data).hexdigest()[:12]}.webp"
        with open(os.path.join(DIR, fn), "wb") as f: f.write(data)
        new = f"/avatars/{fn}"
    with db.conn() as c: c.execute("UPDATE assignees SET icon=? WHERE name=?", (new, name))
    if old and old != new: _remove_file(old)
    return db.list_assignees(True)
