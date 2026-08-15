# %%
############### Validate error detection in JSON output of LLM parse ################
# 8/9: ALL PASSED

from assistant_functions.validate_parse import validate_router_output

test_cases = {
    "valid": '{"max_price": 30, "min_price": null, "subcategory": "Building Toys", "brand": null, "safety_flags": [], "age_mentioned": true, "raw_task": "a building set recommendation"}',

    "not_json": 'Sure! Here is the JSON: {"max_price": 30}',

    "missing field": '{"max_price": 30, "min_price": null, "subcategory": null, "brand": null, "safety_flags": [], "age_mentioned": true}',

    "wrong type": '{"max_price": "thirty", "min_price": null, "subcategory": null, "brand": null, "safety_flags": [], "age_mentioned": false, "raw_task": "x"}',

    "invalid subcategory": '{"max_price": null, "min_price": null, "subcategory": "Outdoor Toys", "brand": null, "safety_flags": [], "age_mentioned": false, "raw_task": "x"}',

    "invalid safety_flag": '{"max_price": null, "min_price": null, "subcategory": null, "brand": null, "safety_flags": ["choking_risk"], "age_mentioned": true, "raw_task": "x"}',

    "min > max price": '{"max_price": 10, "min_price": 50, "subcategory": null, "brand": null, "safety_flags": [], "age_mentioned": false, "raw_task": "x"}',
}

for name, raw in test_cases.items():
    data, error = validate_router_output(raw)
    status = "PASSED" if error is None else f"CAUGHT -> {error}"
    print(f"{name}: {status}")

# %%
############### Validate LLM parse ################ 
# 8/9: ALL PASSED

from openai import OpenAI
from prompts.agent_prompt import agentRole
from assistant_functions.validate_parse import validate_router_output
from dotenv import load_dotenv
import os

load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

def call_router(transcript):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": agentRole},
            {"role": "user", "content": transcript}
        ]
    )
    return response.choices[0].message.content

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
    raw_output = call_router(t)
    data, error = validate_router_output(raw_output)
    print(f"\nTranscript: {t}")
    print(f"Raw output: {raw_output}")
    print(f"Result: {'PASSED' if not error else f'FAILED -> {error}'}")

# %%
############### Validate Full Router Node ################ 
# 8/9: ALL PASSED

from orchestration import AgentState, router_node
from langgraph.graph import StateGraph, START, END

# setup graph
graph = StateGraph(AgentState)

# add the node
graph.add_node('Routing', router_node)

# connect the graph
graph.add_edge(START, 'Routing') # start at routing
graph.add_edge('Routing', END) # end bc want to test the one node only

# use same test transcripts as above
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
    # compile 
    agent = graph.compile()

    # invoke the agent 
    print(f"Query: {t}\nAgent Parse:{agent.invoke({"raw_transcript": t})}")
    

