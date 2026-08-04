#!/usr/bin/env bash
set -e
echo "==> building catalog from raw CSV"
python build_catalog.py
echo
echo "==> building vector index"
python build_index.py
echo
echo "==> smoke test"
python retrieval.py