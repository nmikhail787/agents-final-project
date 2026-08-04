import csv

LABELS = {
    "building set for a seven year old":  [1, 1, 1, 1, 0],
    "jigsaw puzzle for adults":           [1, 1, 0, 0, 1],
    "soft plush animal for a toddler":    [1, 1, 1, 1, 1],
    "science experiment kit for kids":    [1, 1, 1, 1, 1],
    "board game for family game night":   [1, 1, 1, 1, 1],
    "lego building kit":                  [1, 1, 1, 1, 1],
    "art supplies for painting":          [1, 0, 0, 1, 0],
    "dollhouse accessories":              [0, 1, 1, 0, 1],
    "remote control car":                 [1, 1, 1, 1, 1],
    "card game for two players":          [0, 1, 1, 1, 1],
    "wooden toys for babies":             [1, 1, 1, 1, 0],
    "halloween costume for a child":      [1, 0, 1, 1, 0],
    "outdoor water toys for summer":      [1, 0, 0, 0, 0],
    "educational math learning toy":      [1, 1, 1, 1, 1],
    "model airplane kit":                 [1, 1, 1, 1, 1],
    "stuffed dinosaur":                   [1, 1, 1, 0, 0],
    "party balloons and decorations":     [1, 1, 1, 1, 1],
    "magic tricks set":                   [1, 1, 1, 1, 0],
    "puzzle for a four year old":         [0, 0, 1, 0, 1],
    "action figure collectible":          [1, 1, 1, 1, 1],
}

rows = list(csv.DictReader(open("eval/candidates.csv")))
for r in rows:
    if r["doc_id"]:
        r["relevant"] = str(LABELS[r["query"]][int(r["rank"]) - 1])

with open("eval/labeled.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
print("wrote eval/labeled.csv")