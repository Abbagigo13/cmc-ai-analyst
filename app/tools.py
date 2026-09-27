import json
from typing import Any

from . import cmc

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_asset_quotes",
            "description": (
                "Get live prices and percentage changes (1h/24h/7d) for one or "
                "more cryptocurrencies by ticker symbol. Use this for any "
                "price, comparison, or momentum question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ticker symbols, e.g. ['BTC','ETH','SOL']",
                    }
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_overview",
            "description": (
                "Get global crypto market metrics: total market cap, 24h volume, "
                "BTC/ETH dominance, and active asset count. Use for broad "
                "'how is the market doing' questions."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_assets",
            "description": (
                "List the top cryptocurrencies ranked by market cap, volume, or "
                "24h/7d performance. Use for leaderboards and 'best/worst "
                "performers' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many assets to return (1-100). Default 20.",
                    },
                    "sort": {
                        "type": "string",
                        "enum": [
                            "market_cap",
                            "volume_24h",
                            "percent_change_24h",
                            "percent_change_7d",
                        ],
                        "description": "Sort field. Default market_cap.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending",
            "description": (
                "Get currently trending cryptocurrencies plus the top 24h "
                "gainers and losers. Use for discovery and narrative questions."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


async def dispatch(name: str, args: dict[str, Any]) -> dict:
    try:
        if name == "get_asset_quotes":
            symbols = args.get("symbols") or []
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",")]
            symbols = [s for s in symbols if s]
            if not symbols:
                return {"error": "No symbols provided."}
            try:
                quotes = await cmc.get_quotes(symbols)
            except cmc.CMCError as e:
                return {"error": str(e), "symbols_requested": symbols}
            if not quotes:
                return {
                    "error": "CMC returned quotes but none matched the requested symbols.",
                    "symbols_requested": symbols,
                }
            return {"quotes": quotes, "symbols_requested": symbols}

        if name == "get_market_overview":
            return {"global": await cmc.get_global_metrics()}

        if name == "get_top_assets":
            limit = int(args.get("limit") or 20)
            sort = args.get("sort") or "market_cap"
            return {"assets": await cmc.get_listings(limit=limit, sort=sort)}

        if name == "get_trending":
            return await cmc.get_trending()

        return {"error": f"Unknown tool: {name}"}

    except cmc.CMCError as e:
        return {"error": f"CMC API error: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def to_json(result: dict) -> str:
    return json.dumps(result, default=str)
