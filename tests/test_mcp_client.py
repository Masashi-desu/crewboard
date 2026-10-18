import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config
import asyncio, json, os, sys
def J(r):
    if r.isError: raise RuntimeError(r.content[0].text)
    sc=r.structuredContent
    if sc: return sc.get("result", sc)
    v=[json.loads(c.text) for c in r.content]
    return v[0] if len(v)==1 and isinstance(v[0], dict) else v
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
TOKEN = config.MCP_TOKEN
async def main():
    async with streamablehttp_client(os.environ.get("CREWBOARD_MCP_URL", f"http://127.0.0.1:{config.PORT}/mcp/"), headers={"Authorization": f"Bearer {TOKEN}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            j = J(await s.call_tool("create_job", {"title": "MCPテスト"}))
            t = J(await s.call_tool("add_task", {"job_id": j["id"], "title": "タイトルA", "body": "本文A", "assignee": "Agent Bot"}))
            await s.call_tool("update_task", {"task_id": t["id"], "status": "done", "body": "本文B"})
            print("assign", J(await s.call_tool("assign_job", {"job_id": j["id"], "assignees": ["Owner"]}))["assignees"])
            await s.call_tool("move_job", {"job_id": j["id"], "status": "run"})
            g = J(await s.call_tool("get_job", {"job_id": j["id"]}))
            print("job", g["status"], g["task_counts"], g["tasks"][0]["title"], g["tasks"][0]["body"]); await s.call_tool("delete_job", {"job_id": j["id"]})
            print("matrix cells", len(J(await s.call_tool("get_matrix", {}))["cells"])); print("assignees", [a["name"] for a in J(await s.call_tool("list_assignees", {}))])
asyncio.run(main())
