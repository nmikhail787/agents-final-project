#!/usr/bin/env bash
# Start the MCP server on stdio. Runs from the repo root regardless of the
# caller's cwd, which matters because Inspector and Claude Desktop launch it
# from wherever they happen to be.
set -e
cd "$(dirname "$0")"
exec python -m mcp_server.server
