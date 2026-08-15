# live intent wordage: covers time/currency, price, availability and existence (can be expanded later if needed)
# bc word list so small going to do rule based 
live_search_triggers = ["current", "availability", "now", "latest", "in stock", "available", "still",
                            "currently", "right now",  "today", "price", "cost", "how much", "going for", "still", "changed",
                            "available", "out of stock", "sold out", "can i buy", "can i get", "still selling", "still make",
                            "still around", "still exist", "discontinued", "still sold", "anymore"]

def check_live_intent(transcript):
    lowered = transcript.lower()
    matched = [t for t in live_search_triggers if t in lowered]
    return len(matched) > 0, matched # return bool and the matches list which can be used in the planner's reason field
