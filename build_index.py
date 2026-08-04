import chromadb
import pandas as pd

df = pd.read_parquet("data/products.parquet")
print("loaded", len(df), "products")

client = chromadb.PersistentClient(path="chroma")

try:
    client.delete_collection("products")
    print("dropped existing collection")
except Exception:
    pass

col = client.create_collection("products")

docs, metas, ids = [], [], []
for row in df.itertuples(index=False):
    text = " | ".join([
        row.title,
        row.subcategory or "",
        (row.features or "")[:600],
    ])
    docs.append(text)
    metas.append({
        "doc_id": row.doc_id,
        "sku": row.sku,
        "title": row.title,
        "brand": row.brand or "",
        "price": float(row.price),
        "subcategory": row.subcategory or "",
        "category": row.category,
        "features": (row.features or "")[:1000],
        "url": row.url,
    })
    ids.append(row.doc_id)

BATCH = 500
for i in range(0, len(docs), BATCH):
    col.add(
        documents=docs[i:i + BATCH],
        metadatas=metas[i:i + BATCH],
        ids=ids[i:i + BATCH],
    )
    print(f"indexed {min(i + BATCH, len(docs))}/{len(docs)}")

print("\ndone. collection count:", col.count())