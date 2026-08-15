RELEVANCE_SCORE_THRESHOLD = 0.5

def has_relevant_results(merged_results):
    return any(
        item["rag_item"] and item["rag_item"].get("score", 0) >= RELEVANCE_SCORE_THRESHOLD
        for item in merged_results
    )

def build_grounding_context(merged_results):
    context = []
    for item in merged_results:
        if item["rag_item"] and item["rag_item"].get("score", 0) < RELEVANCE_SCORE_THRESHOLD:
            continue
        context.append({
            "match_type": item["match_type"],
            "title": item["rag_item"]["title"] if item["rag_item"] else item["web_item"]["title"],
            "catalog_price": item["rag_item"]["price"] if item["rag_item"] else None,
            "live_price": item["web_item"]["price"] if item["web_item"] else None,
            "live_availability": item["web_item"].get("availability") if item["web_item"] else None,
            "discrepancy_notes": item["discrepancy_notes"],
            "citation": item["citation"],
        })
    return context