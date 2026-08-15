import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os

# StdioServerParameters — where launch config from docs/MCP.md goes (command, args, cwd).
# stdio_client(...) — spawns the server subprocess and gives a read/write stream pair.
# ClientSession(read, write) — wraps those streams into the actual thing that call call_tool() on.

server_params = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.server"],
    cwd=os.getcwd(),
)

# globals
mcp_session = None
_exit_stack = None

async def start_mcp_client():
    global mcp_session, _exit_stack
    _exit_stack = AsyncExitStack()
    read, write = await _exit_stack.enter_async_context(stdio_client(server_params))
    mcp_session = await _exit_stack.enter_async_context(ClientSession(read, write))
    await mcp_session.initialize()
    print("MCP client connected.")

async def stop_mcp_client():
    if _exit_stack:
        await _exit_stack.aclose()
        print("MCP client disconnected.")