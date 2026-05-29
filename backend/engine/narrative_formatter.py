"""叙事呈现层 — 将 simulation 内部状态转为玩家可读的 CRPG 文本。"""
from __future__ import annotations

import html
import re
from typing import Any

from engine.world_state import GameState

# --- 内部 token → 自然语言 ---
ACTIVITY_ZH: dict[str, str] = {
    "guarding_gate": "在村口警戒",
    "pleading_in_square": "在广场求助",
    "watching_from_curtain": "在酒馆门帘后观望",
    "patrol_warehouse": "带队前往仓库巡逻",
    "gossiping": "与酒客低声交谈",
    "resting": "短暂歇息",
    "idle": "停留原地",
    "停留": "停留原地",
}

EMOTION_ZH: dict[str, str] = {
    "tense": "神色紧绷",
    "anxious": "明显有些不安",
    "distressed": "几近崩溃",
    "guarded": "戒备而疏远",
    "hopeful": "带着一丝期盼",
    "calm": "还算平静",
    "angry": "压抑着怒意",
    "sad": "难掩悲伤",
    "平静": "神色平静",
}

CATEGORY_SKILL: dict[str, str] = {
    "investigate": "感知",
    "social": "交涉",
    "stealth": "隐匿",
    "survival": "生存",
    "free": "自由",
}

# 禁止直接出现在玩家面的短语（整句或片段替换）
_BANNED_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"局面暂时停顿[。.]?"), "你环顾四周，一时没有新的动静。"),
    (re.compile(r"你确认当前场景暂时没有更多可见异常[。.]?"), "这里暂时没有更多可见线索。"),
    (re.compile(r"局势没有明显变化[。.]?"), "局势似乎没有新的变化。"),
    (re.compile(r"局势未向有利方向变化"), "局面仍对你不利。"),
    (re.compile(r"对话未取得新信息[。.]?"), "对方没有再多说。"),
    (re.compile(r"需要换个角度再观察[。.]?"), "你需要换个角度再观察。"),
    (re.compile(r"^信息：", re.M), ""),
    (re.compile(r"继续调查(?:最近)?异常动静"), "检查村口附近是否有新的痕迹"),
    (re.compile(r"继续调查"), "继续追查眼前的线索"),
    (re.compile(r"unresolved\s*hook", re.I), ""),
    (re.compile(r"available\s*followups?", re.I), ""),
    (re.compile(r"investigate\s+target", re.I), "调查目标"),
    (re.compile(r"scene\s+observation", re.I), "现场观察"),
    (re.compile(r"current_activity", re.I), ""),
    (re.compile(r"relationship_too_low", re.I), "对方不愿多说"),
    (re.compile(r"topic_sensitive", re.I), "话题过于敏感"),
    (re.compile(r"no_knowledge", re.I), ""),
]

_INTERNAL_ID_RE = re.compile(
    r"\b(?:fact_|pf_|clue_|obs_|hook_|topic_|follow_|change_angle_)[a-z0-9_]+\b",
    re.I,
)
_SNAKE_IN_TEXT_RE = re.compile(r"[a-z]+_[a-z0-9_]+", re.I)
_ACTIVITY_INLINE_RE = re.compile(
    r"([\u4e00-\u9fff]{2,4})正在([a-z][a-z0-9_]+)",
    re.I,
)
_EMOTION_INLINE_RE = re.compile(
    r"情绪显得([a-z][a-z0-9_]+)",
    re.I,
)

_WORLD_EVENT_TEMPLATES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"【NPC】托马斯在村口召集同伴.*加派.*哨岗"),
        "村口的守卫开始频繁换岗，空气里的紧张感愈发明显。",
    ),
    (
        re.compile(r"【NPC】托马斯率队前往仓库巡逻"),
        "远处传来整齐的脚步声，巡逻队正朝仓库方向而去。",
    ),
    (
        re.compile(r"【NPC】米拉在酒馆低声与酒客交谈"),
        "酒馆里人声压得很低，像有什么不愿被外人听见的议论。",
    ),
    (
        re.compile(r"【NPC】艾琳娜在村口徘徊.*打听"),
        "广场边缘传来压抑的啜泣，有人在向路人反复打听消息。",
    ),
    (
        re.compile(r"【NPC】艾琳娜抓住每一位过路人的衣袖"),
        "一名年轻女子在人群中拉住路人，声音发颤地恳求帮助。",
    ),
    (
        re.compile(r"【危机】"),
        "【风声】",  # 稍后去掉标签
    ),
    (re.compile(r"【世界】"), ""),
    (re.compile(r"【NPC】"), ""),
    (re.compile(r"【压力】"), ""),
]

_TRANSITION_ZH: dict[str, str] = {
    "ambient_scene": "风吹过村口，火把在潮湿空气里轻轻摇晃。",
    "suspicious_guard": "托马斯没有继续说下去。空气里只剩下火把燃烧的噼啪声。",
    "guard_confession": "托马斯压低声音，目光仍扫向仓库方向。",
    "desperate_plea": "艾琳娜望着你，等你的回应。",
    "inn_gossip": "酒馆里的低语暂歇，等你开口。",
    "warehouse_probe": "仓库里一片安静，下一步由你决定。",
    "forest_trail": "林间风声盖住了远处的声响。",
    "village_unrest": "村民们屏息看着这场交锋。",
    "rest_break": "短暂的歇息后，你重新打起精神——",
    "travel_transition": "路在前方延伸。",
}


def format_activity(activity: str) -> str:
    key = (activity or "").strip()
    if not key:
        return "停留原地"
    if key in ACTIVITY_ZH:
        return ACTIVITY_ZH[key]
    if re.search(r"[\u4e00-\u9fff]", key):
        return key
    readable = key.replace("_", " ")
    return ACTIVITY_ZH.get(key, f"忙于{readable}")


def format_emotion(emotion: str) -> str:
    key = (emotion or "").strip()
    if key in EMOTION_ZH:
        return EMOTION_ZH[key]
    if re.search(r"[\u4e00-\u9fff]", key):
        return key
    return EMOTION_ZH.get(key, "神色难辨")


def format_npc_activity_line(name: str, activity: str, emotion: str | None = None) -> str:
    act = format_activity(activity)
    if emotion:
        emo = format_emotion(emotion)
        return f"{name}{act}，{emo}。"
    return f"{name}{act}。"


def _strip_internal_ids(text: str) -> str:
    out = _INTERNAL_ID_RE.sub("", text)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def _replace_snake_tokens(text: str) -> str:
    def _fix_activity(m: re.Match[str]) -> str:
        name, act = m.group(1), m.group(2)
        return f"{name}{format_activity(act)}"

    out = _ACTIVITY_INLINE_RE.sub(_fix_activity, text)

    def _fix_emotion(m: re.Match[str]) -> str:
        return f"情绪显得{format_emotion(m.group(1))}"

    out = _EMOTION_INLINE_RE.sub(_fix_emotion, out)
    return out


def polish_prose(text: str) -> str:
    """去掉 engine/debug 用语，替换为自然叙事。"""
    if not text or not str(text).strip():
        return ""
    out = str(text).strip()
    out = _replace_snake_tokens(out)
    for pat, repl in _BANNED_PHRASES:
        out = pat.sub(repl, out)
    out = _INTERNAL_ID_RE.sub("", out)
    # 残留 snake_case（非中文语境）
    def _snake_word(m: re.Match[str]) -> str:
        w = m.group(0)
        if w.lower() in ACTIVITY_ZH:
            return format_activity(w)
        if w.lower() in EMOTION_ZH:
            return format_emotion(w)
        return ""

    out = _SNAKE_IN_TEXT_RE.sub(_snake_word, out)
    out = re.sub(r"[「『]」", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"^[，、；\s]+", "", out)
    return out


def humanize_action_label(
    label: str,
    *,
    state: GameState | None = None,
    source_fact: str = "",
    category: str = "",
    target: str = "",
) -> str:
    """将 action / followup 的系统 label 转为扮演式选项。"""
    raw = (label or "").strip()
    if not raw:
        return "继续观察四周"

    # 已是良好中文且带技能括号
    if raw.startswith("[") and re.search(r"[\u4e00-\u9fff]{4,}", raw):
        return polish_prose(raw)

    low = raw.lower()
    if any(x in low for x in ("investigate", "followup", "unresolved", "hook", "continue investigate")):
        raw = re.sub(r"investigate|followup|unresolved|hook", "", raw, flags=re.I).strip()

    # 「针对『…』继续调查」
    m = re.match(r"针对[「『](.+?)[」』]继续调查", raw)
    if m:
        snippet = polish_prose(m.group(1))
        if "托马斯" in snippet or (target == "托马斯"):
            return "[感知] 继续观察托马斯的异常反应"
        if "米拉" in snippet:
            return "[观察] 留意酒馆门帘后的动静"
        if "艾琳娜" in snippet:
            return "[安抚] 试着让艾琳娜多说几句"
        if len(snippet) > 18:
            snippet = snippet[:18] + "…"
        return f"[感知] 顺着「{snippet}」继续追查"

    m2 = re.match(r"继续调查[：:]\s*(.+)", raw)
    if m2:
        snippet = polish_prose(m2.group(1))[:20]
        return f"[感知] 追查{snippet}"

    if "继续调查" in raw:
        if target == "托马斯" or "托马斯" in raw:
            return "[感知] 继续观察托马斯的举动"
        return "[感知] 检查现场是否有新的痕迹"

    raw = polish_prose(raw)

    # 技能前缀
    skill = CATEGORY_SKILL.get(category, "")
    if skill and not raw.startswith("["):
        # 根据动词选更贴切的标签
        if any(k in raw for k in ("安慰", "询问", "交谈", "说服", "打听")):
            skill = "交涉"
        elif any(k in raw for k in ("观察", "打量", "检查", "搜查", "翻查")):
            skill = "感知"
        elif any(k in raw for k in ("偷听", "隐蔽", "潜行")):
            skill = "隐匿"
        raw = f"[{skill}] {raw}"

    return raw or "继续观察四周"


def format_world_event_text(
    text: str,
    state: GameState | None = None,
    *,
    player_location: str | None = None,
) -> str:
    """世界事件：优先氛围化；仅当玩家能亲眼见到 NPC 时才点名。"""
    line = (text or "").strip()
    if not line:
        return ""

    loc = player_location or (state.location if state else "")
    present: set[str] = set()
    if state:
        present = {n.name for n in state.npc_at_location() if n.present}
        scene = state.flags.get("scene_npcs")
        if isinstance(scene, list):
            present |= {str(x) for x in scene}

    for pat, repl in _WORLD_EVENT_TEMPLATES:
        if pat.search(line):
            line = pat.sub(repl, line)
            break

    line = re.sub(r"^【[^】]+】", "", line).strip()
    line = polish_prose(line)

    # 若玩家不在场却点名 NPC，改为间接描写
    if state and "托马斯" in line and "托马斯" not in present and loc in ("酒馆", "仓库", "森林小路"):
        line = line.replace("托马斯", "守卫")
    if state and "米拉" in line and "米拉" not in present and loc != "酒馆":
        line = line.replace("米拉", "酒馆方向的人影")

    # 包装为氛围句
    if line and not line.startswith("【"):
        if not line.endswith(("。", "！", "？", "…", ".")):
            line += "。"
    return line


def format_choice_transition(encounter_type: str) -> str:
    return _TRANSITION_ZH.get(encounter_type, "你打算——")


def _player_visible_npcs(state: GameState | None) -> set[str]:
    if not state:
        return set()
    names = {n.name for n in state.npc_at_location() if n.present}
    scene = state.flags.get("scene_npcs")
    if isinstance(scene, list):
        names |= {str(x) for x in scene}
    return names


def _rewrite_paragraph_content(text: str, css_class: str, state: GameState | None) -> tuple[str, str]:
    """返回 (polished_text, optional_new_class)。"""
    t = polish_prose(html.unescape(re.sub(r"<[^>]+>", "", text)))
    if not t:
        return "", css_class

    if css_class == "consequence":
        # 系统感后果 → 氛围/内心独白
        if any(
            k in t
            for k in (
                "暂时没有更多",
                "没有明显变化",
                "未取得新信息",
                "不愿多说",
                "关系",
                "态度变为",
            )
        ):
            if "暂时没有更多" in t or "没有明显变化" in t:
                return "你意识到这里暂时没有更多线索。", "scene"
            return f"【{t}】", "scene"
        return f"【{t}】", "scene"

    if css_class == "world":
        t = format_world_event_text(t, state)
        return (f"【{t}】" if t and not t.startswith("【") else t), "world"

    return t, css_class


def format_narrative_html(
    narrative_html: str,
    state: GameState | None = None,
    *,
    intent: dict[str, Any] | None = None,
    changes: dict[str, Any] | None = None,
) -> str:
    """对整段叙事 HTML 做呈现层清洗（玩家可见）。"""
    if not narrative_html or not str(narrative_html).strip():
        return narrative_html

    _ = intent, changes
    parts: list[str] = []
    para_re = re.compile(
        r"<p\s+class=[\"']([^\"']+)[\"'][^>]*>(.*?)</p>",
        re.DOTALL | re.IGNORECASE,
    )

    last = 0
    for m in para_re.finditer(narrative_html):
        before = narrative_html[last : m.start()]
        if before.strip():
            parts.append(before)
        css = m.group(1).strip()
        inner = m.group(2)
        text, new_cls = _rewrite_paragraph_content(inner, css, state)
        if not text:
            last = m.end()
            continue
        safe = html.escape(text) if "<" not in text else text
        if new_cls == "consequence" and css != "consequence":
            parts.append(f'<p class="{new_cls}"><em>{safe}</em></p>' if "【" not in safe else f'<p class="{new_cls}">{safe}</p>')
        elif css == "dialogue":
            parts.append(f'<p class="dialogue">{safe}</p>')
        elif css == "player-action":
            parts.append(f'<p class="player-action">{inner if "<strong>" in inner else safe}</p>')
        else:
            parts.append(f'<p class="{new_cls or css}">{safe}</p>')
        last = m.end()

    tail = narrative_html[last:]
    if tail.strip():
        parts.append(tail)

    out = "".join(parts) if parts else narrative_html
    # 兜底：全文 polish
    def _polish_plain(m: re.Match[str]) -> str:
        return polish_prose(m.group(0))

    out = _SNAKE_IN_TEXT_RE.sub(
        lambda m: format_activity(m.group(0)) if m.group(0) in ACTIVITY_ZH else m.group(0),
        out,
    )
    return out


def format_inline_choices(
    choices: list[dict[str, Any]],
    state: GameState | None = None,
) -> list[dict[str, Any]]:
    """润色选项列表（保留 intent_payload，隐藏 debug 字段）。"""
    out: list[dict[str, Any]] = []
    for ch in choices:
        if not isinstance(ch, dict):
            continue
        item = dict(ch)
        cat = str(item.get("category") or "")
        intent = item.get("intent_payload") if isinstance(item.get("intent_payload"), dict) else {}
        target = str(intent.get("target") or "")
        label = humanize_action_label(
            str(item.get("text") or item.get("label") or ""),
            state=state,
            source_fact=str(item.get("source_fact") or ""),
            category=cat,
            target=target,
        )
        item["text"] = label
        item.pop("source_fact", None)
        item["source_hint"] = ""
        out.append(item)
    return out
