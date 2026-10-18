#!/usr/bin/env python3
"""Usage: python set_avatar.py <assignee name> <image path | --remove>
Registers (or removes) an assignee avatar directly in the data dir DB (128px webp)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, avatars
if len(sys.argv) != 3: sys.exit(__doc__)
db.init(); name, path = sys.argv[1], sys.argv[2]
res = avatars.set_icon(name, None if path == "--remove" else open(path, "rb").read())
print({a["name"]: a.get("icon", "") for a in res}[name] or "(removed)")
