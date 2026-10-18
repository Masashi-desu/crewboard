import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
T = config.MCP_TOKEN
async def m():
    async with streamablehttp_client(os.environ.get("CREWBOARD_MCP_URL", f"http://127.0.0.1:{config.PORT}/mcp/"), headers={"Authorization": f"Bearer {T}"}) as (r,w,_):
        async with ClientSession(r,w) as s:
            init = await s.initialize(); print("instructions mention rules:", "運用ルール" in (init.instructions or ""))
            assert "運用ルール" in (init.instructions or "")
            print("resources:", [str(x.uri) for x in (await s.list_resources()).resources])
            print("resource head:", (await s.read_resource("crewboard://rules")).contents[0].text.splitlines()[0])
            print("get_rules:", (await s.call_tool("get_rules", {})).content[0].text[:20])
            d = {t.name: t.description for t in (await s.list_tools()).tools}
            assert len(d) == 24 and "get_rules" in d
            print("desc has rules:", {n: "ルール" in d[n] or "概要" in d[n] for n in ["create_job","update_job","move_job","add_task","update_task","assign_job"]})
if __name__ == "__main__":
    asyncio.run(m())
