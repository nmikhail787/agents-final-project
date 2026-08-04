# Data preprocessing and retrieval

## Source

Amazon Product Dataset 2020 (Kaggle, `promptcloud/amazon-product-dataset-2020`),
10,002 rows × 28 columns, sampled Jan 2020.

## Why we did not use the Household Cleaning slice

The project brief suggests Household Cleaning as the corpus. Profiling the actual
file showed this is not viable:

- `Health & Household` contains 23 rows.
- `Toys & Games` contains 6,662 rows (67% of the file).
- Ten columns ship **100% empty** in this sample, including `Brand Name`,
  `Ingredients`, `Asin`, `Sku`, `List Price`, and `Product Description`.
- There is no rating column at any coverage.

We therefore indexed the **Toys & Games** slice and revised the filter contract.
Fields the brief assumes (rating, ingredients, price-per-unit) have no source in
this data; price-per-ounce is also semantically meaningless for toys.

## Cleaning pipeline (`build_catalog.py`)

| Step | Rows |
|---|---|
| Toys & Games rows | 6,662 |
| after price parse + sanity range ($0.50–$1000) | 6,559 |
| after variant dedup | 6,461 |

- **Price** — `Selling Price` is a string (`"$99.95"`). Stripped symbols and
  commas; where a range is given, took the low end. Rows with no parseable
  price were dropped.
- **Brand** — no brand column exists. Derived from the first token of
  `Product Name`, which is where Amazon titles conventionally put it. This is
  approximate: it yields `LEGO`, `Hoffmaster`, `GUND` correctly but produces
  noise like `The` or `DC` on ~1% of rows, and cannot capture multi-word brands
  such as "Melissa & Doug". Brand is a secondary filter; primary matching is
  semantic.
- **Subcategory** — second level of the pipe-delimited `Category` field.
  15+ well-populated groups; 100% coverage on the slice.
- **Features** — `About Product`, with Amazon's boilerplate
  "Make sure this fits…" prefix stripped.
- **Dedup** — normalized the first 60 characters of each title (lowercased,
  alphanumeric only) and kept one row per group, collapsing size and colour
  variants of the same product.

Output: `data/products.parquet`, 6,461 rows, ≥99% coverage on every field.

## Index (`build_index.py`)

Chroma persistent client at `chroma/`, collection `products`, using Chroma's
default embedding function (all-MiniLM-L6-v2 via ONNX — chosen over
sentence-transformers to avoid a ~3GB PyTorch dependency; same model, same
vectors).

Embedded text per product: `title | subcategory | features[:600]`.
Full product record is stored in metadata so retrieval needs no second lookup.

## Retrieval (`retrieval.py`)

`search(query, filters, k)` — vector similarity plus **hard** metadata filters.

Filter keys: `max_price`, `min_price`, `subcategory`, `brand`.

Design decisions:
- Filters are constraints, not preferences. A $40 item is never returned for a
  "$30 max" query regardless of similarity.
- Over-fetches 60 candidates before filtering, so tight budgets don't starve
  the result set.
- Returns `[]` rather than relaxing a constraint. Callers must handle the empty
  case; inventing a near-match would produce ungrounded answers downstream.
- Score is `1/(1+distance)`, normalized to 0–1.

## Evaluation (`eval/`)

20 hand-written queries spanning subcategories and filter types, top-5 retrieved
and manually labelled for relevance (`eval/labeled.csv`).

| Metric | Value |
|---|---|
| hit rate @1 | 85% |
| hit rate @3 | 100% |
| mean precision @3 | 0.83 |

Known failure modes:
- **"art supplies for painting"** (P@3 = 0.33) — returns Vallejo model-paint
  pots. Corpus contains hobby paints but few general art supplies; a retrieval
  system cannot surface inventory that isn't there.
- **"outdoor water toys for summer"** (0.33) — "water" pulls bath toys.
- **"puzzle for a four year old"** (0.33) — age qualifiers are ignored. Age
  appears in only 2.4% of product text, so it is not extractable as a filter.
  The Router should not attempt to bind age constraints.

## Rebuilding

    ./run_index.sh

Requires `data/raw/marketing_sample_for_amazon_com-ecommerce__20200101_20200131__10k_data.csv`.