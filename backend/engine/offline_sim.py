"""离线世界演化 — 读档时按离线时长压缩推进 Tick。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.world_state import GameState
from engine.world_tick import advance_world_time, get_world_minutes, run_world_ticks


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp_simulation_time(state: GameState) -> None:
    state.flags["last_simulated_at"] = _now_iso()


def catch_up_offline(state: GameState, *, max_ticks: int = 48) -> dict[str, Any]:
    """
    根据 last_simulated_at 推进世界。
    每 30 分钟离线 ≈ 1 Tick，最多 max_ticks（默认 24 小时）。
    """
    last = state.flags.get("last_simulated_at")
    if not last:
        stamp_simulation_time(state)
        return {"ticks_run": 0, "events": []}

    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        stamp_simulation_time(state)
        return {"ticks_run": 0, "events": []}

    now = datetime.now(timezone.utc)
    elapsed_min = int((now - last_dt).total_seconds() / 60)
    if elapsed_min < 30:
        stamp_simulation_time(state)
        return {"ticks_run": 0, "events": []}

    ticks_to_run = min(max_ticks, elapsed_min // 30)
    all_events: list[dict[str, Any]] = []
    summary_lines: list[str] = []

    for i in range(ticks_to_run):
        advance_world_time(state, 30)
        tick_events = run_world_ticks(state, ticks=1)
        for ev in tick_events:
            all_events.append(ev)
            if len(summary_lines) < 5:
                summary_lines.append(ev.get("text", ""))

    stamp_simulation_time(state)
    return {
        "ticks_run": ticks_to_run,
        "elapsed_minutes": elapsed_min,
        "events": all_events,
        "summary": summary_lines,
    }
