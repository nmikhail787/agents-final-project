import json

REQUIRED_CRITIC_FIELDS = {
    "spoken_answer": (str,),
    "full_answer": (str,),
    "citations": (list,),
}

def check_critic_types(data):
    for field, allowed_types in REQUIRED_CRITIC_FIELDS.items():
        if field not in data:
            return f"missing field: {field}"
        if not isinstance(data[field], allowed_types):
            return f"wrong type for {field}: {type(data[field])}"
    return None

def check_critic_values(data):
    for i, citation in enumerate(data["citations"]):
        if not isinstance(citation, dict):
            return f"citation {i} is not an object"
        if "doc_id" not in citation or "url" not in citation or "claim" not in citation:
            return f"citation {i} missing doc_id/url/claim"
        if citation["doc_id"] is None and citation["url"] is None:
            return f"citation {i} has neither doc_id nor url"
    return None

def validate_critic_output(raw_output):
    try:
        data = json.loads(raw_output)
    except json.JSONDecodeError:
        return None, "not valid JSON"

    error = check_critic_types(data)
    if error:
        return None, error

    error = check_critic_values(data)
    if error:
        return None, error

    return data, None