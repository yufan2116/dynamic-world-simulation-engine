"""NPC 记忆与态度更新。"""
from __future__ import annotations

from engine.world_state import GameState, NPCState


ATTITUDE_LABELS = [
    (-100, -60, "敌对"),
    (-60, -20, "冷淡"),
    (-20, 20, "中立"),
    (20, 60, "友好"),
    (60, 100, "亲密"),
]


def value_to_attitude(value: int) -> str:
    for low, high, label in ATTITUDE_LABELS:
        if low <= value < high:
            return label
    return "中立"


def add_memory(npc: NPCState, memory: str, max_memories: int = 20) -> None:
    if memory not in npc.memories:
        npc.memories.append(memory)
    if len(npc.memories) > max_memories:
        npc.memories = npc.memories[-max_memories:]


def adjust_attitude(npc: NPCState, delta: int) -> None:
    npc.attitude_value = max(-100, min(100, npc.attitude_value + delta))
    npc.attitude = value_to_attitude(npc.attitude_value)


def update_npc_from_action(
    state: GameState,
    npc_name: str,
    *,
    memory: str | None = None,
    attitude_delta: int = 0,
    new_location: str | None = None,
    present: bool | None = None,
) -> dict[str, str | int]:
    """根据玩家行动更新 NPC，返回变化摘要。"""
    if npc_name not in state.npcs:
        return {}
    npc = state.npcs[npc_name]
    changes: dict[str, str | int] = {"npc": npc_name}
    if memory:
        add_memory(npc, memory)
        changes["memory_added"] = memory
    if attitude_delta:
        old = npc.attitude
        adjust_attitude(npc, attitude_delta)
        changes["attitude_from"] = old
        changes["attitude_to"] = npc.attitude
    if new_location:
        npc.location = new_location
        changes["location"] = new_location
    if present is not None:
        npc.present = present
        changes["present"] = str(present)
    return changes


def sync_memories_to_db(state: GameState) -> dict[str, list[str]]:
    return {name: npc.memories for name, npc in state.npcs.items()}


def apply_stored_memories(state: GameState, stored: dict[str, list[str]]) -> None:
    for name, memories in stored.items():
        if name in state.npcs:
            state.npcs[name].memories = memories
