"""玩家可见文本 sanitizer — 禁止 placeholder / debug / 截断污染。"""

from __future__ import annotations

import re
from typing import Any

from engine.location_registry import is_location_public
from engine.world_state import GameState

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "某个方向",
    "某处建筑",
    "某处",
    "某人",
    "某个建筑",
    "某个遗留物",
    "unknown",
    "undefined",
    "null",
    "None",
    "商人失踪者",
    "方向方向",
    "世界：",
    "现场线索",
    "source_id",
    "internal/",
    "discovered/",
    "public/",
    "local/",
)

REPEAT_FIXES: tuple[tuple[str, str], ...] = (
    ("方向方向", "方向"),
    ("村口村口", "村口"),
    ("酒馆酒馆", "酒馆"),
)

TRUNCATED_ENDINGS: tuple[str, ...] = (
    "（",
    "：",
    ":",
    "、",
    "，",
    "…",
    "...",
    "的",
    "与",
)

UNSOURCED_PHRASES: tuple[str, ...] = (
    "有人说",
    "据说",
    "听说",
    "传闻说",
    "向村口打听",
    "向在场者打听",
)

VALID_RUMOR_SOURCE_TYPES: frozenset[str] = frozenset({
    "npc",
    "visible_group",
    "notice_board",
    "overheard_conversation",
})

SAFE_FALLBACK = "四周一片安静，你暂时按兵不动。"


def contains_forbidden(text: str) -> bool:
    if not text:
        return False
    t = str(text)
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in t:
            return True
    if re.search(r"世界：\s*[\u4e00-\u9fff]{0,1}$", t.strip()):
        return True
    return False


def _fix_repetitions(text: str) -> str:
    out = text
    for old, new in REPEAT_FIXES:
        out = out.replace(old, new)
    return out


def is_truncated(text: str) -> bool:
    t = text.strip()
    if len(t) <= 2:
        return True
    if t.endswith(TRUNCATED_ENDINGS):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]", t):
        return True
    return False


def sanitize_player_text(text: str, state: GameState | None = None) -> str:
    if not text:
        return text
    out = _fix_repetitions(str(text))
    if contains_forbidden(out):
        return ""
    if is_truncated(out):
        return ""
    if state:
        if "仓库方向" in out and not is_location_public(state, "旧仓库"):
            out = out.replace("仓库方向", "村口外侧")
        if "某个方向" in out:
            out = out.replace("某个方向", "村口外侧")
    for p in UNSOURCED_PHRASES:
        if p in out:
            out = out.replace(p, "").strip()
    return re.sub(r"\s+", " ", out).strip()


def rumor_source_type_allowed(source_type: str | None) -> bool:
    return str(source_type or "").strip().lower() in VALID_RUMOR_SOURCE_TYPES


def build_rumor_action_label(rumor: dict[str, Any]) -> str:
    """行动化 rumor 选项文案，禁止「向村口打听：有人说…」及泛化求证传闻。"""
    st = str(rumor.get("source_type", "")).strip().lower()
    src = str(rumor.get("source_label", "") or rumor.get("source", "")).strip()
    txt = str(rumor.get("text", "")).strip()
    if not txt or not src or src == "未知来源":
        return ""

    if st == "npc" and src:
        if "打斗" in txt or "动静" in txt:
            return f"询问{src}是否听见昨夜的打斗声"
        if "失踪" in txt or "商队" in txt or "马库斯" in txt:
            return f"询问{src}：她父亲昨夜最后去了哪里" if "艾琳娜" in src else f"询问{src}是否知道商人失踪的详情"
        if "巡逻" in txt or "哨岗" in txt or "加派" in txt:
            return f"追问{src}：为什么要在村口外侧加派巡逻"
        # 具体引用谣言内容，禁止泛化「求证传闻」
        short = txt[:28] + "…" if len(txt) > 28 else txt
        return f"询问{src}：{short}"
    if st == "visible_group":
        return "靠近正在低声交谈的两名村民，听清他们在说什么"
    if st == "overheard_conversation":
        return "靠近低声交谈的人群，听清他们提到的夜间动静"
    if st == "notice_board":
        return "查看公告板是否贴有商队失踪告示"
    return ""


def sanitize_narrative_html(html: str, state: GameState) -> str:
    if not html:
        return html

    def _clean_p(m: re.Match[str]) -> str:
        cls = m.group(1)
        inner = m.group(2)
        clean = sanitize_player_text(inner, state)
        if not clean:
            return ""
        return f'<p class="{cls}">{clean}</p>'

    out = re.sub(
        r'<p\s+class="([^"]+)">([^<]*)</p>',
        _clean_p,
        html,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"<p[^>]*>\s*</p>", "", out)
    if not out.strip() or contains_forbidden(out):
        return f'<p class="scene">{SAFE_FALLBACK}</p>'
    return out
