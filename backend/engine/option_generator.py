"""行动建议 — 委托至动态行动生成器。"""
from __future__ import annotations

from engine.action_generator import generate_actions, generate_options
from engine.world_state import GameState

__all__ = ["generate_actions", "generate_options"]
