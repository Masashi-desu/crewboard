"""Assignee avatar processing: any png/jpg/webp/svg -> 128px square webp under <data dir>/avatars/."""
import io, os, hashlib, base64, re, urllib.request
from PIL import Image, ImageOps
import db
import config
DIR = config.AVATAR_DIR
MAX_BYTES = 5 * 1024 * 1024

def _to_webp(raw: bytes) -> bytes:
    if len(raw) > MAX_BYTES: raise ValueError("image too large (max 5MB)")
    head = raw[:512].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in raw[:1024].lower():
        import cairosvg
        raw = cairosvg.svg2png(bytestring=raw, output_width=256, output_height=256, unsafe=False)
    try: im = Image.open(io.BytesIO(raw)); im.load()
    except Exception: raise ValueError("unsupported image (png/jpg/webp/svg)")
    if im.format not in (None, "PNG", "JPEG", "WEBP", "MPO"): raise ValueError(f"unsupported format {im.format}")
    im = ImageOps.exif_transpose(im).convert("RGBA")
    im = ImageOps.fit(im, (128, 128), Image.LANCZOS)
    out = io.BytesIO(); im.save(out, "WEBP", quality=88); return out.getvalue()

def decode_b64(s: str) -> bytes:
    s = re.sub(r"^data:[^,]*,", "", s.strip())
    return base64.b64decode(s)

def fetch_url(url: str) -> bytes:
    if not url.startswith(("https://", "http://")): raise ValueError("icon_url must be http(s)")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crewboard"}), timeout=15) as r:
        return r.read(MAX_BYTES + 1)

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
        fn = f"{slug}-{hashlib.sha1(data).hexdigest()[:10]}.webp"
        with open(os.path.join(DIR, fn), "wb") as f: f.write(data)
        new = f"/avatars/{fn}"
    with db.conn() as c: c.execute("UPDATE assignees SET icon=? WHERE name=?", (new, name))
    if old and old != new: _remove_file(old)
    return db.list_assignees(True)
