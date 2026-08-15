# %%
############### Validate All Nodes ################ 
from definitions.states_def import AgentState
from orchestration import router_node, planner_node, retriever_node, critic_node
from langgraph.graph import StateGraph, START, END
from mcp_server.async_server_connection import start_mcp_client, stop_mcp_client
import asyncio

async def main():
    # start up the server
    await start_mcp_client()

    try:
        # setup graph
        graph = StateGraph(AgentState)

        # add the node
        graph.add_node('Routing', router_node)
        graph.add_node('Planning', planner_node)
        graph.add_node('Retriever', retriever_node)
        graph.add_node('Critic', critic_node)

        # connect the graph
        graph.add_edge(START, 'Routing') # start at routing
        graph.add_edge('Routing', 'Planning') 
        graph.add_edge('Planning', 'Retriever')
        graph.add_edge('Retriever', 'Critic')
        graph.add_edge('Critic', END)

        # compile 
        agent = graph.compile()

        # test transcripts 
        transcripts = [
            "I need a building set for a seven-year-old under thirty dollars.",
            "What's a good toy for a road trip?",
            "Is the LEGO Classic Creative Box still available, and what's it going for right now?",
            "Show me Melissa & Doug wooden puzzles under twenty dollars.",
            "I want something between fifteen and twenty five dollars for a toddler.",
            "What's the highest-rated dinosaur toy you have?",
            "Find me an eco-friendly stainless steel cleaner under fifteen dollars.",
            "What's a good toy for a one-year-old that has small parts?",
            "I'm looking for outdoor water toys for the backyard.",
        ]
    
        for t in transcripts:

            # invoke the agent 
            result = await agent.ainvoke({"raw_transcript": t})
 
            print(f"\n{'='*60}")
            print(f"Query: {t}")
            print(f"Constraints: {result['constraints']}")
            print(f"Plan: {result['plan']}")
            print(f"Answer: {result['answer']}")
            print(f"Citations: {result['citations']}")

    finally:
        await stop_mcp_client()

# run
if __name__ == "__main__":
    asyncio.run(main())