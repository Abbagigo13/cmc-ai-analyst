import json
import os
import re
from typing import Any

from openai import AsyncOpenAI

from . import cmc
from .tools import TOOL_SCHEMAS, dispatch, to_json

client = AsyncOpenAI(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    base_url=os.environ.get(
        "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ),
)

MODEL = os.environ.get("QWEN_MODEL", "qwen-plus")

SYSTEM_PROMPT = """You are a crypto market analyst powered by live CoinMarketCap data.

You have tools that fetch real market data. When you call a tool, the result
comes back as a JSON message from role="tool". That JSON is the ground truth.

RULES:
1. NEVER state a price, market cap, or percentage change from memory. ALWAYS
   call a tool first.
2. When a tool result arrives, USE IT. It is live data, not an error. Do not
   say "no data found" or "I cannot retrieve data" if the tool result contains
   a "quotes" or "global" or "assets" key - read the values and answer.
3. If a tool result has an "error" key, THEN report the error plainly. Do not
   invent data.
4. For any comparison, call get_asset_quotes once with all symbols.
5. Structure answers: a one-line takeaway, then a markdown table of the key
   figures, then one short interpretation sentence.
6. Be concise. No filler, no disclaimers.
7. NEVER write raw JSON, XML, or tags like <function-call> in your visible
   reply. Use plain prose and markdown only.
"""


_FUNCTION_CALL_RE = re.compile(
    r"<function-call>.*?</function-call>", re.DOTALL | re.IGNORECASE
)
_TOOL_CALL_BLOCK_RE = re.compile(
    r"<tool_call>.*?</tool_call>", re.DOTALL | re.IGNORECASE
)


def _clean_answer(text: str) -> str:
    if not text:
        return ""
    text = _FUNCTION_CALL_RE.sub("", text)
    text = _TOOL_CALL_BLOCK_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


async def run_agent(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    max_steps: int = 6,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    for turn in history or []:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})

    trace: list[dict[str, Any]] = []
    start_credits = cmc.CREDITS_USED

    for _ in range(max_steps):
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.0,
        )
        msg = resp.choices[0].message

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": msg.content or "",
        }

        if not msg.tool_calls:
            messages.append(assistant_msg)
            return {
                "answer": _clean_answer(msg.content) or "(no response)",
                "trace": trace,
                "credits_used": cmc.CREDITS_USED - start_credits,
            }

        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
        messages.append(assistant_msg)

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            result = await dispatch(tc.function.name, args)

            trace.append(
                {
                    "tool": tc.function.name,
                    "args": args,
                    "result": result,
                }
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": to_json(result),
                }
            )

    return {
        "answer": "I hit the maximum number of tool-calling steps. Try a narrower question.",
        "trace": trace,
        "credits_used": cmc.CREDITS_USED - start_credits,
    }
