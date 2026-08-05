"""Domain allowlist for web.search results.

The brief requires a domain allowlist and respect for robots.txt / ToS.

On robots.txt, to be precise about what this server actually does: it does not
crawl. It calls the SerpApi API, which is a licensed commercial interface to
search results, and it returns only the metadata that API hands back (title,
link, snippet, price). We never fetch a product page ourselves, so there is no
crawl for robots.txt to govern. What we do owe is the SerpApi ToS: stay inside
the rate limit and do not cache beyond the freshness window. Both are enforced
in web_tool.py.

The allowlist is therefore a *result* filter, not a crawl filter: it keeps the
assistant from citing a domain nobody vetted.
"""

import os
from urllib.parse import urlparse

# Mainstream retailers and price aggregators. Deliberately conservative — this
# is a product-discovery demo over a toys catalogue, not a general web agent.
DEFAULT_ALLOWLIST = frozenset(
    {
        "amazon.com",
        "walmart.com",
        "target.com",
        "bestbuy.com",
        "ebay.com",
        "costco.com",
        "kohls.com",
        "macys.com",
        "lego.com",
        "melissaanddoug.com",
        "hasbro.com",
        "mattel.com",
        "barnesandnoble.com",
        "gamestop.com",
        "michaels.com",
        "etsy.com",
        "wayfair.com",
        "newegg.com",
        "google.com",
        "shopping.google.com",
    }
)


def _load_allowlist() -> frozenset[str]:
    """WEB_SEARCH_ALLOWLIST, if set, replaces the default (comma-separated)."""
    raw = os.environ.get("WEB_SEARCH_ALLOWLIST", "").strip()
    if not raw:
        return DEFAULT_ALLOWLIST
    return frozenset(d.strip().lower() for d in raw.split(",") if d.strip())


def registrable_domain(url: str) -> str:
    """Host minus any leading www./m./shop. prefix.

    Not a public-suffix parse: a real PSL lookup needs a dependency we do not
    have, and for an allowlist of known retailers the naive form is enough.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    for prefix in ("www.", "m.", "shop.", "smile."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def is_allowed(url: str) -> bool:
    """True if the URL's host is, or is a subdomain of, an allowlisted domain."""
    host = registrable_domain(url)
    if not host:
        return False
    allow = _load_allowlist()
    if host in allow:
        return True
    return any(host.endswith("." + d) for d in allow)


def filter_results(results: list[dict]) -> tuple[list[dict], list[str]]:
    """Split results into (allowed, blocked_domains).

    Blocked domains are returned rather than silently dropped so the tool can
    report what it filtered — an invisible filter is impossible to debug and
    impossible to demo.
    """
    allowed, blocked = [], []
    for r in results:
        url = r.get("url") or ""
        if is_allowed(url):
            allowed.append(r)
        else:
            host = registrable_domain(url)
            if host and host not in blocked:
                blocked.append(host)
    return allowed, blocked
