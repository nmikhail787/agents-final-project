from prompts.agent_prompt import agentRole
from prompts.critic_prompt import criticRole
from assistant_functions.validate_parse import validate_router_output, parse_mcp_result 
import mcp_server.async_server_connection as async_server_connection
from assistant_functions.result_comparison import reconcile_results
from assistant_functions.critic_assist import has_relevant_results, build_grounding_context
import json
from assistant_functions.validate_critic import validate_critic_output
from assistant_functions.planner_assist import check_live_intent
from definitions.states_def import AgentState
from definitions.llm_def import llm
############################################################################

def router_node(state: AgentState):
  # extract task & constraints (budget, material, brand) + safety flag
  # LLM used here bc input is unstructured (natural speech)

    query = state['raw_transcript']

    prompt = f"""
            You are an advanced search assistant designed to help users with finding Toys & Games. 
            Your job is to extract structured shopping constraints from the product request.

            User request: {query}

            """

    # send query to llm and ask to parse and return in correct JSON format
    raw_output = llm.invoke([
        {
            "role": "system",
            "content": agentRole
        },
        {
            "role": "user",
            "content": prompt
        }
    ]).content

    # check if answer is valid
    data, error = validate_router_output(raw_output)
    
    if error:
        # try one more time, telling the model what went wrong
        retry_prompt = f"Your last response had this error: {error}. Fix it and return only JSON."
        raw_output = llm.invoke([
                    {
                        "role": "system",
                        "content": agentRole
                    },
                    {
                        "role": "user",
                        "content": f"""{retry_prompt} Prompt: {prompt}"""
                    }
                ]).content
        
        # recheck after first retry
        data, error = validate_router_output(raw_output)

    if error:
        # give up safely — fall back to a broad, unfiltered search
        print(f"Router validation failed twice: {error}")
        return {"constraints": {
                        "max_price": None, "min_price": None, "subcategory": None,
                        "brand": None, "safety_flags": [], "age_mentioned": False,
                        "raw_task": query
                    }}

    return {"constraints": data}

def planner_node(state: AgentState):
    # determine what calls are needed to answer the user query 
    # always calls rag.search and only calls web.search when transcript signals live intent

    # checking the raw transcript so didn't lose anything in the parsing

    transcript = state['raw_transcript']
    call_web, matched_triggers  = check_live_intent(transcript)

    return {
        "plan": {
            "call_rag": True,
            "call_web": call_web,
            "reason": f"matched live-intent triggers: {matched_triggers }" if matched_triggers  else "no live-intent triggers matched"
            }
        }


async def retriever_node(state: AgentState):
    # made async bc MCP calls are async
    # make rag and web search MCP calls and reconciliate + merge the results

    constraints = state["constraints"]
    plan = state["plan"]

    # input is like this: {"query": "building set", "filters": {"max_price": 30}}
    # so need to change constraints to filters
    filters = {}

    if constraints.get("max_price") is not None:
        filters["max_price"] = constraints["max_price"]
    if constraints.get("min_price") is not None:
        filters["min_price"] = constraints["min_price"]
    if constraints.get("subcategory") is not None:
        filters["subcategory"] = constraints["subcategory"]
    if constraints.get("brand") is not None:
        filters["brand"] = constraints["brand"]

    # MCP server conenction: open connection once and shut down when everything done

    # always run rag search
    rag_result = await async_server_connection.mcp_session.call_tool(
        "rag.search",
        arguments={"query": constraints["raw_task"], "filters_applied": filters},
    )
    # validate and dtype fix
    rag_parsed = parse_mcp_result(rag_result.content)

    # set default results - will catch out of scope queries
    web_parsed = {"results": [], "degraded": False, "notes": []} 

    # only run web if indicated by prior node
    web_result = None
    if plan["call_web"]:
        web_result = await async_server_connection.mcp_session.call_tool(
            "web.search",
            arguments={"query": constraints["raw_task"], "filters_applied": filters},
        )

        # validate outputs and put in same dtype 
        web_parsed = parse_mcp_result(web_result.content)

    # reconcile results 
    merged = reconcile_results(rag_parsed["results"], web_parsed["results"])

    return {
        "raw_rag_results": rag_parsed["results"],
        "raw_web_results": web_parsed["results"],
        "web_degraded": web_parsed.get("degraded", False),
        "merged_results": merged
        }

async def critic_node(state:AgentState):
    # rag search will always happen and retriever will return 
    # what the vector search found and the associated score 
    # low similarity score = "this is a stretch match," not "no results."
    # Answerer/Critic's job to look at scores and recognize "these aren't good enough to recommend"

    # 1. determine which results are relevant (score over 0.5 - based on examples)
    # RAG only
    # if comes back as none then need UI to say "we don't carry anything matching that in our toy catalog"
    # and can surface the web-only items in the UI's comparison table as 
    # "here's what we found outside our catalog, for reference"
    merged_results = state["merged_results"]
    rel_results = has_relevant_results(merged_results) # boolean
    grounding_context = build_grounding_context(merged_results) if rel_results else []

    evidence = {
        "raw_task": state["constraints"]["raw_task"],
        "has_relevant_results": rel_results,
        "safety_flags": state["constraints"]["safety_flags"],
        "grounding_context": grounding_context,
    }

    prompt = f"Evidence:\n{json.dumps(evidence, indent=2)}"

    raw_output = llm.invoke([
        {"role": "system", "content": criticRole},
        {"role": "user", "content": prompt}
    ]).content

    data, error = validate_critic_output(raw_output)

    if error:
        retry_prompt = f"Your last response had this error: {error}. Fix it and return only JSON."
        raw_output = llm.invoke([
            {"role": "system", "content": criticRole},
            {"role": "user", "content": f"{retry_prompt} Evidence:\n{json.dumps(evidence, indent=2)}"}
        ]).content
        data, error = validate_critic_output(raw_output)

    if error:
        print(f"Critic validation failed twice: {error}")
        print(f"Raw output was: {raw_output}")
        return {
            "answer": "Sorry, I wasn't able to put together a reliable answer for that request.",
            "citations": []
        }

    return {
        "answer": data["spoken_answer"],
        "full_answer": data["full_answer"],
        "citations": data["citations"]
    }

  
