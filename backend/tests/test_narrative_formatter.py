"""叙事呈现层 — 人性化与内部 token 清洗。"""
from __future__ import annotations

from engine.narrative_formatter import (
    format_npc_activity_line,
    format_world_event_text,
    humanize_action_label,
    polish_prose,
)
from engine.seed_loader import load_seed_world


def test_format_npc_activity_line():
    line = format_npc_activity_line("托马斯", "guarding_gate", "tense")
    assert "guarding_gate" not in line
    assert "托马斯" in line
    assert "村口" in line or "警戒" in line


def test_humanize_followup_label():
    state = load_seed_world("ravenford_demo")
    label = humanize_action_label(
        "针对「托马斯正在guarding_gate」继续调查",
        state=state,
        category="investigate",
        target="托马斯",
    )
    assert "guarding_gate" not in label
    assert "继续" in label
    assert label.startswith("[")


def test_format_world_event_ambient():
    state = load_seed_world("ravenford_demo")
    state.location = "酒馆"
    text = format_world_event_text(
        "【NPC】托马斯在村口召集同伴，强调今夜村口外侧加派哨岗。",
        state,
    )
    assert "【NPC】" not in text
    assert "托马斯" not in text or "守卫" in text


def test_polish_banned_phrase():
    assert "暂时没有更多可见异常" not in polish_prose("你确认当前场景暂时没有更多可见异常。")
    assert "线索" in polish_prose("你确认当前场景暂时没有更多可见异常。")
