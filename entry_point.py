import asyncio
from orchestration import AgentState, router_node, planner_node, retriever_node, critic_node
from langgraph.graph import StateGraph, START, END
from mcp_server.async_server_connection import start_mcp_client, stop_mcp_client, mcp_session

_agent = None  # compiled graph, built once and reused

def _build_graph():
    graph = StateGraph(AgentState)

    # add nodes
    graph.add_node('Routing', router_node)
    graph.add_node('Planning', planner_node)
    graph.add_node('Retriever', retriever_node)
    graph.add_node('Critic', critic_node)

    # add edges
    graph.add_edge(START, 'Routing')
    graph.add_edge('Routing', 'Planning')
    graph.add_edge('Planning', 'Retriever')
    graph.add_edge('Retriever', 'Critic')
    graph.add_edge('Critic', END)

    # compile
    return graph.compile()


async def get_recommendation(transcript: str) -> dict:
    """
    The one function Person D needs to call.

    Input: a transcript string (output of ASR).
    Output: a dict with everything the UI needs:
      {
        "answer": str,              # short spoken-style answer, feed to TTS
        "full_answer": str,         # longer detail, show on screen
        "citations": [...],         # [{doc_id, url, claim}, ...]
        "merged_results": [...],    # full comparison data, for the comparison table
        "constraints": {...},       # what the Router understood, for the agent step log
        "plan": {...},              # what the Planner decided, for the agent step log
      }

    Starts the MCP connection automatically on first call. Call shutdown()
    once when your app is closing.
    """
    global _agent

    import mcp_server.async_server_connection as async_server_connection
    if async_server_connection.mcp_session is None:
        await start_mcp_client()

    if _agent is None:
        _agent = _build_graph()

    result = await _agent.ainvoke({"raw_transcript": transcript})

    return {
        "answer": result.get("answer", ""),
        "full_answer": result.get("full_answer", ""),
        "citations": result.get("citations", []),
        "merged_results": result.get("merged_results", []),
        "constraints": result.get("constraints", {}),
        "plan": result.get("plan", {}),
    }


async def shutdown():
    """Call once when the app is closing, to cleanly stop the MCP server."""
    await stop_mcp_client()