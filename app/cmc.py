import os
import json as _json
import logging
from typing import Any

import httpx

log = logging.getLogger("cmc")

CMC_BASE = "https://pro-api.coinmarketcap.com"
CMC_KEY = os.environ["CMC_API_KEY"]

CREDITS_USED = 0


class CMCError(Exception):
    pass


async def _get(path: str, params: dict[str, Any]) -> dict:
    global CREDITS_USED
    headers = {"X-CMC_PRO_API_KEY": CMC_KEY, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(CMC_BASE + path, params=params, headers=headers)

    if r.status_code != 200:
        raise CMCError(f"{r.status_code} on {path}: {r.text[:300]}")

    body = r.json()
    used = body.get("status", {}).get("credit_count", 0)
    CREDITS_USED += used
    log.info("CMC %s -> %s credits (total %s)", path, used, CREDITS_USED)
    return body


async def resolve_ids(symbols: list[str]) -> dict[str, int]:
    """Symbol -> CMC numeric ID. This endpoint is FREE (0 credits)."""
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not symbols:
        return {}

    out: dict[str, int] = {}

    try:
        body = await _get("/v1/cryptocurrency/map", {"symbol": ",".join(symbols)})
        for item in body.get("data", []):
            out.setdefault(item["symbol"].upper(), item["id"])
    except CMCError as e:
        log.warning("Batch map failed: %s - falling back to per-symbol", e)

    missing = [s for s in symbols if s not in out]
    for sym in missing:
        try:
            body = await _get("/v1/cryptocurrency/map", {"symbol": sym})
            for item in body.get("data", []):
                out.setdefault(item["symbol"].upper(), item["id"])
        except CMCError as e:
            log.warning("Per-symbol map failed for %s: %s", sym, e)

    log.info("resolve_ids(%s) -> %s", symbols, out)
    return out


def _norm_quote(item: dict) -> dict:
    q = (item.get("quote") or {}).get("USD") or {}
    return {
        "id": item.get("id"),
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "price": round(q.get("price") or 0, 8),
        "percent_change_1h": round(q.get("percent_change_1h") or 0, 2),
        "percent_change_24h": round(q.get("percent_change_24h") or 0, 2),
        "percent_change_7d": round(q.get("percent_change_7d") or 0, 2),
        "market_cap": q.get("market_cap"),
        "volume_24h": q.get("volume_24h"),
        "last_updated": q.get("last_updated"),
    }


async def get_quotes(symbols: list[str]) -> list[dict]:
    """Live quotes for a list of ticker symbols."""
    idmap = await resolve_ids(symbols)
    if not idmap:
        raise CMCError(f"Could not resolve any CMC IDs for symbols: {symbols}")

    ids = ",".join(str(i) for i in idmap.values())
    body = await _get(
        "/v2/cryptocurrency/quotes/latest",
        {"id": ids, "convert": "USD"},
    )

    data = body.get("data", {})
    log.info(
        "CMC raw data type=%s keys=%s",
        type(data).__name__,
        list(data.keys())[:5] if isinstance(data, dict) else "n/a",
    )

    try:
        preview = _json.dumps(data, default=str)[:800]
        log.info("CMC raw data preview: %s", preview)
    except Exception:
        pass

    candidates: list[dict] = []

    def _walk(node):
        # Unwrap lists first - never append a list as a candidate.
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return

        if isinstance(node, dict):
            # A real quote dict has a "symbol" and a dict-typed "quote".
            if "symbol" in node and isinstance(node.get("quote"), dict):
                candidates.append(node)
                return
            # Otherwise recurse into every value.
            for v in node.values():
                _walk(v)

    _walk(data)
    log.info("CMC collected %d candidate quote objects", len(candidates))

    out: list[dict] = []
    for v in candidates:
        try:
            out.append(_norm_quote(v))
        except Exception as e:
            log.warning("Skipping malformed quote: %s", e)

    log.info("get_quotes(%s) -> %d parsed entries", symbols, len(out))
    return out


async def get_listings(limit: int = 20, sort: str = "market_cap") -> list[dict]:
    """Top assets by market cap, volume, or percent change."""
    valid_sorts = {
        "market_cap",
        "volume_24h",
        "percent_change_24h",
        "percent_change_7d",
    }
    sort = sort if sort in valid_sorts else "market_cap"
    body = await _get(
        "/v1/cryptocurrency/listings/latest",
        {"limit": min(max(limit, 1), 100), "convert": "USD", "sort": sort},
    )
    return [
        {
            "rank": item["cmc_rank"],
            "symbol": item["symbol"],
            "name": item["name"],
            "price": round(item["quote"]["USD"]["price"], 8),
            "percent_change_24h": round(
                item["quote"]["USD"].get("percent_change_24h") or 0, 2
            ),
            "percent_change_7d": round(
                item["quote"]["USD"].get("percent_change_7d") or 0, 2
            ),
            "market_cap": item["quote"]["USD"].get("market_cap"),
            "volume_24h": item["quote"]["USD"].get("volume_24h"),
        }
        for item in body.get("data", [])
    ]


async def get_global_metrics() -> dict:
    body = await _get("/v1/global-metrics/quotes/latest", {"convert": "USD"})
    d = body["data"]
    q = d["quote"]["USD"]
    return {
        "total_market_cap_usd": q.get("total_market_cap"),
        "total_volume_24h_usd": q.get("total_volume_24h"),
        "btc_dominance": round(d.get("btc_dominance") or 0, 2),
        "eth_dominance": round(d.get("eth_dominance") or 0, 2),
        "active_cryptocurrencies": d.get("active_cryptocurrencies"),
        "total_market_cap_change_24h": round(
            q.get("total_market_cap_yesterday_percentage_change") or 0, 2
        ),
        "last_updated": d.get("last_updated"),
    }


async def get_trending() -> dict:
    """Trending assets + top gainers/losers. Degrades gracefully on tier limits."""
    out: dict[str, Any] = {}
    try:
        body = await _get("/v1/cryptocurrency/trending/latest", {"limit": 10})
        out["trending"] = [
            {
                "symbol": i["symbol"],
                "name": i["name"],
                "price": round(i["quote"]["USD"]["price"], 8),
                "percent_change_24h": round(
                    i["quote"]["USD"].get("percent_change_24h") or 0, 2
                ),
            }
            for i in body.get("data", [])
        ]
    except CMCError as e:
        out["trending_error"] = str(e)

    try:
        body = await _get(
            "/v1/cryptocurrency/trending/gainers-losers",
            {"limit": 10, "time_period": "24h"},
        )
        data = body.get("data", {})
        out["gainers"] = [
            {
                "symbol": i["symbol"],
                "price": round(i["quote"]["USD"]["price"], 8),
                "percent_change_24h": round(
                    i["quote"]["USD"].get("percent_change_24h") or 0, 2
                ),
            }
            for i in data.get("gainers", [])[:10]
        ]
        out["losers"] = [
            {
                "symbol": i["symbol"],
                "price": round(i["quote"]["USD"]["price"], 8),
                "percent_change_24h": round(
                    i["quote"]["USD"].get("percent_change_24h") or 0, 2
                ),
            }
            for i in data.get("losers", [])[:10]
        ]
    except CMCError as e:
        out["gainers_losers_error"] = str(e)

    return out