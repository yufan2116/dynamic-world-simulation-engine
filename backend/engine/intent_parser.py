"""意图解析：简单关键词 + 可选 LLM 结构化。"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from engine.llm_config import get_llm_api_key, get_llm_base_url, get_llm_model


class ParsedIntent(BaseModel):
    action_type: str  # move | talk | investigate | persuade | intimidate | combat | rest | unknown
    target: str | None = None
    destination: str | None = None
    ability: str = "WIS"
    dc: int = 12
    requires_roll: bool = True
    raw_input: str = ""
    parse_source: str = "keyword"  # keyword | llm


KEYWORD_RULES: list[tuple[str, str, dict[str, Any]]] = [
    (r"(悄悄|潜行|隐蔽).*(前往|去|进入).*(酒馆)", "move", {"destination": "酒馆", "ability": "DEX", "dc": 13}),
    (r"(悄悄|潜行|隐蔽).*(前往|去|进入).*(仓库)", "move", {"destination": "仓库", "ability": "DEX", "dc": 13}),
    (r"(悄悄|潜行|隐蔽).*(前往|去|进入).*(村口|村门)", "move", {"destination": "村口", "ability": "DEX", "dc": 13}),
    (r"(悄悄|潜行|隐蔽).*(前往|去|进入).*(森林|小路)", "move", {"destination": "森林小路", "ability": "DEX", "dc": 14}),
    (r"(去|前往|走到|进入|赶往).*(酒馆)", "move", {"destination": "酒馆", "requires_roll": False}),
    (r"(去|前往|走到|进入|赶往).*(村口|村门|大门)", "move", {"destination": "村口", "requires_roll": False}),
    (r"(去|前往|走到|进入|搜查|调查).*(仓库)", "move", {"destination": "仓库", "requires_roll": False}),
    (r"(去|前往|走到|进入|追踪).*(森林|小路)", "move", {"destination": "森林小路", "requires_roll": False}),
    (r"(偷听|窃听|隐蔽.*听).*(守卫|托马斯|谈话)", "investigate", {"target": "托马斯", "ability": "DEX", "dc": 14}),
    (r"(假装|佯装).*(喝醉|醉酒|酒醉)", "investigate", {"ability": "CHA", "dc": 12}),
    (r"(躲|藏).*(货箱|箱子|阴影)", "investigate", {"ability": "DEX", "dc": 13}),
    (r"(仔细观察|查看|观察).*(周围|环境|四周)", "investigate", {"ability": "WIS", "dc": 11}),
    (r"(屏息|凝神|搜寻).*(细节|隐藏|痕迹)", "investigate", {"ability": "WIS", "dc": 13}),
    (r"(沿|环绕).*(村庄|村界|四周).*(观察|巡逻|脚印)", "investigate", {"ability": "WIS", "dc": 12}),
    (r"(追查|追踪|验证).*(线索)", "investigate", {"ability": "INT", "dc": 12}),
    (r"(调查|查证).*(异常|动静)", "investigate", {"ability": "WIS", "dc": 12}),
    (r"(寻找|找).*(遮蔽|避雨)", "rest", {"requires_roll": False}),
    (r"(过夜|歇息|睡觉|休整)", "rest", {"requires_roll": False}),
    (r"(和|跟|与|找|询问|对话|交谈|打听|盘问|安慰).*(托马斯|守卫)", "talk", {"target": "托马斯", "ability": "CHA", "dc": 12}),
    (r"(托马斯|守卫).*(打听|询问|对话|交谈)", "talk", {"target": "托马斯", "ability": "CHA", "dc": 12}),
    (r"(和|跟|与|找|询问|对话|交谈).*(米拉|老板|酒保)", "talk", {"target": "米拉", "ability": "CHA", "dc": 11}),
    (r"(和|跟|与|找|询问|对话|安慰).*(艾琳娜|女儿)", "talk", {"target": "艾琳娜", "ability": "WIS", "dc": 10}),
    (r"(和|跟|与|找|对话|对峙).*(瓦里克|强盗|首领)", "talk", {"target": "瓦里克", "ability": "CHA", "dc": 15}),
    (r"(向路人|向村民|打听|询问).*(传闻|消息|失踪)", "talk", {"ability": "CHA", "dc": 11, "requires_roll": True}),
    (r"说服托马斯", "persuade", {"target": "托马斯", "ability": "CHA", "dc": 14}),
    (r"说服米拉", "persuade", {"target": "米拉", "ability": "CHA", "dc": 13}),
    (r"说服艾琳娜", "persuade", {"target": "艾琳娜", "ability": "CHA", "dc": 12}),
    (r"说服瓦里克", "persuade", {"target": "瓦里克", "ability": "CHA", "dc": 16}),
    (r"(说服|劝说|劝服).*(告诉我|一切|内情)", "persuade", {"ability": "CHA", "dc": 14}),
    (r"(搜查|搜索|检查|翻找).*(仓库|货物|箱子)", "investigate", {"destination": "仓库", "ability": "INT", "dc": 13}),
    (r"(调查|查看|观察|寻找线索).*(现场|脚印|痕迹|线索)", "investigate", {"ability": "WIS", "dc": 12}),
    (r"(沿小路|追踪).*(脚印|足迹)", "investigate", {"destination": "森林小路", "ability": "WIS", "dc": 13}),
    (r"(与|和).*(瓦里克).*(对峙|交涉|对话)", "talk", {"target": "瓦里克", "ability": "CHA", "dc": 15}),
    (r"(说服|劝说|劝服)", "persuade", {"ability": "CHA", "dc": 13}),
    (r"(恐吓|威胁|威吓)", "intimidate", {"ability": "CHA", "dc": 14}),
    (r"(攻击|战斗|拔剑|开战)", "combat", {"ability": "STR", "dc": 14}),
    (r"(休息|等待)", "rest", {"requires_roll": False}),
]


def _keyword_parse(player_input: str) -> ParsedIntent | None:
    text = player_input.strip()
    for pattern, action_type, extras in KEYWORD_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return ParsedIntent(
                action_type=action_type,
                raw_input=text,
                parse_source="keyword",
                **extras,
            )
    return None


def _is_complex(text: str) -> bool:
    if len(text) > 40:
        return True
    if re.search(r"[，。；、]", text) and len(text) > 20:
        return True
    return False


async def _llm_parse(player_input: str, context: dict[str, Any]) -> ParsedIntent | None:
    api_key = get_llm_api_key()
    if not api_key:
        return None
    model = get_llm_model()
    base_url = get_llm_base_url()
    system = """你是游戏意图解析器。将玩家自然语言转为 JSON，仅包含以下字段：
action_type: move|talk|investigate|persuade|intimidate|combat|rest|unknown
target: NPC名（托马斯|米拉|艾琳娜|瓦里克）或 null
destination: 地点（村口|酒馆|仓库|森林小路）或 null
ability: STR|DEX|CON|INT|WIS|CHA
dc: 8-18 整数
requires_roll: boolean
不要编造不存在的地点或 NPC。只输出 JSON。"""
    user = f"当前地点: {context.get('location')}\n玩家输入: {player_input}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # extract JSON
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                return None
            data = json.loads(match.group())
            return ParsedIntent(
                action_type=data.get("action_type", "unknown"),
                target=data.get("target"),
                destination=data.get("destination"),
                ability=data.get("ability", "WIS"),
                dc=int(data.get("dc", 12)),
                requires_roll=bool(data.get("requires_roll", True)),
                raw_input=player_input,
                parse_source="llm",
            )
    except Exception:
        return None


async def parse_intent(player_input: str, context: dict[str, Any]) -> ParsedIntent:
    simple = _keyword_parse(player_input)
    if simple and not _is_complex(player_input):
        return simple
    if _is_complex(player_input):
        llm_result = await _llm_parse(player_input, context)
        if llm_result:
            return llm_result
    if simple:
        return simple
    return ParsedIntent(
        action_type="unknown",
        raw_input=player_input,
        ability="WIS",
        dc=12,
        requires_roll=True,
        parse_source="keyword",
    )
