from rapidfuzz import fuzz
import re

# can change - set to this now 
MATCH_THRESHOLD = 80
PRICE_DISCREPANCY_ABS = 5.00   # flag if prices differ by more than $5
PRICE_DISCREPANCY_PCT = 0.15   # or more than 15%

def clean_price(price_value):
    # return prices as float - rag returns int or float and web returns string
    if price_value is None:
        return None
    if isinstance(price_value, (int, float)):
        return float(price_value)
    cleaned = str(price_value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None

def normalize_title(title):
    # strip retailer suffixes and mock-fixture prefixes before comparing
    title = re.sub(r"^\[MOCK\]\s*", "", title)
    title = re.sub(r"\s*-\s*(Amazon\.com|Walmart|Target|eBay).*$", "", title, flags=re.IGNORECASE)
    return title.strip()

def compute_discrepancies(rag_item, web_item, web_degraded):
    # For every matched pair of rag/web items, compute discrepancy notes 
    # (price gap, the rating-source distinction, and flag if the web data was degraded/mock).

    notes = []

    rag_price = clean_price(rag_item.get("price"))
    web_price = clean_price(web_item.get("price"))

    if rag_price is not None and web_price is not None:
        # if both searches return prices, compare them

        diff = abs(rag_price - web_price) # price diff

        if rag_price:
            # get percentage diff with rag price as original/baseline
            pct = diff / rag_price 
        else: 0

        if diff > PRICE_DISCREPANCY_ABS and pct > PRICE_DISCREPANCY_PCT:
            # price difference more than $5 AND greater than 15%
            notes.append("price_mismatch")

    # rag rating is always null per the corpus — flag if web has one, so the
    # Answerer never presents it as if it belongs to the catalog product
    if web_item.get("rating") is not None:
        notes.append("web_rating_present_no_catalog_rating")

    if web_item.get("availability") is not None:
        # informational, not a true mismatch
        # rage resutls dotn include info about inventory quantities
        notes.append("web_availability_info_only")  

    if web_degraded:
        notes.append("web_data_is_mock_or_degraded")

    return notes

def reconcile_results(rag_results, web_results, web_degraded=False):
    # compare results
    merged = []
    used_web_indices = set()

    for rag_item in rag_results:
        best_score = 0
        best_index = None

        for i, web_item in enumerate(web_results):
            # for each web(unused)/rag pair, compute a score for title similarity
            # and update best score
            if i in used_web_indices:
                continue
            
            # strip titles since web results tend to have a lot of 'junk' in the titles
            rag_name = normalize_title(rag_item["title"])
            web_name = normalize_title(web_item["title"])

            # token_set_ratio - expands on token_sort_ratio (which ignores word order) by
            # also ignoring duplicate/extra words
            score = fuzz.token_set_ratio(rag_name, web_name)
            if score > best_score:
                best_score = score
                best_index = i

        if best_index is not None and best_score >= MATCH_THRESHOLD:
            web_item = web_results[best_index] # keep best one
            used_web_indices.add(best_index) # remove web resut so cant reuse

            # compute discrepencies between the rag and web results
            # high score means high chance its the exact same item so its like we're 
            # comparing the same item from 2 places
            notes = compute_discrepancies(rag_item, web_item, web_degraded)

            # add the matched pair 
            merged.append({
                "match_type": "matched",
                "rag_item": rag_item,
                "web_item": web_item,
                "match_score": best_score,
                "has_discrepancy": len(notes) > 0,
                "discrepancy_notes": notes,
                "citation": {"doc_id": rag_item["doc_id"], "url": web_item["url"], "claim": rag_item["title"]},
            })
        else:
            # append remaining rag results after checking for matches
            merged.append({
                "match_type": "rag_only",
                "rag_item": rag_item,
                "web_item": None,
                "match_score": None,
                "has_discrepancy": False,
                "discrepancy_notes": [],
                "citation": {"doc_id": rag_item["doc_id"], "url": None, "claim": rag_item["title"]},
            })

    for i, web_item in enumerate(web_results):
        # append remaining web results after checking for matches
        if i not in used_web_indices:
            notes = ["web_data_is_mock_or_degraded"] if web_degraded else []
            merged.append({
                "match_type": "web_only",
                "rag_item": None,
                "web_item": web_item,
                "match_score": None,
                "has_discrepancy": len(notes) > 0,
                "discrepancy_notes": notes,
                "citation": {"doc_id": None, "url": web_item["url"], "claim": web_item["title"]},
            })

    return merged