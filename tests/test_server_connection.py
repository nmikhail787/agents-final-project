# %%
############### Get bare connection working with MCP server ################ 
# 8/9: ALL PASSED

import asyncio
import json
import os
 
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

#  Copied directly from the launch config in docs/MCP.md - describes how to launch the server
server_params = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.server"],
    cwd=os.getcwd(),
)

# open one client session
async def main():
    # whole script lives inside this block so the connection stays open the entire time the script is running

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
 
            # initialize
            await session.initialize()
            print("Connected to MCP server.\n")

            # list the tools the server exposes
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"Available tools: {tool_names}\n")

            # first call - rag.search for query "I need a building set for a seven-year-old under thirty dollars"
            print("Calling rag.search (call #1)...")
            result_1 = await session.call_tool(
                "rag.search",
                arguments={"query": "building set", "filters": {"max_price": 30}},
            )
            print("Result #1:")
            print(json.dumps(result_1.content, indent=2, default=str))
            print()

            # second call - SAME SESSION + NO REOPENING for query: "Show me wooden puzzles"
            print("Calling rag.search (call #2, same connection)...")
            result_2 = await session.call_tool(
                "rag.search",
                arguments={"query": "wooden puzzle", "filters": {}},
            )
            print("Result #2:")
            print(json.dumps(result_2.content, indent=2, default=str))

    # exited both "async with" blocks so session and server subprocesses have been closed automatically and cleanup is done
    print("\nConnection closed cleanly.")

# run
if __name__ == "__main__":
    asyncio.run(main())

