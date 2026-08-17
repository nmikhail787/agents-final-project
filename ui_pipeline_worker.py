"""Isolated LangGraph/MCP worker used by Person D's Streamlit UI on macOS."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from entry_point import get_recommendation


def main() -> None:
    transcript = sys.stdin.read().strip()
    if not transcript:
        print("__UI_RESULT__" + json.dumps({
            "answer": "",
            "full_answer": "No transcript was provided.",
            "citations": [],
            "merged_results": [],
            "constraints": {},
            "plan": {},
        }), flush=True)
        os._exit(0)

    # Deliberately do not close this loop or run normal interpreter cleanup.
    # On the affected Intel Mac, the graph returns correctly and then Python
    # can segfault during native/async cleanup. The OS closes the stdio pipes
    # when this short-lived worker exits, which also disconnects the MCP child.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(get_recommendation(transcript))
        print("__UI_RESULT__" + json.dumps(result, default=str), flush=True)
        os._exit(0)
    except BaseException as exc:
        print(f"WORKER_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        os._exit(1)


if __name__ == "__main__":
    main()
