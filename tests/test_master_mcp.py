import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config
import asyncio, json, os, sys
def L(r):
    sc=r.structuredContent
    return sc["result"] if sc and "result" in sc else [json.loads(c.text) for c in r.content]
def J(r):
    if r.isError: raise RuntimeError(r.content[0].text)
    sc=r.structuredContent
    if sc: return sc.get("result", sc)
    v=[json.loads(c.text) for c in r.content]
    return v[0] if len(v)==1 and isinstance(v[0], dict) else v, sys
sys.path.insert(0,'.')
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
T = config.MCP_TOKEN
async def m():
    async with streamablehttp_client(os.environ.get("CREWBOARD_MCP_URL", f"http://127.0.0.1:{config.PORT}/mcp/"), headers={"Authorization": f"Bearer {T}"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize(); c=lambda n,a={}: s.call_tool(n,a)
            await c("add_group_tag",{"name":"MCPタグ"}); await c("update_group_tag",{"name":"MCPタグ","color":"#f00"})
            print("tags",[t["name"] for t in L(await c("list_group_tags"))])
            await c("delete_group_tag",{"name":"MCPタグ"}); await c("add_assignee",{"name":"Zbot"}); await c("update_assignee",{"name":"Zbot","new_name":"Zbot2"})
            r=await c("delete_assignee",{"name":"Agent Bot"}); print("block:", r.isError, r.content[0].text[:60])
            await c("delete_assignee",{"name":"Zbot2"}); print("assignees",[a["name"] for a in L(await c("list_assignees"))])
asyncio.run(m())
