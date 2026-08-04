import csv
from retrieval import search

QUERIES = [
    ("building set for a seven year old", {"max_price": 30}),
    ("jigsaw puzzle for adults", {}),
    ("soft plush animal for a toddler", {"max_price": 20}),
    ("science experiment kit for kids", {"max_price": 50}),
    ("board game for family game night", {"min_price": 10, "max_price": 40}),
    ("lego building kit", {"brand": "LEGO"}),
    ("art supplies for painting", {"max_price": 25}),
    ("dollhouse accessories", {}),
    ("remote control car", {"max_price": 60}),
    ("card game for two players", {"max_price": 15}),
    ("wooden toys for babies", {"max_price": 30}),
    ("halloween costume for a child", {}),
    ("outdoor water toys for summer", {"max_price": 35}),
    ("educational math learning toy", {"max_price": 40}),
    ("model airplane kit", {}),
    ("stuffed dinosaur", {"max_price": 25}),
    ("party balloons and decorations", {"max_price": 20}),
    ("magic tricks set", {}),
    ("puzzle for a four year old", {"max_price": 15}),
    ("action figure collectible", {"max_price": 50}),
]

with open("eval/candidates.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query", "filters", "rank", "doc_id", "price", "subcategory", "title", "relevant"])
    for q, flt in QUERIES:
        hits = search(q, flt, k=5)
        for i, h in enumerate(hits, 1):
            w.writerow([q, str(flt), i, h["doc_id"], h["price"],
                        h["subcategory"], h["title"][:80], ""])
        if not hits:
            w.writerow([q, str(flt), 0, "", "", "", "NO RESULTS", ""])

print("wrote eval/candidates.csv — fill in the 'relevant' column with 1 or 0")