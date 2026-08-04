import re
import pandas as pd

SRC = "data/raw/marketing_sample_for_amazon_com-ecommerce__20200101_20200131__10k_data.csv"
OUT = "data/products.parquet"


def parse_price(v):
    if not isinstance(v, str):
        return None
    v = v.replace(",", "")
    nums = re.findall(r"\$\s*([\d.]+)", v)
    if not nums:
        return None
    try:
        return float(nums[0])
    except ValueError:
        return None


def guess_brand(title):
    if not isinstance(title, str) or not title.strip():
        return None
    head = title.split(",")[0].split("-")[0].strip()
    tokens = head.split()
    if not tokens:
        return None
    brand = tokens[0].strip(" .")
    return brand if 1 < len(brand) < 30 else None


df = pd.read_csv(SRC)

parts = df["Category"].fillna("").str.split("|")
df["top_cat"] = parts.str[0].str.strip()
df["subcategory"] = parts.str[1].str.strip().replace("", None)

toys = df[df["top_cat"] == "Toys & Games"].copy()
print("toys rows:", len(toys))

toys["price"] = toys["Selling Price"].apply(parse_price)
toys = toys[toys["price"].notna() & toys["price"].between(0.5, 1000)]
print("after price filter:", len(toys))

toys["title"] = toys["Product Name"].str.strip()
toys["brand"] = toys["title"].apply(guess_brand)
toys["features"] = toys["About Product"].fillna("").str.replace(
    r"^Make sure this fits by entering your model number\.\s*\|\s*", "", regex=True
).str.strip()

toys["norm_title"] = toys["title"].str.lower().str.replace(
    r"[^a-z0-9 ]", "", regex=True).str.slice(0, 60)
before = len(toys)
toys = toys.drop_duplicates(subset=["norm_title"])
print("deduped:", before, "->", len(toys))

toys = toys.reset_index(drop=True)
toys["doc_id"] = ["T" + str(i + 1).zfill(5) for i in range(len(toys))]

out = pd.DataFrame({
    "doc_id": toys["doc_id"],
    "sku": toys["Uniq Id"],
    "title": toys["title"],
    "brand": toys["brand"],
    "price": toys["price"],
    "subcategory": toys["subcategory"],
    "category": "toys & games",
    "features": toys["features"],
    "url": toys["Product Url"],
})

out.to_parquet(OUT, index=False)
print("wrote", OUT, out.shape)
print()
print("coverage:")
print((1 - out.isna().mean()).round(3).to_string())
print()
print("price min %.2f median %.2f max %.2f" % (
    out.price.min(), out.price.median(), out.price.max()))
print()
print("top subcategories:")
print(out.subcategory.value_counts().head(8).to_string())
print()
print("sample brands:", out.brand.dropna().head(10).tolist())