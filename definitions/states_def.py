from typing import TypedDict

# state definitions 
# define nested TypedDicts for each structured field, then reference them by name
class Constraints(TypedDict):
    max_price: float | None
    min_price: float | None
    subcategory: str | None
    brand: str | None
    safety_flags: list[str]
    age_mentioned: bool
    raw_task: str

class Plan(TypedDict):
    call_rag: bool
    call_web: bool
    reason: str

class Citation(TypedDict):
    doc_id: str | None
    url: str | None
    claim: str

class AgentState(TypedDict):
    raw_transcript: str
    constraints: Constraints
    plan: Plan
    raw_rag_results: list[dict]
    raw_web_results: list[dict]
    web_degraded: bool # flag - indicates if live web search is on or not
    merged_results: list[dict] # e/ item has own has_discrepancy: bool and discrepancy_note: str
    answer: str
    full_answer: str
    citations: list[Citation]