"""Tests for the MCP server (Person B).

No network: the provider is monkeypatched everywhere. The SerpApi free tier is
metered and a test suite that spends quota is a test suite nobody runs.

    pytest tests/ -q
"""

import json
import time

import pytest

from mcp_server import allowlist, providers, web_tool
from mcp_server.cache import TTLCache, make_key
from mcp_server.jsonl_log import redact
from mcp_server.rag_tool import _clean_filters, _to_result


# --------------------------------------------------------------------------
# TTL cache — the brief requires a 60-300s TTL, so expiry must actually work.
# --------------------------------------------------------------------------

def test_cache_hit_and_miss():
    c = TTLCache(ttl_seconds=60)
    assert c.get("absent") == (False, None)
    c.set("k", {"v": 1})
    assert c.get("k") == (True, {"v": 1})


def test_cache_entry_actually_expires():
    c = TTLCache(ttl_seconds=0.15)
    c.set("k", "v")
    assert c.get("k")[0] is True
    time.sleep(0.25)
    hit, value = c.get("k")
    assert hit is False and value is None


def test_cached_empty_result_is_still_a_hit():
    """A cached [] must not be mistaken for a miss, or an expensive empty
    search gets re-run on every call."""
    c = TTLCache(ttl_seconds=60)
    c.set("k", [])
    assert c.get("k") == (True, [])


def test_cache_evicts_when_full():
    c = TTLCache(ttl_seconds=60, max_entries=3)
    for i in range(5):
        c.set(f"k{i}", i)
    assert len(c._data) <= 3


def test_get_or_call_runs_fn_once():
    c = TTLCache(ttl_seconds=60)
    calls = []

    def fn():
        calls.append(1)
        return "result"

    assert c.get_or_call("k", fn) == ("result", False)
    assert c.get_or_call("k", fn) == ("result", True)
    assert len(calls) == 1


def test_cache_key_is_argument_order_independent():
    """{"a":1,"b":2} and {"b":2,"a":1} are the same query."""
    assert make_key("t", {"a": 1, "b": 2}) == make_key("t", {"b": 2, "a": 1})


def test_web_search_ttl_is_clamped_into_the_required_window():
    assert 60.0 <= web_tool._CACHE.ttl <= 300.0


@pytest.mark.parametrize("env_ttl,expected", [("250", 250.0), ("10", 60.0), ("9999", 300.0)])
def test_ttl_env_var_is_honoured_and_clamped(env_ttl, expected):
    """Runs in a subprocess because the TTL is read at import time. Also guards
    the import ordering in server.py: .env must load before web_tool imports."""
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-c", "from mcp_server.web_tool import _CACHE; print(_CACHE.ttl)"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "WEB_SEARCH_TTL": env_ttl,
             "PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parent.parent)},
    )
    assert out.returncode == 0, out.stderr
    assert float(out.stdout.strip()) == expected


def test_result_with_no_url_is_dropped_and_not_reported_as_a_domain():
    """Documents current behaviour: a urlless row is dropped silently, since
    reporting "" as a blocked domain would be noise."""
    allowed, blocked = allowlist.filter_results([{"url": "", "title": "x"}])
    assert allowed == [] and blocked == []


# --------------------------------------------------------------------------
# Secret redaction — the brief explicitly requires not logging secrets.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "key", ["api_key", "API_KEY", "SERPAPI_API_KEY", "token", "secret", "Authorization", "password"]
)
def test_redact_strips_secret_shaped_keys(key):
    assert redact({key: "sensitive"})[key] == "***REDACTED***"


def test_redact_is_recursive_and_keeps_ordinary_fields():
    out = redact({"query": "lego", "nested": [{"api_key": "abc"}], "num": 3})
    assert out["query"] == "lego"
    assert out["num"] == 3
    assert out["nested"][0]["api_key"] == "***REDACTED***"


def test_redact_leaves_innocuous_keys_alone():
    assert redact({"query": "x", "url": "y"}) == {"query": "x", "url": "y"}


# --------------------------------------------------------------------------
# Domain allowlist — safety requirement, and previously unexercised because
# every live result happened to be on an allowlisted domain.
# --------------------------------------------------------------------------

def test_allowlist_permits_known_retailer():
    assert allowlist.is_allowed("https://www.amazon.com/dp/B000")


def test_allowlist_blocks_unknown_domain():
    assert not allowlist.is_allowed("https://sketchy-deals.example/thing")


def test_allowlist_permits_subdomain():
    assert allowlist.is_allowed("https://smile.amazon.com/dp/B000")


def test_allowlist_rejects_empty_and_malformed_urls():
    assert not allowlist.is_allowed("")
    assert not allowlist.is_allowed("not-a-url")


def test_filter_results_separates_and_reports_blocked():
    rows = [
        {"url": "https://www.target.com/p/1", "title": "ok"},
        {"url": "https://malware.example/x", "title": "bad"},
    ]
    allowed, blocked = allowlist.filter_results(rows)
    assert [r["title"] for r in allowed] == ["ok"]
    assert blocked == ["malware.example"]


def test_allowlist_env_override_replaces_default(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_ALLOWLIST", "onlythis.com")
    assert allowlist.is_allowed("https://onlythis.com/x")
    assert not allowlist.is_allowed("https://www.amazon.com/dp/B000")


# --------------------------------------------------------------------------
# Provider normalisation, including the two live-key bugs found earlier:
# `num` being ignored, and `link` being null on every shopping row.
# --------------------------------------------------------------------------

def test_shopping_normalisation_uses_product_link_when_link_is_null():
    row = providers._normalise_shopping(
        {"title": "T", "link": None, "product_link": "https://p", "price": "$1.00"}
    )
    assert row["url"] == "https://p"
    assert row["price"] == "$1.00"


def test_shopping_snippet_carries_merchant_and_rating():
    row = providers._normalise_shopping(
        {"title": "T", "source": "Target", "rating": 4.8, "reviews": 120, "product_link": "https://p"}
    )
    assert "Target" in row["snippet"]
    assert "4.8" in row["snippet"]


def test_organic_results_have_no_price():
    row = providers._normalise_organic({"title": "T", "link": "https://x", "snippet": "s"})
    assert row["price"] is None and row["availability"] is None
    assert row["url"] == "https://x"


def test_num_is_enforced_locally_because_serpapi_ignores_it(monkeypatch):
    """The shopping engine returns ~40 rows regardless of `num`."""
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"shopping_results": [{"title": f"t{i}", "product_link": f"https://x/{i}"} for i in range(40)]}

    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: FakeResp())
    assert len(providers.serpapi_search("q", "shopping", num=3)) == 3


def test_organic_search_path_returns_normalised_rows(monkeypatch):
    """search_type='search' was never exercised against the real API."""
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"organic_results": [{"title": "T", "link": "https://x", "snippet": "s"}]}

    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: FakeResp())
    rows = providers.serpapi_search("q", "search", num=5)
    assert rows == [{"title": "T", "url": "https://x", "snippet": "s", "price": None, "availability": None}]


def test_missing_api_key_raises_provider_error(monkeypatch):
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(providers.ProviderError):
        providers.serpapi_search("q")


def test_unfilled_placeholder_key_is_treated_as_missing(monkeypatch):
    """A teammate who copied .env.example but never filled it in should get a
    'set your key' message, not a bare 401 from the provider."""
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "your-serpapi-key-here")
    with pytest.raises(providers.ProviderError, match="not set"):
        providers.serpapi_search("q")


def test_serpapi_error_in_200_body_is_raised(monkeypatch):
    """SerpApi reports some failures as HTTP 200 with an `error` key."""
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")

    class FakeResp:
        status_code = 200

        def json(self):
            return {"error": "Invalid API key"}

    monkeypatch.setattr(providers.httpx, "get", lambda *a, **k: FakeResp())
    with pytest.raises(providers.ProviderError, match="Invalid API key"):
        providers.serpapi_search("q")


def test_api_key_is_redacted_from_error_text(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "SUPERSECRET")
    assert "SUPERSECRET" not in providers._redact_url("https://serpapi.com/?api_key=SUPERSECRET")


# --------------------------------------------------------------------------
# web.search degradation — a dead provider must never take the server down,
# because the same process serves rag.search.
# --------------------------------------------------------------------------

def test_web_search_degrades_instead_of_raising(monkeypatch):
    monkeypatch.setattr(
        web_tool.providers,
        "serpapi_search",
        lambda *a, **k: (_ for _ in ()).throw(providers.ProviderError("dead key")),
    )
    web_tool._CACHE._data.clear()
    r = web_tool.run_web_search("anything", num=2)
    assert r.degraded is True
    assert r.count == 0 and r.results == []
    assert any("dead key" in n for n in r.notes)


def test_web_search_marks_fixtures_as_degraded(monkeypatch):
    monkeypatch.setenv("MOCK_WEB_SEARCH", "1")
    web_tool._CACHE._data.clear()
    r = web_tool.run_web_search("lego", num=2)
    assert r.degraded is True
    assert all(x.title.startswith("[MOCK]") for x in r.results)


def test_web_search_reports_blocked_domains(monkeypatch):
    monkeypatch.delenv("MOCK_WEB_SEARCH", raising=False)
    monkeypatch.setattr(
        web_tool.providers,
        "serpapi_search",
        lambda *a, **k: [
            {"title": "ok", "url": "https://www.target.com/p", "snippet": "", "price": None, "availability": None},
            {"title": "bad", "url": "https://evil.example/p", "snippet": "", "price": None, "availability": None},
        ],
    )
    web_tool._CACHE._data.clear()
    r = web_tool.run_web_search("q", num=5)
    assert r.count == 1
    assert r.blocked_domains == ["evil.example"]


# --------------------------------------------------------------------------
# rag.search adapter — the declare-and-null contract for rating/ingredients.
# --------------------------------------------------------------------------

def test_unset_filters_are_dropped_not_passed_as_none():
    """Person A treats any present key as a hard constraint, so passing
    None through would over-constrain the query."""
    assert _clean_filters(None, None, None, None) == ({}, [])
    assert _clean_filters(30, None, None, None) == ({"max_price": 30.0}, [])


def test_filters_are_coerced_and_blank_strings_dropped():
    out, warnings = _clean_filters(30, 5, "", "")
    assert out == {"max_price": 30.0, "min_price": 5.0}
    assert warnings == []


# --- the regression that cost Person C a day: nested vs flat filter shapes ---

def test_nested_filters_dict_is_honoured():
    """The bug: the graph passed {"query":..., "filters":{...}}, which bound to
    nothing, so every search ran unfiltered."""
    out, _ = _clean_filters(None, None, None, None, {"max_price": 30})
    assert out == {"max_price": 30.0}


def test_nested_and_flat_shapes_are_equivalent():
    nested, _ = _clean_filters(None, None, None, None, {"max_price": 30})
    flat, _ = _clean_filters(30, None, None, None, None)
    assert nested == flat


def test_all_four_filters_work_nested():
    out, warnings = _clean_filters(
        None, None, None, None,
        {"max_price": 30, "min_price": 5, "subcategory": "Building Toys", "brand": "LEGO"},
    )
    assert out == {
        "max_price": 30.0, "min_price": 5.0,
        "subcategory": "Building Toys", "brand": "LEGO",
    }
    assert warnings == []


def test_flat_argument_overrides_nested_on_conflict():
    out, _ = _clean_filters(10, None, None, None, {"max_price": 30})
    assert out == {"max_price": 10.0}


def test_nested_none_values_are_dropped():
    """The router emits {'subcategory': None, 'brand': None} for unset fields."""
    out, _ = _clean_filters(
        None, None, None, None,
        {"max_price": 25, "min_price": 15, "subcategory": None, "brand": None},
    )
    assert out == {"max_price": 25.0, "min_price": 15.0}


def test_unsupported_filter_key_is_reported_not_silently_dropped():
    """A silently ignored argument is exactly what made the original bug
    invisible. An unknown key must surface in the response."""
    out, warnings = _clean_filters(None, None, None, None, {"maxprice": 30})
    assert out == {}
    assert len(warnings) == 1
    assert "maxprice" in warnings[0]


def test_filters_applied_is_not_accepted_as_an_input_name():
    """`filters_applied` is a RESPONSE field. Passing it as input must not
    silently behave like `filters` — it should be reported."""
    out, warnings = _clean_filters(
        None, None, None, None, {"filters_applied": {"max_price": 30}}
    )
    assert out == {}
    assert warnings and "filters_applied" in warnings[0]


ROW = {
    "doc_id": "T00497", "sku": "abc", "title": "Wooden Set", "brand": "Melissa",
    "price": 16.99, "subcategory": "Building Toys", "category": "toys & games",
    "features": "f", "url": "https://x", "score": 0.62,
}


def test_rating_and_ingredients_are_always_null():
    r = _to_result(dict(ROW))
    assert r.rating is None
    assert r.ingredients is None


def test_rating_is_null_even_if_upstream_ever_supplies_one():
    """Guards the grounding contract: the corpus has no ratings, so a value
    appearing upstream would be spurious and must not reach a citation."""
    r = _to_result({**ROW, "rating": 4.5, "ingredients": "plastic"})
    assert r.rating is None
    assert r.ingredients is None


def test_doc_id_survives_mapping_as_the_citation_handle():
    assert _to_result(dict(ROW)).doc_id == "T00497"


def test_null_brand_is_preserved():
    assert _to_result({**ROW, "brand": None}).brand is None


# --------------------------------------------------------------------------
# Server registration. These exist because 44 tests once passed green while
# `mcp_server.server` could not be imported at all: installing the LangGraph
# dependency tree downgraded mcp 2.x -> 1.x, which moved the server class.
# Nothing in the suite touched server.py, so the breakage was invisible.
# --------------------------------------------------------------------------

def test_server_module_imports():
    """Fails loudly if the installed mcp SDK moves the server class again."""
    from mcp_server.server import server

    assert server.name == "product-discovery"


def test_both_tools_register_with_the_expected_names():
    import asyncio

    from mcp_server.server import server

    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"rag.search", "web.search"}


def test_rag_search_schema_exposes_both_filter_shapes():
    """Guards the contract itself: a consumer must be able to discover that
    nested `filters` and the flat params both exist."""
    import asyncio

    from mcp_server.server import server

    tools = asyncio.run(server.list_tools())
    rag = next(t for t in tools if t.name == "rag.search")
    # Attribute casing differs between SDK majors (2.x input_schema, 1.x inputSchema).
    schema = getattr(rag, "input_schema", None) or getattr(rag, "inputSchema")
    props = schema["properties"]
    for name in ("query", "k", "filters", "max_price", "min_price", "subcategory", "brand"):
        assert name in props, f"{name} missing from rag.search schema"
    assert schema["required"] == ["query"]
