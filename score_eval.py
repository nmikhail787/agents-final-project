import csv
from collections import defaultdict

rows = list(csv.DictReader(open("eval/labeled.csv")))

by_query = defaultdict(list)
for r in rows:
    if r["doc_id"]:
        by_query[r["query"]].append((int(r["rank"]), r["relevant"].strip()))

unlabeled = [r for r in rows if r["doc_id"] and r["relevant"].strip() not in ("0", "1")]
if unlabeled:
    print(f"WARNING: {len(unlabeled)} rows unlabeled\n")

hits_at_1 = hits_at_3 = 0
p_at_3_total = 0.0
n = len(by_query)

print(f"{'query':<45} {'P@3':>6} {'hit@3':>6}")
print("-" * 60)
for q, items in sorted(by_query.items()):
    items.sort()
    top3 = [rel for rank, rel in items if rank <= 3]
    rel3 = sum(1 for r in top3 if r == "1")
    p3 = rel3 / max(len(top3), 1)
    p_at_3_total += p3
    if rel3 > 0:
        hits_at_3 += 1
    if items and items[0][1] == "1":
        hits_at_1 += 1
    print(f"{q[:44]:<45} {p3:>6.2f} {'yes' if rel3 else 'NO':>6}")

print("-" * 60)
print(f"queries:            {n}")
print(f"hit rate @1:        {hits_at_1/n:.1%}")
print(f"hit rate @3:        {hits_at_3/n:.1%}")
print(f"mean precision @3:  {p_at_3_total/n:.2f}")