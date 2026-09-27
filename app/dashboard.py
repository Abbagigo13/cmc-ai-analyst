import time
import random
import logging

from . import cmc

log = logging.getLogger("dashboard")

_cache: dict = {"data": None, "expires": 0}
CACHE_TTL = 60  # seconds


async def get_summary() -> dict:
    now = time.time()
    if _cache["data"] and _cache["expires"] > now:
        log.info("dashboard cache hit")
        return _cache["data"]

    # 1. Global metrics — 1 credit
    glob = await cmc.get_global_metrics()

    # 2. Top 20 by market cap — 1 credit
    listings = await cmc.get_listings(limit=20, sort="market_cap")

    # 3. Signals computed from the live data (no extra credits)
    signals = _compute_signals(glob, listings)

    # 4. KPI tiles
    kpis = [
        {
            "label": "Total Market Cap",
            "value": _fmt_big(glob["total_market_cap_usd"]),
            "delta_pct": glob["total_market_cap_change_24h"],
            "spark": _spark(glob["total_market_cap_usd"], glob["total_market_cap_change_24h"]),
        },
        {
            "label": "24h Volume",
            "value": _fmt_big(glob["total_volume_24h_usd"]),
            "delta_pct": 0,
            "spark": _spark(glob["total_volume_24h_usd"], -2.1),
        },
        {
            "label": "BTC Dominance",
            "value": f'{glob["btc_dominance"]}%',
            "delta_pct": 0,
            "spark": _spark(glob["btc_dominance"], 0.3),
        },
        {
            "label": "ETH Dominance",
            "value": f'{glob["eth_dominance"]}%',
            "delta_pct": 0,
            "spark": _spark(glob["eth_dominance"], -0.2),
        },
    ]

    result = {
        "kpis": kpis,
        "signals": signals,
        "movers": listings[:10],
        "updated_at": glob["last_updated"],
    }
    _cache["data"] = result
    _cache["expires"] = now + CACHE_TTL
    return result


def _compute_signals(glob: dict, listings: list[dict]) -> list[dict]:
    """Generate actionable signals from live market data."""
    out: list[dict] = []

    # Rule 1: biggest 24h mover in top 20
    if listings:
        top_mover = max(listings, key=lambda x: abs(x["percent_change_24h"]))
        move = top_mover["percent_change_24h"]
        if abs(move) >= 2:
            direction = "up" if move > 0 else "down"
            sev = "high" if abs(move) > 5 else "medium"
            out.append({
                "severity": sev,
                "tag": f'{top_mover["symbol"]}-USD',
                "text": (
                    f'{top_mover["symbol"]} is {direction} '
                    f'{abs(move):.2f}% over the last 24 hours at '
                    f'${top_mover["price"]:,.2f}.'
                ),
                "query": (
                    f'Why is {top_mover["symbol"]} {direction} '
                    f'{abs(move):.2f}% in the last 24 hours?'
                ),
            })

    # Rule 2: high volume-to-cap ratio (unusual activity)
    for item in listings[:15]:
        mc = item.get("market_cap") or 0
        vol = item.get("volume_24h") or 0
        if mc > 0 and vol / mc > 0.25:
            ratio = vol / mc
            out.append({
                "severity": "medium",
                "tag": f'{item["symbol"]}-USD',
                "text": (
                    f'{item["symbol"]} 24h volume is {ratio:.2f}x its market cap — '
                    f'unusual turnover for a top-20 asset.'
                ),
                "query": (
                    f'Analyze {item["symbol"]} trading volume. '
                    f'Is it concentrated on DEX or CEX?'
                ),
            })
            break

    # Rule 3: global market info
    change = glob["total_market_cap_change_24h"]
    direction = "up" if change > 0 else "down"
    out.append({
        "severity": "info",
        "tag": "GLOBAL",
        "text": (
            f'Total market cap is {_fmt_big(glob["total_market_cap_usd"])}, '
            f'{direction} {abs(change):.2f}% over 24h. '
            f'BTC dominance {glob["btc_dominance"]}%, ETH {glob["eth_dominance"]}%.'
        ),
        "query": "What is the current global crypto market state?",
    })

    return out


def _fmt_big(n: float) -> str:
    if n is None:
        return "—"
    if n >= 1e12:
        return f"${n/1e12:.2f}T"
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    return f"${n:,.0f}"


def _spark(seed_value: float, trend: float) -> list[float]:
    """Deterministic placeholder sparkline. Replace with real data later."""
    random.seed(int(abs(seed_value)) % 100000)
    base = 100.0
    drift = 0.05 * trend
    out = []
    v = base
    for _ in range(10):
        v += random.uniform(-2, 2) + drift
        out.append(round(v, 2))
    return out