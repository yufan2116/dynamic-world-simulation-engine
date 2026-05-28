"""D20 检定规则引擎。"""
from __future__ import annotations

import random
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from engine.world_state import Player, ability_modifier


class RollOutcome(str, Enum):
    CRITICAL_SUCCESS = "大成功"
    SUCCESS = "成功"
    FAILURE = "失败"
    CRITICAL_FAILURE = "大失败"


class DiceRollInfo(BaseModel):
    die_roll: int = Field(description="d20 原始点数")
    modifier: int = Field(description="属性调整值")
    total: int = Field(description="检定总值")
    dc: int = Field(description="难度等级")
    ability: str = Field(description="检定属性")
    outcome: RollOutcome
    description: str = ""


def roll_d20() -> int:
    return random.randint(1, 20)


def evaluate_roll(total: int, dc: int, natural: int) -> RollOutcome:
    if natural == 20:
        return RollOutcome.CRITICAL_SUCCESS
    if natural == 1:
        return RollOutcome.CRITICAL_FAILURE
    if total >= dc:
        return RollOutcome.SUCCESS
    return RollOutcome.FAILURE


def perform_check(
    player: Player,
    ability: str,
    dc: int,
    *,
    advantage: bool = False,
    description: str = "",
) -> DiceRollInfo:
    """执行 1d20 + 属性调整值 vs DC 检定。"""
    mod = player.get_modifier(ability)
    if advantage:
        r1, r2 = roll_d20(), roll_d20()
        natural = max(r1, r2)
    else:
        natural = roll_d20()
    total = natural + mod
    outcome = evaluate_roll(total, dc, natural)
    return DiceRollInfo(
        die_roll=natural,
        modifier=mod,
        total=total,
        dc=dc,
        ability=ability.upper(),
        outcome=outcome,
        description=description or f"{ability.upper()} 检定",
    )


def outcome_succeeds(outcome: RollOutcome) -> bool:
    return outcome in (RollOutcome.CRITICAL_SUCCESS, RollOutcome.SUCCESS)


def dice_roll_to_dict(info: DiceRollInfo) -> dict[str, Any]:
    return {
        "die_roll": info.die_roll,
        "modifier": info.modifier,
        "total": info.total,
        "dc": info.dc,
        "ability": info.ability,
        "outcome": info.outcome.value,
        "description": info.description,
    }
